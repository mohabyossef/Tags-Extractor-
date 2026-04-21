import streamlit as st
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import folium
from streamlit_folium import st_folium
import re

# --- 1. PASSWORD PROTECTION ---
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
    else: return True

if check_password():
    st.set_page_config(page_title="Hobz AI Tagger", layout="wide")

    @st.cache_data
    def load_tagging_resources():
        try:
            bl_df = pd.read_csv("Category Blacklist  .xlsx - Sheet1.csv")
            blacklist = [str(x).strip().lower() for x in bl_df.iloc[:, 0].dropna()]
            tags_df = pd.read_csv("The Tag Sheet.xlsx - Sheet1.csv")
            all_tags = tags_df['tag_name'].dropna().unique().tolist()
            clean_tags = [t for t in all_tags if not re.search(r"%|off|sale|sar|jod|deal|offer", str(t), re.IGNORECASE)]
            return blacklist, clean_tags
        except: return [], []

    st.sidebar.title("🛠️ Tools")
    mode = st.sidebar.radio("Select Module:", ["🏷️ Menu Tagger", "📍 Zone Identifier"])
    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()

    if mode == "🏷️ Menu Tagger":
        st.title("🏷️ Hobz AI Menu Tagger (Merged Context)")
        blacklist, clean_tags = load_tagging_resources()
        
        col1, col2 = st.columns([1, 2])
        with col1:
            res_name = st.text_input("Restaurant Name")
            upload_file = st.file_uploader("Upload Menu (Excel/CSV)", type=['xlsx', 'csv'])
        
        if upload_file:
            # Load file
            df = pd.read_csv(upload_file) if upload_file.name.endswith('csv') else pd.read_excel(upload_file)
            
            # --- AUTO-DETECT COLUMNS ---
            # We take the first two columns regardless of their names
            if len(df.columns) >= 2:
                cat_vals = df.iloc[:, 0].astype(str)
                item_vals = df.iloc[:, 1].astype(str)
                
                # Combine them into a temporary dataframe
                proc_df = pd.DataFrame({'cat': cat_vals, 'item': item_vals})
                
                # Filter Blacklist
                # It removes rows where the first column matches your blacklist
                mask = proc_df['cat'].str.lower().str.strip().isin(blacklist)
                df_clean = proc_df[~mask].copy()
                
                # Merged Identity
                df_clean['context'] = df_clean['cat'] + " " + df_clean['item']
                merged_items = df_clean['context'].tolist()
                total_count = len(merged_items)

                if total_count > 0:
                    # Deep Scan
                    item_stats = []
                    for tag in clean_tags:
                        if "Subpage" in str(tag): continue
                        # Match tag inside the merged string
                        count = sum(1 for context in merged_items if str(tag).lower() in context.lower())
                        if count > 0:
                            item_stats.append({"tag": tag, "perc": (count / total_count) * 100})
                    
                    stats_df = pd.DataFrame(item_stats)

                    # Tag Logic
                    normal_tags = []
                    if not stats_df.empty:
                        normal_tags = stats_df[stats_df['perc'] >= 30]['tag'].tolist()
                        if not normal_tags:
                            normal_tags = [stats_df.sort_values(by='perc', ascending=False).iloc[0]['tag']]

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
                        st.write(f"Analyzed **{total_count}** items after filtering blacklist.")
                        
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.write("**Cuisine**")
                            for c in cuisine_tags if cuisine_tags else ["N/A"]: st.success(c)
                        with c2:
                            st.write("**Normal (30%+)**")
                            for n in normal_tags:
                                p = stats_df[stats_df['tag'] == n]['perc'].values[0]
                                st.button(f"{n} ({p:.0f}%)", key=n)
                        with c3:
                            st.write("**Subpage**")
                            if subpages: st.warning(subpages[0])
                            else: st.error("Manual Required")

                        # DEBUG WINDOW (Expand to see why it matches/fails)
                        with st.expander("🔍 See System Data Scan"):
                            st.write("First 10 items processed after blacklist:")
                            st.write(merged_items[:10])
                else:
                    st.error("All items in your file were filtered out by the Blacklist.")
            else:
                st.error("File needs at least 2 columns (Category and Item).")
