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
    st.set_page_config(page_title="Hobz AI Tagger", layout="wide")

    # --- 2. DATA LOADERS ---
    @st.cache_data
    def load_tagging_resources():
        try:
            bl_df = pd.read_csv("Category Blacklist  .xlsx - Sheet1.csv")
            # Get category names from the first column
            blacklist = [str(x).strip().lower() for x in bl_df.iloc[:, 0].dropna()]
            
            tags_df = pd.read_csv("The Tag Sheet.xlsx - Sheet1.csv")
            all_tags = tags_df['tag_name'].dropna().unique().tolist()
            # Filter marketing/campaign tags
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
        st.title("🏷️ Hobz AI Menu Tagger (Merged Context Mode)")
        blacklist, clean_tags = load_tagging_resources()
        
        col1, col2 = st.columns([1, 2])
        with col1:
            res_name = st.text_input("Restaurant Name")
            upload_file = st.file_uploader("Upload Menu (Excel/CSV)", type=['xlsx', 'csv'])
            st.caption("Ensure file has 'Category' and 'Item Name' columns.")
        
        if upload_file:
            # Load the file
            df = pd.read_csv(upload_file) if upload_file.name.endswith('csv') else pd.read_excel(upload_file)
            
            # Standardize column names (lowercase)
            df.columns = [str(c).strip().lower() for c in df.columns]
            
            # --- THE FIX: MERGED CONTEXT LOGIC ---
            # We look for common column names for Category and Item
            cat_col = next((c for c in df.columns if 'cat' in c), None)
            item_col = next((c for c in df.columns if 'item' in c or 'name' in c), None)

            if cat_col and item_col:
                # 1. Filter out Blacklisted Categories first
                df_clean = df[~df[cat_col].astype(str).str.lower().isin(blacklist)].copy()
                
                # 2. Create the "Merged Identity" for each row
                # This combines Category + Item Name so "Pizza" + "Ranch" becomes "Pizza Ranch"
                df_clean['merged_context'] = df_clean[cat_col].astype(str) + " " + df_clean[item_col].astype(str)
                merged_items = df_clean['merged_context'].tolist()
                
                total_count = len(merged_items)
                
                # 3. Deep Scan using the Merged Context
                item_stats = []
                for tag in clean_tags:
                    if "Subpage" in str(tag): continue
                    
                    # Count how many merged items contain this tag
                    count = sum(1 for context in merged_items if str(tag).lower() in context.lower())
                    if count > 0:
                        item_stats.append({"tag": tag, "perc": (count / total_count) * 100})
                
                stats_df = pd.DataFrame(item_stats)

                # Identify Normal Tags
                normal_tags = []
                if not stats_df.empty:
                    normal_tags = stats_df[stats_df['perc'] >= 30]['tag'].tolist()
                    if not normal_tags: # Fallback to highest
                        normal_tags = [stats_df.sort_values(by='perc', ascending=False).iloc[0]['tag']]

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
                    st.subheader("📋 Audit Results")
                    st.write(f"Analyzed **{total_count}** Main Items (Categories like 'Drinks/Desserts' excluded).")
                    
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.write("**Cuisine Tags**")
                        for c in cuisine_tags if cuisine_tags else ["N/A"]: st.success(c)
                    with c2:
                        st.write("**Normal Tags (30%+)**")
                        for n in normal_tags:
                            p = stats_df[stats_df['tag'] == n]['perc'].values[0]
                            st.button(f"{n} ({p:.0f}%)", key=n)
                    with c3:
                        st.write("**Subpage**")
                        if subpages: st.warning(subpages[0])
                        else: st.error("Manual Subpage Required")
            else:
                st.error("Could not find 'Category' or 'Item Name' columns in your file.")

    # --- ZONE IDENTIFIER ---
    elif mode == "📍 Zone Identifier":
        st.title("📍 Zone Identifier Module")
        # (Existing Zone Code)
