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
        blacklist, clean_tags = [], []
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
            campaign_regex = r"%|off|sale|sar|jod|deal|offer|discount|promo"
            clean_tags = [str(t).strip() for t in all_tags if not re.search(campaign_regex, str(t), re.IGNORECASE)]
        return blacklist, clean_tags

    # --- 3. SIDEBAR (Cleaned) ---
    st.sidebar.title(":hammer_and_wrench: Hobz AI Tagger")

    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    # --- MAIN MODULE: MENU TAGGER ---
    st.title(":label: Hobz AI Menu Tagger")
    blacklist, clean_tags = load_tagging_resources()

    col1, col2 = st.columns([1, 2])
    with col1:
        res_name = st.text_input("Restaurant Name")
        upload_file = st.file_uploader("Upload Menu (Excel/CSV)", type=['xlsx', 'csv'])

    if upload_file:
        df = pd.read_csv(upload_file) if upload_file.name.endswith('csv') else pd.read_excel(upload_file)
        if len(df.columns) >= 2:
            # --- 40% SMART OVERRIDE LOGIC ---
            original_total = len(df)
            cat_series = df.iloc[:, 0].astype(str).str.lower().str.strip()
            cat_counts = cat_series.value_counts()

            # Find blacklisted categories that represent >= 40% of the entire menu
            rescued_categories = [cat for cat, count in cat_counts.items()
                                 if cat in blacklist and (count / original_total) >= 0.40]

            # Filter: Block blacklist UNLESS it was rescued by the 40% rule
            active_blacklist = [b for b in blacklist if b not in rescued_categories]

            df_clean = df[~cat_series.isin(active_blacklist)].copy()
            df_clean['merged'] = df_clean.iloc[:, 0].astype(str) + " " + df_clean.iloc[:, 1].astype(str)
            merged_items = df_clean['merged'].tolist()
            total_count = len(merged_items)

            if total_count > 0:
                item_stats = []
                for tag in clean_tags:
                    if "Subpage" in str(tag): continue

                    t_search = str(tag).lower().strip()
                    match_count = sum(1 for context in merged_items if t_search in context.lower())

                    if match_count > 0:
                        item_stats.append({"tag": tag, "perc": (match_count / total_count) * 100})

                stats_df = pd.DataFrame(item_stats)

                # --- DISPLAY LOGIC ---
                normal_tags = []
                if not stats_df.empty:
                    # 1. Tags crossing 30%
                    high_perc = stats_df[stats_df['perc'] >= 30]
                    if not high_perc.empty:
                        normal_tags = high_perc['tag'].tolist()

                    # 2. Top 3 items regardless of percentage (filtered by blacklist)
                    fallback_pool = stats_df[~stats_df['tag'].str.lower().isin(active_blacklist)]
                    top_items = fallback_pool.sort_values(by='perc', ascending=False).head(3)['tag'].tolist()
                    normal_tags.extend(top_items)

                normal_tags = list(set(normal_tags))

                # Cuisine Logic
                cuisine_tags = []
                context_str = (res_name + " " + " ".join(normal_tags)).lower()
                for t in clean_tags:
                    if "Subpage" not in str(t) and str(t).lower() in context_str:
                        cuisine_tags.append(str(t))
                cuisine_tags = list(set(cuisine_tags))[:3]

                # Subpage Logic
                subpages = []
                refs = [str(x).lower() for x in (normal_tags + cuisine_tags)]
                for t in clean_tags:
                    if "Subpage" in str(t) and any(r in str(t).lower() for r in refs if len(r) > 3):
                        subpages.append(str(t))

                with col2:
                    st.subheader(":clipboard: Audit Results")
                    if rescued_categories:
                        st.info(f":bulb: **Identity Override:** '{', '.join(rescued_categories)}' detected as main identity (>40%). Blacklist bypassed.")

                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.write("**Cuisine Tags**")
                        if cuisine_tags:
                            for c in cuisine_tags: st.success(c)
                        else: st.write("N/A")
                    with c2:
                        st.write("**Normal Tags (All Matches)**")
                        if normal_tags:
                            display_df = stats_df[stats_df['tag'].isin(normal_tags)].sort_values(by='perc', ascending=False)
                            for _, row in display_df.iterrows():
                                st.button(f"{row['tag']} ({row['perc']:.1f}%)", key=f"btn_{row['tag']}")
                        else: st.write("N/A")
                    with c3:
                        st.write("**Subpages**")
                        if subpages:
                            for s in list(set(subpages))[:3]: st.warning(s)
                        else: st.error("Manual Required")

                    with st.expander(":mag: Debug View: Item Breakdown"):
                        st.write(stats_df.sort_values(by='perc', ascending=False))
            else:
                st.error("Zero items found after blacklist. Check your file columns.")
        else:
            st.error("Error: Need 'Category' and 'Item Name' columns.")
