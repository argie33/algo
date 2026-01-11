#!/usr/bin/env python3
# FORCE REBUILD TRIGGER: 20260107-220000-AWS-ECS - Ensure analyst sentiment images built
"""
Analyst Sentiment Data Loader for yfinance
Extracts analyst consensus ratings, price targets, and calculates rating distribution
Works with AWS Lambda/RDS via Secrets Manager and local PostgreSQL via environment variables
"""
import sys
import time
import logging
import json
import os
import gc
import resource

import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

import boto3
import yfinance as yf
from db_helper import get_db_connection

SCRIPT_NAME = "loadanalystsentiment.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

def get_db_config():
    """Get database configuration from local env or AWS Secrets Manager."""
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    # AWS mode - use Secrets Manager
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
            logging.warning(f"Failed to get secrets from AWS: {e}, falling back to environment variables")

    # Local mode - use environment variables
    logging.info("Using local database configuration from environment variables")
    return {
        "host":   os.environ.get("DB_HOST", "localhost"),
        "port":   int(os.environ.get("DB_PORT", 5432)),
        "user":   os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", "bed0elAn"),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

def parse_rating(rating_str):
    """
    Parse averageAnalystRating string like "2.0 - Buy" into numeric rating.
    Returns tuple: (numeric_rating, rating_name)
    """
    if not rating_str:
        return None, None

    try:
        # Extract numeric part before " - "
        parts = str(rating_str).split(" - ")
        if len(parts) >= 1:
            numeric = float(parts[0].strip())
            name = parts[1].strip() if len(parts) > 1 else "Unknown"
            return numeric, name
    except (ValueError, AttributeError):
        pass

    return None, None

def calculate_rating_distribution(numeric_rating, analyst_count):
    """
    Estimate analyst rating distribution from average rating.

    Ratings: 1=Strong Buy, 2=Buy, 3=Hold, 4=Sell, 5=Strong Sell

    Since yfinance only provides average rating (1.0-5.0), we estimate the
    distribution using: bullish = analysts where rating <= 2.5, neutral = rating 2.5-3.5, bearish = rating > 3.5

    Returns: (strong_buy, buy, hold, sell, strong_sell) estimated counts
    """
    if numeric_rating is None or analyst_count is None or analyst_count == 0:
        return 0, 0, 0, 0, 0

    analyst_count = int(analyst_count)

    # Simple linear mapping based on where average rating falls
    if numeric_rating <= 1.5:
        # Mostly strong buy + buy
        bullish = analyst_count
        neutral = 0
        bearish = 0
    elif numeric_rating <= 2.5:
        # Mixed bullish/neutral
        bullish = int(analyst_count * (2.5 - numeric_rating) / 1.0)  # Weights from 1.5 to 2.5
        neutral = analyst_count - bullish
        bearish = 0
    elif numeric_rating <= 3.5:
        # Mixed neutral/bearish
        neutral = int(analyst_count * (3.5 - numeric_rating) / 1.0)  # Weights from 2.5 to 3.5
        bullish = 0
        bearish = analyst_count - neutral
    else:
        # Mostly bearish
        neutral = 0
        bullish = 0
        bearish = analyst_count

    # Distribute bullish among strong_buy + buy
    strong_buy = bullish // 2
    buy = bullish - strong_buy

    # Keep hold as neutral
    hold = neutral

    # Distribute bearish among sell + strong_sell
    sell = bearish // 2
    strong_sell = bearish - sell

    return strong_buy, buy, hold, sell, strong_sell

def fetch_analyst_data(symbol):
    """Fetch analyst sentiment data from yfinance. Returns None if no real data available."""
    try:
        # Convert ticker format for yfinance (e.g., BRK.B → BRK-B)
        yf_symbol = symbol.replace('.', '-').replace('$', '-').upper()
        ticker = yf.Ticker(yf_symbol)
        info = ticker.info

        # Extract analyst data fields - NO FAKE DEFAULTS
        analyst_count = info.get("numberOfAnalystOpinions")  # None if missing (not fake 0)
        avg_rating_str = info.get("averageAnalystRating")
        target_mean = info.get("targetMeanPrice")

        # Only return data if we have REAL analyst information
        if analyst_count is None and not avg_rating_str and not target_mean:
            return None

        numeric_rating, rating_name = parse_rating(avg_rating_str)

        return {
            "analyst_count": analyst_count,  # Real count or None (not fake 0)
            "numeric_rating": numeric_rating,
            "rating_name": rating_name,
            "target_mean": target_mean,
            "target_high": info.get("targetHighPrice"),
            "target_low": info.get("targetLowPrice"),
            "target_median": info.get("targetMedianPrice"),
        }
    except Exception as e:
        logging.warning(f"Failed to fetch analyst data for {symbol}: {e}")
        return None

def load_analyst_sentiment(symbols, cur, conn):
    """Load analyst sentiment data for all symbols."""
    total = len(symbols)
    logging.info(f"Loading analyst sentiment data for {total} symbols")
    inserted, failed, no_data = 0, [], 0

    for idx, symbol in enumerate(symbols):
        if idx % 100 == 0:
            log_mem(f"Processing {symbol} ({idx+1}/{total})")

        data = fetch_analyst_data(symbol)

        if data is None:
            no_data += 1
            continue

        # Calculate rating distribution
        strong_buy, buy, hold, sell, strong_sell = calculate_rating_distribution(
            data["numeric_rating"],
            data["analyst_count"]
        )

        # Get current price for target comparison
        try:
            yf_symbol = symbol.replace('.', '-').replace('$', '-').upper()
            ticker2 = yf.Ticker(yf_symbol)
            current_price = ticker2.info.get("currentPrice") or ticker2.info.get("regularMarketPrice")
        except Exception as e:
            logging.warning(f"Failed to fetch current price for {symbol} from yfinance: {str(e)}")
            current_price = None

        # Calculate price target vs current
        upside_downside_percent = None
        if data["target_mean"] and current_price:
            try:
                upside_downside_percent = ((float(data["target_mean"]) / float(current_price)) - 1.0) * 100
            except Exception as e:
                logging.warning(f"Failed to calculate upside/downside for {symbol}: {str(e)}")
                pass

        # Map to table columns: bullish_count, neutral_count, bearish_count
        # If rating is available, use estimated distribution; otherwise leave NULL
        if data["numeric_rating"] is not None:
            bullish_count = strong_buy + buy  # Combine strong buy + buy
            neutral_count = hold
            bearish_count = strong_sell + sell  # Combine sell + strong sell
        else:
            # No rating available - leave counts as NULL
            bullish_count = None
            neutral_count = None
            bearish_count = None

        row = [
            symbol,
            datetime.now().date(),
            bullish_count,      # bullish_count (estimated from average rating)
            neutral_count,      # neutral_count (estimated from average rating)
            bearish_count,      # bearish_count (estimated from average rating)
            data["analyst_count"],  # total_analysts
            data["target_mean"],    # target_price
            current_price,          # current_price
            upside_downside_percent  # upside_downside_percent
        ]

        # Insert analyst sentiment data (fresh load, no conflicts expected)
        sql = """
            INSERT INTO analyst_sentiment_analysis
            (symbol, date_recorded, bullish_count, neutral_count, bearish_count,
             total_analysts, target_price, current_price, upside_downside_percent)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        try:
            cur.execute(sql, row)
            conn.commit()
            inserted += 1
            if data["analyst_count"] is not None and data["analyst_count"] > 0:
                logging.info(f"{symbol}: {data['analyst_count']} analysts, avg rating {data['numeric_rating']}")
        except Exception as e:
            logging.error(f"Failed to insert {symbol}: {e}")
            conn.rollback()
            failed.append(symbol)

        gc.collect()
        time.sleep(1)  # Rate limiting - 1 second delay per symbol to avoid yfinance rate limits

    return total, inserted, no_data, failed

def lambda_handler(event, context):
    """Main handler for Lambda execution."""
    log_mem("startup")
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor()

    # Get all symbols
    cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol;")
    symbols = [r[0] for r in cur.fetchall()]

    # Load analyst sentiment data
    total, inserted, no_data, failed = load_analyst_sentiment(symbols, cur, conn)

    # Update last_updated
    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Analyst Sentiment — total: {total}, inserted: {inserted}, no_data: {no_data}, failed: {len(failed)}")

    cur.close()
    conn.close()
    logging.info("✅ All done.")

    return {
        "total": total,
        "inserted": inserted,
        "no_data": no_data,
        "failed": failed,
        "peak_rss_mb": peak
    }

def main():
    """Main function for local/ECS execution."""
    try:
        result = lambda_handler(None, None)
        if result and result.get("total", 0) >= 0:
            logging.info("✅ Task completed successfully")
            sys.exit(0)
        else:
            logging.error("❌ Task failed")
            sys.exit(1)
    except Exception as e:
        logging.error(f"❌ Unhandled error: {e}")
        import traceback
        logging.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
