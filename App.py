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
        blacklist, clean_tags, cuisine_map, all_triggers = [], [], {}, set()
        
        def try_read(base_name):
            # Tries various names for compatibility
            possible_names = [base_name, f"{base_name}_sheet", f"the_{base_name}_sheet"]
            for name in possible_names:
                for ext in [".csv", ".xlsx"]:
                    path = f"{name}{ext}"
                    if os.path.exists(path):
                        return pd.read_csv(path) if ext == ".csv" else pd.read_excel(path)
            return None

        # Load resources
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
                    all_triggers.add(trigger)
            
        return blacklist, clean_tags, cuisine_map, all_triggers

    # --- 3. UI SIDEBAR ---
    st.sidebar.title(":hammer_and_wrench: Hobz AI Tagger")
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.title(":label: Hobz AI Menu Tagger")
    blacklist, clean_tags, cuisine_map, all_triggers = load_tagging_resources()
    
    col1, col2 = st.columns([1, 2])
    with col1:
        res_name = st.text_input("Restaurant Name", help="Matches here are given 100% priority.")
        upload_file = st.file_uploader("Upload Menu (Excel/CSV)", type=['xlsx', 'csv'])
        
    if upload_file:
        df = pd.read_csv(upload_file) if upload_file.name.endswith('csv') else pd.read_excel(upload_file)
        
        if len(df.columns) >= 2:
            # Data Pre-processing
            df = df.dropna(subset=[df.columns[0], df.columns[1]]).drop_duplicates()
            final_count = len(df)
            
            cat_series = df.iloc[:, 0].astype(str).str.lower().str.strip()
            rescued_categories = [cat for cat, count in cat_series.value_counts().items() 
                                 if cat in blacklist and (count / final_count) >= 0.40]
            active_blacklist = [b for b in blacklist if b not in rescued_categories]
            
            df_clean = df[~cat_series.isin(active_blacklist)].copy()
            df_clean['merged'] = df_clean.iloc[:, 0].astype(str) + " " + df_clean.iloc[:, 1].astype(str)
            merged_items = df_clean['merged'].tolist()
            total_count = len(merged_items)

            if total_count > 0:
                # 1. SCAN MENU FOR EVERYTHING (Tags + Triggers + Targets)
                tag_perc_lookup = {}
                search_pool = set([t.lower() for t in clean_tags]) | all_triggers | set([k.lower() for k in cuisine_map.keys()])
                
                for term in search_pool:
                    match_count = sum(1 for context in merged_items if term in context.lower())
                    if match_count > 0:
                        tag_perc_lookup[term] = (match_count / total_count) * 100

                # 2. DEFINE MASTER SETS (The Union Logic)
                final_cuisine_tags = set()
                final_normal_tags = set()
                forced_percs = {} # Stores scores for the UI display

                # --- PHASE A: RESTAURANT NAME (GLOBAL PRIORITY) ---
                if res_name:
                    name_low = res_name.lower()
                    # Check Master Tags
                    for t in clean_tags:
                        if t.lower() in name_low:
                            final_cuisine_tags.add(t)
                            final_normal_tags.add(t)
                            forced_percs[t] = 100.0
                    # Check Mapping Targets and Triggers
                    for target, triggers in cuisine_map.items():
                        if target.lower() in name_low or any(trig in name_low for trig in triggers):
                            final_cuisine_tags.add(target)
                            final_normal_tags.add(target)
                            forced_percs[target] = 100.0

                # --- PHASE B: AGGREGATE MENU LOGIC ---
                for target, triggers in cuisine_map.items():
                    combined_p = sum(tag_perc_lookup.get(trig, 0) for trig in triggers)
                    if combined_p >= 30:
                        final_cuisine_tags.add(target)
                        final_normal_tags.add(target)
                        if target not in forced_percs:
                            forced_percs[target] = combined_p

                # --- PHASE C: INDIVIDUAL ELIGIBILITY (30%) ---
                for tag in clean_tags:
                    p = tag_perc_lookup.get(tag.lower(), 0)
                    if p >= 30:
                        final_normal_tags.add(tag)
                        # Auto-promote to cuisine if it's a known cuisine term
                        final_cuisine_tags.add(tag)

                # --- PHASE D: FALLBACK DIVERSITY (Top 3) ---
                # Only adds tags NOT in blacklist to normal set
                fallback_pool = sorted(tag_perc_lookup.items(), key=lambda x: x[1], reverse=True)
                added_count = 0
                for tag_low, p in fallback_pool:
                    if tag_low not in active_blacklist and added_count < 3:
                        # Find original casing from clean_tags or use capitalized
                        original_name = next((t for t in clean_tags if t.lower() == tag_low), tag_low.capitalize())
                        final_normal_tags.add(original_name)
                        added_count += 1

                # --- UI DISPLAY ---
                with col2:
                    st.subheader(":hospital: Menu Health Check")
                    st.write(f"Scanned {final_count} items. Total valid for audit: {total_count}")
                    st.divider()
                    st.warning("ℹ️ Mandatory UAE Tags: Cplus, New Restaurants")

                    st.subheader(":clipboard: Audit Results")
                    c1, c2, c3 = st.columns(3)
                    
                    with c1:
                        st.write("**Cuisine Tags**")
                        # This combines Name Priority + Aggregation + Menu Threshold
                        if final_cuisine_tags:
                            for c in sorted(list(final_cuisine_tags)): st.success(c)
                        else: st.write("N/A")
                        
                    with c2:
                        st.write("**Normal Tags**")
                        # Build button list based on prioritized percentages
                        display_list = []
                        for tag_name in final_normal_tags:
                            p = forced_percs.get(tag_name, tag_perc_lookup.get(tag_name.lower(), 0))
                            display_list.append({"name": tag_name, "perc": p})
                        
                        if display_list:
                            display_df = pd.DataFrame(display_list).sort_values(by="perc", ascending=False)
                            for _, row in display_df.iterrows():
                                st.button(f"{row['name']} ({row['perc']:.1f}%)", key=f"btn_{row['name']}")
                        else: st.write("N/A")

                    with c3:
                        # Subpage Logic
                        subpages = []
                        all_active_refs = [str(x).lower() for x in (list(final_normal_tags) + list(final_cuisine_tags))]
                        for t in clean_tags:
                            if "Subpage" in str(t) and any(ref in str(t).lower() for ref in all_active_refs if len(ref) > 3):
                                subpages.append(str(t))
                        st.write("**Subpages**")
                        if subpages:
                            for s in sorted(list(set(subpages))): st.warning(s)
                        else: st.error("Manual Required")
