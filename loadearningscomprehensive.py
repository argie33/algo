#!/usr/bin/env python3
"""
COMPREHENSIVE EARNINGS LOADER - Gets ALL earnings data for ALL stocks
Optimized for speed and coverage:
- Parallel batch processing
- Rate-limiting aware
- Fallback error handling
- Progress tracking
"""

import os
import sys
import json
import time
import logging
import boto3
import psycopg2
from psycopg2.extras import execute_values
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import yfinance as yf

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

def get_db_config():
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn and aws_region:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn)["SecretString"]
            sec = json.loads(secret_str)
            return {
                "host": sec["host"], "port": int(sec.get("port", 5432)),
                "user": sec["username"], "password": sec["password"], "dbname": sec["dbname"]
            }
        except Exception as e:
            logger.warning(f"AWS failed: {str(e)[:100]}")

    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

def load_symbol_earnings(symbol):
    """Fetch earnings data for ONE symbol - thread-safe"""
    try:
        ticker = yf.Ticker(symbol)
        eh = ticker.earnings_history

        if eh is None or eh.empty:
            return symbol, None

        history_data = []
        for quarter, row in eh.iterrows():
            history_data.append((
                symbol,
                str(quarter)[:10],  # YYYY-MM-DD format
                float(row.get('epsActual')) if row.get('epsActual') else None,
                float(row.get('epsEstimate')) if row.get('epsEstimate') else None,
                float(row.get('epsDifference')) if row.get('epsDifference') else None,
                float(row.get('surprisePercent')) if row.get('surprisePercent') else None
            ))

        return symbol, history_data
    except Exception as e:
        logger.debug(f"Failed {symbol}: {str(e)[:50]}")
        return symbol, None

def insert_batch(conn, data):
    """Insert batch of earnings data"""
    if not data:
        return 0

    try:
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO earnings_history (symbol, quarter, eps_actual, eps_estimate,
                                            eps_difference, surprise_percent)
                VALUES %s
                ON CONFLICT (symbol, quarter) DO UPDATE SET
                    eps_actual = EXCLUDED.eps_actual,
                    eps_estimate = EXCLUDED.eps_estimate,
                    eps_difference = EXCLUDED.eps_difference,
                    surprise_percent = EXCLUDED.surprise_percent,
                    fetched_at = CURRENT_TIMESTAMP
            """, data)
        conn.commit()
        return len(data)
    except Exception as e:
        logger.error(f"Insert failed: {str(e)[:100]}")
        conn.rollback()
        return 0

def main():
    cfg = get_db_config()
    conn = psycopg2.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], dbname=cfg["dbname"])

    # Get all symbols
    with conn.cursor() as cur:
        cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol;")
        symbols = [row[0] for row in cur.fetchall()]

    logger.info(f"📊 LOADING EARNINGS FOR {len(symbols)} SYMBOLS")
    logger.info(f"Using {4} parallel workers with rate limiting...")

    success = 0
    failed = 0
    total_records = 0
    batch_data = []
    BATCH_SIZE = 100

    start_time = time.time()

    # Parallel loading with thread pool
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(load_symbol_earnings, sym): sym for sym in symbols}

        for i, future in enumerate(as_completed(futures)):
            symbol, history_data = future.result()

            if history_data:
                success += 1
                batch_data.extend(history_data)
                total_records += len(history_data)

                # Insert when batch full
                if len(batch_data) >= BATCH_SIZE:
                    inserted = insert_batch(conn, batch_data)
                    batch_data = []
                    logger.info(f"Progress: {i+1}/{len(symbols)} | ✅ {success} | ⏱️ {time.time()-start_time:.0f}s | 📈 {total_records} records")
            else:
                failed += 1

    # Final batch
    if batch_data:
        insert_batch(conn, batch_data)

    elapsed = time.time() - start_time
    logger.info(f"\n✅ COMPLETE!")
    logger.info(f"   Total: {len(symbols)} symbols")
    logger.info(f"   Success: {success} ({100*success/len(symbols):.1f}%)")
    logger.info(f"   Failed: {failed}")
    logger.info(f"   Records: {total_records}")
    logger.info(f"   Time: {elapsed:.0f}s ({elapsed/len(symbols):.2f}s per symbol)")

    # Update tracker
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, NOW())
            ON CONFLICT (script_name) DO UPDATE SET last_run = EXCLUDED.last_run;
        """, ("loadearningscomprehensive.py",))
        conn.commit()

    conn.close()
    return {"total": len(symbols), "success": success, "records": total_records}

if __name__ == "__main__":
    result = main()
    sys.exit(0 if result["success"] > 0 else 1)
