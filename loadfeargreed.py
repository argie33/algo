#!/usr/bin/env python3
"""
Fear & Greed Index Data Loader

This script scrapes the CNN Fear & Greed Index data using a headless browser
and loads it into the PostgreSQL database. The Fear & Greed Index is a market
sentiment indicator that ranges from 0 (Extreme Fear) to 100 (Extreme Greed).

Key Features:
- Scrapes historical Fear & Greed data from CNN's API endpoint
- Uses headless Chromium browser with Pyppeteer for JavaScript rendering
- Implements retry logic for browser failures in containerized environments
- Deduplicates data by date before insertion
- Tracks memory usage and execution metrics
- Updates last_updated table for monitoring purposes

Database Schema:
- fear_greed_index: Stores daily Fear & Greed readings (date, index_value, rating)
- last_updated: Tracks script execution timestamps

Updated: 2025-10-04 14:00 - Deploy Fear & Greed Index sentiment loader
"""
import asyncio
import gc
import json
import logging
import math
import os
import resource
import sys
import time
from datetime import datetime

import boto3
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from pyppeteer import launch

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadfeargreed.py"
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
        float: Memory usage in MB. On Linux, converts from KB to MB.
               On other platforms (macOS), converts from bytes to MB.
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
# Browser scraping can be flaky in containerized environments, so we retry up to 3 times
MAX_BROWSER_RETRIES = 3
RETRY_DELAY = 2.0  # seconds to wait between browser retry attempts

# -------------------------------
# Fear & Greed table columns
# -------------------------------
# These columns map to the fear_greed_index table schema
FEAR_GREED_COLUMNS = ["date", "index_value", "rating"]
COL_LIST = ", ".join(FEAR_GREED_COLUMNS)  # Used in SQL INSERT statements

# -------------------------------
# CNN Fear & Greed API endpoint
# -------------------------------
# This URL serves JSON data with historical Fear & Greed Index readings
# The data includes timestamp (x), index value (y), and rating (text label)
FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    """
    Retrieve database credentials from AWS Secrets Manager.

    Returns:
        dict: Database connection parameters including host, port, user,
              password, and dbname. Reads from DB_SECRET_ARN environment variable.

    Raises:
        KeyError: If DB_SECRET_ARN environment variable is not set
        ClientError: If secret retrieval from AWS Secrets Manager fails
    """
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

    The CNN API endpoint returns JSON data with historical Fear & Greed Index values.
    Since the endpoint requires JavaScript rendering, we use Pyppeteer (headless Chromium)
    instead of simple HTTP requests.

    Browser Configuration:
        - Uses containerized Chromium with Docker-optimized flags
        - Implements retry logic for reliability in containerized environments
        - Sets user agent to avoid bot detection
        - Waits for network idle to ensure data is fully loaded

    Returns:
        list: Array of dictionaries containing:
            - x (int): UNIX timestamp in milliseconds
            - y (float): Fear & Greed index value (0-100)
            - rating (str): Text label (e.g., "Fear", "Greed", "Neutral")

    Raises:
        Exception: If all retry attempts fail to scrape data
    """
    logging.info(f"Scraping Fear & Greed data from: {FEAR_GREED_URL}")

    browser = None
    for attempt in range(1, MAX_BROWSER_RETRIES + 1):
        try:
            logging.info(f"Browser attempt {attempt}/{MAX_BROWSER_RETRIES}")

            # Launch browser with Docker-optimized arguments for containerized environment
            # These flags disable sandboxing and GPU features that may cause issues in containers
            browser = await launch(
                executablePath="/usr/bin/chromium",
                args=[
                    "--no-sandbox",  # Required in Docker containers
                    "--disable-setuid-sandbox",  # Required in Docker containers
                    "--disable-dev-shm-usage",  # Prevent shared memory issues
                    "--disable-accelerated-2d-canvas",  # Reduce resource usage
                    "--no-first-run",  # Skip first-run setup
                    "--no-zygote",  # Disable zygote process (Docker optimization)
                    "--disable-gpu",  # No GPU in headless mode
                    "--disable-background-timer-throttling",  # Consistent timing
                    "--disable-backgrounding-occluded-windows",  # Prevent pausing
                    "--disable-renderer-backgrounding",  # Keep renderer active
                ],
                headless=True,
            )

            page = await browser.newPage()

            # Set user agent to mimic a real browser and avoid bot detection
            await page.setUserAgent(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )

            # Navigate to the Fear & Greed API endpoint
            # waitUntil="networkidle0" ensures all network requests complete before proceeding
            await page.goto(FEAR_GREED_URL, waitUntil="networkidle0", timeout=30000)

            # Wait for the JSON data to appear in a <pre> tag
            selector = "pre"
            await page.waitForSelector(selector, timeout=30000)

            # Extract the JSON data from the page
            element = await page.querySelector(selector)
            data = await page.evaluate("(element) => element.textContent", element)
            data_json = json.loads(data)

            # Extract the historical data array from the nested JSON structure
            data_array = data_json["fear_and_greed_historical"]["data"]

            logging.info(f"Successfully scraped {len(data_array)} Fear & Greed records")

            # Clean up browser resources
            await browser.close()
            browser = None

            return data_array

        except Exception as e:
            logging.warning(f"Browser attempt {attempt} failed: {e}")
            # Ensure browser is closed even if an error occurred
            if browser:
                try:
                    await browser.close()
                except:
                    pass
                browser = None

            # Wait before retrying, or raise exception if all attempts exhausted
            if attempt < MAX_BROWSER_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                raise Exception(
                    f"Failed to scrape Fear & Greed data after {MAX_BROWSER_RETRIES} attempts: {e}"
                )


# -------------------------------
# Main loader with batched inserts
# -------------------------------
async def load_fear_greed_data(cur, conn):
    """
    Load Fear & Greed Index data into the database.

    This function orchestrates the entire data loading process:
    1. Scrapes historical Fear & Greed data from CNN
    2. Transforms the data (converts timestamps to dates)
    3. Deduplicates by date
    4. Batch inserts into database with UPSERT logic

    Data Processing:
        - Converts UNIX timestamps (ms) to YYYY-MM-DD date format
        - Deduplicates records by date (keeps last occurrence)
        - Handles NULL values for index_value and rating
        - Uses batch insert for performance

    Database Strategy:
        - Uses execute_values for efficient batch insertion
        - ON CONFLICT (date) DO UPDATE implements UPSERT logic
        - Updates fetched_at timestamp on conflicts
        - Rolls back transaction on error

    Args:
        cur: PostgreSQL cursor (with RealDictCursor factory)
        conn: PostgreSQL connection object

    Returns:
        tuple: (total_scraped, total_inserted, error_list)
            - total_scraped (int): Number of records scraped from CNN
            - total_inserted (int): Number of records inserted/updated in DB
            - error_list (list): List of error messages (empty if successful)
    """
    logging.info("Loading Fear & Greed data")

    try:
        # Step 1: Scrape the Fear & Greed data from CNN
        data_array = await get_fear_greed_data()

        if not data_array:
            logging.warning("No Fear & Greed data scraped")
            return 0, 0, []

        # Step 2: Transform and deduplicate data
        # Use dict to deduplicate by date (dict keys are unique)
        rows_dict = {}
        for item in data_array:
            try:
                # Convert UNIX timestamp (milliseconds) to YYYY-MM-DD format
                dt = timestamptodatestr(item["x"])
                index_value = float(item["y"]) if item["y"] is not None else None
                rating = str(item["rating"]) if item["rating"] else None

                # Keep the most recent data for each date (overwrites if duplicate)
                rows_dict[dt] = [dt, index_value, rating]
            except Exception as e:
                logging.warning(f"Failed to process item {item}: {e}")
                continue

        # Convert dict values back to list for batch insert
        rows = list(rows_dict.values())

        if not rows:
            logging.warning("No valid rows after processing")
            return 0, 0, []

        logging.info(
            f"Processing {len(rows)} unique Fear & Greed records (deduplicated from {len(data_array)} total)"
        )

        # Step 3: Batch insert the data with UPSERT logic
        try:
            # UPSERT: Insert new records or update existing ones based on date
            sql = f"INSERT INTO fear_greed_index ({COL_LIST}) VALUES %s ON CONFLICT (date) DO UPDATE SET index_value = EXCLUDED.index_value, rating = EXCLUDED.rating, fetched_at = CURRENT_TIMESTAMP"
            execute_values(cur, sql, rows)
            conn.commit()

            inserted = len(rows)
            logging.info(f"Successfully inserted {inserted} Fear & Greed records")

            return len(data_array), inserted, []

        except Exception as insert_error:
            logging.error(f"Database insert error: {insert_error}")
            conn.rollback()  # Rollback the failed transaction to prevent partial updates
            return 0, 0, [str(insert_error)]

    except Exception as e:
        logging.error(f"Error loading Fear & Greed data: {e}")
        return 0, 0, [str(e)]


# -------------------------------
# Entrypoint
# -------------------------------
async def main():
    """
    Main execution function for the Fear & Greed Index data loader.

    Workflow:
    1. Establishes database connection using AWS Secrets Manager credentials
    2. Recreates fear_greed_index table (drops and recreates for fresh data)
    3. Ensures last_updated tracking table exists
    4. Scrapes and loads Fear & Greed data
    5. Records execution timestamp in last_updated table
    6. Reports memory usage and execution statistics

    Database Tables Created/Modified:
        - fear_greed_index: Stores daily Fear & Greed readings
        - last_updated: Tracks when this script last ran

    Note: This script uses DROP TABLE IF EXISTS to ensure a clean slate
          on each run. Historical data is reloaded from CNN's API.
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

    # Step 2: Recreate fear_greed_index table for fresh data
    # Note: We drop and recreate to ensure no stale data remains
    logging.info("Recreating fear_greed_index table...")
    cur.execute("DROP TABLE IF EXISTS fear_greed_index;")
    cur.execute(
        """
        CREATE TABLE fear_greed_index (
            id          SERIAL PRIMARY KEY,
            date        DATE         NOT NULL UNIQUE,
            index_value DOUBLE PRECISION,
            rating      VARCHAR(50),
            fetched_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """
    )

    # Step 3: Ensure monitoring/tracking table exists
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS last_updated (
            script_name VARCHAR(100) PRIMARY KEY,
            last_run    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """
    )
    conn.commit()

    # Step 4: Scrape and load Fear & Greed data
    total, inserted, failed = await load_fear_greed_data(cur, conn)

    # Step 5: Record this script's execution timestamp for monitoring
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

    # Step 6: Report execution statistics
    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(
        f"Fear & Greed — total: {total}, inserted: {inserted}, failed: {len(failed)}"
    )

    # Clean up database connections
    cur.close()
    conn.close()
    logging.info("All done.")


if __name__ == "__main__":
    asyncio.run(main())
