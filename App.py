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
        blacklist, clean_tags, trigger_groups = [], [], {}
        
        def try_read(base_name):
            if os.path.exists(f"{base_name}.csv"):
                return pd.read_csv(f"{base_name}.csv")
            elif os.path.exists(f"{base_name}.xlsx"):
                return pd.read_excel(f"{base_name}.xlsx")
            return None

        # Load Blacklist
        bl_df = try_read("blacklist")
        if bl_df is not None:
            blacklist = [str(x).strip().lower() for x in bl_df.iloc[:, 0].dropna()]
            
        # Load Tags
        tags_df = try_read("tags")
        if tags_df is not None:
            all_tags = tags_df.iloc[:, 0].dropna().unique().tolist()
            campaign_regex = r"%|\boff\b|\bsale\b|\bsar\b|\bjod\b|\bdeal\b|\boffer\b|\bdiscount\b|\bpromo\b"
            clean_tags = [str(t).strip() for t in all_tags if not re.search(campaign_regex, str(t), re.IGNORECASE)]
            
        # --- NEW: Load Trigger Groups Mapping ---
        # File structure: Column 0 = Group Name (Asian), Column 1 = Member Tag (Ramen)
        group_df = try_read("trigger_groups")
        if group_df is not None:
            for _, row in group_df.iterrows():
                group_name = str(row.iloc[0]).strip()
                member_tag = str(row.iloc[1]).strip().lower()
                if group_name not in trigger_groups:
                    trigger_groups[group_name] = []
                trigger_groups[group_name].append(member_tag)
                
        return blacklist, clean_tags, trigger_groups

    # --- 3. SIDEBAR ---
    st.sidebar.title(":hammer_and_wrench: Hobz AI Tagger")
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    # --- MAIN MODULE ---
    st.title(":label: Hobz AI Menu Tagger")
    blacklist, clean_tags, trigger_groups = load_tagging_resources()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        res_name = st.text_input("Restaurant Name")
        upload_file = st.file_uploader("Upload Menu (Excel/CSV)", type=['xlsx', 'csv'])
        
    if upload_file:
        df = pd.read_csv(upload_file) if upload_file.name.endswith('csv') else pd.read_excel(upload_file)
        
        if len(df.columns) >= 2:
            # Cleanup
            initial_count = len(df)
            df = df.dropna(subset=[df.columns[0], df.columns[1]]).drop_duplicates()
            final_count = len(df)
            duplicates_removed = initial_count - final_count

            # Smart Override Logic
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
                item_stats = {} # Use dict for faster lookup
                for tag in clean_tags:
                    if "Subpage" in str(tag): continue
                    t_search = str(tag).lower().strip()
                    match_count = sum(1 for context in merged_items if t_search in context.lower())
                    if match_count > 0:
                        item_stats[tag] = (match_count / total_count) * 100
                
                # Convert back to DataFrame for display
                stats_df = pd.DataFrame([{"tag": k, "perc": v} for k, v in item_stats.items()])

                # Normal Tags (Purple Buttons)
                normal_tags = []
                if not stats_df.empty:
                    high_perc = stats_df[stats_df['perc'] >= 30]['tag'].tolist()
                    normal_tags.extend(high_perc)
                    fallback_pool = stats_df[~stats_df['tag'].str.lower().isin(active_blacklist)]
                    top_items = fallback_pool.sort_values(by='perc', ascending=False).head(3)['tag'].tolist()
                    normal_tags.extend(top_items)
                
                normal_tags = list(set(normal_tags))

                # --- CUISINE & COMBINED GROUP LOGIC ---
                cuisine_tags = []
                
                # 1. Direct tag identification (Name/Threshold/Keyword)
                for t in clean_tags:
                    if "Subpage" in str(t): continue
                    t_lower = str(t).lower()
                    if t_lower in res_name.lower() or any(t_lower == str(nt).lower() for nt in normal_tags) or any(t_lower in context.lower() for context in merged_items):
                        cuisine_tags.append(str(t))

                # 2. COMBINED GROUP TRIGGER (The 30% Logic)
                # This checks if the SUM of tags in a group hits 30%
                for group_name, members in trigger_groups.items():
                    combined_perc = sum(item_stats.get(m_tag, 0) for m_tag in members if any(m_tag == k.lower() for k in item_stats.keys()))
                    
                    # Also check if the group name appears in the restaurant name
                    if combined_perc >= 30 or group_name.lower() in res_name.lower():
                        cuisine_tags.append(group_name)
                
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
                    st.warning(":information_source: Don't forget To add the mandatory tags for UAE: Cplus, New Restaurants")

                    st.subheader(":clipboard: Audit Results")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.write("**Cuisine & Groups**")
                        if cuisine_tags:
                            for c in cuisine_tags: st.success(c)
                        else: st.write("N/A")
                    with c2:
                        st.write("**Normal Tags**")
                        if normal_tags:
                            display_df = stats_df[stats_df['tag'].isin(normal_tags)].sort_values(by='perc', ascending=False)
                            for _, row in display_df.iterrows():
                                st.button(f"{row['tag']} ({row['perc']:.1f}%)", key=f"btn_{row['tag']}")
                    with c3:
                        st.write("**Subpages**")
                        if subpages:
                            for s in list(set(subpages))[:3]: st.warning(s)
                        else: st.error("Manual Required")
                        
                    with st.expander(":mag: Debug View"):
                        st.write(stats_df.sort_values(by='perc', ascending=False))
