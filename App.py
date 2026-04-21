import streamlit as st
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import folium
from streamlit_folium import st_folium
import re
from collections import Counter

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
    st.set_page_config(page_title="Hobz AI Tagger", layout="wide")

    # --- 2. LOAD DATA ---
    @st.cache_data
    def load_tagging_resources():
        try:
            bl_df = pd.read_csv("Category Blacklist  .xlsx - Sheet1.csv")
            blacklist = [str(x).strip().lower() for x in bl_df.iloc[:, 0].dropna()]
            tags_df = pd.read_csv("The Tag Sheet.xlsx - Sheet1.csv")
            all_tags = tags_df['tag_name'].dropna().unique().tolist()
            # Clean marketing tags
            clean_tags = [t for t in all_tags if not re.search(r"%|off|sale|sar|jod|deal|offer", str(t), re.IGNORECASE)]
            return blacklist, clean_tags
        except: return [], []

    # --- 3. SIDEBAR ---
    st.sidebar.title("🛠️ Tools")
    mode = st.sidebar.radio("Select Module:", ["🏷️ Menu Tagger", "📍 Zone Identifier"])
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    if mode == "🏷️ Menu Tagger":
        st.title("🏷️ Hobz AI Menu Tagger (Deep Scan Mode)")
        blacklist, clean_tags = load_tagging_resources()
        
        col1, col2 = st.columns([1, 2])
        with col1:
            res_name = st.text_input("Restaurant Name")
            upload_file = st.file_uploader("Upload Menu (Excel/CSV)", type=['xlsx', 'csv'])
        
        if upload_file:
            df_upload = pd.read_csv(upload_file) if upload_file.name.endswith('csv') else pd.read_excel(upload_file)
            # Flatten all cells into one long list of items
            all_raw_items = df_upload.astype(str).values.flatten().tolist()
            all_raw_items = [i.strip() for i in all_raw_items if i.strip() and i.lower() != 'nan']

            # Filter Blacklist
            main_items = [i for i in all_raw_items if not any(b in i.lower() for b in blacklist)]
            if not main_items: main_items = all_raw_items
            
            # --- NEW DEEP ITEM SCAN LOGIC ---
            total_count = len(main_items)
            tag_matches = []

            # Check every tag in your sheet against every item in the menu
            # We count how many items "contain" a specific tag word
            item_stats = []
            for tag in clean_tags:
                if "Subpage" in str(tag): continue
                
                # Count how many items contain this tag name
                # e.g., how many items contain the word "Burger"
                count = sum(1 for item in main_items if str(tag).lower() in item.lower())
                if count > 0:
                    percentage = (count / total_count) * 100
                    item_stats.append({"tag": tag, "perc": percentage})
            
            stats_df = pd.DataFrame(item_stats)
            
            # Identify Normal Tags (30% Rule)
            normal_tags = []
            if not stats_df.empty:
                # Rule 1: Take everything >= 30%
                normal_tags = stats_df[stats_df['perc'] >= 30]['tag'].tolist()
                
                # Rule 2: Fallback - if nothing is >= 30%, take the single highest percentage item
                if not normal_tags:
                    highest_item = stats_df.sort_values(by='perc', ascending=False).iloc[0]['tag']
                    normal_tags = [highest_item]

            # Cuisine Logic (from Name and Normal Tags)
            cuisine_tags = []
            combined_context = (res_name + " " + " ".join(normal_tags)).lower()
            for t in clean_tags:
                if "Subpage" not in str(t) and str(t).lower() in combined_context:
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
                m1, m2 = st.columns(2)
                m1.metric("Total Main Items Scanned", total_count)
                
                st.markdown("### 🏷️ Suggested Tagging Profile")
                res_c1, res_c2, res_c3 = st.columns(3)
                
                with res_c1:
                    st.write("**Cuisine Tags**")
                    for c in cuisine_tags if cuisine_tags else ["N/A"]: st.success(c)

                with res_c2:
                    st.write("**Normal Tags (Purple)**")
                    # Show percentages for clarity
                    for n in normal_tags:
                        p = stats_df[stats_df['tag'] == n]['perc'].values[0]
                        st.button(f"{n} ({p:.1f}%)", key=n)

                with res_c3:
                    st.write("**Subpage**")
                    if subpages: st.warning(subpages[0])
                    else: st.error("Manual Subpage Required")

    # --- ZONE IDENTIFIER ---
    elif mode == "📍 Zone Identifier":
        st.title("📍 Zone Identifier Module")
        # (Your existing zone code stays here)
