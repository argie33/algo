#!/usr/bin/env python3 
import logging
import sys
import json
import os
import gc
import resource
import math
import time
import random

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime
import requests

import boto3
import yfinance as yf
import pandas as pd

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadcalendar.py"
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
MAX_BATCH_RETRIES = 2
RETRY_DELAY = 0.5  # seconds between download retries

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

def load_calendar_info(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading calendar info for {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE, PAUSE = 3, 0.5
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.replace('.', '-').replace('$','-').upper() for s in batch]
        mapping = dict(zip(yq_batch, batch))

        logging.info(f"Processing batch {batch_idx+1}/{batches}")
        log_mem(f"Batch {batch_idx+1} start")
        
        for yq_sym, orig_sym in mapping.items():
            calendar_data = None  # Initialize calendar_data variable
            for attempt in range(1, MAX_BATCH_RETRIES+1):
                try:
                    ticker = yf.Ticker(yq_sym)
                    calendar_data = ticker.calendar
                    if not calendar_data or not isinstance(calendar_data, dict):
                        raise ValueError("No calendar data received")
                    break
                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {orig_sym}: {e}")
                    if attempt == MAX_BATCH_RETRIES:
                        failed.append(orig_sym)
                        break  # Break instead of continue to skip processing
                    time.sleep(RETRY_DELAY)
            
            # Skip processing if calendar_data was not successfully retrieved
            if calendar_data is None:
                logging.error(f"Skipping {orig_sym} - failed to retrieve calendar data after {MAX_BATCH_RETRIES} attempts")
                continue
            
            try:
                events_to_insert = []
                
                # Process earnings events
                if 'Earnings Date' in calendar_data:
                    earnings_date = calendar_data.get('Earnings Date')
                    # Handle earnings date which can be a single value or a range
                    if isinstance(earnings_date, list):
                        start_date = pd.to_datetime(earnings_date[0]) if earnings_date else None
                        end_date = pd.to_datetime(earnings_date[1]) if len(earnings_date) > 1 else start_date
                    else:
                        start_date = pd.to_datetime(earnings_date)
                        end_date = start_date

                    earnings_title = "Q" + str(calendar_data.get('Earnings Quarter', '')) + " Earnings"
                    events_to_insert.append((
                        orig_sym,
                        'earnings',
                        start_date,
                        end_date,
                        earnings_title
                    ))

                # Process dividend events
                if 'Dividend Date' in calendar_data:
                    div_date = pd.to_datetime(calendar_data.get('Dividend Date'))
                    ex_date = pd.to_datetime(calendar_data.get('Ex-Dividend Date'))
                    div_amount = calendar_data.get('Dividend', 0.0)
                    if div_date is not None:
                        events_to_insert.append((
                            orig_sym,
                            'dividend',
                            div_date,
                            div_date,
                            f"Dividend Payment ${div_amount:.4f}"
                        ))
                    if ex_date is not None:
                        events_to_insert.append((
                            orig_sym,
                            'dividend',
                            ex_date,
                            ex_date,
                            f"Ex-Dividend ${div_amount:.4f}"
                        ))

                # Add any splits
                try:
                    splits = ticker.splits
                    if not splits.empty:
                        for date, ratio in splits.items():
                            events_to_insert.append((
                                orig_sym,
                                'split',
                                pd.to_datetime(date),
                                pd.to_datetime(date),
                                f"{ratio}:1 Stock Split"
                            ))
                except Exception as e:
                    logging.warning(f"Failed to fetch splits for {orig_sym}: {e}")
                
                if events_to_insert:
                    # Batch insert all events
                    execute_values(cur, """
                        INSERT INTO calendar_events 
                        (symbol, event_type, start_date, end_date, title)
                        VALUES %s
                    """, events_to_insert)
                    
                    logging.info(f"Successfully processed {len(events_to_insert)} calendar events for {orig_sym}")
                else:
                    logging.info(f"No calendar events found for {orig_sym}")

                processed += 1

            except Exception as e:
                logging.error(f"Error processing calendar events for {orig_sym}: {e}")
                failed.append(orig_sym)
                continue
        
        # Pause between batches  
        log_mem(f"Batch {batch_idx+1} end")
        if batch_idx < batches - 1:
            time.sleep(PAUSE)
    
    logging.info(f"Completed loading calendar info: {processed} processed, {len(failed)} failed")
    if failed:
        logging.warning(f"Failed symbols: {failed[:10]}{'...' if len(failed) > 10 else ''}")
    
    return processed, failed

def main():
    conn = None
    try:
        log_mem("startup")
        
        logging.info("Recreating calendar tables...")
        
        db_config = get_db_config()
        conn = psycopg2.connect(**db_config)
        
        with conn.cursor() as cur:
            # Drop & recreate calendar tables 
            cur.execute("DROP TABLE IF EXISTS calendar_events;")
            cur.execute("""
                CREATE TABLE calendar_events (
                    id          SERIAL PRIMARY KEY,
                    symbol     VARCHAR(10) NOT NULL,
                    event_type VARCHAR(50) NOT NULL,
                    start_date TIMESTAMPTZ,
                    end_date   TIMESTAMPTZ,
                    title      TEXT,
                    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            # Create index on symbol for faster lookups
            cur.execute("""
                CREATE INDEX idx_calendar_events_symbol 
                ON calendar_events (symbol);
            """)
        conn.commit()

        log_mem("Before fetching symbols")
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT symbol 
                FROM stock_symbols 
                ORDER BY symbol;
            """)
            symbols = [r["symbol"] for r in cur.fetchall()]
        log_mem("After fetching symbols")

        if not symbols:
            logging.warning("No symbols found in stock_symbols table")
            return

        # Process symbols with batch handling
        with conn.cursor() as cur:
            processed, failed = load_calendar_info(symbols, cur, conn)

        # Update last_updated table
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS last_updated (
                    script_name VARCHAR(255) PRIMARY KEY,
                    last_run    TIMESTAMPTZ NOT NULL
                );
            """)
            cur.execute("""
                INSERT INTO last_updated (script_name, last_run)
                VALUES (%s, NOW())
                ON CONFLICT (script_name) DO UPDATE
                  SET last_run = EXCLUDED.last_run;
            """, (SCRIPT_NAME,))
        conn.commit()
        
        log_mem("End of processing")
        logging.info(f"Calendar loading complete: {processed} processed, {len(failed)} failed")
        
    except Exception:
        logging.exception("Fatal error in main()")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                logging.exception("Error closing database connection")
        log_mem("End of script")
        logging.info("loadcalendar complete.")

if __name__ == "__main__":
    main()
