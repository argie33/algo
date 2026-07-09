#!/usr/bin/env python3
"""Diagnostic script to check ETF loader status and investigate staleness."""

import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Any

# Add project to path
sys.path.insert(0, '/c/Users/arger/code/algo')

def main():
    """Check ETF loader status."""
    from utils.db.context import DatabaseContext
    import logging

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    logger.info("=" * 80)
    logger.info("ETF LOADER STALENESS INVESTIGATION")
    logger.info("=" * 80)

    # Check ETF loader status
    try:
        with DatabaseContext("read") as cur:
            # 1. Check ETF loader status
            logger.info("\n[1] ETF Loader Status:")
            cur.execute("""
                SELECT
                    table_name,
                    status,
                    completion_pct,
                    row_count,
                    latest_date,
                    last_updated,
                    EXTRACT(EPOCH FROM (NOW() - last_updated)) / 3600 as hours_stale,
                    EXTRACT(EPOCH FROM (NOW() - execution_completed)) / 3600 as hours_since_completion,
                    symbol_count,
                    symbols_loaded,
                    error_message
                FROM data_loader_status
                WHERE table_name LIKE 'etf_price_%'
                ORDER BY last_updated DESC
            """)

            etf_status = cur.fetchall()
            if etf_status:
                for row in etf_status:
                    logger.info(f"\n  Table: {row['table_name']}")
                    logger.info(f"    Status: {row['status']}")
                    logger.info(f"    Completion: {row['completion_pct']}%")
                    logger.info(f"    Row count: {row['row_count']}")
                    logger.info(f"    Latest date: {row['latest_date']}")
                    logger.info(f"    Last updated: {row['last_updated']}")
                    logger.info(f"    Hours stale: {row['hours_stale']:.1f}")
                    logger.info(f"    Hours since completion: {row['hours_since_completion']:.1f}")
                    logger.info(f"    Symbol coverage: {row['symbols_loaded']}/{row['symbol_count']}")
                    if row['error_message']:
                        logger.info(f"    Error: {row['error_message'][:200]}")
            else:
                logger.warning("  No ETF loader status records found!")

            # 2. Check stock price loader status (should be recent)
            logger.info("\n[2] Stock Price Loader Status (for comparison):")
            cur.execute("""
                SELECT
                    table_name,
                    status,
                    completion_pct,
                    row_count,
                    latest_date,
                    last_updated,
                    EXTRACT(EPOCH FROM (NOW() - last_updated)) / 3600 as hours_stale
                FROM data_loader_status
                WHERE table_name LIKE 'price_%'
                ORDER BY last_updated DESC
                LIMIT 3
            """)

            stock_status = cur.fetchall()
            for row in stock_status:
                logger.info(f"\n  Table: {row['table_name']}")
                logger.info(f"    Status: {row['status']}")
                logger.info(f"    Completion: {row['completion_pct']}%")
                logger.info(f"    Last updated: {row['last_updated']} ({row['hours_stale']:.1f}h ago)")

            # 3. Check if ETF tables have any data
            logger.info("\n[3] ETF Table Data:")
            cur.execute("""
                SELECT
                    'etf_price_daily' as table_name,
                    COUNT(*) as row_count,
                    MAX(date) as latest_date,
                    COUNT(DISTINCT symbol) as symbols
                FROM etf_price_daily
                UNION ALL
                SELECT
                    'etf_price_weekly',
                    COUNT(*),
                    MAX(date),
                    COUNT(DISTINCT symbol)
                FROM etf_price_weekly
                UNION ALL
                SELECT
                    'etf_price_monthly',
                    COUNT(*),
                    MAX(date),
                    COUNT(DISTINCT symbol)
                FROM etf_price_monthly
            """)

            for row in cur.fetchall():
                logger.info(f"\n  Table: {row['table_name']}")
                logger.info(f"    Rows: {row['row_count']}")
                logger.info(f"    Unique symbols: {row['symbols']}")
                logger.info(f"    Latest date: {row['latest_date']}")

            # 4. Check EventBridge rule state
            logger.info("\n[4] Checking EventBridge Schedule Configuration:")
            cur.execute("""
                SELECT algo_config_key, config_value
                FROM algo_config
                WHERE algo_config_key LIKE '%etf%' OR algo_config_key LIKE '%stock_price%'
                ORDER BY algo_config_key
            """)

            config = cur.fetchall()
            if config:
                for row in config:
                    logger.info(f"  {row['algo_config_key']}: {row['config_value']}")
            else:
                logger.info("  No ETF/price-specific config found (using defaults)")

            # 5. Check for recent loader invocations (from logs perspective)
            logger.info("\n[5] Last 5 loader executions (any table):")
            cur.execute("""
                SELECT
                    table_name,
                    status,
                    last_updated,
                    EXTRACT(EPOCH FROM (NOW() - execution_started)) / 3600 as hours_since_start,
                    symbol_count
                FROM data_loader_status
                ORDER BY execution_started DESC
                LIMIT 5
            """)

            for row in cur.fetchall():
                logger.info(f"  {row['table_name']}: {row['status']} ({row['hours_since_start']:.1f}h ago) - {row['symbol_count']} symbols")

    except Exception as e:
        logger.error(f"Error checking database: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

    logger.info("\n" + "=" * 80)
    logger.info("DIAGNOSIS COMPLETE")
    logger.info("=" * 80)

    return 0

if __name__ == "__main__":
    sys.exit(main())
