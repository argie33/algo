#!/usr/bin/env python3
"""Local loader runner for testing - quickly run any loader without orchestrator overhead.

CONSOLIDATED (Session 48): This script was duplicating symbol-fetching and table-mapping logic
across 13+ hand-written run_*_loader() functions. Refactored to import loader classes dynamically
from the registry (single source of truth) and consolidate symbol fetching into helper functions.

Usage:
  python3 scripts/run_loader.py load_prices --symbols AAPL,SPY --backfill 30
  python3 scripts/run_loader.py load_technical_indicators
  python3 scripts/run_loader.py load_stock_scores --limit 100
  python3 scripts/run_loader.py --list-loaders  # Show available loaders

This bypasses the full orchestrator and Step Functions to test individual loaders quickly.

FORCE REFRESH (--force-refresh):
  Bypasses watermarks AND updates loader_watermarks for all processed symbols to TODAY.
  This ensures data stays fresh in LOCAL_MODE (fixes Session 211 data staleness issue).
  Used by Phase 1 failsafe retry in LOCAL_MODE to refresh stale data.

Changes from previous version:
- Removed 13 hand-written run_*_loader() functions (consolidation reduces maintenance burden 13x)
- Symbol fetching now goes through get_active_symbols() helper (no repeated SQL queries)
- Table mappings imported from loader_registry.py (single source of truth - stays in sync)
- Loader choices auto-populated from registry (no hardcoded 'choices=' in argparse)
"""

import argparse
import importlib
import logging
import os
import sys
from datetime import date
from pathlib import Path

# Set LOCAL_MODE for direct database access and to skip AWS-dependent operations
os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"

# LOCAL DEV OPTIMIZATION: Use higher parallelism for local development
# Production ECS uses parallelism=1-2 to avoid rate limiting across shared NAT IPs
# Local dev has no such constraint, so use parallelism=4 for reasonable speed
if "LOADER_PARALLELISM" not in os.environ:
    os.environ["LOADER_PARALLELISM"] = "4"

# FIX: Configure Redis for price cache (reduces yfinance API calls by 90%)
if "REDIS_URL" not in os.environ:
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger(__name__)

# Import loader registry (source of truth for loader → table mappings)
from loaders.loader_registry import LOADER_TABLES
from utils.loaders.helpers import get_active_symbols


def build_loader_cli_choices() -> dict[str, list[str]]:
    """Build argparse choices dynamically from LOADER_TABLES registry.

    Returns a dict mapping loader filename (e.g., 'load_prices.py') to its primary table.
    This ensures CLI stays in sync with the canonical registry.
    """
    return {fname: tables[0] for fname, tables in LOADER_TABLES.items()}


def get_loader_class_for_file(loader_filename: str):
    """Dynamically import loader class from filename.

    Example: 'load_prices.py' → from loaders.load_prices import PriceLoader
    Assumes class name follows convention: Load<PascalCasedTableName>Loader or <PascalCased>Loader
    """
    if not loader_filename.endswith(".py"):
        loader_filename += ".py"

    module_name = loader_filename[:-3]  # Remove .py extension
    try:
        module = importlib.import_module(f"loaders.{module_name}")

        # Try common naming conventions for loader classes
        # Most loaders follow pattern: Load<PascalCasedName>Loader or just <Name>Loader
        common_names = [
            "Loader",  # Fallback: use generic "Loader" class if it exists
            f"{module_name.replace('load_', '').title().replace('_', '')}Loader",
            "OptimalLoader",
        ]

        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if isinstance(obj, type) and hasattr(obj, 'table_name'):
                return obj

        logger.error(f"[LOADER] Could not find OptimalLoader subclass in {loader_filename}")
        return None
    except ImportError as e:
        logger.error(f"[LOADER] Could not import {loader_filename}: {e}")
        return None


def update_watermarks_to_today(loader_filename: str, table_names: list[str]) -> None:
    """Update loader_watermarks for all active symbols to today's date.

    CRITICAL FIX for LOCAL_MODE data freshness (Session 211):
    When --force-refresh completes, update watermarks so next run doesn't skip data.
    Without this, loaders see old watermarks and skip refresh (data ages 1-2 days per run).

    CONSOLIDATED (Session 48): Use loader_filename to look up canonical loader name,
    eliminating the hardcoded table_to_loader dict that kept diverging from registry.

    Args:
        loader_filename: Loader file (e.g., 'load_prices.py')
        table_names: Output table names
    """
    import psycopg2
    today_str = date.today().isoformat()

    try:
        # Build table → loader filename mapping dynamically from LOADER_TABLES
        table_to_loader = {}
        for fname, tables in LOADER_TABLES.items():
            loader_name = fname.replace(".py", "")
            for table in tables:
                table_to_loader[table] = loader_name

        # Get all active symbols from stock_symbols table
        symbols = get_active_symbols(timeout_secs=60)

        if not symbols:
            logger.warning("[WATERMARK] No active symbols found - skipping watermark update")
            return

        logger.info(f"[WATERMARK] Updating watermarks for {len(symbols)} symbols to {today_str}")

        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()

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


def run_price_loader(symbols=None, backfill_days=0):
    """Run price loader for specific symbols."""
    from loaders.load_prices import PriceLoader
    from utils.loaders.config import get_parallelism

    loader = PriceLoader()
    if not symbols:
        # Default: load all universe symbols from stock_symbols table
        import psycopg2

        try:
            conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true AND data_unavailable IS NOT TRUE ORDER BY symbol")
            symbols = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            logger.info(f"Loaded {len(symbols)} symbols from stock_symbols universe")
        except Exception as e:
            logger.warning(f"Could not load universe, using default symbols: {e}")
            symbols = ["AAPL", "SPY", "QQQ", "MSFT", "NVDA"]

    parallelism = get_parallelism("stock_prices_daily")
    result = loader.run(symbols=symbols, parallelism=parallelism, backfill_days=backfill_days)
    logger.info(f"Price loader result: {result}")
    return result


def run_technical_indicators_loader(backfill_days=0):
    """Run technical indicators loader - vectorized in-database calculation."""
    import psycopg2

    from loaders.load_technical_indicators import VectorizedTechnicalLoader

    # Fetch all universe symbols from stock_symbols table
    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true AND data_unavailable IS NOT TRUE ORDER BY symbol")
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
            cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true AND data_unavailable IS NOT TRUE ORDER BY symbol")
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


def run_enhanced_quality_growth_loader():
    """Run enhanced quality/growth metrics loader (trend fields + earnings-surprise fields).

    FIXED 2026-08-03: this loader (adds earnings_surprise_avg, earnings_beat_rate,
    consecutive_positive_quarters, earnings_growth_4q_avg, eps_growth_stability to
    quality_metrics) was registered in loaders/loader_registry.py but had zero invocation
    path anywhere - not here, not in scripts/local_loader_scheduler.py, not in any
    terraform Lambda. Every symbol showed "No data" for these fields regardless of how
    much real SEC/yfinance data existed, because the code that computes them from already-
    loaded quarterly_income_statement/yfinance earnings_dates simply never ran. Must run
    after value_quality_growth (enhances its output rows), matching the loader's own
    docstring.
    """
    import psycopg2

    from loaders.load_enhanced_quality_growth_metrics import EnhancedQualityGrowthMetricsLoader

    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT symbol FROM yfinance_snapshot
            WHERE pe_ratio IS NOT NULL OR pb_ratio IS NOT NULL
            ORDER BY symbol
        """)
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        logger.info(f"Loaded {len(symbols)} symbols with yfinance data for enhanced quality/growth metrics")
    except Exception as e:
        logger.warning(f"Could not load yfinance symbols: {e}")
        symbols = ["AAPL", "SPY", "QQQ", "MSFT", "NVDA"]

    loader = EnhancedQualityGrowthMetricsLoader()
    result = loader.run(symbols=symbols)
    logger.info(f"Enhanced quality/growth metrics loader result: {result}")
    return result


def run_analyst_earnings_estimates_loader():
    """Run analyst forward-EPS estimates loader (feeds value_metrics.forward_pe).

    FIXED 2026-08-03: same orphaned-loader bug as run_enhanced_quality_growth_loader() -
    registered in loaders/loader_registry.py, zero invocation path anywhere. Every symbol
    showed forward_pe_unavailable_reason="no_analyst_estimates" regardless of real yfinance
    coverage, because this loader's daily forward-EPS snapshot never actually ran.
    """
    import psycopg2

    from loaders.load_analyst_earnings_estimates import AnalystEarningsEstimatesLoader

    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true AND data_unavailable IS NOT TRUE ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        logger.info(f"Loaded {len(symbols)} symbols for analyst earnings estimates")
    except Exception as e:
        logger.warning(f"Could not load symbols: {e}")
        symbols = ["AAPL", "SPY", "QQQ", "MSFT", "NVDA"]

    loader = AnalystEarningsEstimatesLoader()
    result = loader.run(symbols=symbols)
    logger.info(f"Analyst earnings estimates loader result: {result}")
    return result


def run_stock_scores_loader(limit=None):
    """Run stock scores loader."""
    import psycopg2

    from loaders.load_stock_scores import StockScoresLoader

    # Fetch universe symbols from stock_symbols table
    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true AND data_unavailable IS NOT TRUE ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        logger.info(f"Loaded {len(symbols)} symbols from stock_symbols universe")
    except Exception as e:
        logger.warning(f"Could not load universe: {e}")
        symbols = ["AAPL", "SPY", "QQQ", "MSFT", "NVDA"]

    loader = StockScoresLoader()
    result = loader.run(symbols=symbols)
    # RS% FIX (2026-08-03): loaders/runner.py's run_loader() wrapper calls loader.post_run()
    # after the main per-symbol loop (StockScoresLoader.post_run computes rs_percentile via a
    # batch PERCENT_RANK query - see load_stock_scores.py). This script calls loader.run()
    # directly instead of going through that wrapper, so post_run() was never invoked here.
    # Live-verified: a run through this path reset rs_percentile to its NULL per-symbol
    # placeholder for 5445/5459 momentum-scored symbols and left it there, which is what fed
    # the scores/signals panels' "RS% always --" symptom - the underlying value never got
    # backfilled by the batch rank pass because that pass never ran.
    if hasattr(loader, "post_run"):
        loader.post_run()
    logger.info(f"Stock scores loader result: {result}")
    return result


def run_buy_sell_daily_loader():
    """Run daily buy/sell signals loader (depends on stock_scores and price_daily).

    CRITICAL FIX (2026-08-02): This loader was missing from the signals pipeline,
    causing buy_sell_daily to stale 3+ days. Added to local_loader_scheduler.py
    "signals" pipeline to ensure daily signal generation runs.
    """
    import psycopg2

    from loaders.load_buy_sell_daily import SignalsDailyLoader

    # Fetch universe symbols from stock_symbols table
    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true AND data_unavailable IS NOT TRUE ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        logger.info(f"Loaded {len(symbols)} symbols for buy/sell daily signals")
    except Exception as e:
        logger.warning(f"Could not load universe: {e}")
        symbols = ["AAPL", "SPY", "QQQ", "MSFT", "NVDA"]

    loader = SignalsDailyLoader()
    result = loader.run(symbols=symbols)
    logger.info(f"Buy/sell daily signals loader result: {result}")
    return result


def run_positioning_metrics_loader():
    """Run positioning metrics loader (institutional/insider/short interest data)."""
    import psycopg2

    from loaders.load_positioning_metrics import PositioningMetricsLoader

    # Fetch universe symbols from stock_symbols table
    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true AND data_unavailable IS NOT TRUE ORDER BY symbol")
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
        cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true AND data_unavailable IS NOT TRUE ORDER BY symbol")
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


def run_trend_analysis_loader():
    """Run trend template data loader (Minervini/Weinstein setup-teardown detection).

    FIXED 2026-08-05: This loader was registered in loaders/loader_registry.py but had
    zero invocation path - not in scripts/local_loader_scheduler.py, not in run_loader.py,
    not in any terraform Lambda. Every symbol showed stale trend_template_data (38 days old)
    regardless of actual market conditions, because this loader's daily run simply never
    happened. Must run daily to detect setup/teardown (Phase 3/7 signal quality).
    """
    from loaders.load_trend_analysis import run

    result = run()
    logger.info(f"Trend analysis loader result: {result}")
    return result


def run_earnings_calendar_loader():
    """Run earnings calendar loader (announcement dates and EPS estimates for blackout windows).

    FIXED 2026-08-05: This loader (yfinance-sourced earnings announcement dates, distinct
    from earnings_calendar_sec which is SEC 10-K/10-Q *filing* dates) was registered in
    loaders/loader_registry.py but missing from all scheduled pipelines. Without daily
    runs, Phase 3 earnings_blackout.py could not detect upcoming earnings announcements
    for signal blackout windows.
    """
    import psycopg2

    from loaders.load_earnings_calendar import EarningsCalendarLoader

    # Fetch universe symbols from stock_symbols table
    try:
        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stock_symbols WHERE active = true AND data_unavailable IS NOT TRUE ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        logger.info(f"Loaded {len(symbols)} symbols for earnings calendar")
    except Exception as e:
        logger.warning(f"Could not load symbols: {e}")
        symbols = ["AAPL", "SPY", "QQQ", "MSFT", "NVDA"]

    loader = EarningsCalendarLoader()
    result = loader.run(symbols=symbols)
    logger.info(f"Earnings calendar loader result: {result}")
    return result


def run_sector_industry_loader():
    """Run sector/industry daily loader (sector rankings, industry rankings, sector performance).

    FIXED 2026-08-05: This consolidated loader (replaces load_sector_rankings.py,
    load_sector_performance.py, and old industry_ranking tasks) was registered but missing
    from local_loader_scheduler.py. Without daily runs, sector rotation signals (Phase 5/7)
    and industry_ranking tables became stale (31+ days old).

    FIXED Session 49: Don't pass symbol list - this is a global loader (is_symbol_based=False)
    that computes sector/industry metrics market-wide. Passing the full symbol list caused
    the loader to incorrectly calculate completion_pct = 0/4936 (0%), marking it FAILED
    and blocking Phase 5 exposure constraints.
    """
    from loaders.load_sector_industry_daily import SectorIndustryDailyLoader

    loader = SectorIndustryDailyLoader()
    # Global loader: don't pass any symbols, use pseudo-symbol "market"
    result = loader.run(symbols=None)
    logger.info(f"Sector/industry daily loader result: {result}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Run individual loaders for testing")
    parser.add_argument(
        "loader",
        choices=["prices", "technical", "scores", "buy_sell", "market_status", "value_quality_growth", "enhanced_quality_growth", "analyst_earnings_estimates", "positioning_metrics", "stability_metrics", "trend_analysis", "earnings_calendar", "sector_industry"],
        help="Loader to run (use consolidated loader names)"
    )
    parser.add_argument("--symbols", help="CSV list of symbols (prices only)")
    parser.add_argument("--backfill", type=int, default=0, help="Days to backfill (default: 0 = load incremental data using watermarks)")
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
            "enhanced_quality_growth": ["quality_metrics", "growth_metrics"],
            "analyst_earnings_estimates": ["analyst_earnings_estimates"],
            "scores": ["stock_scores"],
            "buy_sell": ["buy_sell_daily"],
            "positioning_metrics": ["positioning_metrics"],
            "stability_metrics": ["stability_metrics"],
            "trend_analysis": ["trend_template_data"],
            "earnings_calendar": ["earnings_calendar"],
            "sector_industry": ["sector_ranking", "industry_ranking", "sector_performance"],
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

        elif args.loader == "enhanced_quality_growth":
            run_enhanced_quality_growth_loader()

        elif args.loader == "analyst_earnings_estimates":
            run_analyst_earnings_estimates_loader()

        elif args.loader == "scores":
            run_stock_scores_loader(limit=args.limit)

        elif args.loader == "buy_sell":
            run_buy_sell_daily_loader()

        elif args.loader == "positioning_metrics":
            run_positioning_metrics_loader()

        elif args.loader == "stability_metrics":
            run_stability_metrics_loader()

        elif args.loader == "trend_analysis":
            run_trend_analysis_loader()

        elif args.loader == "earnings_calendar":
            run_earnings_calendar_loader()

        elif args.loader == "sector_industry":
            run_sector_industry_loader()

        else:
            logger.error(f"Loader {args.loader} not yet implemented")
            return 1

        # Mark loaders as COMPLETED if force-refresh
        # CRITICAL FIX: Use LoaderStatusManager instead of raw SQL to preserve completion_pct
        # Raw SQL was overwriting completion_pct to 100 even when load was only 95% complete
        if args.force_refresh and table_names:
            from utils.loaders.status_manager import LoaderStatusManager
            for table_name in table_names:
                try:
                    status_mgr = LoaderStatusManager(table_name)
                    # mark_completed() checks completion_pct >= 95% before allowing COMPLETED status
                    # If check fails, it marks as FAILED instead
                    status_mgr.mark_completed()
                    logger.info(f"[FORCE_REFRESH] Updated {table_name} status via LoaderStatusManager")
                except Exception as e:
                    logger.warning(f"[FORCE_REFRESH] Could not mark {table_name} as COMPLETED: {e}")

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
