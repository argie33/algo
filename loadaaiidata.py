# Updated: 2025-10-07 17:09 - Trigger deployment
# Deployment trigger: 2025-10-07 17:10:06
"""
AAII Investor Sentiment Survey Data Loader

This script downloads and loads the American Association of Individual Investors (AAII)
weekly sentiment survey data into the PostgreSQL database. The AAII sentiment survey
is one of the longest-running sentiment indicators, tracking individual investor
sentiment since 1987.

Key Features:
- Downloads AAII sentiment survey Excel file directly from AAII.com
- Parses historical bullish, neutral, and bearish percentages
- Drops and recreates table on each run for fresh data
- Handles Excel parsing with proper encoding and column mapping
- Retry logic for download failures
- Memory usage tracking

Data Source:
- AAII.com weekly sentiment survey (Excel format)
- URL: https://www.aaii.com/files/surveys/sentiment.xls
- Survey asks: "What direction do you think the stock market will go in the next 6 months?"

Database Schema:
- aaii_sentiment: Stores weekly sentiment readings (date, bullish%, neutral%, bearish%)
- last_updated: Tracks script execution timestamps

Sentiment Interpretation:
- Bullish: Percentage expecting market to rise in next 6 months
- Neutral: Percentage expecting no significant change
- Bearish: Percentage expecting market to decline
- Historical averages: ~38% bullish, ~30% neutral, ~30% bearish
- Extreme readings (>55% bullish or bearish) often signal contrarian opportunities

Updated: 2025-10-04 14:00 - Deploy AAII investor sentiment survey loader
"""
import gc
import json
import logging
import math
import os
import resource
import sys
import time
from datetime import datetime
from io import BytesIO

import boto3
import pandas as pd
import psycopg2
import requests
from psycopg2.extras import RealDictCursor, execute_values

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadaaiidata.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    """
    Get current memory usage in megabytes (RSS - Resident Set Size).

    Returns:
        float: Memory usage in MB
    """
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024  # Linux reports in KB
    return usage / (1024 * 1024)  # macOS reports in bytes


def log_mem(stage: str):
    """
    Log current memory usage at a specific stage of execution.

    Args:
        stage: Descriptive label for the current execution stage
    """
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")


# -------------------------------
# Retry settings
# -------------------------------
# Excel file downloads can be flaky, especially when hitting external sites
MAX_DOWNLOAD_RETRIES = 3
RETRY_DELAY = 1.0  # seconds between download retries

# -------------------------------
# AAII Sentiment table columns
# -------------------------------
# These map to the aaii_sentiment database table
SENTIMENT_COLUMNS = ["date", "bullish", "neutral", "bearish"]
COL_LIST = ", ".join(SENTIMENT_COLUMNS)

# -------------------------------
# Direct URL to the AAII sentiment survey Excel file
# -------------------------------
# This Excel file is updated weekly by AAII with historical sentiment data
# Format: .xls (old Excel format, requires xlrd engine)
AAII_EXCEL_URL = "https://www.aaii.com/files/surveys/sentiment.xls"


# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    """
    Retrieve database credentials from AWS Secrets Manager or local env vars.

    Returns:
        dict: Database connection parameters

    Raises:
        KeyError: If DB_SECRET_ARN environment variable is not set (in AWS mode)
    """
    # Check if we're in AWS (has DB_SECRET_ARN)
    if os.environ.get("DB_SECRET_ARN"):
        # AWS mode - use Secrets Manager
        secret_str = boto3.client("secretsmanager").get_secret_value(
            SecretId=os.environ["DB_SECRET_ARN"]
        )["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"],
        }
    else:
        # Local mode - use environment variables
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "user": os.environ.get("DB_USER", "stocks"),
            "password": os.environ.get("DB_PASSWORD", "stocks"),
            "dbname": os.environ.get("DB_NAME", "stocks"),
        }


# -------------------------------
# Download AAII sentiment data
# -------------------------------
def get_aaii_sentiment_data():
    """
    Downloads the AAII sentiment survey Excel file and extracts historical data.

    The AAII.com website publishes a weekly Excel file containing historical
    sentiment survey results. This function downloads the file, parses it,
    and extracts the key sentiment percentages.

    Excel File Structure:
        - Format: Old Excel (.xls) format, requires xlrd engine
        - First 3 rows: Headers/metadata (skipped)
        - Columns: Date, Bullish, Neutral, Bearish (and others we ignore)
        - Data: Weekly readings going back to 1987

    Data Processing:
        - Skip first 3 rows (headers/metadata)
        - Parse Date, Bullish, Neutral, Bearish columns
        - Remove "%" symbols and convert to numeric
        - Convert dates to YYYY-MM-DD format
        - Sort chronologically (oldest first)

    Returns:
        pandas.DataFrame: Historical sentiment data with columns:
            - Date: Survey date in YYYY-MM-DD format
            - Bullish: Percentage expecting market to rise (0-100)
            - Neutral: Percentage expecting no change (0-100)
            - Bearish: Percentage expecting market to decline (0-100)

    Raises:
        Exception: If download fails after all retries
        ValueError: If Excel file structure is unexpected

    Note:
        Uses browser-like headers to avoid bot detection by AAII website.
    """
    logging.info(f"Downloading AAII sentiment survey Excel file from: {AAII_EXCEL_URL}")

    # Custom headers to mimic a browser request for an Excel file
    # These help avoid bot detection and ensure we get the actual Excel file
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.aaii.com/",  # Indicate we came from AAII site
        "Accept": "application/vnd.ms-excel, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
        try:
            logging.info(f"Download attempt {attempt}/{MAX_DOWNLOAD_RETRIES}")

            # Download the Excel file with 30-second timeout
            response = requests.get(
                AAII_EXCEL_URL, headers=headers, allow_redirects=True, timeout=30
            )
            response.raise_for_status()  # Raise exception for HTTP errors (4xx, 5xx)

            # Check the content-type header to verify we got an Excel file
            content_type = response.headers.get("Content-Type", "")
            logging.info(f"Content-Type returned: {content_type}")

            # If the response looks like HTML rather than an Excel file, raise an error
            # This can happen if AAII site changes or blocks our request
            if "html" in content_type.lower():
                raise ValueError(
                    "Server returned HTML instead of an Excel file. Check the URL or headers."
                )

            # Load the Excel file from the downloaded bytes using xlrd engine
            # Note: skiprows=3 because AAII file has 3 header rows before data
            excel_data = BytesIO(response.content)
            df = pd.read_excel(excel_data, skiprows=3, engine="xlrd")

            # Remove extra whitespace from column names for clean matching
            df.columns = df.columns.str.strip()

            # Validate that we have the required columns
            required_cols = ["Date", "Bullish", "Neutral", "Bearish"]
            for col in required_cols:
                if col not in df.columns:
                    raise ValueError(
                        f"Expected column '{col}' not found. Found columns: {df.columns.tolist()}"
                    )

            # Select only the required columns (ignore extra columns like S&P, etc.)
            df = df[required_cols]

            # Clean percentage columns: remove "%" symbol and convert to numeric
            # AAII stores values like "35.2%" which need to be parsed as 35.2
            for col in ["Bullish", "Neutral", "Bearish"]:
                df[col] = (
                    df[col].astype(str).str.replace("%", "", regex=False).str.strip()
                )
                df[col] = pd.to_numeric(df[col], errors="coerce")  # Convert to float, invalid -> NaN

            # Convert the Date column to datetime and then to string in YYYY-MM-DD format
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"])  # Drop rows where date conversion failed
            df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

            # Sort by Date (oldest first) and reset index for clean insertion
            df.sort_values("Date", inplace=True)
            df.reset_index(drop=True, inplace=True)

            logging.info(
                f"Successfully downloaded AAII sentiment data: {len(df)} records"
            )
            return df

        except Exception as e:
            logging.warning(f"Download attempt {attempt} failed: {e}")
            if attempt < MAX_DOWNLOAD_RETRIES:
                time.sleep(RETRY_DELAY)  # Wait before retrying
            else:
                raise Exception(
                    f"Failed to download AAII sentiment data after {MAX_DOWNLOAD_RETRIES} attempts: {e}"
                )


# -------------------------------
# Main loader with batched inserts
# -------------------------------
def load_sentiment_data(cur, conn):
    """
    Load AAII sentiment data into the database.

    This function orchestrates the entire data loading process:
    1. Downloads sentiment data from AAII website
    2. Transforms DataFrame into database-ready format
    3. Batch inserts using execute_values for performance
    4. Handles NULL values properly

    Data Transformation:
        - Converts pandas DataFrame to list of tuples
        - Handles NaN values by converting to None (SQL NULL)
        - Ensures all percentages are floats

    Args:
        cur: PostgreSQL cursor object
        conn: PostgreSQL connection object

    Returns:
        tuple: (total_downloaded, total_inserted, errors_list)
            - total_downloaded (int): Number of records downloaded from AAII
            - total_inserted (int): Number of records inserted into database
            - errors_list (list): List of error messages (empty if successful)
    """
    logging.info("Loading AAII sentiment data")

    try:
        # Step 1: Download the sentiment data from AAII website
        df = get_aaii_sentiment_data()

        if df.empty:
            logging.warning("No sentiment data downloaded")
            return 0, 0, []

        # Step 2: Convert DataFrame to list of tuples for batch insert
        rows = []
        for _, row in df.iterrows():
            rows.append(
                [
                    row["Date"],  # Survey date (YYYY-MM-DD)
                    None if pd.isna(row["Bullish"]) else float(row["Bullish"]),  # Bullish %
                    None if pd.isna(row["Neutral"]) else float(row["Neutral"]),  # Neutral %
                    None if pd.isna(row["Bearish"]) else float(row["Bearish"]),  # Bearish %
                ]
            )

        if not rows:
            logging.warning("No valid rows after processing")
            return 0, 0, []

        # Step 3: Batch insert the data for performance
        # execute_values is much faster than individual INSERTs
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
    """
    Main execution function for the AAII sentiment loader.

    Workflow:
    1. Establishes database connection using AWS Secrets Manager credentials
    2. Recreates aaii_sentiment table (drops and recreates for fresh data)
    3. Downloads and loads sentiment data from AAII website
    4. Records execution timestamp in last_updated table
    5. Reports memory usage and execution statistics

    Database Tables Created/Modified:
        - aaii_sentiment: Stores weekly sentiment readings
        - last_updated: Tracks when this script last ran

    Note:
        This script uses DROP TABLE IF EXISTS to ensure a clean slate on each run.
        All existing sentiment data is replaced with fresh data from AAII.
        The date column has a UNIQUE constraint to prevent duplicates.
    """
    log_mem("startup")

    # Step 1: Connect to database using AWS Secrets Manager credentials
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["dbname"],
    )
    conn.autocommit = False  # Use explicit transactions for better error handling
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Step 2: Recreate aaii_sentiment table for fresh data
    logging.info("Recreating aaii_sentiment table...")
    cur.execute("DROP TABLE IF EXISTS aaii_sentiment;")
    cur.execute(
        """
        CREATE TABLE aaii_sentiment (
            id          SERIAL PRIMARY KEY,
            date        DATE         NOT NULL UNIQUE,
            bullish     DOUBLE PRECISION,
            neutral     DOUBLE PRECISION,
            bearish     DOUBLE PRECISION,
            fetched_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """
    )
    conn.commit()

    # Step 3: Download and load sentiment data from AAII
    total, inserted, failed = load_sentiment_data(cur, conn)

    # Step 4: Record this script's execution timestamp for monitoring
    cur.execute(
        """
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """,
        (SCRIPT_NAME,),
    )
    conn.commit()

    # Step 5: Report execution statistics
    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(
        f"AAII Sentiment — total: {total}, inserted: {inserted}, failed: {len(failed)}"
    )

    # Clean up database connections
    cur.close()
    conn.close()
    logging.info("All done.")

# Trigger deployment comment for aaii, feargreed, naaim, sectordata loaders
# Trigger rebuild 1759855026
