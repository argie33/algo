#!/usr/bin/env python3
"""Backfill enhanced quality/growth metrics for stocks with existing quality_metrics rows.

This script runs the EnhancedQualityGrowthMetrics loader on a subset of stocks to:
1. Populate earnings_growth_4q_avg, eps_growth_stability, etc.
2. Verify the data flows through to the API and frontend
3. Test before full production backfill

Usage:
    python scripts/backfill_enhanced_metrics.py [--symbols AAPL,MSFT,GOOGL] [--all] [--check-only]

Args:
    --symbols: Comma-separated list of symbols to backfill (default: top 10 by volume)
    --all: Backfill all ~5500 stocks (requires 30+ minutes, ~4 ECS tasks)
    --check-only: Just check database state, don't run loader
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Add repo to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def check_database_state():
    """Check if database has the required data for enhanced metrics computation."""
    logger.info("Checking database state...")

    try:
        from utils.db.connection import get_db_connection

        conn = get_db_connection()
        cur = conn.cursor()

        # Check if quality_metrics table exists and has rows
        cur.execute("SELECT COUNT(*) FROM quality_metrics")
        qm_count = cur.fetchone()[0]
        logger.info(f"  quality_metrics: {qm_count:,} rows")

        # Check if quarterly_income_statement has data
        cur.execute("SELECT COUNT(*) FROM quarterly_income_statement WHERE data_unavailable IS NOT TRUE")
        qi_count = cur.fetchone()[0]
        logger.info(f"  quarterly_income_statement (valid): {qi_count:,} rows")

        # Check coverage of key quarterly metrics
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(consecutive_positive_quarters) as cpq,
                COUNT(earnings_growth_4q_avg) as e4q,
                COUNT(eps_growth_stability) as egs
            FROM quality_metrics
        """)
        total, cpq, e4q, egs = cur.fetchone()
        logger.info(f"  quality_metrics coverage:")
        logger.info(f"    - consecutive_positive_quarters: {cpq}/{total} ({cpq/total*100:.1f}%)")
        logger.info(f"    - earnings_growth_4q_avg: {e4q}/{total} ({e4q/total*100:.1f}%)")
        logger.info(f"    - eps_growth_stability: {egs}/{total} ({egs/total*100:.1f}%)")

        # Get sample of missing data
        cur.execute("""
            SELECT symbol FROM quality_metrics
            WHERE consecutive_positive_quarters IS NULL
            LIMIT 5
        """)
        missing_symbols = [row[0] for row in cur.fetchall()]
        logger.info(f"  Sample stocks needing data: {', '.join(missing_symbols)}")

        cur.close()
        conn.close()

        return {
            "quality_metrics_rows": qm_count,
            "quarterly_income_rows": qi_count,
            "missing_stocks": missing_symbols
        }

    except Exception as e:
        logger.error(f"Database check failed: {e}")
        return None


def run_loader_for_symbols(symbols: list[str]):
    """Run EnhancedQualityGrowthMetrics loader for specific symbols."""
    logger.info(f"Running EnhancedQualityGrowthMetrics loader for {len(symbols)} symbols...")

    try:
        from loaders.load_enhanced_quality_growth_metrics import EnhancedQualityGrowthMetricsLoader

        loader = EnhancedQualityGrowthMetricsLoader()
        result = loader.run(symbols, parallelism=2)

        logger.info(f"  Succeeded: {result.get('symbols_succeeded', 0)}")
        logger.info(f"  Failed: {result.get('symbols_failed', 0)}")
        logger.info(f"  Success: {result.get('success', False)}")

        return result

    except Exception as e:
        logger.error(f"Loader execution failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def verify_data_loaded(symbols: list[str]):
    """Verify that data was actually written to the database."""
    logger.info("Verifying data was loaded...")

    try:
        from utils.db.connection import get_db_connection

        conn = get_db_connection()
        cur = conn.cursor()

        for symbol in symbols:
            cur.execute("""
                SELECT
                    consecutive_positive_quarters,
                    earnings_growth_4q_avg,
                    eps_growth_stability,
                    estimate_momentum_60d,
                    revision_activity_30d
                FROM quality_metrics
                WHERE symbol = %s
            """, (symbol,))

            row = cur.fetchone()
            if row:
                cpq, e4q, egs, em60, ra30 = row
                logger.info(f"  {symbol}:")
                logger.info(f"    - consecutive_positive_quarters: {cpq}")
                logger.info(f"    - earnings_growth_4q_avg: {e4q}")
                logger.info(f"    - eps_growth_stability: {egs}")
                logger.info(f"    - estimate_momentum_60d: {em60}")
                logger.info(f"    - revision_activity_30d: {ra30}")
            else:
                logger.warning(f"  {symbol}: No row found in quality_metrics")

        cur.close()
        conn.close()

    except Exception as e:
        logger.error(f"Verification failed: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", help="Comma-separated list of symbols")
    parser.add_argument("--all", action="store_true", help="Backfill all stocks")
    parser.add_argument("--check-only", action="store_true", help="Just check database state")

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("ENHANCED METRICS BACKFILL")
    logger.info("=" * 80)
    logger.info(f"Start time: {datetime.now().isoformat()}")

    # Check database state first
    db_state = check_database_state()
    if not db_state:
        logger.error("Cannot proceed without database access")
        return 1

    if args.check_only:
        logger.info("Check-only mode: exiting")
        return 0

    # Determine which symbols to process
    if args.all:
        logger.info("Processing ALL stocks - this will take 30+ minutes")
        # Fetch all symbols from database
        try:
            from utils.db.connection import get_db_connection
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT symbol FROM quality_metrics ORDER BY symbol")
            symbols = [row[0] for row in cur.fetchall()]
            cur.close()
            conn.close()
            logger.info(f"Fetched {len(symbols)} symbols from database")
        except Exception as e:
            logger.error(f"Failed to fetch symbols: {e}")
            return 1
    elif args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        # Use missing symbols from database check
        symbols = db_state.get("missing_stocks", ["AAPL", "MSFT", "GOOGL"])
        if not symbols:
            symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "NFLX", "BRK.B", "JNJ"]

    if symbols:
        logger.info(f"Will process: {', '.join(symbols[:5])}" +
                    (f" ... and {len(symbols)-5} more" if len(symbols) > 5 else ""))
    else:
        logger.info("Will process: ALL stocks (~5700)")

    # Run loader
    result = run_loader_for_symbols(symbols)

    if result.get("success"):
        logger.info("Loader completed successfully")
        # Verify data was loaded
        verify_data_loaded(symbols)
    else:
        logger.error(f"Loader failed: {result.get('error', 'Unknown error')}")
        return 1

    logger.info(f"End time: {datetime.now().isoformat()}")
    logger.info("=" * 80)
    logger.info("NEXT STEPS:")
    logger.info("  1. Check Quality & Fundamentals section in dashboard")
    logger.info("  2. Look for data in: Earnings Growth 4Q Avg, EPS Growth Stability")
    logger.info("  3. Verify API returns metrics: curl http://localhost:3001/api/scores/AAPL")
    logger.info("  4. Check frontend displays metrics correctly")
    logger.info("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
