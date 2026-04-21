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
            blacklist = [str(x).strip().lower() for x in bl_df.iloc[:, 0].dropna()]
            
        tags_df = try_read("tags")
        if tags_df is not None:
            all_tags = tags_df.iloc[:, 0].dropna().unique().tolist()
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
