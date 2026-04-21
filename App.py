# --- MODULE 2: MENU TAFGER (Updated Fail-Proof Version) ---
    elif mode == "🏷️ Menu Tagger":
        st.title("🏷️ Hobz AI Menu Tagger")
        blacklist, clean_tags = load_tagging_data()
        
        col1, col2 = st.columns([1, 2])
        with col1:
            res_name = st.text_input("Restaurant Name (e.g., Al Jaddaf Burger)")
            st.caption("Paste categories like: Burger, Burger, Fries, Drink, Dessert")
            menu_input = st.text_area("Paste Menu Categories", height=250)
            
        if menu_input:
            # 1. Clean and Filter
            lines = [line.strip() for line in menu_input.split('\n') if line.strip()]
            
            # Remove Blacklisted items (Drinks/Desserts)
            main_items = []
            for l in lines:
                is_blacklisted = any(b.lower() in l.lower() for b in blacklist)
                if not is_blacklisted:
                    main_items.append(l)
            
            # If everything was blacklisted, use the original list so we don't have 0
            if not main_items: main_items = lines 
            
            # 2. 30% Logic (Normal Purple Tags)
            total_main = len(main_items)
            counts = pd.Series(main_items).value_counts()
            
            normal_proposals = []
            for item, count in counts.items():
                perc = (count / total_main) * 100
                if perc >= 30:
                    # Find any tag in the sheet that contains the item name
                    # Example: if item is "Pizza", match "Pizza", "Italian Pizza", etc.
                    matches = [t for t in clean_tags if item.lower() in t.lower() and "Subpage" not in t]
                    if matches:
                        # Use the shortest match as it's usually the most "Generic/Normal" tag
                        best_match = min(matches, key=len)
                        normal_proposals.append(f"{best_match}")

            # 3. Cuisine Logic (Check Restaurant Name + Normal Tags)
            cuisine_proposals = []
            search_text = (res_name + " " + " ".join(main_items)).lower()
            
            for t in clean_tags:
                if "Subpage" not in t:
                    # If the tag name is found in the restaurant name or menu
                    if t.lower() in search_text:
                        cuisine_proposals.append(t)
            
            # Clean up Cuisine results (Unique, Max 3, and remove duplicates of Normal tags)
            cuisine_proposals = list(set(cuisine_proposals))
            cuisine_proposals = [c for c in cuisine_proposals if c not in [n.split(' (')[0] for n in normal_proposals]]
            cuisine_proposals = cuisine_proposals[:3]

            # 4. Subpage Logic (Identify which subpage fits the tags found)
            subpage_proposals = []
            all_found_tags = [n for n in normal_proposals] + cuisine_proposals
            
            for t in clean_tags:
                if "Subpage" in t:
                    if any(word.lower() in t.lower() for word in all_found_tags if len(word) > 3):
                        subpage_proposals.append(t)
            
            subpage_proposals = list(set(subpage_proposals))

            with col2:
                st.subheader("📋 Recommended Tag Profile")
                st.markdown("---")
                
                # Visual Dashboard
                c1, c2, c3 = st.columns(3)
                
                with c1:
                    st.markdown("### 🌍 Cuisine")
                    if cuisine_proposals:
                        for c in cuisine_proposals: st.write(f"✅ {c}")
                    else: st.write("No Cuisine detected")
                
                with c2:
                    st.markdown("### 💜 Normal (30%)")
                    if normal_proposals:
                        for n in normal_proposals: st.write(f"🟣 {n}")
                    else: st.write("No single category > 30%")
                
                with c3:
                    st.markdown("### 📄 Subpages")
                    if subpage_proposals:
                        for s in subpage_proposals: st.write(f"📄 {s}")
                    else: st.write("Assign manual subpage")

                st.divider()
                st.write(f"**Audit Stats:** {total_main} Main Items processed (excluded {len(lines)-len(main_items)} blacklisted items).")
