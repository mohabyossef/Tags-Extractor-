import streamlit as st
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import folium
from streamlit_folium import st_folium
import re

# --- 1. SECURE PASSWORD PROTECTION ---
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]: 
            st.session_state["password_correct"] = True
            del st.session_state["password"] 
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.title("🔒 Hobz Logistics Hub Access")
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.title("🔒 Hobz Logistics Hub Access")
        st.text_input("Enter Password", type="password", on_change=password_entered, key="password")
        st.error("😕 Password incorrect.")
        return False
    else:
        return True

# --- 2. MAIN APP CONTENT ---
if check_password():
    # --- 3. DATA LOADERS ---
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

    @st.cache_data
    def load_tagging_data():
        try:
            bl_df = pd.read_csv("Category Blacklist  .xlsx - Sheet1.csv")
            blacklist = [str(x).strip().lower() for x in bl_df.iloc[:, 0].dropna()]
            tags_df = pd.read_csv("The Tag Sheet.xlsx - Sheet1.csv")
            all_tags = tags_df['tag_name'].dropna().unique().tolist()
            campaign_regex = r"%|off|sale|sar|jod|deal|offer|discount|promo"
            clean_tags = [t for t in all_tags if not re.search(campaign_regex, str(t), re.IGNORECASE)]
            return blacklist, clean_tags
        except: return [], []

    # --- 4. SIDEBAR NAVIGATION ---
    st.sidebar.title("🗺️ UAE Hub Controls")
    mode = st.sidebar.selectbox("Choose Module:", ["📍 Zone Identifier", "🏷️ Menu Tagger"])
    
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    # --- MODULE 1: ZONE IDENTIFIER ---
    if mode == "📍 Zone Identifier":
        emirate = st.sidebar.radio("Select Emirate:", ["Dubai", "Sharjah", "Ajman", "Ras Al Khaimah", "Umm Al Quwain", "Fujairah"])
        zones_gdf, matrix_df = load_logistics_data(emirate)
        
        st.title(f"📍 {emirate} Community & Delivery Finder")
        if zones_gdf is not None:
            col1, col2 = st.columns([1, 1])
            with col1:
                coords_raw = st.text_input("Paste Coordinates (Lat, Long)")
                if coords_raw:
                    try:
                        lat, lon = map(float, coords_raw.split(','))
                        p = Point(lon, lat)
                        match = zones_gdf[zones_gdf.contains(p)]
                        if not match.empty:
                            row = match.iloc[0]
                            potential_headers = ['CNAME_E', 'name', 'COMM_NAME', 'NAME_EN', 'LABEL']
                            zone_name = next((str(row[h]).strip() for h in potential_headers if h in match.columns and pd.notna(row[h]) and str(row[h]).lower() != "none"), "Undefined Zone")
                            st.success(f"🎯 **Zone:** {zone_name}")
                            st.code(zone_name)
                            logic_match = matrix_df[matrix_df['Home_Zone'].str.contains(zone_name, case=False, na=False)]
                            if not logic_match.empty:
                                st.metric("Eligible Zones", logic_match.iloc[0]['Zone_Count'])
                                st.info(f"**Delivers To:** {logic_match.iloc[0]['Eligible_Zones']}")
                        else: st.warning("Outside boundaries.")
                    except: st.error("Use format: Lat, Long")
            with col2:
                centers = {"Dubai": [25.15, 55.3], "Sharjah": [25.35, 55.45], "Ajman": [25.40, 55.50], "Ras Al Khaimah": [25.75, 55.95], "Umm Al Quwain": [25.55, 55.55], "Fujairah": [25.12, 56.32]}
                m = folium.Map(location=centers.get(emirate, [25.0, 55.0]), zoom_start=11)
                folium.GeoJson(zones_gdf).add_to(m)
                st_folium(m, width="100%", height=500)

    # --- MODULE 2: MENU TAGGER ---
    elif mode == "🏷️ Menu Tagger":
        st.title("🏷️ Hobz AI Menu Tagger")
        blacklist, clean_tags = load_tagging_data()
        
        col1, col2 = st.columns([1,
