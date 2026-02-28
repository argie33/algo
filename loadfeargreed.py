#!/usr/bin/env python3
"""
Fear & Greed Index Loader - Market Sentiment Indicators

DEPLOYMENT MODES:
  • AWS Production: Uses DB_SECRET_ARN environment variable (Lambda/ECS)
    └─ Fetches DB credentials from AWS Secrets Manager
    └─ Fetches CNN Fear & Greed data via HTTPS
    └─ Writes to PostgreSQL RDS database

  • Local Development: Uses DB_HOST/DB_USER/DB_PASSWORD env vars
    └─ Falls back if DB_SECRET_ARN not set
    └─ Same data fetching & processing logic
    └─ Perfect for testing without AWS infrastructure

DATA SOURCE:
  • CNN Fear & Greed Index (https://production.dataviz.cnn.io/index/fearandgreed/graphdata)
  • Browser-based scraping using pyppeteer (headless Chrome)
  • Extracts: date, index_value (0-100), rating (Fear/Greed)

TABLES:
  • fear_greed: Stores daily sentiment index

OUTPUTS:
  • market page: Market sentiment indicators

Version: v5.3
Last Updated: 2026-01-28 - Data loss fix deployed and ready for ECS execution
FIXED: Removed DROP TABLE vulnerability - data now safely preserved on crash
"""
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
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
MAX_RETRIES = 5
RETRY_DELAY = 5.0  # seconds between browser retries
BACKOFF_MULTIPLIER = 2.0  # exponential backoff multiplier

# -------------------------------
# Fear & Greed columns
# -------------------------------
FEAR_GREED_COLUMNS = ["date", "fear_greed_value"]
COL_LIST = ", ".join(FEAR_GREED_COLUMNS)

# -------------------------------
# CNN Fear & Greed API URL
# -------------------------------
FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    """Get database configuration - works in AWS and locally.

    Priority:
    1. AWS Secrets Manager (if DB_SECRET_ARN is set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
    """
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    # Try AWS Secrets Manager first
    if db_secret_arn and aws_region:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logging.info(f"Using AWS Secrets Manager for database config")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.warning(f"AWS Secrets Manager failed ({e.__class__.__name__}): {str(e)[:100]}. Falling back to environment variables.")

    # Fall back to environment variables
    logging.info("Using environment variables for database config")
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }


def timestamptodatestr(ts):
    """Convert UNIX timestamp (milliseconds) to 'YYYY-MM-DD' date string."""
    d = datetime.fromtimestamp(ts / 1000)
    return d.strftime("%Y-%m-%d")

# -------------------------------
# Fetch Fear & Greed data via HTTP
# -------------------------------
async def get_fear_greed_data():
    """
    Fetches the CNN Fear & Greed index data via HTTP.
    Returns a list of dictionaries with date, index_value, and rating.
    """
    logging.info(f"🔄 Starting Fear & Greed data fetch from: {FEAR_GREED_URL}")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logging.info(f"🌐 HTTP attempt {attempt}/{MAX_RETRIES}")

            # Create a session with retries
            session = requests.Session()
            retry = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=(500, 502, 503, 504),
                allowed_methods=["GET"]
            )
            adapter = HTTPAdapter(max_retries=retry)
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            # Set headers to avoid being blocked
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            # Fetch the data
            logging.info(f"📡 Fetching JSON from CNN API...")
            response = session.get(FEAR_GREED_URL, headers=headers, timeout=30)
            response.raise_for_status()

            data_json = response.json()

            # Extract the historical data array
            data_array = data_json['fear_and_greed_historical']['data']

            logging.info(f"✅ Successfully fetched {len(data_array)} Fear & Greed records")
            session.close()

            return data_array

        except Exception as e:
            logging.error(f"❌ HTTP attempt {attempt} failed: {e}")
            logging.error(f"❌ Error type: {type(e).__name__}")
            import traceback
            logging.error(f"❌ Stack trace: {traceback.format_exc()}")

            if attempt < MAX_RETRIES:
                retry_delay = RETRY_DELAY * (BACKOFF_MULTIPLIER ** (attempt - 1))
                logging.info(f"⏳ Retrying in {retry_delay:.1f} seconds... (attempt {attempt}/{MAX_RETRIES})")
                await asyncio.sleep(retry_delay)  # Use async sleep
            else:
                logging.error(f"❌ CRITICAL: Failed to fetch Fear & Greed data after {MAX_RETRIES} attempts")
                logging.error(f"❌ Final error: {e}")
                raise Exception(f"Failed to fetch Fear & Greed data after {MAX_RETRIES} attempts: {e}")

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
                fear_greed_value = int(item['y']) if item['y'] is not None else None

                # Keep the most recent data for each date (if duplicates exist)
                rows_dict[dt] = [dt, fear_greed_value]
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
            sql = f"INSERT INTO fear_greed_index ({COL_LIST}) VALUES %s ON CONFLICT (date) DO UPDATE SET fear_greed_value = EXCLUDED.fear_greed_value, created_at = CURRENT_TIMESTAMP"
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
    )
    logging.info("✅ Database connection established")
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Ensure fear_greed_index table exists (never drop - avoid data loss)
    logging.info("Ensuring fear_greed_index table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fear_greed_index (
            id                  SERIAL PRIMARY KEY,
            date                DATE         NOT NULL UNIQUE,
            fear_greed_value    INTEGER,
            created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        # Handle event loop properly for Python 3.10+
        import platform
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(main())
        finally:
            # Don't close the loop if it's already closed by pyppeteer
            try:
                loop.close()
            except RuntimeError:
                pass  # Loop already closed by pyppeteer
    except Exception as e:
        logging.error(f"❌ CRITICAL ERROR in Fear & Greed loader: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {traceback.format_exc()}")
        sys.exit(1) 