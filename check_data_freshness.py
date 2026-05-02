#!/usr/bin/env python3
"""
Hourly Data Freshness Check - Runs every hour to verify data is current
Detects stale data immediately instead of waiting for manual discovery
"""

import os
import json
import logging
from datetime import datetime, timedelta
import psycopg2
from dotenv import load_dotenv
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

def get_db_config() -> dict:
    """Get database config from environment"""
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

def check_table_freshness(conn, table_name: str, date_column: str = "date") -> dict:
    """Check if table data is current"""
    try:
        cur = conn.cursor()

        # Get max date in table
        cur.execute(f"SELECT MAX({date_column}) FROM {table_name}")
        max_date = cur.fetchone()[0]

        if not max_date:
            return {
                "table": table_name,
                "status": "EMPTY",
                "max_date": None,
                "age_days": None,
                "fresh": False
            }

        age_days = (datetime.today().date() - max_date).days

        # Determine freshness
        if age_days == 0:
            status = "FRESH"
            fresh = True
        elif age_days == 1:
            status = "STALE_1DAY"
            fresh = True  # Acceptable (data loads may run after market close)
        elif age_days <= 3:
            status = "STALE"
            fresh = False  # Warning - data is 2-3 days old
        else:
            status = "VERY_STALE"
            fresh = False  # Alert - data is 3+ days old

        cur.close()

        return {
            "table": table_name,
            "status": status,
            "max_date": max_date.isoformat() if max_date else None,
            "age_days": age_days,
            "fresh": fresh
        }

    except Exception as e:
        return {
            "table": table_name,
            "status": "ERROR",
            "error": str(e),
            "fresh": False
        }

def run_freshness_check():
    """Run complete data freshness check"""
    logger.info("=" * 80)
    logger.info("DATA FRESHNESS CHECK - Hourly Monitor")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)

    # Tables to check
    tables_to_check = [
        ("price_daily", "date"),
        ("price_weekly", "date"),
        ("price_monthly", "date"),
        ("etf_price_daily", "date"),
        ("etf_price_weekly", "date"),
        ("etf_price_monthly", "date"),
        ("buy_sell_daily", "date"),
        ("buy_sell_weekly", "date"),
        ("buy_sell_monthly", "date"),
        ("technical_data_daily", "date"),
        ("earnings_history", "date"),
        ("stock_scores", "fetched_at"),
    ]

    try:
        db_config = get_db_config()
        conn = psycopg2.connect(**db_config)

        results = []
        stale_count = 0
        fresh_count = 0

        logger.info("\nCHECKING TABLES:\n")

        for table_name, date_col in tables_to_check:
            result = check_table_freshness(conn, table_name, date_col)
            results.append(result)

            status = result["status"]
            age = result.get("age_days", "?")

            if result["fresh"]:
                fresh_count += 1
                logger.info(f"  {table_name:30} FRESH ({age}d old)")
            else:
                stale_count += 1
                logger.warning(f"  {table_name:30} {status:15} ({age}d old)")

        conn.close()

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info(f"SUMMARY: {fresh_count} fresh | {stale_count} stale")
        logger.info("=" * 80)

        if stale_count > 0:
            logger.warning(f"\nALERT: {stale_count} tables have stale data. Check loader status.")
            return False
        else:
            logger.info("\nOK: All data is current")
            return True

    except Exception as e:
        logger.error(f"Freshness check failed: {e}")
        return False

if __name__ == "__main__":
    success = run_freshness_check()
    exit(0 if success else 1)
