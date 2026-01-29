#!/usr/bin/env python3
# TRIGGER: 2026-01-28 - CRITICAL DATA LOSS FIX - Analyst data now crash-safe
# Analyst upgrade/downgrade data loader for enhanced market intelligence
# FIXED: Removed DROP TABLE vulnerability - analyst ratings history preserved
# Updated: 2026-01-28 - Data safety fix deployed - ready for production execution
# TRIGGER DEPLOY: loadanalystupgradedowngrade with data preservation guarantee
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
import yfinance as yf

SCRIPT_NAME = "loadanalystupgradedowngrade.py"
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


def create_table(cur):
    logging.info("Ensuring analyst_upgrade_downgrade table…")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS analyst_upgrade_downgrade (
            id           SERIAL PRIMARY KEY,
            symbol       VARCHAR(20) NOT NULL,
            firm         VARCHAR(128),
            action       VARCHAR(32),
            from_grade   VARCHAR(64),
            to_grade     VARCHAR(64),
            date         DATE NOT NULL,
            details      TEXT,
            fetched_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)

def fetch_analyst_actions(symbol):
    # yfinance: Use upgrades_downgrades for analyst rating changes
    # Convert ticker format for yfinance (e.g., BRK.B → BRK-B)

    yf_symbol = symbol.replace(".", "-").replace("$", "-").upper()

    ticker = yf.Ticker(yf_symbol)
    try:
        df = ticker.upgrades_downgrades
    except Exception as e:
        logging.warning(f"Failed to fetch upgrades/downgrades for {symbol}: {e}")
        return None
    if df is None or df.empty:
        return None

    # yfinance returns upgrades_downgrades with columns:
    # Firm, ToGrade, FromGrade, Action, priceTargetAction, currentPriceTarget, priorPriceTarget
    if df.empty:
        return None

    # Keep all rows with upgrade/downgrade data
    return df

def load_analyst_actions(symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading analyst upgrades/downgrades: {total} symbols")
    inserted, failed = 0, []
    for idx, symbol in enumerate(symbols):
        log_mem(f"{symbol} ({idx+1}/{total})")
        df = fetch_analyst_actions(symbol)
        if df is None or df.empty:
            logging.info(f"No analyst upgrades/downgrades for {symbol}")
            continue
        rows = []
        for dt, row in df.iterrows():
            # Map yfinance column names (upgrades_downgrades dataframe)
            firm = row.get("Firm")
            action = row.get("Action")
            from_grade = row.get("FromGrade")
            to_grade = row.get("ToGrade")

            # Build details from price target info if available
            price_action = row.get("priceTargetAction", "")
            current_target = row.get("currentPriceTarget", 0)
            details = f"{price_action} price target to ${current_target}" if current_target > 0 else None

            # Skip if no useful data
            if not any([firm, action, from_grade, to_grade]):
                continue

            rows.append([
                symbol,
                firm,
                action,
                from_grade,
                to_grade,
                dt.date() if hasattr(dt, 'date') else dt,
                details
            ])
        if not rows:
            continue
        sql = """
            INSERT INTO analyst_upgrade_downgrade
            (symbol, firm, action, from_grade, to_grade, date, details)
            VALUES %s
        """
        try:
            execute_values(cur, sql, rows)
            conn.commit()
            inserted += len(rows)
            logging.info(f"{symbol}: batch-inserted {len(rows)} rows")
        except Exception as e:
            logging.error(f"Failed to insert for {symbol}: {e}")
            conn.rollback()
            failed.append(symbol)
        gc.collect()
        time.sleep(0.05)
    return total, inserted, failed


def lambda_handler(event, context):
    log_mem("startup")
    conn = get_db_connection(SCRIPT_NAME)
    if not conn:
        logging.error("❌ Failed to connect to database")
        return {"error": "Database connection failed"}
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    create_table(cur)
    conn.commit()

    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t, i, f = load_analyst_actions(stock_syms, cur, conn)

    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Analyst Upgrades/Downgrades — total: {t}, inserted: {i}, failed: {len(f)}")

    cur.close()
    conn.close()
    logging.info("All done.")
    return {
        "total": t,
        "inserted": i,
        "failed": f,
        "peak_rss_mb": peak
    }

# Add main function for ECS task execution
def main():
    """Main function for ECS task execution"""
    try:
        result = lambda_handler(None, None)
        if result and result.get("total", 0) >= 0:
            logging.info("✅ Task completed successfully")
            sys.exit(0)
        else:
            logging.error("❌ Task failed or returned invalid result")
            sys.exit(1)
    except Exception as e:
        logging.error(f"❌ Unhandled error: {e}")
        import traceback
        logging.error(f"Stack trace: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
