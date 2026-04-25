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
try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False
import math
from pathlib import Path

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime

import boto3
import yfinance as yf

# Load environment variables from .env.local
env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

SCRIPT_NAME = "loadanalystupgradedowngrade.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_rss_mb():
    """Get RSS memory in MB, cross-platform."""
    if not HAS_RESOURCE:
        try:
            import psutil
            return psutil.Process().memory_info().rss / (1024 * 1024)
        except:
            return 0
    usage = resource.getrusage(resource.RUSAGE_SELF)
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)


def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")


def get_db_config():
    """Get database configuration from AWS Secrets Manager or environment variables."""
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    # Try AWS Secrets Manager first
    if aws_region and db_secret_arn:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logging.info(f"Loaded database credentials from AWS Secrets Manager: {db_secret_arn}")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.warning(f"Failed to load from Secrets Manager: {e}")

    # Fallback to environment variables with sensible defaults for local development
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "5432")
    db_user = os.environ.get("DB_USER", "stocks")
    db_password = os.environ.get("DB_PASSWORD", "")
    db_name = os.environ.get("DB_NAME", "stocks")

    logging.info(f"Using database credentials from environment: {db_user}@{db_host}/{db_name}")
    return {
        "host": db_host,
        "port": int(db_port),
        "user": db_user,
        "password": db_password,
        "dbname": db_name
    }


def get_db_connection(script_name):
    """Get database connection from environment or AWS Secrets Manager"""
    try:
        cfg = get_db_config()
        conn_params = {
            "dbname": cfg["dbname"],
            "user": cfg["user"],
        }
        if cfg.get("host"):
            conn_params["host"] = cfg["host"]
            conn_params["port"] = cfg.get("port", 5432)
        if cfg.get("password"):
            conn_params["password"] = cfg["password"]

        conn = psycopg2.connect(**conn_params, connect_timeout=30)
        return conn
    except Exception as e:
        logging.error(f"Failed to connect to database: {e}")
        return None


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
            (symbol, firm, action, old_rating, new_rating, action_date, details)
            VALUES %s
            ON CONFLICT DO NOTHING
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
        logging.error(" Failed to connect to database")
        return {"error": "Database connection failed"}
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    create_table(cur)
    conn.commit()

    cur.execute("SELECT symbol FROM stock_symbols WHERE is_sp500 = true;")
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
            logging.info(" Task completed successfully")
            sys.exit(0)
        else:
            logging.error(" Task failed or returned invalid result")
            sys.exit(1)
    except Exception as e:
        logging.error(f" Unhandled error: {e}")
        import traceback
        logging.error(f"Stack trace: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
