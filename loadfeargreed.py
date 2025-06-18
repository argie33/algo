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
    """Fetch Fear & Greed index data from CNN."""
    logging.info("Launching headless browser...")
    
    # Enhanced browser launch with better container compatibility
    launch_args = [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',  # Overcome limited resource problems
        '--disable-gpu',
        '--disable-web-security',
        '--disable-features=VizDisplayCompositor',
        '--disable-extensions',
        '--disable-plugins',
        '--disable-images',  # Faster loading
        '--disable-javascript',  # Not needed for this specific task
        '--no-first-run',
        '--no-default-browser-check',
        '--single-process',  # Reduce memory usage
    ]
    
    try:
        # Try Chrome first
        browser = await launch(
            args=launch_args,
            headless=True,
            executablePath='/usr/bin/google-chrome'  # Explicit path
        )
        logging.info("Successfully launched Chrome browser")
    except Exception as e:
        logging.warning(f"Chrome launch failed: {e}, trying Chromium...")
        try:
            # Fallback to Chromium
            browser = await launch(
                args=launch_args,
                headless=True,
                executablePath='/usr/bin/chromium-browser'  # Chromium path
            )
            logging.info("Successfully launched Chromium browser")
        except Exception as e2:
            logging.warning(f"Chromium launch failed: {e2}, trying auto-detection...")
            # Final fallback - let pyppeteer auto-detect
            browser = await launch(
                args=launch_args,
                headless=True
            )
            logging.info("Successfully launched browser (auto-detected)")
    
    try:
        page = await browser.newPage()
        await page.goto('https://production.dataviz.cnn.io/index/fearandgreed/graphdata')
        await page.waitForSelector('pre')
        
        element = await page.querySelector('pre')
        data = await page.evaluate('(element) => element.textContent', element)
        data_json = json.loads(data)
        
        data_array = data_json['fear_and_greed_historical']['data']
        return data_array
    
    finally:
        await browser.close()
        logging.info("Browser closed")

async def main():
    logging.info("Starting Fear & Greed index data load")
    
    try:
        # Get Fear & Greed data
        data = await get_fear_greed_data()
        logging.info(f"Retrieved {len(data)} Fear & Greed index records")
        
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
