#!/usr/bin/env python3
"""
Audit missing symbols from price_daily.
Identifies which tradable symbols have no price data and categorizes them.
"""

import logging
from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def audit_missing_symbols() -> None:
    """Audit missing symbols and categorize root causes."""

    with DatabaseContext("read") as cur:
        # Query 1: Get all active symbols
        logger.info("[AUDIT] Query 1: Counting all active symbols...")
        cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = TRUE")
        total_active = cur.fetchone()[0]
        logger.info(f"[AUDIT] Total active symbols: {total_active}")

        # Query 2: Which active symbols have NO recent price_daily data?
        logger.info("[AUDIT] Query 2: Identifying symbols with missing price data...")
        cur.execute("""
            SELECT COUNT(*) as missing_count
            FROM stock_symbols ss
            LEFT JOIN price_daily pd ON ss.symbol = pd.symbol
                AND pd.date >= CURRENT_DATE - INTERVAL '30 days'
            WHERE pd.symbol IS NULL
            AND ss.active = TRUE
        """)
        result = cur.fetchone()
        missing_count = result[0] if result else 0
        logger.info(f"[AUDIT] Symbols with NO recent price data: {missing_count}")

        # Query 3: Coverage by exchange
        logger.info("[AUDIT] Query 3: Coverage by exchange...")
        cur.execute("""
            SELECT ss.exchange, COUNT(*) as total,
                   SUM(CASE WHEN pd.symbol IS NULL THEN 1 ELSE 0 END) as missing
            FROM stock_symbols ss
            LEFT JOIN price_daily pd ON ss.symbol = pd.symbol
                AND pd.date >= CURRENT_DATE - INTERVAL '30 days'
            WHERE ss.active = TRUE
            GROUP BY ss.exchange
            ORDER BY missing DESC
        """)
        exchange_stats = cur.fetchall()
        logger.info("[AUDIT] Coverage by exchange:")
        for exchange, total, missing in exchange_stats:
            coverage_pct = 100 * (total - missing) / total if total > 0 else 0
            logger.info(f"  {exchange}: {total - missing}/{total} ({coverage_pct:.1f}%)")

        # Query 4: Get sample of missing symbols
        logger.info("[AUDIT] Query 4: Sample of 20 missing symbols...")
        cur.execute("""
            SELECT ss.symbol, ss.exchange
            FROM stock_symbols ss
            LEFT JOIN price_daily pd ON ss.symbol = pd.symbol
                AND pd.date >= CURRENT_DATE - INTERVAL '30 days'
            WHERE pd.symbol IS NULL
            AND ss.active = TRUE
            ORDER BY ss.symbol
            LIMIT 20
        """)
        missing_symbols = cur.fetchall()
        for symbol, exchange in missing_symbols:
            logger.info(f"  {symbol} ({exchange})")

        # Query 5: Check if any symbols have historical data
        logger.info("[AUDIT] Query 5: Symbols with stale historical data...")
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
        stale_result = cur.fetchone()
        stale_count = stale_result[0] if stale_result else 0
        logger.info(f"[AUDIT] Symbols with stale historical data (>30 days old, no recent): {stale_count}")

        # Summary
        coverage_pct = 100 * (total_active - missing_count) / total_active if total_active > 0 else 0
        logger.info(f"\n[AUDIT] SUMMARY:")
        logger.info(f"  Total active symbols: {total_active}")
        logger.info(f"  Symbols with recent price data: {total_active - missing_count}")
        logger.info(f"  Coverage: {coverage_pct:.1f}%")
        logger.info(f"  Symbols with stale historical data: {stale_count}")


if __name__ == "__main__":
    audit_missing_symbols()
    logger.info("[AUDIT] Complete")
