#!/usr/bin/env python3
"""Local loader runner for testing - quickly run any loader without orchestrator overhead.

Usage:
  python3 scripts/run_loader.py prices --symbols AAPL,SPY --backfill 30
  python3 scripts/run_loader.py technical_indicators
  python3 scripts/run_loader.py stock_scores --limit 100

This bypasses the full orchestrator and Step Functions to test individual loaders quickly.
"""

import argparse
import logging
import os
import sys

# Set LOCAL_MODE for direct database access and to skip AWS-dependent operations
os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"

# FIX: Configure Redis for price cache (reduces yfinance API calls by 90%)
if "REDIS_URL" not in os.environ:
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger(__name__)


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
            cursor.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
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
    from loaders.load_technical_indicators import VectorizedTechnicalLoader
    import psycopg2

    # Fetch all universe symbols from stock_symbols table
    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
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
    from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader
    import psycopg2

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
            cursor.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
            symbols = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            logger.info(f"Loaded {len(symbols)} symbols from stock_symbols (note: may include indices)")
        except:
            symbols = ["AAPL", "SPY", "QQQ", "MSFT", "NVDA"]

    loader = ValueQualityGrowthMetricsLoader()
    result = loader.run(symbols=symbols)
    logger.info(f"Value/quality/growth metrics loader result: {result}")
    return result


def run_stock_scores_loader(limit=None):
    """Run stock scores loader."""
    from loaders.load_stock_scores import StockScoresLoader
    import psycopg2

    # Fetch universe symbols from stock_symbols table
    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
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


def main():
    parser = argparse.ArgumentParser(description="Run individual loaders for testing")
    parser.add_argument(
        "loader",
        choices=["prices", "technical", "scores", "market_status", "value_quality_growth"],
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

        logger.info("Loader completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Loader failed: {e}", exc_info=args.debug)
        return 1


if __name__ == "__main__":
    sys.exit(main())
