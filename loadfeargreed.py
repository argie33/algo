#!/usr/bin/env python3
# Fear & Greed Index loader - market sentiment indicators  
# Trigger deploy-app-stocks workflow - loadfeargreed update v5.4 - Data population for dashboard
import sys
import time
import logging
import json
import os
import gc
import resource
import math
import asyncio

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime

import boto3
import pandas as pd
from pyppeteer import launch

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
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Retry settings
# -------------------------------
MAX_BROWSER_RETRIES = 5
RETRY_DELAY = 5.0  # seconds between browser retries
BACKOFF_MULTIPLIER = 2.0  # exponential backoff multiplier

# -------------------------------
# Fear & Greed columns
# -------------------------------
FEAR_GREED_COLUMNS = ["date", "index_value", "rating"]
COL_LIST = ", ".join(FEAR_GREED_COLUMNS)

# -------------------------------
# CNN Fear & Greed API URL
# -------------------------------
FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host":   sec["host"],
        "port":   int(sec.get("port", 5432)),
        "user":   sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

# -------------------------------
# Utility functions
# -------------------------------
def timestamptodatestr(ts):
    """Convert UNIX timestamp (milliseconds) to 'YYYY-MM-DD' date string."""
    d = datetime.fromtimestamp(ts / 1000)
    return d.strftime("%Y-%m-%d")

# -------------------------------
# Scrape Fear & Greed data
# -------------------------------
async def get_fear_greed_data():
    """
    Scrapes the CNN Fear & Greed index data using a headless browser.
    Returns a list of dictionaries with date, index_value, and rating.
    """
    logging.info(f"🔄 Starting Fear & Greed data scraping from: {FEAR_GREED_URL}")
    
    browser = None
    for attempt in range(1, MAX_BROWSER_RETRIES + 1):
        try:
            logging.info(f"🌐 Browser attempt {attempt}/{MAX_BROWSER_RETRIES}")
            
            # Launch browser with comprehensive arguments for containerized environment
            browser_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--no-zygote",
                "--disable-gpu",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--memory-pressure-off",
                "--max_old_space_size=4096",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-sync",
                "--disable-translate",
                "--hide-scrollbars",
                "--metrics-recording-only",
                "--mute-audio",
                "--no-default-browser-check",
                "--no-pings",
                "--password-store=basic",
                "--use-mock-keychain",
                "--disable-blink-features=AutomationControlled"
            ]
            
            logging.info(f"🚀 Launching browser with {len(browser_args)} arguments")
            browser = await launch(
                executablePath='/usr/bin/chromium',
                args=browser_args,
                headless=True,
                timeout=60000,  # 60 second timeout
                ignoreHTTPSErrors=True,
                defaultViewport={'width': 1280, 'height': 720}
            )
            
            page = await browser.newPage()
            
            # Set user agent to avoid detection
            await page.setUserAgent(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            
            # Navigate to the Fear & Greed API endpoint
            await page.goto(FEAR_GREED_URL, waitUntil='networkidle0', timeout=30000)
            
            # Wait for the data to load
            selector = 'pre'
            await page.waitForSelector(selector, timeout=30000)
            
            # Extract the JSON data
            element = await page.querySelector(selector)
            data = await page.evaluate('(element) => element.textContent', element)
            data_json = json.loads(data)
            
            # Extract the historical data array
            data_array = data_json['fear_and_greed_historical']['data']
            
            logging.info(f"Successfully scraped {len(data_array)} Fear & Greed records")
            
            # Close browser
            await browser.close()
            browser = None
            
            return data_array
            
        except Exception as e:
            logging.error(f"❌ Browser attempt {attempt} failed: {e}")
            logging.error(f"❌ Error type: {type(e).__name__}")
            import traceback
            logging.error(f"❌ Stack trace: {traceback.format_exc()}")
            if browser:
                try:
                    await browser.close()
                    logging.info("🔄 Browser closed successfully")
                except Exception as close_error:
                    logging.error(f"❌ Failed to close browser: {close_error}")
                browser = None
            
            if attempt < MAX_BROWSER_RETRIES:
                retry_delay = RETRY_DELAY * (BACKOFF_MULTIPLIER ** (attempt - 1))
                logging.info(f"⏳ Retrying in {retry_delay:.1f} seconds... (attempt {attempt}/{MAX_BROWSER_RETRIES})")
                await asyncio.sleep(retry_delay)  # Use async sleep
            else:
                logging.error(f"❌ CRITICAL: Failed to scrape Fear & Greed data after {MAX_BROWSER_RETRIES} attempts")
                logging.error(f"❌ Final error: {e}")
                raise Exception(f"Failed to scrape Fear & Greed data after {MAX_BROWSER_RETRIES} attempts: {e}")

# -------------------------------
# Main loader with batched inserts
# -------------------------------
async def load_fear_greed_data(cur, conn):
    logging.info("Loading Fear & Greed data")
    
    try:
        # Scrape the Fear & Greed data
        data_array = await get_fear_greed_data()
        
        if not data_array:
            logging.warning("No Fear & Greed data scraped")
            return 0, 0, []
        
        # Convert data to list of tuples for batch insert and deduplicate by date
        rows_dict = {}  # Use dict to deduplicate by date
        for item in data_array:
            try:
                dt = timestamptodatestr(item['x'])
                index_value = float(item['y']) if item['y'] is not None else None
                rating = str(item['rating']) if item['rating'] else None
                
                # Keep the most recent data for each date (if duplicates exist)
                rows_dict[dt] = [dt, index_value, rating]
            except Exception as e:
                logging.warning(f"Failed to process item {item}: {e}")
                continue
        
        # Convert back to list
        rows = list(rows_dict.values())
        
        if not rows:
            logging.warning("No valid rows after processing")
            return 0, 0, []
        
        logging.info(f"Processing {len(rows)} unique Fear & Greed records (deduplicated from {len(data_array)} total)")
        
        # Batch insert the data with proper error handling
        try:
            sql = f"INSERT INTO fear_greed_index ({COL_LIST}) VALUES %s ON CONFLICT (date) DO UPDATE SET index_value = EXCLUDED.index_value, rating = EXCLUDED.rating, fetched_at = CURRENT_TIMESTAMP"
            execute_values(cur, sql, rows)
            conn.commit()
            
            inserted = len(rows)
            logging.info(f"Successfully inserted {inserted} Fear & Greed records")
            
            return len(data_array), inserted, []
            
        except Exception as insert_error:
            logging.error(f"Database insert error: {insert_error}")
            conn.rollback()  # Rollback the failed transaction
            return 0, 0, [str(insert_error)]
        
    except Exception as e:
        logging.error(f"Error loading Fear & Greed data: {e}")
        return 0, 0, [str(e)]

# -------------------------------
# Entrypoint
# -------------------------------
async def main():
    logging.info(f"🚀 Starting {SCRIPT_NAME} execution")
    log_mem("startup")

    # Connect to DB
    logging.info("🔌 Loading database configuration...")
    cfg = get_db_config()
    logging.info(f"🔌 Connecting to database: {cfg['host']}:{cfg['port']}/{cfg['dbname']}")
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    ,
            sslmode="require"
    )
    logging.info("✅ Database connection established")
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Recreate fear_greed_index table
    logging.info("Recreating fear_greed_index table...")
    cur.execute("DROP TABLE IF EXISTS fear_greed_index;")
    cur.execute("""
        CREATE TABLE fear_greed_index (
            id          SERIAL PRIMARY KEY,
            date        DATE         NOT NULL UNIQUE,
            index_value DOUBLE PRECISION,
            rating      VARCHAR(50),
            fetched_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Ensure last_updated table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS last_updated (
            script_name VARCHAR(100) PRIMARY KEY,
            last_run    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()

    # Load Fear & Greed data
    total, inserted, failed = await load_fear_greed_data(cur, conn)

    # Record last run
    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Fear & Greed — total: {total}, inserted: {inserted}, failed: {len(failed)}")

    cur.close()
    conn.close()
    logging.info("All done.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"❌ CRITICAL ERROR in Fear & Greed loader: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {traceback.format_exc()}")
        sys.exit(1) 