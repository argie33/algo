#!/usr/bin/env python3
"""Local loader runner for testing - quickly run any loader without orchestrator overhead.

Usage:
  python3 scripts/run_loader.py prices --symbols AAPL,SPY --backfill 30
  python3 scripts/run_loader.py technical_indicators
  python3 scripts/run_loader.py stock_scores --limit 100

This bypasses the full orchestrator and Step Functions to test individual loaders quickly.

FORCE REFRESH (--force-refresh):
  Bypasses watermarks AND updates loader_watermarks for all processed symbols to TODAY.
  This ensures data stays fresh in LOCAL_MODE (fixes Session 211 data staleness issue).
  Used by Phase 1 failsafe retry in LOCAL_MODE to refresh stale data.

FIX (2026-07-20): every "load the universe" query in this file (watermark update +
all 6 run_*_loader functions) selected from stock_symbols with no `active` filter,
unlike load_positioning_metrics.py/load_financial_statements.py/utils/loaders/helpers.py,
which all filter `WHERE active = true`. This file is not just a manual dev tool -
algo/orchestrator/phase1_failsafe_retry.py invokes it automatically via subprocess with
--force-refresh, so any symbol marked inactive (delisted, but not yet purged from
stock_symbols) would still get reprocessed into stability_metrics/momentum_metrics/etc
every time the failsafe retry fires, undoing any manual stale-row cleanup. Added the
same `WHERE active = true` filter everywhere else already uses.
"""

import argparse
import logging
import os
import sys
from datetime import date

# Set LOCAL_MODE for direct database access and to skip AWS-dependent operations
os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"

# FIX: Configure Redis for price cache (reduces yfinance API calls by 90%)
if "REDIS_URL" not in os.environ:
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger(__name__)


def update_watermarks_to_today(loader_name: str, table_names: list[str]) -> None:
    """Update loader_watermarks for all active symbols to today's date.

    CRITICAL FIX for LOCAL_MODE data freshness (Session 211):
    When --force-refresh completes, update watermarks so next run doesn't skip data.
    Without this, loaders see old watermarks and skip refresh (data ages 1-2 days per run).

    Args:
        loader_name: Loader identifier (e.g., 'load_prices', 'load_technical_indicators')
        table_names: Output table names (used to map to loader_name)
    """
    import psycopg2
    today_str = date.today().isoformat()

    try:
        # Map table names to loader names used in loader_watermarks
        table_to_loader = {
            "price_daily": "load_prices",
            "technical_data_daily": "load_technical_indicators",
            "market_health_daily": "load_market_status_daily",
            "value_metrics": "load_value_quality_growth_metrics",
            "quality_metrics": "load_value_quality_growth_metrics",
            "growth_metrics": "load_value_quality_growth_metrics",
            "stock_scores": "load_stock_scores",
            "positioning_metrics": "load_positioning_metrics",
            "stability_metrics": "load_risk_metrics_daily",
        }

        # Get all active symbols from stock_symbols table
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]

        if not symbols:
            logger.warning("[WATERMARK] No active symbols found - skipping watermark update")
            cursor.close()
            conn.close()
            return

        logger.info(f"[WATERMARK] Updating watermarks for {len(symbols)} symbols to {today_str}")

        # Update watermarks for each table's loader
        for table_name in table_names:
            map_loader_name = table_to_loader.get(table_name)
            if not map_loader_name:
                logger.warning(f"[WATERMARK] Unknown table {table_name}, skipping watermark update")
                continue

            # Update all symbols' watermarks to today (use upsert pattern)
            for symbol in symbols:
                cursor.execute(
                    """
                    INSERT INTO loader_watermarks (loader, symbol, granularity, watermark, rows_loaded, last_run_at, last_success_at)
                    VALUES (%s, %s, 'symbol', %s, 0, NOW(), NOW())
                    ON CONFLICT (loader, symbol, granularity)
                    DO UPDATE SET
                        watermark = %s,
                        last_run_at = NOW(),
                        last_success_at = NOW(),
                        error_count = 0,
                        last_error = NULL
                    """,
                    (map_loader_name, symbol, today_str, today_str)
                )

            conn.commit()
            logger.info(f"[WATERMARK] ✓ Updated {map_loader_name} watermarks ({len(symbols)} symbols)")

        cursor.close()
        conn.close()

    except Exception as e:
        logger.error(f"[WATERMARK] Failed to update watermarks: {e}", exc_info=True)


def run_price_loader(symbols=None, backfill_days=1):
    """Run price loader for specific symbols."""
    from loaders.load_prices import PriceLoader

    loader = PriceLoader()
    if not symbols:
        # Default: load all universe symbols from stock_symbols table
        import psycopg2

        try:
            conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true ORDER BY symbol")
            symbols = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            logger.info(f"Loaded {len(symbols)} symbols from stock_symbols universe")
        except Exception as e:
            logger.warning(f"Could not load universe, using default symbols: {e}")
            symbols = ["AAPL", "SPY", "QQQ", "MSFT", "NVDA"]

    result = loader.run(symbols=symbols, backfill_days=backfill_days)
    logger.info(f"Price loader result: {result}")
    return result


def run_technical_indicators_loader(backfill_days=1):
    """Run technical indicators loader - vectorized in-database calculation."""
    import psycopg2

    from loaders.load_technical_indicators import VectorizedTechnicalLoader

    # Fetch all universe symbols from stock_symbols table
    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        logger.info(f"Loaded {len(symbols)} symbols from stock_symbols universe")
    except Exception as e:
        logger.warning(f"Could not load universe, using default symbols: {e}")
        symbols = ["AAPL", "SPY", "QQQ", "MSFT", "NVDA"]

    loader = VectorizedTechnicalLoader()
    result = loader.run(symbols=symbols)
    logger.info(f"Technical indicators loader result: {result}")
    return result


def run_market_status_loader():
    """Run consolidated market status loader (Phase 2).

    Replaces: load_market_health_daily, load_market_exposure_daily, load_market_sentiment
    Outputs: market_health_daily, market_exposure_daily, market_sentiment (atomic)
    """
    from loaders.load_market_status_daily import MarketStatusDailyLoader

    loader = MarketStatusDailyLoader()
    result = loader.run()
    logger.info(f"Market status daily loader result: {result}")
    return result


def run_value_quality_growth_loader():
    """Run consolidated value/quality/growth metrics loader (Phase 3).

    Replaces: load_yfinance_derived_metrics, separate quality/value/growth states
    Outputs: value_metrics, quality_metrics, growth_metrics (atomic)

    CRITICAL: Only load symbols with available yfinance data to avoid creating NULL-filled rows
    (yfinance only covers ~4,700 real stocks, not indices/delisted/etc in full price_daily universe)
    """
    import psycopg2

    from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader

    # Fetch symbols with yfinance data available (only real tradeable stocks)
    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        # Only load symbols that exist in yfinance_snapshot (verified data available)
        cursor.execute("""
            SELECT DISTINCT symbol FROM yfinance_snapshot
            WHERE pe_ratio IS NOT NULL OR pb_ratio IS NOT NULL
            ORDER BY symbol
        """)
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        logger.info(f"Loaded {len(symbols)} symbols with yfinance data (skipping indices/non-tradeable)")
    except Exception as e:
        logger.warning(f"Could not load yfinance symbols: {e}")
        # Fallback: use stock_symbols table
        try:
            conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true ORDER BY symbol")
            symbols = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            logger.info(f"Loaded {len(symbols)} symbols from stock_symbols (note: may include indices)")
        except Exception as e:
            logger.error(f"Failed to load symbols from stock_symbols table: {e}. Falling back to hardcoded list.")
            symbols = ["AAPL", "SPY", "QQQ", "MSFT", "NVDA"]

    loader = ValueQualityGrowthMetricsLoader()
    result = loader.run(symbols=symbols)
    logger.info(f"Value/quality/growth metrics loader result: {result}")
    return result


def run_stock_scores_loader(limit=None):
    """Run stock scores loader."""
    import psycopg2

    from loaders.load_stock_scores import StockScoresLoader

    # Fetch universe symbols from stock_symbols table
    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        logger.info(f"Loaded {len(symbols)} symbols from stock_symbols universe")
    except Exception as e:
        logger.warning(f"Could not load universe: {e}")
        symbols = ["AAPL", "SPY", "QQQ", "MSFT", "NVDA"]

    loader = StockScoresLoader()
    result = loader.run(symbols=symbols)
    logger.info(f"Stock scores loader result: {result}")
    return result


def run_positioning_metrics_loader():
    """Run positioning metrics loader (institutional/insider/short interest data)."""
    import psycopg2

    from loaders.load_positioning_metrics import PositioningMetricsLoader

    # Fetch universe symbols from stock_symbols table
    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        logger.info(f"Loaded {len(symbols)} symbols for positioning metrics")
    except Exception as e:
        logger.warning(f"Could not load symbols: {e}")
        symbols = ["AAPL", "SPY", "QQQ", "MSFT", "NVDA"]

    loader = PositioningMetricsLoader()
    result = loader.run(symbols=symbols, parallelism=4)
    logger.info(f"Positioning metrics loader result: {result}")
    return result


def run_stability_metrics_loader():
    """Run stability metrics loader (risk metrics)."""
    import psycopg2

    from loaders.load_risk_metrics_daily import RiskMetricsLoader

    # Fetch universe symbols from stock_symbols table
    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        logger.info(f"Loaded {len(symbols)} symbols for stability metrics")
    except Exception as e:
        logger.warning(f"Could not load symbols: {e}")
        symbols = ["AAPL", "SPY", "QQQ", "MSFT", "NVDA"]

    loader = RiskMetricsLoader()
    result = loader.run(symbols=symbols, parallelism=4)
    logger.info(f"Stability metrics loader result: {result}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Run individual loaders for testing")
    parser.add_argument(
        "loader",
        choices=["prices", "technical", "scores", "market_status", "value_quality_growth", "positioning_metrics", "stability_metrics"],
        help="Loader to run (use consolidated loader names)"
    )
    parser.add_argument("--symbols", help="CSV list of symbols (prices only)")
    parser.add_argument("--backfill", type=int, default=1, help="Days to backfill")
    parser.add_argument("--limit", type=int, help="Limit for scores loader")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--force-refresh", action="store_true", help="Force refresh by bypassing watermarks and updating status")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Handle --force-refresh: bypass watermarks and update loader status
    if args.force_refresh:
        os.environ["TECH_FULL_REFRESH"] = "true"
        logger.info("[FORCE_REFRESH] Enabled - bypassing watermarks and updating loader status")

    try:
        # Map loader command to table names
        table_mapping = {
            "prices": ["price_daily"],
            "technical": ["technical_data_daily"],
            "market_status": ["market_health_daily"],
            "value_quality_growth": ["value_metrics", "quality_metrics", "growth_metrics"],
            "scores": ["stock_scores"],
            "positioning_metrics": ["positioning_metrics"],
            "stability_metrics": ["stability_metrics"],
        }
        table_names = table_mapping.get(args.loader, [])

        # Mark loaders as RUNNING if force-refresh
        if args.force_refresh and table_names:
            import psycopg2
            try:
                conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
                cursor = conn.cursor()
                for table_name in table_names:
                    cursor.execute(
                        "UPDATE data_loader_status SET status = %s, execution_started = NOW() WHERE table_name = %s",
                        ("RUNNING", table_name)
                    )
                    if cursor.rowcount == 0:
                        cursor.execute(
                            "INSERT INTO data_loader_status (table_name, status, last_updated, execution_started) VALUES (%s, %s, NOW(), NOW())",
                            (table_name, "RUNNING")
                        )
                conn.commit()
                cursor.close()
                conn.close()
                logger.info(f"[FORCE_REFRESH] Marked {table_names} as RUNNING")
            except Exception as e:
                logger.warning(f"[FORCE_REFRESH] Could not update status to RUNNING: {e}")

        if args.loader == "prices":
            symbols = args.symbols.split(",") if args.symbols else None
            run_price_loader(symbols=symbols, backfill_days=args.backfill)

        elif args.loader == "technical":
            run_technical_indicators_loader(backfill_days=args.backfill)

        elif args.loader == "market_status":
            run_market_status_loader()

        elif args.loader == "value_quality_growth":
            run_value_quality_growth_loader()

        elif args.loader == "scores":
            run_stock_scores_loader(limit=args.limit)

        elif args.loader == "positioning_metrics":
            run_positioning_metrics_loader()

        elif args.loader == "stability_metrics":
            run_stability_metrics_loader()

        else:
            logger.error(f"Loader {args.loader} not yet implemented")
            return 1

        # Mark loaders as COMPLETED if force-refresh
        if args.force_refresh and table_names:
            import psycopg2
            try:
                conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
                cursor = conn.cursor()
                for table_name in table_names:
                    cursor.execute(
                        "UPDATE data_loader_status SET status = %s, execution_completed = NOW(), last_updated = NOW() WHERE table_name = %s",
                        ("COMPLETED", table_name)
                    )
                conn.commit()
                cursor.close()
                conn.close()
                logger.info(f"[FORCE_REFRESH] Marked {table_names} as COMPLETED")
            except Exception as e:
                logger.warning(f"[FORCE_REFRESH] Could not update status to COMPLETED: {e}")

            # CRITICAL FIX (Session 211): Update watermarks after --force-refresh
            # Ensures next orchestrator run sees fresh data (prevents 1-2 day staleness in LOCAL_MODE)
            try:
                update_watermarks_to_today(args.loader, table_names)
            except Exception as e:
                logger.error(f"[WATERMARK] Failed to update watermarks after force-refresh: {e}", exc_info=True)

        logger.info("Loader completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Loader failed: {e}", exc_info=args.debug)
        return 1


if __name__ == "__main__":
    sys.exit(main())
