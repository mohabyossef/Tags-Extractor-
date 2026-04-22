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
        st.title("🔒 Hobz Hub Access")
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.title("🔒 Hobz Hub Access")
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        st.error("😕 Password incorrect.")
        return False
    else:
        return True

if check_password():
    st.set_page_config(page_title="Hobz AI Hub", layout="wide")

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
            # Load blacklist from source [cite: 1]
            blacklist = [str(x).strip().lower() for x in bl_df.iloc[:, 0].dropna() if len(str(x)) > 2]
            
        tags_df = try_read("tags")
        if tags_df is not None:
            # Load tags from source [cite: 2]
            all_tags = tags_df.iloc[:, 0].dropna().unique().tolist()
            campaign_regex = r"%|off|sale|sar|jod|deal|offer|discount|promo"
            clean_tags = [str(t).strip() for t in all_tags if not re.search(campaign_regex, str(t), re.IGNORECASE)]
        return blacklist, clean_tags

    @st.cache_data
    def load_logistics_data(city_choice):
        # Implementation for logistics [cite: 1, 9]
        file_map = {
            "Dubai": "dubai_communities.geojson",
            "Sharjah": "sharjah_districts.geojson",
            "Ajman": "ajman_zones.geojson",
            "Ras Al Khaimah": "rak_zones.geojson",
            "Umm Al Quwain": "uaq_zones.geojson",
            "Fujairah": "fujairah_zones.geojson"
        }
        try:
            gdf = gpd.read_file(file_map[city_choice])
            xls = pd.ExcelFile("delivery_matrix.xlsx")
            target_sheet = city_choice if city_choice in xls.sheet_names else 0
            raw_matrix = pd.read_excel(xls, sheet_name=target_sheet) 
            processed_data = []
            for _, row in raw_matrix.iterrows():
                if pd.isna(row.iloc[0]): continue
                destinations = [str(val).strip() for val in row.iloc[1:] if pd.notna(val) and str(val).strip() != ""]
                processed_data.append({"Home_Zone": str(row.iloc[0]).strip(), "Eligible_Zones": ", ".join(destinations), "Zone_Count": len(destinations)})
            return gdf, pd.DataFrame(processed_data)
        except Exception: return None, None

    st.sidebar.title("🛠️ Hub Controls")
    mode = st.sidebar.radio("Select Module:", ["🏷️ Menu Tagger", "📍 Zone Identifier"])
    
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    if mode == "🏷️ Menu Tagger":
        st.title("🏷️ Hobz AI Menu Tagger")
        blacklist, clean_tags = load_tagging_resources()
        
        col1, col2 = st.columns([1, 2])
        with col1:
            res_name = st.text_input("Restaurant Name")
            upload_file = st.file_uploader("Upload Menu", type=['xlsx', 'csv'])
            
        if upload_file:
            df = pd.read_csv(upload_file) if upload_file.name.endswith('csv') else pd.read_excel(upload_file)
            if len(df.columns) >= 2:
                # --- NEW INTELLIGENT OVERRIDE LOGIC ---
                all_items_count = len(df)
                
                # Check for "Dominant" blacklisted items (e.g., if Salads are 60% of the whole menu)
                rescued_from_blacklist = []
                for b_item in blacklist:
                    b_count = sum(1 for cat in df.iloc[:, 0].astype(str).str.lower() if b_item in cat)
                    if (b_count / all_items_count) >= 0.60:
                        rescued_from_blacklist.append(b_item)

                # Filter data, but SPARE the "rescued" items
                def smart_filter(cat_name):
                    cat_name = str(cat_name).lower()
                    # If it's blacklisted BUT NOT rescued, block it
                    is_bl = any(b in cat_name for b in blacklist)
                    is_rescued = any(r in cat_name for r in rescued_from_blacklist)
                    return is_bl and not is_rescued

                df_clean = df[~df.iloc[:, 0].apply(smart_filter)].copy()
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
                    normal_tags = []
                    if not stats_df.empty:
                        high_perc = stats_df[stats_df['perc'] >= 30]
                        normal_tags = high_perc['tag'].tolist() if not high_perc.empty else stats_df.sort_values(by='perc', ascending=False).head(3)['tag'].tolist()
                    
                    # Final buttons
                    normal_tags = list(set(normal_tags))
                    
                    cuisine_tags = []
                    context_str = (res_name + " " + " ".join(normal_tags)).lower()
                    for t in clean_tags:
                        if "Subpage" not in str(t) and str(t).lower() in context_str:
                            cuisine_tags.append(str(t))
                    cuisine_tags = list(set(cuisine_tags))[:3]

                    subpages = []
                    refs = [str(x).lower() for x in (normal_tags + cuisine_tags)]
                    for t in clean_tags:
                        if "Subpage" in str(t) and any(r in str(t).lower() for r in refs if len(r) > 3):
                            subpages.append(str(t))

                    with col2:
                        st.subheader("📋 Audit Results")
                        if rescued_from_blacklist:
                            st.info(f"💡 **Identity Override:** '{', '.join(rescued_from_blacklist)}' detected as main identity. Blacklist ignored for these items.")
                        
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.write("**Cuisine**")
                            for c in cuisine_tags if cuisine_tags else ["N/A"]: st.success(c)
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
