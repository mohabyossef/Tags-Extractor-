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
        blacklist, clean_tags, trigger_rules = [], [], {}
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
        
        # NEW: Load Trigger Logic Mapping (Col A: Constituent, Col B: Group/Triggered Tag)
        logic_df = try_read("trigger_logic")
        if logic_df is not None:
            for _, row in logic_df.iterrows():
                constituent = str(row.iloc[0]).strip().lower()
                group_tag = str(row.iloc[1]).strip()
                if group_tag not in trigger_rules:
                    trigger_rules[group_tag] = []
                trigger_rules[group_tag].append(constituent)
            
        return blacklist, clean_tags, trigger_rules

    # --- 3. SIDEBAR ---
    st.sidebar.title(":hammer_and_wrench: Hobz AI Tagger")
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    # --- MAIN MODULE ---
    st.title(":label: Hobz AI Menu Tagger")
    blacklist, clean_tags, trigger_rules = load_tagging_resources()
    
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
                # 1. Calculate Individual Tag Stats
                item_stats = []
                for tag in clean_tags:
                    if "Subpage" in str(tag): continue
                    t_search = str(tag).lower().strip()
                    match_count = sum(1 for context in merged_items if t_search in context.lower())
                    if match_count > 0:
                        item_stats.append({"tag": tag, "perc": (match_count / total_count) * 100})
                
                stats_df = pd.DataFrame(item_stats)

                # 2. Process Group Trigger Logic (Ramen + Noodles = Asian > 30%)
                group_results = []
                for group_tag, constituents in trigger_rules.items():
                    # Priority 1: Check if Group Name or any Constituent is in Restaurant Name
                    name_priority = (group_tag.lower() in res_name.lower()) or any(c in res_name.lower() for c in constituents)
                    
                    # Priority 2: Check Menu Percentages
                    group_perc = 0
                    if not stats_df.empty:
                        # Sum up percentages of all constituent tags found in menu
                        group_perc = stats_df[stats_df['tag'].str.lower().isin(constituents)]['perc'].sum()
                    
                    if name_priority or group_perc >= 30:
                        group_results.append({"tag": group_tag, "perc": group_perc, "forced": name_priority})

                # 3. Compile Final Tag Lists
                normal_tags = []
                # Add tags that hit 30% individually
                if not stats_df.empty:
                    normal_tags.extend(stats_df[stats_df['perc'] >= 30]['tag'].tolist())
                    # Add Top 3 Fallback (if not blacklisted)
                    fallback = stats_df[~stats_df['tag'].str.lower().isin(active_blacklist)]
                    normal_tags.extend(fallback.sort_values(by='perc', ascending=False).head(3)['tag'].tolist())
                
                # Add Group-Triggered tags to Normal tags
                normal_tags.extend([g['tag'] for g in group_results])
                normal_tags = list(set(normal_tags))

                # 4. Cuisine Tags (Priority to Groups and Name matches)
                cuisine_tags = []
                for t in clean_tags:
                    if "Subpage" in str(t): continue
                    t_low = t.lower()
                    # Trigger if in name, if in triggered groups, or if individually strong
                    if (t_low in res_name.lower()) or any(t_low == g['tag'].lower() for g in group_results) or any(t_low == str(nt).lower() for nt in normal_tags):
                        cuisine_tags.append(t)
                
                cuisine_tags = list(set(cuisine_tags))[:5]

                # 5. Subpage Logic
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
                    st.divider()
                    st.warning("ℹ️ Don't forget To add the mandatory tags for UAE: Cplus, New Restaurants")

                    st.subheader(":clipboard: Audit Results")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.write("**Cuisine Tags**")
                        for c in cuisine_tags if cuisine_tags else ["N/A"]: st.success(c)
                    with c2:
                        st.write("**Normal Tags**")
                        if normal_tags:
                            # Display with calculated group/individual percentages
                            for nt in normal_tags:
                                # Find perc from stats or groups
                                p = 0
                                if not stats_df.empty and nt in stats_df['tag'].values:
                                    p = stats_df[stats_df['tag'] == nt]['perc'].values[0]
                                else:
                                    # Check if it was a group tag
                                    matched_group = next((g for g in group_results if g['tag'] == nt), None)
                                    p = matched_group['perc'] if matched_group else 0
                                st.button(f"{nt} ({p:.1f}%)", key=f"btn_{nt}")
                    with c3:
                        st.write("**Subpages**")
                        for s in list(set(subpages))[:3] if subpages else ["N/A"]: st.warning(s)
            else:
                st.error("Zero items found after filtering.")
