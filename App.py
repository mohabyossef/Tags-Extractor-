import streamlit as st
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import folium
from streamlit_folium import st_folium
import re
import os

# --- 1. SECURE PASSWORD PROTECTION ---
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]: 
            st.session_state["password_correct"] = True
            del st.session_state["password"] 
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.title(":lock: Hobz Hub Access")
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.title(":lock: Hobz Hub Access")
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        st.error(":confused: Password incorrect.")
        return False
    else:
        return True

if check_password():
    st.set_page_config(page_title="Hobz AI Tagger", layout="wide")

    # --- 2. DATA LOADERS ---
    @st.cache_data
    def load_tagging_resources():
        blacklist, clean_tags, cuisine_map, aggregate_map = [], [], {}, {}
        
        def try_read(base_name):
            if os.path.exists(f"{base_name}.csv"):
                return pd.read_csv(f"{base_name}.csv")
            elif os.path.exists(f"{base_name}.xlsx"):
                return pd.read_excel(f"{base_name}.xlsx")
            return None

        # Blacklist
        bl_df = try_read("blacklist")
        if bl_df is not None:
            blacklist = [str(x).strip().lower() for x in bl_df.iloc[:, 0].dropna()]
            
        # Tags
        tags_df = try_read("tags")
        if tags_df is not None:
            all_tags = tags_df.iloc[:, 0].dropna().unique().tolist()
            campaign_regex = r"%|\boff\b|\bsale\b|\bsar\b|\bjod\b|\bdeal\b|\boffer\b|\bdiscount\b|\bpromo\b"
            clean_tags = [str(t).strip() for t in all_tags if not re.search(campaign_regex, str(t), re.IGNORECASE)]
        
        # --- NEW: AGGREGATE MAPPING LOADER ---
        agg_df = try_read("aggregate_mapping")
        if agg_df is not None:
            for _, row in agg_df.iterrows():
                if pd.notna(row.iloc[0]) and pd.notna(row.iloc[1]):
                    trigger = str(row.iloc[0]).strip().lower()
                    parent = str(row.iloc[1]).strip()
                    if parent not in aggregate_map:
                        aggregate_map[parent] = []
                    aggregate_map[parent].append(trigger)

        # --- CUISINE MAPPING LOADER ---
        mapping_df = try_read("cuisine_mapping")
        if mapping_df is not None:
            for _, row in mapping_df.iterrows():
                if pd.notna(row.iloc[0]) and pd.notna(row.iloc[1]):
                    trigger = str(row.iloc[0]).strip().lower()
                    target = str(row.iloc[1]).strip()
                    if target not in cuisine_map:
                        cuisine_map[target] = []
                    cuisine_map[target].append(trigger)
            
        return blacklist, clean_tags, cuisine_map, aggregate_map

    # --- 3. SIDEBAR ---
    st.sidebar.title(":hammer_and_wrench: Hobz AI Tagger")
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    # --- MAIN MODULE: MENU TAGGER ---
    st.title(":label: Hobz AI Menu Tagger")
    blacklist, clean_tags, cuisine_map, aggregate_map = load_tagging_resources()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        res_name = st.text_input("Restaurant Name")
        upload_file = st.file_uploader("Upload Menu (Excel/CSV)", type=['xlsx', 'csv'])
        
    if upload_file:
        df = pd.read_csv(upload_file) if upload_file.name.endswith('csv') else pd.read_excel(upload_file)
        
        if len(df.columns) >= 2:
            initial_count = len(df)
            df = df.dropna(subset=[df.columns[0], df.columns[1]]).drop_duplicates()
            final_count = len(df)
            duplicates_removed = initial_count - final_count

            # 40% Smart Override Logic
            original_total = len(df)
            cat_series = df.iloc[:, 0].astype(str).str.lower().str.strip()
            cat_counts = cat_series.value_counts()
            rescued_categories = [cat for cat, count in cat_counts.items() if cat in blacklist and (count / original_total) >= 0.40]
            active_blacklist = [b for b in blacklist if b not in rescued_categories]
            
            df_clean = df[~cat_series.isin(active_blacklist)].copy()
            df_clean['merged'] = df_clean.iloc[:, 0].astype(str) + " " + df_clean.iloc[:, 1].astype(str)
            merged_items = df_clean['merged'].tolist()
            total_count = len(merged_items)

            if total_count > 0:
                item_stats = []
                tag_perc_lookup = {}
                
                for tag in clean_tags:
                    if "Subpage" in str(tag): continue
                    t_search = str(tag).lower().strip()
                    match_count = sum(1 for context in merged_items if t_search in context.lower())
                    if match_count > 0:
                        p = (match_count / total_count) * 100
                        item_stats.append({"tag": tag, "perc": p})
                        tag_perc_lookup[t_search] = p
                
                stats_df = pd.DataFrame(item_stats)

                # --- NEW: AGGREGATE TRIGGER LOGIC (Ramen + Noodles = Asian) ---
                aggregate_triggered_cuisines = []
                for parent_tag, triggers in aggregate_map.items():
                    combined_perc = 0
                    for trig in triggers:
                        combined_perc += tag_perc_lookup.get(trig.lower(), 0)
                    
                    if combined_perc >= 30:
                        aggregate_triggered_cuisines.append(parent_tag)

                # --- CUISINE & AGGREGATE LOGIC ---
                cuisine_tags = list(set(aggregate_triggered_cuisines)) # Start with aggregated tags
                
                # Check Restaurant Name Priority
                for target, triggers in cuisine_map.items():
                    if target.lower() in res_name.lower():
                        cuisine_tags.append(target)
                    for trig in triggers:
                        if trig in res_name.lower():
                            cuisine_tags.append(target)

                # Check individual cuisine triggers over 30%
                for target, triggers in cuisine_map.items():
                    for trig in triggers:
                        if tag_perc_lookup.get(trig.lower(), 0) >= 30:
                            cuisine_tags.append(target)

                # Display Logic for Normal Tags
                normal_tags = []
                if not stats_df.empty:
                    normal_tags = stats_df[stats_df['perc'] >= 30]['tag'].tolist()
                    # Add Top 3 Fallback
                    fallback_pool = stats_df[~stats_df['tag'].str.lower().isin(active_blacklist)]
                    top_items = fallback_pool.sort_values(by='perc', ascending=False).head(3)['tag'].tolist()
                    normal_tags.extend(top_items)
                
                normal_tags = list(set(normal_tags))

                # Final Cuisine cleanup
                cuisine_tags = list(set(cuisine_tags))[:5]

                # Subpage Logic
                subpages = []
                refs = [str(x).lower() for x in (normal_tags + cuisine_tags)]
                for t in clean_tags:
                    if "Subpage" in str(t) and any(r in str(t).lower() for r in refs if len(r) > 3):
                        subpages.append(str(t))

                with col2:
                    st.subheader(":hospital: Menu Health Check")
                    h_col1, h_col2, h_col3 = st.columns(3)
                    h_col1.metric("Items Scanned", final_count)
                    h_col2.metric("Duplicates Cleared", duplicates_removed)
                    if final_count < 10: h_col3.warning(":warning: Small Menu")
                    else: h_col3.success(":white_check_mark: Data Healthy")

                    st.divider()
                    st.warning("ℹ️ Don't forget: Cplus, New Restaurants")

                    st.subheader(":clipboard: Audit Results")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.write("**Cuisine Tags**")
                        if cuisine_tags:
                            for c in cuisine_tags: st.success(c)
                        else: st.write("N/A")
                    with c2:
                        st.write("**Normal Tags**")
                        if normal_tags:
                            for t_name in normal_tags:
                                p_val = tag_perc_lookup.get(t_name.lower(), 0)
                                st.button(f"{t_name} ({p_val:.1f}%)", key=f"btn_{t_name}")
                    with c3:
                        st.write("**Subpages**")
                        if subpages:
                            for s in list(set(subpages))[:3]: st.warning(s)
                        else: st.error("Manual Required")
                        
                    with st.expander(":mag: Debug View"):
                        st.write(stats_df.sort_values(by='perc', ascending=False))
