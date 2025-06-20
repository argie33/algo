#!/usr/bin/env python3 
import sys
import logging
import json
import os
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import boto3
import asyncio
import aiohttp

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadfeargreed.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

def timestamp_to_date(ts):
    """Convert UNIX timestamp (milliseconds) to 'YYYY-MM-DD' date string."""
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")

async def get_fear_greed_data():
    """Fetch Fear & Greed index data from CNN using a browser automation fallback if HTTP fails."""
    url = 'https://production.dataviz.cnn.io/index/fearandgreed/graphdata'
    logging.info(f"Fetching Fear & Greed data directly from {url} ...")
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Referer': 'https://edition.cnn.com/',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
            }
            async with session.get(url, headers=headers, timeout=30) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status} error fetching data")
                data_json = await resp.json()
        if 'fear_and_greed_historical' not in data_json:
            raise Exception("Expected data structure not found in response")
        data_array = data_json['fear_and_greed_historical']['data']
        logging.info(f"Parsed {len(data_array)} historical data points")
        return data_array
    except Exception as e:
        logging.error(f"Error fetching Fear & Greed data via HTTP: {str(e)}")
        # Fallback: try browser automation (undetected-chromedriver)
        try:
            import undetected_chromedriver as uc
            from selenium.webdriver.common.by import By
            import time
            import json as pyjson
            logging.info("Trying browser automation fallback with undetected-chromedriver...")
            options = uc.ChromeOptions()
            options.headless = True
            driver = uc.Chrome(options=options)
            driver.get(url)
            time.sleep(2)
            pre = driver.find_element(By.TAG_NAME, "pre")
            data = pre.text
            driver.quit()
            data_json = pyjson.loads(data)
            if 'fear_and_greed_historical' not in data_json:
                raise Exception("Expected data structure not found in browser response")
            data_array = data_json['fear_and_greed_historical']['data']
            logging.info(f"Parsed {len(data_array)} historical data points (browser fallback)")
            return data_array
        except Exception as e2:
            logging.error(f"Browser automation fallback also failed: {str(e2)}")
            raise Exception(f"Both HTTP and browser fallback failed: {e2}")

async def main():
    logging.info("Starting Fear & Greed index data load")
    
    try:
        # Get Fear & Greed data
        data = await get_fear_greed_data()
        logging.info(f"Retrieved {len(data)} Fear & Greed index records")
        
        # Deduplicate by date (keep last occurrence for each date)
        deduped = {}
        for item in data:
            date_str = timestamp_to_date(item['x'])
            deduped[date_str] = item  # overwrite, so last wins
        data = list(deduped.values())
        logging.info(f"Deduplicated to {len(data)} unique date records")
        
        # Connect to database
        cfg = get_db_config()
        conn = psycopg2.connect(**cfg)
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Recreate table
            logging.info("Recreating fear_greed_index table...")
            cur.execute("DROP TABLE IF EXISTS fear_greed_index CASCADE;")
            cur.execute("""
                CREATE TABLE fear_greed_index (
                    date DATE PRIMARY KEY,
                    index_value DOUBLE PRECISION,
                    rating VARCHAR(50),
                    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX idx_fear_greed_date ON fear_greed_index(date);
            """)
            
            # Insert data
            insert_data = [
                (
                    timestamp_to_date(item['x']),
                    item['y'],
                    item['rating'],
                    datetime.now()
                )
                for item in data
            ]
            
            execute_values(
                cur,
                """
                INSERT INTO fear_greed_index (
                    date, index_value, rating, fetched_at
                ) VALUES %s
                """,
                insert_data,
                page_size=1000
            )
            
            # Update last_updated table
            cur.execute("""
                INSERT INTO last_updated (script_name, last_run)
                VALUES (%s, NOW())
                ON CONFLICT (script_name) DO UPDATE
                    SET last_run = EXCLUDED.last_run;
            """, (SCRIPT_NAME,))
            
            conn.commit()
            logging.info(f"Successfully loaded {len(data)} Fear & Greed index records")
            
        except Exception as e:
            conn.rollback()
            raise e
        
        finally:
            cur.close()
            conn.close()
            
    except Exception as e:
        logging.error(f"Failed to load Fear & Greed index data: {str(e)}")
        sys.exit(1)
    
    logging.info("Fear & Greed index data load completed successfully")

if __name__ == "__main__":
    asyncio.run(main())
