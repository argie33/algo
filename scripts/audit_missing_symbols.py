#!/usr/bin/env python3
"""
Audit missing symbols from price_daily.
Identifies which tradable symbols have no price data and categorizes them.
"""

import logging
from datetime import datetime, timedelta
from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def audit_missing_symbols() -> None:
    """Audit missing symbols and categorize root causes."""

    with DatabaseContext("read") as cur:
        # Query 1: Which active symbols in stock_symbols have NO recent price_daily data?
        logger.info("[AUDIT] Query 1: Identifying symbols with missing price data...")
        cur.execute("""
            SELECT ss.symbol, ss.exchange, ss.active
            FROM stock_symbols ss
            LEFT JOIN price_daily pd ON ss.symbol = pd.symbol
                AND pd.date >= CURRENT_DATE - INTERVAL '30 days'
            WHERE pd.symbol IS NULL
            AND ss.active = TRUE
            ORDER BY ss.exchange, ss.symbol
        """)

        missing_active = cur.fetchall()
        logger.info(f"[AUDIT] Found {len(missing_active)} active symbols with no recent price data")

        # Query 2: Check if they're marked as delisted
        logger.info("[AUDIT] Query 2: Checking for delisted status...")
        cur.execute("""
            SELECT ss.symbol, ss.exchange, cis.delisting_date, cis.status
            FROM stock_symbols ss
            LEFT JOIN company_info_sec cis ON ss.symbol = cis.ticker
            WHERE ss.symbol IN (
                SELECT ss2.symbol
                FROM stock_symbols ss2
                LEFT JOIN price_daily pd ON ss2.symbol = pd.symbol
                    AND pd.date >= CURRENT_DATE - INTERVAL '30 days'
                WHERE pd.symbol IS NULL
                AND ss2.active = TRUE
            )
            ORDER BY ss.exchange, ss.symbol
        """)

        delisting_info = cur.fetchall()
        delisted_count = sum(1 for row in delisting_info if row[2] is not None)
        logger.info(f"[AUDIT] Of these, {delisted_count} have delisting_date in company_info_sec")

        # Query 3: Check technical_data_daily coverage
        logger.info("[AUDIT] Query 3: Checking technical_data_daily coverage...")
        cur.execute("""
            SELECT COUNT(DISTINCT symbol) as symbols_with_technical_data
            FROM technical_data_daily
            WHERE date >= CURRENT_DATE - INTERVAL '5 days'
        """)
        technical_coverage = cur.fetchone()
        logger.info(f"[AUDIT] technical_data_daily has {technical_coverage[0]} symbols with recent data")

        # Query 4: Coverage by exchange
        logger.info("[AUDIT] Query 4: Missing symbols by exchange...")
        cur.execute("""
            SELECT ss.exchange, COUNT(*) as missing_count,
                   COUNT(CASE WHEN cis.delisting_date IS NOT NULL THEN 1 END) as delisted
            FROM stock_symbols ss
            LEFT JOIN price_daily pd ON ss.symbol = pd.symbol
                AND pd.date >= CURRENT_DATE - INTERVAL '30 days'
            LEFT JOIN company_info_sec cis ON ss.symbol = cis.ticker
            WHERE pd.symbol IS NULL
            AND ss.active = TRUE
            GROUP BY ss.exchange
            ORDER BY missing_count DESC
        """)

        exchange_summary = cur.fetchall()
        logger.info("[AUDIT] Missing symbols by exchange:")
        for exchange, total, delisted in exchange_summary:
            logger.info(f"  {exchange}: {total} missing ({delisted} delisted)")

        # Query 5: Check if symbols appear in historical price_daily (older than 30 days)
        logger.info("[AUDIT] Query 5: Checking for stale historical data...")
        cur.execute("""
            SELECT COUNT(DISTINCT ss.symbol) as stale_historical_count
            FROM stock_symbols ss
            INNER JOIN price_daily pd ON ss.symbol = pd.symbol
            WHERE ss.active = TRUE
            AND pd.date < CURRENT_DATE - INTERVAL '30 days'
            AND ss.symbol NOT IN (
                SELECT DISTINCT symbol FROM price_daily
                WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            )
        """)

        stale_count = cur.fetchone()[0]
        logger.info(f"[AUDIT] {stale_count} symbols have stale historical data (>30 days old, no recent)")

        # Summary
        total_active = cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = TRUE")
        total_active_result = cur.fetchone()
        total_active_count = total_active_result[0] if total_active_result else 0

        coverage_pct = 100 * (1 - len(missing_active) / total_active_count) if total_active_count > 0 else 0
        logger.info(f"\n[AUDIT] SUMMARY:")
        logger.info(f"  Total active symbols: {total_active_count}")
        logger.info(f"  Symbols with recent price data: {total_active_count - len(missing_active)}")
        logger.info(f"  Coverage: {coverage_pct:.1f}%")
        logger.info(f"  Delisted: {delisted_count}")
        logger.info(f"  Stale historical: {stale_count}")


if __name__ == "__main__":
    audit_missing_symbols()
    logger.info("[AUDIT] Complete - results logged above")
