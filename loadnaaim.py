#!/usr/bin/env python3
"""
NAAIM Exposure Index Loader - Fund Manager Positioning

DEPLOYMENT MODES:
  • AWS Production: Uses DB_SECRET_ARN environment variable (Lambda/ECS)
    └─ Fetches DB credentials from AWS Secrets Manager
    └─ Scrapes NAAIM exposure index via HTTPS
    └─ Browser-based extraction with pyppeteer
    └─ Writes to PostgreSQL RDS database

  • Local Development: Uses DB_HOST/DB_USER/DB_PASSWORD env vars
    └─ Falls back if DB_SECRET_ARN not set
    └─ Same data fetching & processing logic
    └─ Perfect for testing without AWS infrastructure

DATA SOURCE:
  • NAAIM Exposure Index (https://www.naaim.org/programs/naaim-exposure-index/)
  • Weekly fund manager equity exposure polling
  • Extracts: date, bullish%, neutral%, bearish%

TABLES:
  • naaim_exposure: Stores weekly fund manager positioning

OUTPUTS:
  • market page: NAAIM fund manager sentiment indicators

Version: v1.0
Last Updated: 2025-10-27 - AWS TESTED
"""
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
from bs4 import BeautifulSoup

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = "loadnaaim.py"
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
# NAAIM columns
# -------------------------------
NAAIM_COLUMNS = ["date", "naaim_number_mean", "bearish", "quart1", "quart2", "quart3", "bullish", "deviation"]
COL_LIST = ", ".join(NAAIM_COLUMNS)

# -------------------------------
# NAAIM Exposure Index URL
# -------------------------------
NAAIM_URL = "https://www.naaim.org/programs/naaim-exposure-index/"

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    """Get database configuration from AWS Secrets Manager or local environment."""
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    # Try AWS Secrets Manager first (for production/Lambda)
    if db_secret_arn:
        try:
            secret_str = boto3.client("secretsmanager") \
                             .get_secret_value(SecretId=db_secret_arn)["SecretString"]
            sec = json.loads(secret_str)
            return {
                "host":   sec["host"],
                "port":   int(sec.get("port", 5432)),
                "user":   sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.warning(f"Failed to fetch from AWS Secrets Manager: {e}, falling back to environment variables")

    # Fall back to environment variables (for local development)
    return {
        "host":   os.environ.get("DB_HOST", "localhost"),
        "port":   int(os.environ.get("DB_PORT", 5432)),
        "user":   os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", "password"),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

# -------------------------------
# Download NAAIM data
# -------------------------------
def get_naaim_data():
    """
    Downloads the NAAIM Exposure Index data from their website.
    Returns a DataFrame with the NAAIM exposure data.
    """
    logging.info(f"🔄 Starting NAAIM data download from: {NAAIM_URL}")
    
    # Custom headers to mimic a browser request and avoid compression
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/115.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",  # Request uncompressed content
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }
    
    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
        try:
            logging.info(f"Download attempt {attempt}/{MAX_DOWNLOAD_RETRIES}")
            
            # Send HTTP request
            response = requests.get(NAAIM_URL, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Debug: Log the first 1000 characters of the response
            logging.info(f"Response status: {response.status_code}")
            logging.info(f"Response content preview: {response.text[:1000]}...")
            
            # Try to find tables in the HTML
            logging.info("Parsing HTML tables...")
            
            # Method 1: Try pandas read_html
            try:
                from io import StringIO
                dfs = pd.read_html(StringIO(response.text))
                logging.info(f"Found {len(dfs)} tables with pandas read_html")
                
                if dfs:
                    # Get the first dataframe (NAAIM data table)
                    data = dfs[0]
                    logging.info(f"Found table with shape: {data.shape}")
                    logging.info(f"Table columns: {list(data.columns)}")
                    logging.info(f"First few rows: {data.head()}")
                    
                    # Check if this looks like NAAIM data
                    if len(data.columns) >= 7:  # Expected columns
                        # Assign meaningful column names
                        data.columns = ['Date', 'NAAIM Number Mean/Average', 'Bearish', 'Quart1', 'Quart2', 'Quart3', 'Bullish', 'Deviation']
                        
                        # Clean the data
                        data = data.where(pd.notnull(data), None)
                        
                        # Convert date column to proper format
                        data['Date'] = pd.to_datetime(data['Date'], errors='coerce')
                        data = data.dropna(subset=['Date'])  # Drop rows where date conversion failed
                        data['Date'] = data['Date'].dt.strftime('%Y-%m-%d')
                        
                        # Convert numeric columns
                        numeric_columns = ['NAAIM Number Mean/Average', 'Bearish', 'Quart1', 'Quart2', 'Quart3', 'Bullish', 'Deviation']
                        for col in numeric_columns:
                            if col in data.columns:
                                data[col] = pd.to_numeric(data[col], errors='coerce')
                        
                        logging.info(f"Successfully downloaded NAAIM data: {len(data)} records")
                        return data
                    else:
                        logging.warning(f"Table found but doesn't look like NAAIM data. Columns: {list(data.columns)}")
                        
            except Exception as e:
                logging.warning(f"pandas read_html failed: {e}")
            
            # Method 2: Try to find table elements manually
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')
                tables = soup.find_all('table')
                logging.info(f"Found {len(tables)} table elements with BeautifulSoup")
                
                for i, table in enumerate(tables):
                    logging.info(f"Table {i}: {table.get('class', 'no-class')} - {table.get('id', 'no-id')}")
                    rows = table.find_all('tr')
                    logging.info(f"  Rows: {len(rows)}")
                    if rows:
                        first_row = rows[0]
                        cells = first_row.find_all(['td', 'th'])
                        logging.info(f"  First row cells: {len(cells)}")
                        if cells:
                            logging.info(f"  First cell content: {cells[0].get_text(strip=True)}")
                
                # If we found tables, try to parse the largest one
                if tables:
                    largest_table = max(tables, key=lambda t: len(t.find_all('tr')))
                    logging.info(f"Attempting to parse largest table with {len(largest_table.find_all('tr'))} rows")
                    
                    # Convert to DataFrame
                    rows = []
                    for tr in largest_table.find_all('tr'):
                        row = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                        if row:  # Skip empty rows
                            rows.append(row)
                    
                    if rows:
                        data = pd.DataFrame(rows[1:], columns=rows[0])  # First row as headers
                        logging.info(f"Parsed table with shape: {data.shape}")
                        logging.info(f"Columns: {list(data.columns)}")
                        
                        # Check if this looks like NAAIM data
                        if len(data.columns) >= 7:
                            # Clean and process the data
                            data = data.where(pd.notnull(data), None)
                            
                            # Try to convert date column
                            date_col = data.columns[0]  # Assume first column is date
                            data[date_col] = pd.to_datetime(data[date_col], errors='coerce')
                            data = data.dropna(subset=[date_col])
                            data[date_col] = data[date_col].dt.strftime('%Y-%m-%d')
                            
                            # Convert numeric columns
                            for col in data.columns[1:]:  # Skip date column
                                data[col] = pd.to_numeric(data[col], errors='coerce')
                            
                            logging.info(f"Successfully parsed NAAIM data: {len(data)} records")
                            return data
                            
            except Exception as e:
                logging.warning(f"BeautifulSoup parsing failed: {e}")
            
            # If we get here, no valid table was found
            raise ValueError("No valid NAAIM data tables found on the page")
            
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
                logging.error(f"❌ CRITICAL: Failed to download NAAIM data after {MAX_DOWNLOAD_RETRIES} attempts")
                logging.error(f"❌ Final error: {e}")
                raise Exception(f"Failed to download NAAIM data after {MAX_DOWNLOAD_RETRIES} attempts: {e}")

# -------------------------------
# Main loader with batched inserts
# -------------------------------
def load_naaim_data(cur, conn):
    logging.info("Loading NAAIM data")
    
    try:
        # Download the NAAIM data
        df = get_naaim_data()
        
        if df.empty:
            logging.warning("No NAAIM data downloaded")
            return 0, 0, []
        
        # Convert DataFrame to list of tuples for batch insert
        rows = []
        for _, row in df.iterrows():
            try:
                rows.append([
                    row['Date'],
                    None if pd.isna(row['NAAIM Number Mean/Average']) else float(row['NAAIM Number Mean/Average']),
                    None if pd.isna(row['Bearish']) else float(row['Bearish']),
                    None if pd.isna(row['Quart1']) else float(row['Quart1']),
                    None if pd.isna(row['Quart2']) else float(row['Quart2']),
                    None if pd.isna(row['Quart3']) else float(row['Quart3']),
                    None if pd.isna(row['Bullish']) else float(row['Bullish']),
                    None if pd.isna(row['Deviation']) else float(row['Deviation'])
                ])
            except Exception as e:
                logging.warning(f"Failed to process row {row}: {e}")
                continue
        
        if not rows:
            logging.warning("No valid rows after processing")
            return 0, 0, []
        
        # Batch insert the data
        sql = f"INSERT INTO naaim ({COL_LIST}) VALUES %s ON CONFLICT (date) DO UPDATE SET naaim_number_mean = EXCLUDED.naaim_number_mean, bearish = EXCLUDED.bearish, quart1 = EXCLUDED.quart1, quart2 = EXCLUDED.quart2, quart3 = EXCLUDED.quart3, bullish = EXCLUDED.bullish, deviation = EXCLUDED.deviation"
        execute_values(cur, sql, rows)
        conn.commit()
        
        inserted = len(rows)
        logging.info(f"Successfully inserted {inserted} NAAIM records")
        
        return len(df), inserted, []
        
    except Exception as e:
        logging.error(f"Error loading NAAIM data: {e}")
        return 0, 0, [str(e)]

# -------------------------------
# Entrypoint
# -------------------------------
def main():
    """Main synchronous function to run NAAIM data loading."""
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

    # Recreate naaim table
    logging.info("Recreating naaim table...")
    cur.execute("DROP TABLE IF EXISTS naaim;")
    cur.execute("""
        CREATE TABLE naaim (
            id                  SERIAL PRIMARY KEY,
            date                DATE         NOT NULL UNIQUE,
            naaim_number_mean   DOUBLE PRECISION,
            bearish             DOUBLE PRECISION,
            quart1              DOUBLE PRECISION,
            quart2              DOUBLE PRECISION,
            quart3              DOUBLE PRECISION,
            bullish             DOUBLE PRECISION,
            deviation           DOUBLE PRECISION,
            fetched_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
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

    # Load NAAIM data
    total, inserted, failed = load_naaim_data(cur, conn)

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
    logging.info(f"NAAIM — total: {total}, inserted: {inserted}, failed: {len(failed)}")

    cur.close()
    conn.close()
    logging.info("All done.")
    
    return total, inserted, failed

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"❌ CRITICAL ERROR in NAAIM loader: {e}")
        import traceback
        logging.error(f"❌ Full traceback: {traceback.format_exc()}")
        sys.exit(1) 