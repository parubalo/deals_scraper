import requests
import pandas as pd
import time
import os
from datetime import datetime
import pytz

# --- 1. CONFIGURATION ---
CSV_FILENAME = "deals_history.csv"
EST = pytz.timezone('US/Eastern')
today_date = datetime.now(EST).strftime('%Y-%m-%d')

# Securely fetch credentials from GitHub Secrets
EMAIL = os.getenv("DEALSLIDE_EMAIL")
PASSWORD = os.getenv("DEALSLIDE_PWD")

def run_scraper():
    session = requests.Session()
    login_url = "https://dealslide.com/api/v1/auth/login"
    payload = {
        "email": EMAIL, 
        "password": PASSWORD, 
        "mode": "normal", 
        "interval": "month"
    }
    headers = {"Content-Type": "application/json", "Origin": "https://dealslide.com"}

    try:
        print("Logging in...")
        login_res = session.post(login_url, json=payload, headers=headers)
        login_res.raise_for_status()
        
        # Extract session cookie
        session_id = session.cookies.get_dict().get('session')
        if not session_id:
            print("Login failed: No session cookie found.")
            return
            
        cookies = {'session': session_id}
        base_url = "https://dealslide.com/api/v1/listings"
        all_listings = []

        print("Starting scrape...")
        for page in range(1, 101):  # 100 pages
            params = {'page': page, 'pageSize': '100', 'sortBy': 'createdAt', 'sortOrder': 'desc'}
            response = requests.get(base_url, params=params, cookies=cookies)
            
            if response.status_code != 200:
                break
                
            data = response.json().get('listings', [])
            if not data:
                break
                
            all_listings.extend(data)
            time.sleep(0.5)

        # Create Today's DataFrame
        df_today = pd.DataFrame(all_listings)
        if df_today.empty:
            print("No data scraped today.")
            return

        # Flatten source column
        if 'source' in df_today.columns:
            source_df = df_today['source'].apply(pd.Series).add_prefix('source_')
            df_today = pd.concat([df_today.drop('source', axis=1), source_df], axis=1)

        # --- MERGE LOGIC ---
        if os.path.exists(CSV_FILENAME):
            print("Merging with existing history...")
            df_yesterday = pd.read_csv(CSV_FILENAME)
            
            if 'date_last_seen' not in df_yesterday.columns:
                df_yesterday['date_last_seen'] = None

            # Mark items that are in CSV but NOT in current scrape
            # Using 'id' as the unique key
            missing_mask = ~df_yesterday['id'].isin(df_today['id'])
            
            # Update date_last_seen only for newly missing items
            df_yesterday.loc[missing_mask & df_yesterday['date_last_seen'].isna(), 'date_last_seen'] = today_date
            
            # Keep everything from today (Active) + items that have already been marked as Dead
            df_dead = df_yesterday[df_yesterday['date_last_seen'].notna()]
            df_final = pd.concat([df_today, df_dead], ignore_index=True).drop_duplicates(subset=['id'], keep='first')
        else:
            print("First run: Creating new history file.")
            df_today['date_last_seen'] = None
            df_final = df_today

        df_final.to_csv(CSV_FILENAME, index=False)
        print(f"File updated: {len(df_final)} total records.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_scraper()
