import streamlit as st
from recipe_scrapers import scrape_me
import sqlite3
from collections import Counter
from datetime import datetime, timedelta # NEW: Gives our app a sense of time!

# --- 1. OUR CUSTOM INGREDIENT CLEANER ---
def get_core_ingredient(raw_string):
    raw_string = raw_string.lower()
    trash_words = [
        "teaspoon", "teaspoons", "tsp", "tablespoon", "tablespoons", "tbsp", 
        "cup", "cups", "oz", "ounce", "ounces", "g", "gram", "grams", "ml", "liter",
        "lb", "lbs", "pound", "pounds", "pinch", "dash", "clove", "cloves",
        "of", "chopped", "diced", "sliced", "minced", "fresh", "ground", "large", "small",
        "and", "to", "taste"
    ]
    words = raw_string.split()
    core_words = []
    for word in words:
        if not any(char.isdigit() for char in word):
            clean_word = word.replace(",", "").replace("(", "").replace(")", "")
            if clean_word not in trash_words and clean_word != "":
                core_words.append(clean_word)
    return " ".join(core_words).title()

# --- 2. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('meals.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS meals (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, url TEXT, image_url TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ingredients (id INTEGER PRIMARY KEY AUTOINCREMENT, meal_id INTEGER, name TEXT, FOREIGN KEY (meal_id) REFERENCES meals (id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS staples (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, frequency TEXT)''')
    
    # NEW: Automatically upgrade the database if it doesn't have the date columns yet
    try:
        c.execute("ALTER TABLE staples ADD COLUMN last_purchased TEXT")
        c.execute("ALTER TABLE staples ADD COLUMN next_due TEXT")
    except sqlite3.OperationalError:
        pass # The columns already exist, skip!
        
    conn.commit()
    conn.close()

init_db() 

# --- HELPER FUNCTION: Calculate Due Dates ---
def calculate_next_due(frequency):
    today = datetime.now()
    if frequency == "Every 1 week": return (today + timedelta(days=7)).strftime("%Y-%m-%d")
    if frequency == "Every 2 weeks": return (today + timedelta(days=14)).strftime("%Y-%m-%d")
    if frequency == "Every 3 weeks": return (today + timedelta(days=21)).strftime("%Y-%m-%d")
    if frequency == "Every 4 weeks": return (today + timedelta(days=28)).strftime("%Y-%m-%d")
    return today.strftime("%Y-%m-%d")

# --- 3. THE DASHBOARD ---
st.set_page_config(page_title="My Meal Planner", page_icon="🍳", layout="wide")
st.title("🍳 Weekly Meal Planner")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["➕ Scrape Recipe", "🗓️ My Meal Plan", "🥛 Staples", "📝 Manual Recipe", "⚙️ Manage Recipes"])

# --- TAB 1: ADDING RECIPES FROM WEB ---
with tab1:
    st.write("Paste a recipe link to scrape and save it to your planner!")
    recipe_url = st.text_input("Recipe URL:")
    if st.button("Scrape & Save Recipe"):
        if recipe_url: 
            try:
                scraper = scrape_me(recipe_url)
                try: recipe_title = scraper.title()
                except: recipe_title = "Unknown Recipe Title"
                try: image_url = scraper.image()
                except: image_url = "https://via.placeholder.com/400x300.png?text=No+Picture+Available"
                
                conn = sqlite3.connect('meals.db')
                c = conn.cursor()
                c.execute("INSERT INTO meals (title, url, image_url) VALUES (?, ?, ?)", (recipe_title, recipe_url, image_url))
                meal_id = c.lastrowid 
                st.success(f"Successfully saved: **{recipe_title}**!")
                
                try:
                    ingredients = scraper.ingredients()
                    for item in ingredients:
                        clean_item = get_core_ingredient(item)
                        if clean_item.strip(): 
                            c.execute("INSERT INTO ingredients (meal_id, name) VALUES (?, ?)", (meal_id, clean_item))
                except: pass
                conn.commit()
                conn.close()
            except Exception as e:
                st.error(f"Oops! Couldn't scrape that URL. Details: {e}")
        else:
            st.warning("Please paste a URL first!")

# --- TAB 2: VIEWING THE PLANNER & SMART LIST ---
with tab2:
    # SMART ALERT: Check for staples running low!
    conn = sqlite3.connect('meals.db')
    c = conn.cursor()
    c.execute("SELECT name, next_due FROM staples")
    all_staples = c.fetchall()
    
    low_staples = []
    today_str = datetime.now().strftime("%Y-%m-%d")
    for staple in all_staples:
        if staple[1] and staple[1] <= today_str: # If due date is today or in the past
            low_staples.append(staple[0])
            
    if low_staples:
        st.warning(f"🔔 **Smart Reminder:** You are projected to be running low on: **{', '.join(low_staples)}**!")

    st.write("### 👨‍🍳 Choose Your Dinners!")
    c.execute("SELECT id, title, image_url FROM meals")
    saved_meals = c.fetchall() 
    
    if len(saved_meals) == 0:
        st.info("You haven't saved any meals yet.")
    else:
        cols = st.columns(3)
        selected_meal_ids = []
        for index, meal in enumerate(saved_meals):
            meal_id, title, img_url = meal
            with cols[index % 3]:
                st.image(img_url, use_container_width=True)
                is_selected = st.checkbox(f"**{title}**", key=f"chk_{meal_id}")
                if is_selected: selected_meal_ids.append(meal_id)
                st.write("---")
        
        if len(selected_meal_ids) > 0:
            st.write("### 🛒 Your Interactive Shopping List")
            placeholders = ','.join('?' * len(selected_meal_ids))
            c.execute(f"SELECT name FROM ingredients WHERE meal_id IN ({placeholders})", selected_meal_ids)
            tallied_ingredients = Counter([item[0] for item in c.fetchall()])
            
            for item, count in tallied_ingredients.items():
                col_name, col_basket, col_pantry = st.columns([0.5, 0.25, 0.25])
                with col_basket: in_basket = st.checkbox("🛒 Basket", key=f"basket_{item}")
                with col_pantry: in_pantry = st.checkbox("🏠 Have It", key=f"pantry_{item}")
                with col_name:
                    display_name = f"{item} **(x{count})**" if count > 1 else f"{item}"
                    if in_basket or in_pantry: st.write(f"~~{display_name}~~")
                    else: st.write(f"- {display_name}")
            
            st.write("---")
            st.write("### 🥛 Recurring Staples")
            for staple in all_staples:
                item_name = staple[0]
                col_s_name, col_s_basket, col_s_pantry = st.columns([0.5, 0.25, 0.25])
                with col_s_basket: s_in_basket = st.checkbox("🛒 Basket", key=f"sbasket_{item_name}")
                with col_s_pantry: s_in_pantry = st.checkbox("🏠 Have It", key=f"spantry_{item_name}")
                with col_s_name:
                    display_s_name = f"**{item_name}**"
                    if s_in_basket or s_in_pantry: st.write(f"~~{display_s_name}~~")
                    else: st.write(f"- {display_s_name}")
            
            st.write("---")
            # --- NEW: CHECKOUT BUTTON ---
            if st.button("✅ Checkout & Update Inventory", type="primary"):
                items_updated = 0
                today_str = datetime.now().strftime("%Y-%m-%d")
                
                # Check which staples are in the basket using Streamlit's session state memory
                c.execute("SELECT id, name, frequency FROM staples")
                for s_id, s_name, s_freq in c.fetchall():
                    # If this staple was checked off as "In Basket"
                    if st.session_state.get(f"sbasket_{s_name}", False):
                        next_due = calculate_next_due(s_freq)
                        c.execute("UPDATE staples SET last_purchased = ?, next_due = ? WHERE id = ?", (today_str, next_due, s_id))
                        items_updated += 1
                        
                conn.commit()
                st.success(f"Checkout complete! Updated dates for {items_updated} staples. Uncheck your boxes for your next trip!")
    conn.close()

# --- TAB 3: RECURRING STAPLES ---
with tab3:
    st.write("### Manage Your Recurring Staples")
    col1, col2 = st.columns(2)
    with col1: staple_name = st.text_input("Item Name:")
    with col2: frequency = st.selectbox("How often?", ["Every 1 week", "Every 2 weeks", "Every 3 weeks", "Every 4 weeks"])
        
    if st.button("Save Staple"):
        if staple_name:
            conn = sqlite3.connect('meals.db')
            c = conn.cursor()
            next_due = calculate_next_due(frequency)
            today_str = datetime.now().strftime("%Y-%m-%d")
            c.execute("INSERT INTO staples (name, frequency, last_purchased, next_due) VALUES (?, ?, ?, ?)", (staple_name.title(), frequency, today_str, next_due))
            conn.commit()
            conn.close()
            st.success(f"Added **{staple_name.title()}**! Next due: {next_due}")
            
    st.write("---")
    st.write("### 📋 Your Current Staples")
    conn = sqlite3.connect('meals.db')
    c = conn.cursor()
    c.execute("SELECT name, frequency, next_due FROM staples")
    saved_staples = c.fetchall()
    conn.close()
    
    if len(saved_staples) > 0:
        for staple in saved_staples:
            due_text = staple[2] if staple[2] else "Not tracked yet"
            st.write(f"- **{staple[0]}** *(Buys: {staple[1]})* | **Due:** {due_text}")

# --- TAB 4 & 5 OMITTED FOR BREVITY (Keep your existing Tab 4 and Tab 5 exactly the same!) ---
with tab4:
    st.write("### 📝 Add Your Own Family Recipe")
    # (Keep your Tab 4 code here)

with tab5:
    st.write("### 🗑️ Delete a Recipe")
    # (Keep your Tab 5 code here)
        