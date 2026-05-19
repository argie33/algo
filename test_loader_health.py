#!/usr/bin/env python3
"""
Test loader health: verify all critical tables exist and can be queried.
This identifies what data is missing and what loaders need to run.
"""

import logging
import sys
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Critical tables needed by Phase 1 and orchestrator
CRITICAL_TABLES = {
    'price_daily': {'date_column': 'date', 'sla_days': 1},
    'technical_data_daily': {'date_column': 'date', 'sla_days': 1},
    'market_health_daily': {'date_column': 'date', 'sla_days': 1},
    'trend_template_data': {'date_column': 'date', 'sla_days': 1},
    'signal_quality_scores': {'date_column': 'date', 'sla_days': 1},
    'buy_sell_daily': {'date_column': 'date', 'sla_days': 1},
    'stock_scores': {'date_column': 'date', 'sla_days': 1},
    'sector_ranking': {'date_column': 'date', 'sla_days': 1},
    'industry_ranking': {'date_column': 'date', 'sla_days': 1},
    'swing_trader_scores': {'date_column': 'date', 'sla_days': 1},
}

# Optional enrichment tables (API uses these but Phase 1 doesn't require them)
OPTIONAL_TABLES = {
    'fear_greed_index': {'date_column': 'date', 'sla_days': 7},
    'analyst_sentiment_analysis': {'date_column': 'date', 'sla_days': 7},
    'economic_data': {'date_column': 'date', 'sla_days': 7},
    'aaii_sentiment': {'date_column': 'date', 'sla_days': 7},
    'naaim': {'date_column': 'date', 'sla_days': 7},
}

def test_loader_health():
    """Check if all tables exist and have recent data."""
    try:
        from utils.db_connection import get_db_connection
    except ImportError:
        logger.error("Cannot import db_connection. Set up environment first: python3 init_database.py")
        return False

    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as e:
        logger.error(f"Cannot connect to database: {e}")
        logger.error("Make sure PostgreSQL is running and DB_* environment variables are set")
        return False

    logger.info("\n" + "="*70)
    logger.info("CRITICAL TABLES (Required for trading)")
    logger.info("="*70)

    critical_ok = True
    for table, config in CRITICAL_TABLES.items():
        date_col = config['date_column']
        sla_days = config['sla_days']
        cutoff = datetime.now() - timedelta(days=sla_days)

        try:
            cur.execute(f"SELECT COUNT(*), MAX({date_col}) FROM {table}")
            count, max_date = cur.fetchone()

            if count == 0:
                logger.error(f"❌ {table:30} | EMPTY (0 rows)")
                critical_ok = False
            elif max_date and max_date.replace(tzinfo=None) < cutoff:
                logger.warning(f"⚠️  {table:30} | STALE (latest: {max_date.date()}, need < {sla_days}d old)")
                critical_ok = False
            else:
                logger.info(f"✅ {table:30} | OK ({count:,} rows, latest: {max_date.date() if max_date else 'N/A'})")
        except Exception as e:
            logger.error(f"❌ {table:30} | ERROR: {str(e)[:50]}")
            critical_ok = False

    logger.info("\n" + "="*70)
    logger.info("OPTIONAL TABLES (For API enrichment)")
    logger.info("="*70)

    for table, config in OPTIONAL_TABLES.items():
        date_col = config['date_column']
        sla_days = config['sla_days']
        cutoff = datetime.now() - timedelta(days=sla_days)

        try:
            cur.execute(f"SELECT COUNT(*), MAX({date_col}) FROM {table}")
            count, max_date = cur.fetchone()

            if count == 0:
                logger.warning(f"⚠️  {table:30} | EMPTY (0 rows) - Run loader to enable feature")
            elif max_date and max_date.replace(tzinfo=None) < cutoff:
                logger.warning(f"⚠️  {table:30} | STALE (latest: {max_date.date()})")
            else:
                logger.info(f"✅ {table:30} | OK ({count:,} rows, latest: {max_date.date() if max_date else 'N/A'})")
        except Exception as e:
            logger.debug(f"ℹ️  {table:30} | Not yet created (will be created by loader)")

    cur.close()
    conn.close()

    logger.info("\n" + "="*70)
    if critical_ok:
        logger.info("✅ ALL CRITICAL TABLES OK - Orchestrator can run")
    else:
        logger.info("❌ CRITICAL TABLES MISSING/STALE - Run: python3 run-all-loaders.py")
    logger.info("="*70 + "\n")

    return critical_ok

if __name__ == '__main__':
    success = test_loader_health()
    sys.exit(0 if success else 1)
