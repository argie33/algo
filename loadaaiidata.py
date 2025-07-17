#!/usr/bin/env python3
# AAII data loader - sentiment and allocation data
# Trigger deploy-app-stocks workflow - loadaaiidata update v5.6 - ARM64 architecture test
import sys
import time
import logging
import json
import os
import gc
import resource
import math

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime

import boto3
import pandas as pd
import requests
from io import BytesIO

# -------------------------------
# Script metadata & logging setup   
# -------------------------------
SCRIPT_NAME = "loadaaiidata.py"
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
MAX_DOWNLOAD_RETRIES = 5  
RETRY_DELAY = 3.0  # seconds between download retries
BACKOFF_MULTIPLIER = 2.0  # exponential backoff multiplier

# -------------------------------
# AAII Sentiment columns
# -------------------------------
SENTIMENT_COLUMNS = ["date", "bullish", "neutral", "bearish"]
COL_LIST = ", ".join(SENTIMENT_COLUMNS)

# -------------------------------
# Direct URL to the AAII sentiment survey Excel file
# -------------------------------
AAII_EXCEL_URL = "https://www.aaii.com/files/surveys/sentiment.xls"

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
# Download AAII sentiment data
# -------------------------------
def get_aaii_sentiment_data():
    """
    Downloads the AAII sentiment survey Excel file and extracts historical data.
    Returns a DataFrame with the columns: Date, Bullish, Neutral, and Bearish.
    """
    logging.info(f"🔄 Starting AAII sentiment data download from: {AAII_EXCEL_URL}")
    
    # Custom headers to mimic a browser request for an Excel file
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/115.0.0.0 Safari/537.36"),
        "Referer": "https://www.aaii.com/",
        "Accept": "application/vnd.ms-excel, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
        try:
            logging.info(f"Download attempt {attempt}/{MAX_DOWNLOAD_RETRIES}")
            response = requests.get(AAII_EXCEL_URL, headers=headers, allow_redirects=True, timeout=30)
            response.raise_for_status()
            
            # Check the content-type header for debugging
            content_type = response.headers.get("Content-Type", "")
            content_length = response.headers.get("Content-Length", "unknown")
            logging.info(f"✅ Response received - Content-Type: {content_type}, Content-Length: {content_length}")
            
            # If the response looks like HTML rather than an Excel file, raise an error
            if "html" in content_type.lower():
                logging.error(f"❌ Server returned HTML instead of Excel file")
                logging.error(f"❌ Response preview: {response.content[:500]}")
                raise ValueError("Server returned HTML instead of an Excel file. Check the URL or headers.")
            
            # Validate file size
            if len(response.content) < 1000:  # Excel files should be larger than 1KB
                logging.error(f"❌ Response too small ({len(response.content)} bytes) - likely not an Excel file")
                raise ValueError(f"Response too small ({len(response.content)} bytes) - likely not an Excel file")
            
            # Load the Excel file from the downloaded bytes using xlrd
            excel_data = BytesIO(response.content)
            logging.info("📊 Attempting to parse Excel file...")
            df = pd.read_excel(excel_data, skiprows=3, engine="xlrd")
            
            # Remove extra whitespace from column names
            df.columns = df.columns.str.strip()
            
            # We need at least these columns; adjust if necessary
            required_cols = ["Date", "Bullish", "Neutral", "Bearish"]
            logging.info(f"📋 Found columns: {df.columns.tolist()}")
            
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                logging.error(f"❌ Missing required columns: {missing_cols}")
                logging.error(f"❌ Available columns: {df.columns.tolist()}")
                raise ValueError(f"Expected columns {missing_cols} not found. Found columns: {df.columns.tolist()}")
            
            # Select only the required columns
            df = df[required_cols]
            logging.info(f"✅ Selected {len(df)} rows with required columns")
            
            # Clean percentage columns: remove "%" and convert to numeric
            for col in ["Bullish", "Neutral", "Bearish"]:
                df[col] = df[col].astype(str).str.replace("%", "", regex=False).str.strip()
                df[col] = pd.to_numeric(df[col], errors="coerce")
            
            # Convert the Date column to datetime and then to string in YYYY-MM-DD format
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"])  # Drop rows where date conversion failed
            df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
            
            # Sort by Date (oldest first) and reset index
            df.sort_values("Date", inplace=True)
            df.reset_index(drop=True, inplace=True)
            
            logging.info(f"Successfully downloaded AAII sentiment data: {len(df)} records")
            return df
            
        except Exception as e:
            logging.error(f"❌ Download attempt {attempt} failed: {e}")
            logging.error(f"❌ Error type: {type(e).__name__}")
            import traceback
            logging.error(f"❌ Stack trace: {traceback.format_exc()}")
            if attempt < MAX_DOWNLOAD_RETRIES:
                retry_delay = RETRY_DELAY * (BACKOFF_MULTIPLIER ** (attempt - 1))
                logging.info(f"⏳ Retrying in {retry_delay:.1f} seconds... (attempt {attempt}/{MAX_DOWNLOAD_RETRIES})")
                time.sleep(retry_delay)
            else:
                logging.error(f"❌ CRITICAL: Failed to download AAII sentiment data after {MAX_DOWNLOAD_RETRIES} attempts")
                logging.error(f"❌ Final error: {e}")
                raise Exception(f"Failed to download AAII sentiment data after {MAX_DOWNLOAD_RETRIES} attempts: {e}")

# -------------------------------
# Main loader with batched inserts
# -------------------------------
def load_sentiment_data(cur, conn):
    logging.info("Loading AAII sentiment data")
    
    try:
        # Download the sentiment data
        df = get_aaii_sentiment_data()
        
        if df.empty:
            logging.warning("No sentiment data downloaded")
            return 0, 0, []
        
        # Convert DataFrame to list of tuples for batch insert
        rows = []
        for _, row in df.iterrows():
            rows.append([
                row["Date"],
                None if pd.isna(row["Bullish"]) else float(row["Bullish"]),
                None if pd.isna(row["Neutral"]) else float(row["Neutral"]),
                None if pd.isna(row["Bearish"]) else float(row["Bearish"])
            ])
        
        if not rows:
            logging.warning("No valid rows after processing")
            return 0, 0, []
        
        # Batch insert the data
        sql = f"INSERT INTO aaii_sentiment ({COL_LIST}) VALUES %s"
        execute_values(cur, sql, rows)
        conn.commit()
        
        inserted = len(rows)
        logging.info(f"Successfully inserted {inserted} sentiment records")
        
        return len(df), inserted, []
        
    except Exception as e:
        logging.error(f"Error loading sentiment data: {e}")
        return 0, 0, [str(e)]

# -------------------------------
# Entrypoint
# -------------------------------
if __name__ == "__main__":
    try:
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

        # Recreate aaii_sentiment table
        logging.info("Recreating aaii_sentiment table...")
        cur.execute("DROP TABLE IF EXISTS aaii_sentiment;")
        cur.execute("""
            CREATE TABLE aaii_sentiment (
                id          SERIAL PRIMARY KEY,
                date        DATE         NOT NULL UNIQUE,
                bullish     DOUBLE PRECISION,
                neutral     DOUBLE PRECISION,
                bearish     DOUBLE PRECISION,
                fetched_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

        # Load sentiment data
        total, inserted, failed = load_sentiment_data(cur, conn)

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
        logging.info(f"AAII Sentiment — total: {total}, inserted: {inserted}, failed: {len(failed)}")

        cur.close()
        conn.close()
        logging.info("All done.")
    except Exception as e:
        logging.error(f"❌ CRITICAL ERROR in AAII loader: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {traceback.format_exc()}")
        sys.exit(1) 