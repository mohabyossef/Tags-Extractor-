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

    # --- 2. DATA LOADERS (Smart Format Detection) ---
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
            # We grab the first column as the tag names
            all_tags = tags_df.iloc[:, 0].dropna().unique().tolist()
            # Remove marketing/campaign noise
            campaign_regex = r"%|off|sale|sar|jod|deal|offer|discount|promo"
            clean_tags = [t for t in all_tags if not re.search(campaign_regex, str(t), re.IGNORECASE)]
            
        return blacklist, clean_tags

    @st.cache_data
    def load_logistics_data(city_choice):
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
            if gdf.crs is None: gdf.set_crs(epsg=4326, inplace=True)
            else: gdf = gdf.to_crs(epsg=4326)
            
            xls = pd.ExcelFile("delivery_matrix.xlsx")
            target_sheet = city_choice if city_choice in xls.sheet_names else 0
            raw_matrix = pd.read_excel(xls, sheet_name=target_sheet) 
            
            processed_data = []
            for _, row in raw_matrix.iterrows():
                if pd.isna(row.iloc[0]): continue
                destinations = [str(val).strip() for val in row.iloc[1:] if pd.notna(val) and str(val).strip() != ""]
                processed_data.append({
                    "Home_Zone": str(row.iloc[0]).strip(), 
                    "Eligible_Zones": ", ".join(destinations), 
                    "Zone_Count": len(destinations)
                })
            return gdf, pd.DataFrame(processed_data)
        except: return None, None

    # --- 3. SIDEBAR NAVIGATION ---
    st.sidebar.title("🛠️ Hub Controls")
    mode = st.sidebar.radio("Select Module:", ["🏷️ Menu Tagger", "📍 Zone Identifier"])
    
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    # --- MODULE 2: MENU TAGGER ---
    if mode == "🏷️ Menu Tagger":
        st.title("🏷️ Hobz AI Menu Tagger")
        blacklist, clean_tags = load_tagging_resources()
        
        if not clean_tags:
            st.error("⚠️ Database Error: 'tags' file not found.")
        
        col1, col2 = st.columns([1, 2])
        with col1:
            res_name = st.text_input("Restaurant Name")
            upload_file = st.file_uploader("Upload Menu (Excel/CSV)", type=['xlsx', 'csv'])
            
        if upload_file:
            df = pd.read_csv(upload_file) if upload_file.name.endswith('csv') else pd.read_excel(upload_file)
            
            if len(df.columns) >= 2:
                # Column 0: Category, Column 1: Item Name
                df_clean = df[~df.iloc[:, 0].astype(str).str.lower().str.strip().isin(blacklist)].copy()
                df_clean['merged'] = df_clean.iloc[:, 0].astype(str) + " " + df_clean.iloc[:, 1].astype(str)
                merged_items = df_clean['merged'].tolist()
                total_count = len(merged_items)

                if total_count > 0:
                    item_stats = []
                    for tag in clean_tags:
                        if "Subpage" in str(tag): continue
                        
                        t_lower = str(tag).lower().strip()
                        # Check if tag is in merged context (e.g. "Pie" in "Pastry Apple Pie")
                        match_count = sum(1 for context in merged_items if t_lower in context.lower())
                        
                        if match_count > 0:
                            item_stats.append({"tag": tag, "perc": (match_count / total_count) * 100})
                    
                    stats_df = pd.DataFrame(item_stats)

                    # --- MULTI-TAG 30% LOGIC ---
                    normal_tags = []
                    if not stats_df.empty:
                        # Grab all tags crossing the 30% threshold
                        high_perc = stats_df[stats_df['perc'] >= 30]
                        if not high_perc.empty:
                            normal_tags = high_perc['tag'].tolist()
                        else:
                            # Fallback: Top 3 highest matches
                            normal_tags = stats_df.sort_values(by='perc', ascending=False).head(3)['tag'].tolist()
                    
                    normal_tags = list(set(normal
