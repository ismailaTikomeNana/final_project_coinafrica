# my_app.py

import streamlit as st
from bs4 import BeautifulSoup
import requests
import pandas as pd
import sqlite3
import time
import os
import io
import matplotlib.pyplot as plt
import seaborn as sns
from urllib.parse import urljoin

#config & utilities

BASE_DATA_DIR = "data"
DB_PATH = os.path.join(BASE_DATA_DIR, "coinafrica.db")

# Ensure data directory exists

os.makedirs(BASE_DATA_DIR, exist_ok=True)

st.set_page_config(
    page_title="Coinafrica Scraper & Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Some light CSS to make app cleaner (keeps to theme colors)
# 

st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(90deg, #0D1B2A 0%, #1B263B 100%);
    }
    .card {
        padding: 14px;
        border-radius: 12px;
        box-shadow: 0 4px 14px rgba(0,0,0,0.06);
        background: white;
    }
    .small {
        font-size:0.9rem;color:#333;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

#Database helpers

def get_db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn

def save_df_to_db(df: pd.DataFrame, table_name: str):
    conn = get_db_conn()
    # Use pandas to_sql with sqlite3; if table exists append
    df.to_sql(table_name, conn, if_exists="append", index=False)
    conn.commit()
    conn.close()

def create_tables_if_not_exists():
    conn = get_db_conn()
    cur = conn.cursor()
    # table for raw scraped data
    cur.execute("""
        CREATE TABLE IF NOT EXISTS raw_ads (
            category TEXT,
            name TEXT,
            price_raw TEXT,
            address TEXT,
            image_link TEXT,
            scraped_at TEXT
        );
    """)


    # table for cleaned data

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cleaned_ads (
            category TEXT,
            name TEXT,
            price INTEGER,
            address TEXT,
            image_link TEXT,
            scraped_at TEXT
        );
    """)

    # table for evaluations
    cur.execute("""
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            rating INTEGER,
            pros TEXT,
            cons TEXT,
            comment TEXT,
            submitted_at TEXT
        );
    """)
    conn.commit()
    conn.close()

create_tables_if_not_exists()

#scraping logic

def extract_items_from_page_text(html_text):
    """Return list of dicts extracted from page html using site's classes."""
    soup = BeautifulSoup(html_text, "html.parser")
    items = soup.find_all("div", class_="col s6 m4 l3")
    results = []
    for item in items:
        # name/details
        name_tag = item.find("p", class_="ad__card-description")
        name = name_tag.get_text(strip=True) if name_tag else None

        # price raw (keep raw for "uncleaned" data)
        price_tag = item.find("p", class_="ad__card-price")
        price_raw = price_tag.get_text(strip=True) if price_tag else None

        # address
        address_tag = item.find("p", class_="ad__card-location")
        address = address_tag.get_text(strip=True) if address_tag else None

        # image link (relative or absolute)
        img_tag = item.find("img", class_="ad__card-img")
        image_link = None
        if img_tag:
            image_link = img_tag.get("src") or img_tag.get("data-src")
        results.append({
            "name": name,
            "price_raw": price_raw,
            "address": address,
            "image_link": image_link
        })
    return results

def clean_price_to_int(price_raw):
    """Robust cleaning: keep only digits, return int or None."""
    if not price_raw:
        return None
    import re
    digits = re.sub(r"[^0-9]", "", price_raw)
    return int(digits) if digits else None

@st.cache_data(show_spinner=False)
def fetch_page(url):
    """Simple GET with retries."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CoinafricaScraper/1.0)"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        return None

def scrape_category(url_base, category_key, max_pages=10, sleep=1.0, progress_callback=None):
    """
    Scrape pages page=1..max_pages from url_base (which accepts ?page=N).
    Returns raw_df, cleaned_df
    """
    all_raw = []
    all_cleaned = []
    for page in range(1, max_pages+1):
        page_url = f"{url_base}?page={page}"
        html = fetch_page(page_url)
        if not html:
            break
        items = extract_items_from_page_text(html)
        if not items:
            break
        timestamp = pd.Timestamp.now().isoformat()
        for it in items:
            raw_row = {
                "category": category_key,
                "name": it["name"],
                "price_raw": it["price_raw"],
                "address": it["address"],
                "image_link": it["image_link"],
                "scraped_at": timestamp
            }
            price_clean = clean_price_to_int(it["price_raw"])
            cleaned_row = {
                "category": category_key,
                "name": it["name"],
                "price": price_clean,
                "address": it["address"],
                "image_link": it["image_link"],
                "scraped_at": timestamp
            }
            all_raw.append(raw_row)
            all_cleaned.append(cleaned_row)
        # progress callback for UI (optional)
        if progress_callback:
            progress_callback(page, max_pages)
        time.sleep(sleep)
    raw_df = pd.DataFrame(all_raw)
    cleaned_df = pd.DataFrame(all_cleaned)
    return raw_df, cleaned_df

#UI : Sidebar

st.sidebar.header("Coinafrica — Tools")
app_mode = st.sidebar.radio("Navigation", ["Home", "Scraper", "Download (uncleaned)", "Dashboard", "Evaluation Form", "DB Viewer"])

st.sidebar.markdown("---")
st.sidebar.markdown(" Tip: the CSV files are in the `data/` folder.")
st.sidebar.markdown(" Base SQLite: `data/coinafrica.db`")

#Home

if app_mode == "Home":
    st.title(" Coinafrica — Scraper & Dashboard")
    st.markdown(
        """
            This application allows you to scrape animal categories from Coinafrica,
            save the 'raw' and 'cleaned' data in SQLite, download the uncleaned CSV files,
            explore the cleaned data via an interactive dashboard, and submit an evaluation.
        """
    )
    col1, col2 = st.columns([2,1])
    with col1:
        st.subheader("Quick Actions")
        st.write("- Launch the scraper in the **Scraper** tab.")
        st.write("- Download the uncleaned CSV files in **Download (uncleaned)**.")
        st.write("- View the graphs in **Dashboard**.")
    with col2:
        st.image("images/poulets.avif" if os.path.exists("images/poulets.avif") else "https://upload.wikimedia.org/wikipedia/commons/6/6e/Golde33443.jpg", width=250)


#Scraper page

elif app_mode == "Scraper":
    st.header(" Scraper — Coinafrica (animals)")
    st.markdown("Configure the category, the number of pages and start scraping.")

    # default urls (change if needed)
    default_urls = {
        "dogs": "https://sn.coinafrique.com/categorie/chiens",
        "sheeps": "https://sn.coinafrique.com/categorie/moutons",
        "chickens-rabbits-pigeons": "https://sn.coinafrique.com/categorie/poules-lapins-et-pigeons",
        "other-animals": "https://sn.coinafrique.com/categorie/autres-animaux"
    }

    categories = list(default_urls.keys())

    selected_category = st.selectbox("Select category", categories)
    pages = st.slider("Maximum number of pages to scrape", min_value=1, max_value=30, value=6)
    sleep_time = st.number_input("Time between requests (recommended 0.8–2.0)", value=1.0, step=0.1)

    url_input = st.text_input("Base URL (editable)", value=default_urls[selected_category])
    st.write("URL used:", url_input)

    start_button = st.button("Start scraping")

    if start_button:
        status_area = st.empty()
        prog = st.progress(0)
        status_area.info("Scraping has begun...")
        def prog_cb(page, maxp):
            prog.progress(int(page/maxp * 100))

        raw_df, cleaned_df = scrape_category(url_input, selected_category, max_pages=pages, sleep=sleep_time, progress_callback=prog_cb)

        if not raw_df.empty:
            # Save CSVs
            raw_csv_path = os.path.join(BASE_DATA_DIR, f"{selected_category}_raw.csv")
            cleaned_csv_path = os.path.join(BASE_DATA_DIR, f"{selected_category}_cleaned.csv")
            raw_df.to_csv(raw_csv_path, index=False)
            cleaned_df.to_csv(cleaned_csv_path, index=False)

            # Save to DB
            # For reliability, write rows directly to DB tables
            conn = get_db_conn()
            raw_df.to_sql("raw_ads", conn, if_exists="append", index=False)
            cleaned_df.to_sql("cleaned_ads", conn, if_exists="append", index=False)
            conn.close()

            status_area.success(f"Scraping terminé — {len(raw_df)} annonces récupérées.")
            st.markdown(f"- CSV raw: `{raw_csv_path}` — CSV cleaned: `{cleaned_csv_path}`")
            st.dataframe(cleaned_df.head(30))
        else:
            status_area.warning("Aucune annonce récupérée. Vérifie l'URL ou paramètres.")

#Download

elif app_mode == "Download (uncleaned)":
    st.header(" Download the uncleaned data")
    st.markdown("Choose a raw file (in the `data/` folder) and then download it.")

    raw_files = [f for f in os.listdir(BASE_DATA_DIR) if f.endswith("_raw.csv") or f.endswith(".csv")]
    if not raw_files:
        st.warning("No CSV files were found in the data/ folder.")
    else:
        file_choice = st.selectbox("Raw file available", raw_files)
        if file_choice:
            path = os.path.join(BASE_DATA_DIR, file_choice)
            df = pd.read_csv(path)
            st.write(f"Fichier: `{file_choice}` — {len(df)} lignes")
            st.dataframe(df.head(50))
            # prepare download
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", data=csv_bytes, file_name=file_choice, mime="text/csv")

#Dashboard

elif app_mode == "Dashboard":
    st.header(" Dashboard — Cleaned Data")
    st.markdown("Visualizes and filters cleaned data (from the SQLite database).")

    # load cleaned data from DB
    conn = get_db_conn()
    try:
        cleaned_df = pd.read_sql_query("SELECT * FROM cleaned_ads", conn)
    except Exception:
        cleaned_df = pd.DataFrame()
    conn.close()

    if cleaned_df.empty:
        st.info("No data has been cleaned in the database. Run the scraper first.")
    else:
        # basic preprocessing
        
        cleaned_df["price"] = pd.to_numeric(cleaned_df["price"], errors="coerce")

        MAX_ALLOWED = 10_000_000  # 10 million FCFA – adjust if needed
        cleaned_df = cleaned_df[(cleaned_df["price"] > 0) & (cleaned_df["price"] <= MAX_ALLOWED)]

        cleaned_df["category"] = cleaned_df["category"].astype(str)


        # Filters
        left, right = st.columns([1,3])
        with left:
            cat_sel = st.multiselect("Category", options=cleaned_df["category"].unique(), default=cleaned_df["category"].unique())
            min_price, max_price = int(cleaned_df["price"].min() or 0), int(cleaned_df["price"].max() or 0)
            price_range = st.slider("Price range", min_value=min_price, max_value=max_price, value=(min_price, max_price))
            addr_search = st.text_input("Search address (substring)")

        # Apply filters
        df_f = cleaned_df[cleaned_df["category"].isin(cat_sel)]
        df_f = df_f[df_f["price"].between(price_range[0], price_range[1], inclusive="both")]
        if addr_search:
            df_f = df_f[df_f["address"].str.contains(addr_search, case=False, na=False)]

        # KPIs
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Ads (after filters)", len(df_f))
        with col2:
            st.metric("Average price", f"{0 if df_f['price'].mean() != df_f['price'].mean() else int(df_f['price'].mean()):,} FCFA")
        with col3:
            st.metric("Categories", df_f['category'].nunique())

        # Charts
        st.subheader("Price distribution")
        fig1 = plt.figure(figsize=(8,3.5))
        sns.histplot(df_f['price'].dropna(), bins=30, kde=False)
        plt.xlabel("Price (FCFA)")
        st.pyplot(fig1)

        st.subheader("Top addresses (more listings)")
        top_addr = df_f['address'].value_counts().head(10)
        fig2 = plt.figure(figsize=(8,3.5))
        sns.barplot(x=top_addr.values, y=top_addr.index)
        plt.xlabel("Number of ads")
        st.pyplot(fig2)

        st.subheader("List of announcements (excerpt)")
        st.dataframe(df_f.sort_values("price", ascending=False).reset_index(drop=True).head(200), use_container_width=True)

        # allow export of filtered view
        csv_bytes = df_f.to_csv(index=False).encode("utf-8")
        st.download_button("Export filtered views (CSV)", data=csv_bytes, file_name="filtered_cleaned_ads.csv", mime="text/csv")

#Evaluation form

elif app_mode == "Evaluation Form":
    st.header(" Application evaluation")

    st.markdown(
        """
            ### You can evaluate the app using one of the following two methods:

            - **Google Forms** → your responses will be automatically saved to Google Sheets
            - **KoboCollect / KoboToolbox** → your responses will be saved to your Kobo account

            Both forms contain **exactly the same questions**, as required.
        """
    )

    st.markdown("---")

    # Choix entre Google Forms et KoboCollect
    choix = st.radio(
        "Choose your assessment method:",
        ["Google Forms", "KoboCollect"],
        index=0
    )

    st.markdown("---")

    #Google forms option

    if choix == "Google Forms":

        st.subheader(" Evaluation via Google Forms")

        st.markdown(
            """
            Click the button below to open the form:

            **All sections are included:**

            - Reviewer Information
            - Interface & First Impressions
            - Features
            - Issues Encountered
            - Overall Satisfaction
            - Suggestions for Improvement
            """
        )

        GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScWokECHnNApiKcAvBluCZ0-MgmsvgSajkH5Pp20ZV7J1iIHg/viewform?usp=header"

        st.markdown(
            f"""
            <a href="{GOOGLE_FORM_URL}" target="_blank" style="
                background-color:#1a73e8;
                padding:14px 26px;
                color:white;
                border-radius:8px;
                text-decoration:none;
                font-size:17px;">
                Open the Google Form
            </a>
            """,
            unsafe_allow_html=True
        )

        st.info("The responses will be automatically saved in your associated Google Sheet.")

            #Kobocollect option
    
    elif choix == "KoboCollect":

        st.subheader(" Review via KoboCollect")

        st.markdown(
            """
            Click the button below to open your Kobo form:  
            """
        )

        KOBO_FORM_URL = "https://ee.kobotoolbox.org/x/TCMV4u8N"

        st.markdown(
            f"""
            <a href="{KOBO_FORM_URL}" target="_blank" style="
                background-color:#009670;
                padding:14px 26px;
                color:white;
                border-radius:8px;
                text-decoration:none;
                font-size:17px;">
                Open the KoboCollect form
            </a>
            """,
            unsafe_allow_html=True
        )

        st.info("The answers will be saved in your KoboCollect dashboard.")


#db viewer

elif app_mode == "DB Viewer":
    st.header(" Database Viewer")
    st.markdown("Displays the contents of SQLite tables.")

    conn = get_db_conn()
    try:
        raw_df = pd.read_sql_query("SELECT * FROM raw_ads ORDER BY scraped_at DESC LIMIT 500", conn)
    except Exception:
        raw_df = pd.DataFrame()
    try:
        cleaned_df = pd.read_sql_query("SELECT * FROM cleaned_ads ORDER BY scraped_at DESC LIMIT 500", conn)
    except Exception:
        cleaned_df = pd.DataFrame()
    conn.close()

    st.subheader("Raw (extrait)")
    st.dataframe(raw_df.head(200))
    st.subheader("Cleaned (extrait)")
    st.dataframe(cleaned_df.head(200))

    if not raw_df.empty:
        st.download_button("Export raw (CSV)", data=raw_df.to_csv(index=False).encode("utf-8"), file_name="db_raw_export.csv", mime="text/csv")
    if not cleaned_df.empty:
        st.download_button("Exporter cleaned (CSV)", data=cleaned_df.to_csv(index=False).encode("utf-8"), file_name="db_cleaned_export.csv", mime="text/csv")