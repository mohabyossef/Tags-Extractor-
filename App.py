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
    # --- 2. CONFIG ---
    st.set_page_config(page_title="Hobz AI Tagger", layout="wide")

    # --- 3. LOAD DATA ---
    @st.cache_data
    def load_tagging_resources():
        try:
            bl_df = pd.read_csv("Category Blacklist  .xlsx - Sheet1.csv")
            blacklist = [str(x).strip().lower() for x in bl_df.iloc[:, 0].dropna()]
            tags_df = pd.read_csv("The Tag Sheet.xlsx - Sheet1.csv")
            all_tags = tags_df['tag_name'].dropna().unique().tolist()
            # Clean campaigns
            clean_tags = [t for t in all_tags if not re.search(r"%|off|sale|sar|jod|deal|offer", str(t), re.IGNORECASE)]
            return blacklist, clean_tags
        except: return [], []

    # --- 4. SIDEBAR NAVIGATION ---
    st.sidebar.title("🛠️ Tools")
    # You can change this to a radio if you want to allow switching, 
    # or hardcode it to "🏷️ Menu Tagger" to hide the Zones tool.
    mode = st.sidebar.radio("Select Module:", ["🏷️ Menu Tagger", "📍 Zone Identifier"])
    
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    if mode == "🏷️ Menu Tagger":
        st.title("🏷️ Hobz AI Menu Tagger (Audit Mode)")
        blacklist, clean_tags = load_tagging_resources()
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            res_name = st.text_input("Restaurant Name")
            upload_file = st.file_uploader("Upload Menu Export (Excel or CSV)", type=['xlsx', 'csv'])
            st.info("The file should have a column named 'Category' or 'Item Name'.")

        # Process Data
        menu_data = []
        if upload_file:
            if upload_file.name.endswith('csv'):
                df_upload = pd.read_csv(upload_file)
            else:
                df_upload = pd.read_excel(upload_file)
            
            # Flatten all text from the file into a list of items
            menu_data = df_upload.astype(str).values.flatten().tolist()
            menu_data = [i.strip() for i in menu_data if i.strip() and i.lower() != 'nan']

        if menu_data:
            # Filter Blacklist
            main_items = [i for i in menu_data if not any(b in i.lower() for b in blacklist)]
            if not main_items: main_items = menu_data
            
            # 30% Logic
            counts = pd.Series(main_items).value_counts()
            total = len(main_items)
            
            normal_tags = []
            for item, count in counts.items():
                if (count / total) >= 0.30:
                    # Find matching tag
                    match = next((t for t in clean_tags if item.lower() in str(t).lower() and "Subpage" not in str(t)), None)
                    if match: normal_tags.append(str(match))

            # Cuisine Logic
            cuisine_tags = []
            combined_text = (res_name + " " + " ".join(menu_data)).lower()
            for t in clean_tags:
                if "Subpage" not in str(t) and str(t).lower() in combined_text:
                    cuisine_tags.append(str(t))
            cuisine_tags = list(set(cuisine_tags))[:3]

            # Subpage Logic
            subpages = []
            refs = [str(x).lower() for x in (normal_tags + cuisine_tags)]
            for t in clean_tags:
                if "Subpage" in str(t) and any(r in str(t).lower() for r in refs if len(r) > 3):
                    subpages.append(str(t))

            with col2:
                st.subheader("📋 Audit Results")
                m1, m2, m3 = st.columns(3)
                m1.metric("Main Items", total)
                m2.metric("Filtered Categories", len(menu_data) - total)
                m3.metric("Normal Tags", len(normal_tags))

                st.markdown("### 🏷️ Suggested Tagging Profile")
                res_col1, res_col2 = st.columns(2)
                
                with res_col1:
                    st.write("**Cuisine Tags (Transparent)**")
                    if cuisine_tags:
                        for c in cuisine_tags: st.success(c)
                    else: st.write("No matching cuisine found.")

                with res_col2:
                    st.write("**Normal Tags (Purple)**")
                    if normal_tags:
                        for n in normal_tags: st.button(n, key=n, use_container_width=True)
                    else: st.write("No item reached 30% threshold.")

                st.write("**Mandatory Subpage**")
                if subpages:
                    st.warning(subpages[0])
                else:
                    st.error("⚠️ Manual Subpage Required")

    # --- ZONE IDENTIFIER MODULE ---
    elif mode == "📍 Zone Identifier":
        # (The existing zone code goes here, same as before)
        st.title("📍 Zone Identifier Module")
        st.write("This tool is currently active for Logistics audits.")
