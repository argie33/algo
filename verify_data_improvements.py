#!/usr/bin/env python3
"""
Verify Data Improvements - Validate that loader fixes worked

After loaddailycompanydata.py and loadstockscores.py complete:
1. Check stock scores were loaded for all stocks
2. Verify debt_to_equity improvements (fewer missing values)
3. Verify quality scores are being calculated
"""

import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_db_config():
    """Get database configuration - works in AWS, locally via socket, or with env vars"""
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn:
        import boto3
        secret_str = boto3.client("secretsmanager").get_secret_value(
            SecretId=db_secret_arn
        )["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"],
        }

    # Try local socket connection first (peer authentication)
    try:
        test_conn = psycopg2.connect(
            dbname=os.environ.get("DB_NAME", "stocks"),
            user="stocks"
        )
        test_conn.close()
        return {
            "host": None,
            "user": "stocks",
            "password": None,
            "dbname": os.environ.get("DB_NAME", "stocks"),
        }
    except:
        pass

    # Fall back to environment variables
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", "password"),
        "dbname": os.environ.get("DB_NAME", "stocks"),
    }


def connect_db():
    """Connect to database"""
    cfg = get_db_config()

    connect_params = {
        "dbname": cfg["dbname"],
        "user": cfg["user"],
    }

    if cfg.get("host"):
        connect_params["host"] = cfg["host"]
        connect_params["port"] = cfg.get("port", 5432)

    if cfg.get("password"):
        connect_params["password"] = cfg["password"]

    return psycopg2.connect(**connect_params)


def verify_stock_scores():
    """Verify stock scores were loaded"""
    conn = connect_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    logging.info("=" * 70)
    logging.info("VERIFICATION 1: Stock Scores")
    logging.info("=" * 70)

    # Check total loaded
    cur.execute("SELECT COUNT(*) as count FROM stock_scores WHERE composite_score IS NOT NULL")
    result = cur.fetchone()
    loaded = result['count'] if result else 0

    logging.info(f"✅ Stock scores loaded: {loaded}/5,297 ({100*loaded/5297:.1f}%)")

    # Check components
    cur.execute("""
        SELECT
            COUNT(CASE WHEN composite_score IS NOT NULL THEN 1 END) as with_composite,
            COUNT(CASE WHEN momentum_score IS NOT NULL THEN 1 END) as with_momentum,
            COUNT(CASE WHEN growth_score IS NOT NULL THEN 1 END) as with_growth,
            COUNT(CASE WHEN quality_score IS NOT NULL THEN 1 END) as with_quality,
            COUNT(CASE WHEN stability_score IS NOT NULL THEN 1 END) as with_stability,
            COUNT(CASE WHEN positioning_score IS NOT NULL THEN 1 END) as with_positioning
        FROM stock_scores
    """)
    result = cur.fetchone()

    logging.info(f"   Momentum scores: {result['with_momentum']}")
    logging.info(f"   Growth scores: {result['with_growth']}")
    logging.info(f"   Quality scores: {result['with_quality']}")
    logging.info(f"   Stability scores: {result['with_stability']}")
    logging.info(f"   Positioning scores: {result['with_positioning']}")

    conn.close()


def verify_debt_to_equity():
    """Verify debt_to_equity improvements"""
    conn = connect_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    logging.info("")
    logging.info("=" * 70)
    logging.info("VERIFICATION 2: Debt to Equity - Data Gap Improvement")
    logging.info("=" * 70)

    # Check quality metrics coverage
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN debt_to_equity IS NOT NULL THEN 1 END) as has_de,
            COUNT(CASE WHEN de_source = 'CALCULATED' THEN 1 END) as calculated_de
        FROM quality_metrics
    """)
    result = cur.fetchone()

    total = result['total']
    has_de = result['has_de']
    calculated = result['calculated_de']

    logging.info(f"✅ Debt/Equity coverage: {has_de}/{total} ({100*has_de/total:.1f}%)")
    logging.info(f"   Previously missing: ~872 stocks")
    logging.info(f"   Now calculated: {calculated} stocks")
    logging.info(f"   New gap: {total - has_de} stocks ({100*(total-has_de)/total:.1f}%)")

    # Sample some calculated values
    cur.execute("""
        SELECT symbol, debt_to_equity, de_source
        FROM quality_metrics
        WHERE de_source = 'CALCULATED'
        LIMIT 5
    """)
    samples = cur.fetchall()

    if samples:
        logging.info("")
        logging.info("   Sample calculated values:")
        for row in samples:
            logging.info(f"      {row['symbol']}: {row['debt_to_equity']:.2f} ({row['de_source']})")

    conn.close()


def verify_roic():
    """Check ROIC coverage (for next enhancement)"""
    conn = connect_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    logging.info("")
    logging.info("=" * 70)
    logging.info("VERIFICATION 3: ROIC - Current Status (for future enhancement)")
    logging.info("=" * 70)

    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN return_on_invested_capital_pct IS NOT NULL THEN 1 END) as has_roic
        FROM factor_metrics
    """)
    result = cur.fetchone()

    if result:
        total = result['total']
        has_roic = result['has_roic']

        logging.info(f"ℹ️  ROIC coverage: {has_roic}/{total} ({100*has_roic/total:.1f}%)")
        logging.info(f"   Missing: {total - has_roic} stocks ({100*(total-has_roic)/total:.1f}%)")
        logging.info(f"   Potential improvement: Similar calculation approach as debt_to_equity")
    else:
        logging.info("   factor_metrics table not found or empty")

    conn.close()


def main():
    logging.info("")
    logging.info("🔍 Stock Data Quality Verification")
    logging.info(f"   Started: {datetime.now().isoformat()}")

    try:
        verify_stock_scores()
        verify_debt_to_equity()
        verify_roic()

        logging.info("")
        logging.info("=" * 70)
        logging.info("✅ Verification Complete")
        logging.info("=" * 70)

    except Exception as e:
        logging.error(f"❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
