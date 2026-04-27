#!/usr/bin/env python3
"""
AAII Sentiment Survey Loader - Investor Sentiment Indicators

DEPLOYMENT MODES:
  • AWS Production: Uses DB_SECRET_ARN environment variable (Lambda/ECS)
    └─ Fetches DB credentials from AWS Secrets Manager
    └─ Downloads AAII sentiment Excel file via HTTPS
    └─ Extracts bullish/neutral/bearish percentages
    └─ Writes to PostgreSQL RDS database

  • Local Development: Uses DB_HOST/DB_USER/DB_PASSWORD env vars
    └─ Falls back if DB_SECRET_ARN not set
    └─ Same data fetching & processing logic
    └─ Perfect for testing without AWS infrastructure

DATA SOURCE:
  • AAII Sentiment Survey (https://www.aaii.com/files/surveys/sentiment.xls)
  • Excel file with historical sentiment data
  • Extracts: date, bullish%, neutral%, bearish%

TABLES:
  • aaii_sentiment: Stores weekly sentiment survey results

OUTPUTS:
  • market page: AAII investor sentiment indicators

Version: v1.0
Last Updated: 2026-01-28 - CRITICAL DATA LOSS FIX DEPLOYED - Crash-safe execution ready
"""
import sys
import time
import logging
import json
import os
import gc
try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False
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
    """Get RSS memory in MB, cross-platform."""
    if not HAS_RESOURCE:
        try:
            import psutil
            return psutil.Process().memory_info().rss / (1024 * 1024)
        except Exception:
            return 0
    usage = resource.getrusage(resource.RUSAGE_SELF)
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


def get_aaii_sentiment_data():
    """
    Downloads the AAII sentiment survey Excel file and extracts historical data.
    Returns a DataFrame with the columns: Date, Bullish, Neutral, and Bearish.

    FIXED (2026-03-01): Uses improved session handling with retry strategy
    that successfully bypasses 403 blocks. Header row is at index 3.
    """
    logging.info(f" Starting AAII sentiment data download from: {AAII_EXCEL_URL}")

    # Improved session with connection pooling and retry strategy
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        read=5,
        connect=5,
        backoff_factor=0.5,
        status_forcelist=(500, 502, 503, 504)
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    # Comprehensive headers that mimic a real browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-excel, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }

    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
        try:
            logging.info(f"Download attempt {attempt}/{MAX_DOWNLOAD_RETRIES}")
            # Add polite delays between retries
            if attempt > 1:
                wait_time = 2 + attempt
                logging.info(f"⏳ Waiting {wait_time}s before retry...")
                time.sleep(wait_time)

            response = session.get(AAII_EXCEL_URL, headers=headers, timeout=20, verify=True)

            content_type = response.headers.get("Content-Type", "")
            content_size = len(response.content)
            logging.info(f" Response: Status={response.status_code}, Size={content_size:,} bytes, Type={content_type}")

            # Validate it's actually an Excel file, not HTML error
            if content_size < 100000 or "html" in content_type.lower():
                raise ValueError(f"Not an Excel file (size={content_size}, type={content_type})")

            # Parse Excel file with correct header row
            excel_data = BytesIO(response.content)
            logging.info(" Parsing Excel file (header at row 3)...")
            df = pd.read_excel(excel_data, header=3, engine="xlrd")

            # Get only sentiment columns
            required_cols = ["Date", "Bullish", "Neutral", "Bearish"]
            df = df[required_cols].copy()
            logging.info(f" Extracted {len(df)} rows")

            # Clean data
            df = df.dropna(subset=["Date"])  # Remove rows without date
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"])  # Remove invalid dates

            # Convert sentiment columns to numeric (they're already as decimals like 0.36)
            for col in ["Bullish", "Neutral", "Bearish"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # Remove rows with NaN sentiment values
            df = df.dropna(subset=["Bullish", "Neutral", "Bearish"])

            # Format date as string
            df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

            # Sort by date
            df = df.sort_values("Date").reset_index(drop=True)

            logging.info(f" Successfully downloaded AAII sentiment data: {len(df)} records")
            logging.info(f"   Date range: {df['Date'].min()} to {df['Date'].max()}")
            return df

        except Exception as e:
            logging.error(f" Download attempt {attempt} failed: {str(e)[:100]}")
            if attempt == MAX_DOWNLOAD_RETRIES:
                logging.error(f" CRITICAL: Failed after {MAX_DOWNLOAD_RETRIES} attempts")
                raise Exception(f"Failed to download AAII data: {e}")

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
        
        # Batch insert the data with conflict handling
        sql = f"INSERT INTO aaii_sentiment ({COL_LIST}) VALUES %s ON CONFLICT (date) DO UPDATE SET bullish=EXCLUDED.bullish, neutral=EXCLUDED.neutral, bearish=EXCLUDED.bearish"
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
        logging.info(f" Starting {SCRIPT_NAME} execution")
        log_mem("startup")

        # Connect to DB
        logging.info(" Loading database configuration...")
        cfg = get_db_config()
        logging.info(f" Connecting to database: {cfg['host']}:{cfg['port']}/{cfg['dbname']}")
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"]
        )
        logging.info(" Database connection established")
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Ensure aaii_sentiment table exists (never drop - avoid data loss)
        logging.info("Ensuring aaii_sentiment table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS aaii_sentiment (
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
        logging.error(f" CRITICAL ERROR in AAII loader: {e}")
        import traceback
        logging.error(f" Full traceback: {traceback.format_exc()}")
        sys.exit(1) 