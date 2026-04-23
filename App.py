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
        blacklist, clean_tags, cuisine_map = [], [], {}
        def try_read(base_name):
            if os.path.exists(f"{base_name}.csv"):
                return pd.read_csv(f"{base_name}.csv")
            elif os.path.exists(f"{base_name}.xlsx"):
                return pd.read_excel(f"{base_name}.xlsx")
            return None

        bl_df = try_read("blacklist")
        if bl_df is not None:
            blacklist = [str(x).strip().lower() for x in bl_df.iloc[:, 0].dropna()]
            
        tags_df = try_read("tags")
        if tags_df is not None:
            all_tags = tags_df.iloc[:, 0].dropna().unique().tolist()
            campaign_regex = r"%|\boff\b|\bsale\b|\bsar\b|\bjod\b|\bdeal\b|\boffer\b|\bdiscount\b|\bpromo\b"
            clean_tags = [str(t).strip() for t in all_tags if not re.search(campaign_regex, str(t), re.IGNORECASE)]
        
        mapping_df = try_read("cuisine_mapping")
        if mapping_df is not None:
            for _, row in mapping_df.iterrows():
                if pd.notna(row.iloc[0]) and pd.notna(row.iloc[1]):
                    trigger = str(row.iloc[0]).strip().lower()
                    target = str(row.iloc[1]).strip()
                    if target not in cuisine_map:
                        cuisine_map[target] = []
                    cuisine_map[target].append(trigger)
            
        return blacklist, clean_tags, cuisine_map

    # --- 3. SIDEBAR ---
    st.sidebar.title(":hammer_and_wrench: Hobz AI Tagger")
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    # --- MAIN MODULE ---
    st.title(":label: Hobz AI Menu Tagger")
    blacklist, clean_tags, cuisine_map = load_tagging_resources()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        res_name = st.text_input("Restaurant Name")
        upload_file = st.file_uploader("Upload Menu (Excel/CSV)", type=['xlsx', 'csv'])
        
    if upload_file:
        df = pd.read_csv(upload_file) if upload_file.name.endswith('csv') else pd.read_excel(upload_file)
        
        if len(df.columns) >= 2:
            # Cleanup & Duplicate Removal
            initial_count = len(df)
            df = df.dropna(subset=[df.columns[0], df.columns[1]]).drop_duplicates()
            final_count = len(df)
            duplicates_removed = initial_count - final_count

            # 40% Smart Override
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
                tag_perc_lookup = {}
                item_stats = []
                
                # PRE-CALCULATE ALL TAG PERCENTAGES
                for tag in clean_tags:
                    if "Subpage" in str(tag): continue
                    t_search = str(tag).lower().strip()
                    match_count = sum(1 for context in merged_items if t_search in context.lower())
                    if match_count > 0:
                        p = (match_count / total_count) * 100
                        tag_perc_lookup[tag.lower()] = p
                        item_stats.append({"tag": tag, "perc": p})
                
                stats_df = pd.DataFrame(item_stats)

                # --- NEW PRIORITY-BASED CUISINE LOGIC ---
                cuisine_tags = []
                forced_normal_tags = []

                # 1. PRIORITY: Check Restaurant Name for Tag Sheet Matches
                # If "Japanese" is in the name and "Japanese" is in clean_tags, it's a win.
                for t in clean_tags:
                    if str(t).lower() in res_name.lower():
                        cuisine_tags.append(str(t))

                # 2. PRIORITY: Check Cuisine Map for Aggregates or Triggers
                for target, triggers in cuisine_map.items():
                    # If target name is in Res name, or any trigger is in Res name
                    if target.lower() in res_name.lower() or any(trig in res_name.lower() for trig in triggers):
                        cuisine_tags.append(target)
                    
                    # If combined triggers from menu exceed 30%
                    combined_p = sum(tag_perc_lookup.get(trig, 0) for trig in triggers)
                    if combined_p >= 30:
                        cuisine_tags.append(target)
                        forced_normal_tags.append({"tag": target, "perc": combined_p})

                # Deduplicate Cuisine
                cuisine_tags = list(set(cuisine_tags))

                # --- NORMAL TAGS LOGIC ---
                normal_tags_list = []
                if not stats_df.empty:
                    # Individual 30% hits
                    normal_tags_list = stats_df[stats_df['perc'] >= 30]['tag'].tolist()
                    
                    # Add Aggregate Targets (like Asian/Japanese)
                    for f in forced_normal_tags:
                        normal_tags_list.append(f['tag'])
                    
                    # Fallback Top 3 (excluding active blacklist)
                    fallback_pool = stats_df[~stats_df['tag'].str.lower().isin(active_blacklist)]
                    top_items = fallback_pool.sort_values(by='perc', ascending=False).head(3)['tag'].tolist()
                    normal_tags_list.extend(top_items)

                normal_tags_list = list(set(normal_tags_list))

                with col2:
                    st.subheader(":hospital: Menu Health Check")
                    h_col1, h_col2, h_col3 = st.columns(3)
                    h_col1.metric("Items Scanned", final_count)
                    h_col2.metric("Duplicates Cleared", duplicates_removed)
                    if final_count < 10: h_col3.warning(":warning: Small Menu")
                    else: h_col3.success(":white_check_mark: Data Healthy")

                    st.divider()
                    st.warning("ℹ️ Don't forget To add the mandatory tags for UAE: Cplus, New Restaurants")

                    st.subheader(":clipboard: Audit Results")
                    c1, c2, c3 = st.columns(3)
                    
                    with c1:
                        st.write("**Cuisine Tags**")
                        if cuisine_tags:
                            for c in cuisine_tags[:4]: st.success(c)
                        else: st.write("N/A")
                        
                    with c2:
                        st.write("**Normal Tags**")
                        # Build a display dataframe including forced tags
                        display_df = stats_df[stats_df['tag'].isin(normal_tags_list)].copy()
                        for f in forced_normal_tags:
                            if f['tag'] not in display_df['tag'].values:
                                display_df = pd.concat([display_df, pd.DataFrame([f])])
                        
                        if not display_df.empty:
                            for _, row in display_df.sort_values(by='perc', ascending=False).iterrows():
                                st.button(f"{row['tag']} ({row['perc']:.1f}%)", key=f"btn_{row['tag']}")
                        else: st.write("N/A")
                        
                    with c3:
                        # Subpage Logic
                        subpages = []
                        refs = [str(x).lower() for x in (normal_tags_list + cuisine_tags)]
                        for t in clean_tags:
                            if "Subpage" in str(t) and any(r in str(t).lower() for r in refs if len(r) > 3):
                                subpages.append(str(t))
                        st.write("**Subpages**")
                        if subpages:
                            for s in list(set(subpages))[:3]: st.warning(s)
                        else: st.error("Manual Required")
                        
                    with st.expander(":mag: Debug View: Item Breakdown"):
                        st.write(stats_df.sort_values(by='perc', ascending=False))
