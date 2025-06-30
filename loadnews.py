#!/usr/bin/env python3  
import sys
import time
import logging
import json
import os
import gc
import resource
import math
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

import boto3
import yfinance as yf

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadnews.py"
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
MAX_BATCH_RETRIES = 3
RETRY_DELAY = 0.2  # seconds between download retries

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId="loadfundamentals-secrets")["SecretString"]
    secret_json = json.loads(secret_str)
    return {
        "host": secret_json["host"],
        "port": secret_json["port"],
        "user": secret_json["user"],
        "password": secret_json["password"],
        "dbname": secret_json["dbname"]
    }

# -------------------------------
# Environment
# -------------------------------
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "30"))
PAUSE = float(os.environ.get("PAUSE", "0.5"))

# -------------------------------
# News loading
# -------------------------------
def load_news_data(symbols, cur, conn):
    """
    Load news data for given symbols using yfinance.
    Returns (total, processed, failed).
    """
    total = len(symbols)
    processed = 0
    failed = []
    
    # Calculate batch count
    num_batches = math.ceil(total / BATCH_SIZE)
    
    logging.info(f"Loading news for {total} symbols in {num_batches} batches of {BATCH_SIZE}")
    
    for batch_idx in range(num_batches):
        start_idx = batch_idx * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, total)
        batch = symbols[start_idx:end_idx]
        
        log_mem(f"Batch {batch_idx+1} start")
        logging.info(f"Processing batch {batch_idx+1}/{num_batches}: symbols {start_idx+1}-{end_idx}")
        
        for symbol in batch:
            orig_sym = symbol
            try:
                logging.info(f"Fetching news for {orig_sym}")
                
                # Get ticker object
                ticker = yf.Ticker(orig_sym)
                
                # Get news data
                news_data = ticker.news
                
                if not news_data:
                    logging.warning(f"No news data found for {orig_sym}")
                    continue
                
                # Process each news item
                news_items = []
                for news_item in news_data:
                    # Extract news data
                    uuid = news_item.get('uuid')
                    title = news_item.get('title', '')
                    publisher = news_item.get('publisher', '')
                    link = news_item.get('link', '')
                    publish_time = news_item.get('providerPublishTime')
                    news_type = news_item.get('type', '')
                    
                    # Convert timestamp to datetime
                    publish_datetime = None
                    if publish_time:
                        try:
                            publish_datetime = datetime.fromtimestamp(publish_time)
                        except (ValueError, TypeError):
                            logging.warning(f"Invalid timestamp for {orig_sym}: {publish_time}")
                    
                    # Get thumbnail and related tickers
                    thumbnail = None
                    if 'thumbnail' in news_item and 'resolutions' in news_item['thumbnail']:
                        thumbnails = news_item['thumbnail']['resolutions']
                        if thumbnails:
                            thumbnail = thumbnails[0].get('url')
                    
                    related_tickers = []
                    if 'relatedTickers' in news_item:
                        related_tickers = [ticker for ticker in news_item['relatedTickers'] if ticker]
                    
                    news_items.append((
                        uuid,
                        orig_sym,
                        title,
                        publisher,
                        link,
                        publish_datetime,
                        news_type,
                        thumbnail,
                        json.dumps(related_tickers) if related_tickers else None
                    ))
                
                # Insert news items
                if news_items:
                    execute_values(
                        cur,
                        """
                        INSERT INTO stock_news (
                            uuid, ticker, title, publisher, link, 
                            publish_time, news_type, thumbnail, related_tickers
                        ) VALUES %s
                        ON CONFLICT (uuid) DO UPDATE SET
                            title = EXCLUDED.title,
                            publisher = EXCLUDED.publisher,
                            link = EXCLUDED.link,
                            publish_time = EXCLUDED.publish_time,
                            news_type = EXCLUDED.news_type,
                            thumbnail = EXCLUDED.thumbnail,
                            related_tickers = EXCLUDED.related_tickers
                        """,
                        news_items
                    )
                    
                    logging.info(f"Inserted {len(news_items)} news items for {orig_sym}")
                
                conn.commit()
                processed += 1
                logging.info(f"Successfully processed news for {orig_sym}")
                
            except Exception as e:
                logging.error(f"Failed to process news for {orig_sym}: {str(e)}")
                failed.append(orig_sym)
                conn.rollback()
        
        del batch
        gc.collect()
        log_mem(f"Batch {batch_idx+1} end")
        time.sleep(PAUSE)
    
    return total, processed, failed

# -------------------------------
# Entrypoint
# -------------------------------
if __name__ == "__main__":
    log_mem("startup")
    
    # Connect to DB
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Create news table if it doesn't exist
    logging.info("Creating stock_news table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_news (
            id SERIAL PRIMARY KEY,
            uuid VARCHAR(255) UNIQUE NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            title TEXT NOT NULL,
            publisher VARCHAR(255),
            link TEXT,
            publish_time TIMESTAMP,
            news_type VARCHAR(100),
            thumbnail TEXT,
            related_tickers JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (ticker) REFERENCES company_profile(ticker) ON DELETE CASCADE
        );
    """)
    
    # Create indexes for better performance
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_news_ticker ON stock_news(ticker);
        CREATE INDEX IF NOT EXISTS idx_stock_news_publish_time ON stock_news(publish_time DESC);
        CREATE INDEX IF NOT EXISTS idx_stock_news_uuid ON stock_news(uuid);
        CREATE INDEX IF NOT EXISTS idx_stock_news_publisher ON stock_news(publisher);
    """)
    
    conn.commit()
    
    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, p_s, f_s = load_news_data(stock_syms, cur, conn)
    
    # Load ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols ORDER BY symbol;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, p_e, f_e = load_news_data(etf_syms, cur, conn)
    
    # Clean up old news (keep only last 30 days)
    logging.info("Cleaning up old news data...")
    cleanup_date = datetime.now() - timedelta(days=30)
    cur.execute("""
        DELETE FROM stock_news 
        WHERE publish_time < %s OR publish_time IS NULL
    """, (cleanup_date,))
    
    deleted_count = cur.rowcount
    logging.info(f"Deleted {deleted_count} old news items")
    
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
    logging.info(f"Stocks — total: {t_s}, processed: {p_s}, failed: {len(f_s)}")
    logging.info(f"ETFs   — total: {t_e}, processed: {p_e}, failed: {len(f_e)}")
    
    if f_s:
        logging.warning(f"Failed stock symbols: {f_s[:10]}{'...' if len(f_s) > 10 else ''}")
    if f_e:
        logging.warning(f"Failed ETF symbols: {f_e[:10]}{'...' if len(f_e) > 10 else ''}")
    
    cur.close()
    conn.close()
    logging.info("News loading complete.")
