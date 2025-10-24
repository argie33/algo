#!/usr/bin/env python3
"""
Analyst Sentiment Data Loader for yfinance
Extracts analyst consensus ratings, price targets, and calculates rating distribution
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
            logging.error(f"Failed to get secrets from AWS: {e}")
            raise

    # Local mode - use environment variables
    logging.info("Using local database configuration from environment variables")
    return {
        "host":   os.environ.get("DB_HOST", "localhost"),
        "port":   int(os.environ.get("DB_PORT", 5432)),
        "user":   os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", "password"),
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
    Estimate rating distribution from average rating and analyst count.
    Ratings: 1=Strong Buy, 2=Buy, 3=Hold, 4=Sell, 5=Strong Sell
    """
    if not numeric_rating or analyst_count <= 0:
        return 0, 0, analyst_count, 0, 0

    # Distribute analysts across rating buckets based on average rating
    # This is an approximation since we don't have the actual distribution
    strong_buy = int(analyst_count * max(0, (2.0 - numeric_rating) / 4.0))
    buy = int(analyst_count * max(0, (3.0 - numeric_rating) / 4.0))
    hold = analyst_count - strong_buy - buy - int(analyst_count * max(0, (numeric_rating - 3.0) / 4.0)) - int(analyst_count * max(0, (numeric_rating - 4.0) / 4.0))
    sell = int(analyst_count * max(0, (numeric_rating - 3.0) / 4.0))
    strong_sell = int(analyst_count * max(0, (numeric_rating - 4.0) / 4.0))

    # Ensure we use all analysts
    total = strong_buy + buy + hold + sell + strong_sell
    if total != analyst_count:
        hold += analyst_count - total

    return strong_buy, buy, hold, sell, strong_sell

def fetch_analyst_data(symbol):
    """Fetch analyst sentiment data from yfinance."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        # Extract analyst data fields
        analyst_count = info.get("numberOfAnalystOpinions", 0)
        avg_rating_str = info.get("averageAnalystRating")
        target_mean = info.get("targetMeanPrice")

        if analyst_count == 0 and not avg_rating_str and not target_mean:
            return None

        numeric_rating, rating_name = parse_rating(avg_rating_str)

        return {
            "analyst_count": analyst_count or 0,
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
            ticker = yf.Ticker(symbol)
            current_price = ticker.info.get("currentPrice") or ticker.info.get("regularMarketPrice")
        except:
            current_price = None

        # Calculate price target vs current
        price_target_vs_current = None
        if data["target_mean"] and current_price:
            try:
                price_target_vs_current = ((float(data["target_mean"]) / float(current_price)) - 1.0) * 100
            except:
                pass

        row = [
            symbol,
            datetime.now().date(),
            data["numeric_rating"],
            data["analyst_count"],
            data["target_mean"],
            price_target_vs_current,
            strong_buy,
            buy,
            hold,
            sell,
            strong_sell,
            0,  # upgrades_last_30d (from upgrade/downgrade table)
            0,  # downgrades_last_30d (from upgrade/downgrade table)
            0,  # eps_revisions_up_last_30d
            0,  # eps_revisions_down_last_30d
        ]

        # Insert with UPSERT
        sql = """
            INSERT INTO analyst_sentiment_analysis
            (symbol, date, recommendation_mean, total_analysts, avg_price_target,
             price_target_vs_current, strong_buy_count, buy_count, hold_count,
             sell_count, strong_sell_count, upgrades_last_30d, downgrades_last_30d,
             eps_revisions_up_last_30d, eps_revisions_down_last_30d)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, date) DO UPDATE SET
                recommendation_mean = EXCLUDED.recommendation_mean,
                total_analysts = EXCLUDED.total_analysts,
                avg_price_target = EXCLUDED.avg_price_target,
                price_target_vs_current = EXCLUDED.price_target_vs_current,
                strong_buy_count = EXCLUDED.strong_buy_count,
                buy_count = EXCLUDED.buy_count,
                hold_count = EXCLUDED.hold_count,
                sell_count = EXCLUDED.sell_count,
                strong_sell_count = EXCLUDED.strong_sell_count
        """

        try:
            cur.execute(sql, row)
            conn.commit()
            inserted += 1
            if data["analyst_count"] > 0:
                logging.info(f"{symbol}: {data['analyst_count']} analysts, avg rating {data['numeric_rating']}")
        except Exception as e:
            logging.error(f"Failed to insert {symbol}: {e}")
            conn.rollback()
            failed.append(symbol)

        gc.collect()
        time.sleep(0.02)  # Rate limiting

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
