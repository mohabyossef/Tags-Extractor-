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

    # --- MAIN MODULE: MENU TAGGER ---
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
            df = df.dropna(subset=[df.columns[0], df.columns[1]]).drop_duplicates()
            final_count = len(df)

            # 40% Smart Override Logic
            cat_series = df.iloc[:, 0].astype(str).str.lower().str.strip()
            cat_counts = cat_series.value_counts()
            rescued_categories = [cat for cat, count in cat_counts.items() if cat in blacklist and (count / final_count) >= 0.40]
            active_blacklist = [b for b in blacklist if b not in rescued_categories]
            
            df_clean = df[~cat_series.isin(active_blacklist)].copy()
            df_clean['merged'] = df_clean.iloc[:, 0].astype(str) + " " + df_clean.iloc[:, 1].astype(str)
            merged_items = df_clean['merged'].tolist()
            total_count = len(merged_items)

            if total_count > 0:
                tag_perc_lookup = {}
                item_stats = []
                
                for tag in clean_tags:
                    if "Subpage" in str(tag): continue
                    t_search = str(tag).lower().strip()
                    match_count = sum(1 for context in merged_items if t_search in context.lower())
                    if match_count > 0:
                        p = (match_count / total_count) * 100
                        item_stats.append({"tag": tag, "perc": p})
                        tag_perc_lookup[tag.lower()] = p
                
                stats_df = pd.DataFrame(item_stats)

                # --- CUISINE & NORMAL TAGS COMBINED LOGIC ---
                cuisine_tags_set = set()
                normal_tags_set = set()
                forced_percs = {}

                # 1. PRIORITY: Restaurant Name Match
                if res_name:
                    res_name_low = res_name.lower()
                    # Check Master Tags in Name
                    for t in clean_tags:
                        if t.lower() in res_name_low:
                            cuisine_tags_set.add(t)
                            normal_tags_set.add(t)
                            forced_percs[t] = 100.0
                    
                    # Check Mapping Triggers/Targets in Name
                    for target, triggers in cuisine_map.items():
                        if target.lower() in res_name_low or any(trig in res_name_low for trig in triggers):
                            cuisine_tags_set.add(target)
                            normal_tags_set.add(target)
                            forced_percs[target] = 100.0

                # 2. AGGREGATE LOGIC: Menu Thresholds (30%)
                for target, triggers in cuisine_map.items():
                    combined_p = sum(tag_perc_lookup.get(trig, 0) for trig in triggers)
                    if combined_p >= 30:
                        cuisine_tags_set.add(target)
                        normal_tags_set.add(target)
                        if target not in forced_percs:
                            forced_percs[target] = combined_p

                # 3. INDIVIDUAL LOGIC: Master Tag Threshold (30%)
                if not stats_df.empty:
                    high_perc_tags = stats_df[stats_df['perc'] >= 30]['tag'].tolist()
                    for ht in high_perc_tags:
                        normal_tags_set.add(ht)
                        # If the tag is a known cuisine term, add to cuisine column
                        if ht.lower() in [ct.lower() for ct in clean_tags]:
                            cuisine_tags_set.add(ht)

                # 4. FALLBACK: Diversity Top 3
                fallback_pool = stats_df[~stats_df['tag'].str.lower().isin(active_blacklist)]
                top_3 = fallback_pool.sort_values(by='perc', ascending=False).head(3)['tag'].tolist()
                for t in top_3:
                    normal_tags_set.add(t)

                # Final lists for display
                # UPDATED: cuisine_tags now limits to 6
                cuisine_tags = sorted(list(cuisine_tags_set))[:6] 
                normal_tags = list(normal_tags_set)

                with col2:
                    st.subheader(":hospital: Menu Health Check")
                    h_col1, h_col2, h_col3 = st.columns(3)
                    h_col1.metric("Items Scanned", final_count)
                    h_col2.metric("Filtered for Audit", total_count)
                    if final_count < 10: h_col3.warning(":warning: Small Menu")
                    else: h_col3.success(":white_check_mark: Data Healthy")

                    st.divider()
                    st.warning("ℹ️ Don't forget To add the mandatory tags for UAE: Cplus, New Restaurants")

                    st.subheader(":clipboard: Audit Results")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.write("**Cuisine Tags**")
                        if cuisine_tags:
                            for c in cuisine_tags: st.success(c)
                        else: st.write("N/A")
                    with c2:
                        st.write("**Normal Tags**")
                        display_data = []
                        for tag_name in normal_tags:
                            p = forced_percs.get(tag_name, tag_perc_lookup.get(tag_name.lower(), 0))
                            display_data.append({"tag": tag_name, "perc": p})
                        
                        if display_data:
                            display_df = pd.DataFrame(display_data).sort_values(by='perc', ascending=False)
                            for _, row in display_df.iterrows():
                                st.button(f"{row['tag']} ({row['perc']:.1f}%)", key=f"btn_{row['tag']}")
                        else: st.write("N/A")
                    with c3:
                        subpages = []
                        all_active_refs = [str(x).lower() for x in (normal_tags + cuisine_tags)]
                        for t in clean_tags:
                            if "Subpage" in str(t) and any(r in str(t).lower() for r in all_active_refs if len(r) > 3):
                                subpages.append(str(t))
                        st.write("**Subpages**")
                        if subpages:
                            for s in sorted(list(set(subpages)))[:4]: st.warning(s)
                        else: st.error("Manual Required")
