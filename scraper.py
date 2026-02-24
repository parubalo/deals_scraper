import requests
import pandas as pd
import time
import os
from datetime import datetime
import pytz

# --- CONFIGURATION ---
CSV_FILENAME = "deals_history.csv"
EST = pytz.timezone('US/Eastern')
today_date = datetime.now(EST).strftime('%Y-%m-%d')

# Fetch secrets from GitHub environment variables
EMAIL = os.getenv("DEALSLIDE_EMAIL")
PASSWORD = os.getenv("DEALSLIDE_PWD")

def main():
    if not EMAIL or not PASSWORD:
        print("ERROR: Missing credentials. Ensure DEALSLIDE_EMAIL and DEALSLIDE_PWD are set in GitHub Secrets.")
        return

    session = requests.Session()
    login_url = "https://dealslide.com/api/v1/auth/login"
    payload = {"email": EMAIL, "password": PASSWORD, "mode": "normal", "interval": "month"}
    headers = {"Content-Type": "application/json", "Origin": "https://dealslide.com"}

    try:
        # 1. Login
        print("Logging in to DealSlide...")
        login_res = session.post(login_url, json=payload, headers=headers)
        login_res.raise_for_status()
        
        session_id = session.cookies.get_dict().get('session')
        if not session_id:
            print("Login failed: Session cookie not found.")
            return
        
        cookies = {'session': session_id}

        # 2. Scrape Data
        base_url = "https://dealslide.com/api/v1/listings"
        all_listings = []
        print("Starting 100-page scrape...")
        
        for page in range(1, 101):
            params = {
                'page': page, 
                'pageSize': '100', 
                'sortBy': 'createdAt', 
                'sortOrder': 'desc'
            }
            res = requests.get(base_url, params=params, cookies=cookies)
            
            if res.status_code != 200:
                print(f"Stopped at page {page} (Status: {res.status_code})")
                break
            
            data = res.json().get('listings', [])
            if not data:
                print(f"No more data at page {page}.")
                break
            
            all_listings.extend(data)
            time.sleep(0.4) # Avoid rate limiting
            if page % 10 == 0:
                print(f"Processed {page} pages...")

        df_today = pd.DataFrame(all_listings)
        
        if df_today.empty:
            print("No listings captured today. Ending run.")
            return

        # Flatten 'source' metadata if present
        if 'source' in df_today.columns:
            source_df = df_today['source'].apply(lambda x: x if isinstance(x, dict) else {}).apply(pd.Series).add_prefix('source_')
            df_today = pd.concat([df_today.drop('source', axis=1), source_df], axis=1)

        # 3. Merging Logic
        if os.path.exists(CSV_FILENAME):
            print(f"Comparing {len(df_today)} new items with existing history...")
            df_hist = pd.read_csv(CSV_FILENAME)
            
            if 'date_last_seen' not in df_hist.columns:
                df_hist['date_last_seen'] = None

            # Find items in history that are NOT in today's scrape
            # Assumes 'id' is the unique identifier
            is_missing = ~df_hist['id'].isin(df_today['id'])
            
            # Update date_last_seen only if it hasn't been set before
            df_hist.loc[is_missing & df_hist['date_last_seen'].isna(), 'date_last_seen'] = today_date
            
            # Combine today's active items with items already marked as dead
            df_dead = df_hist[df_hist['date_last_seen'].notna()]
            df_final = pd.concat([df_today, df_dead], ignore_index=True)
            
            # Ensure no duplicates (keeps the newest active version)
            df_final = df_final.drop_duplicates(subset=['id'], keep='first')
        else:
            print("No existing CSV found. Creating initial file.")
            df_today['date_last_seen'] = None
            df_final = df_today

        # 4. Save to CSV
        df_final.to_csv(CSV_FILENAME, index=False)
        print(f"Success! Total rows in {CSV_FILENAME}: {len(df_final)}")

    except Exception as e:
        print(f"Critical error during execution: {e}")

if __name__ == "__main__":
    main()
