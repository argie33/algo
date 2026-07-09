#!/usr/bin/env python3
"""
Bootstrap all data loaders - populates database for orchestrator execution.

Runs loaders in dependency sequence to ensure data prerequisites are satisfied.
This is used for:
  - Initial system setup
  - Data refresh when EventBridge loaders fail
  - Testing without AWS infrastructure
"""

import os
import sys
import logging
import subprocess
import time
from pathlib import Path
from typing import List, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Repo root
REPO_ROOT = Path(__file__).parent.parent.absolute()

# Loader dependency order - mirrors EventBridge schedule but sequential for local dev
LOADER_SEQUENCE: List[Tuple[str, str]] = [
    # Phase 1: Price data (prerequisite for all technical analysis)
    ("loaders.load_prices", "Stock prices (OHLCV) - required for all analysis"),

    # Phase 2: Technical indicators (depends on prices)
    ("loaders.load_technical_data_daily", "50/200-day SMA - depends on prices"),

    # Phase 3: Market health and fundamentals (parallel - no dependencies)
    ("loaders.load_market_health_daily", "Market health (VIX, breadth, trend)"),
    ("loaders.load_dxy_index", "DXY/USD economic indicator"),

    # Phase 4: Financial statement data (SEC Edgar - upstream for metrics)
    ("loaders.load_financial_statements", "Financial statements (income, balance, cashflow)"),

    # Phase 5: Fundamental metrics (depends on financial statements + prices)
    ("loaders.load_quality_metrics", "Quality metrics - depends on SEC data"),
    ("loaders.load_growth_metrics", "Growth metrics - depends on SEC data"),
    ("loaders.load_value_metrics", "Value metrics (P/E, P/B, P/S)"),
    ("loaders.load_positioning_metrics", "Positioning metrics (short interest)"),
    ("loaders.load_stability_metrics", "Stability metrics (dividend yield)"),
    ("loaders.load_momentum_metrics", "Momentum metrics (1m/3m/6m/12m returns)"),

    # Phase 6: Composite scores (depends on all metrics)
    ("loaders.load_stock_scores", "Composite stock scores - depends on metrics"),

    # Phase 7: Rankings (depends on stock scores)
    ("loaders.load_sector_ranking", "Sector rankings - depends on stock scores"),
    ("loaders.load_industry_ranking", "Industry rankings - depends on stock scores"),

    # Phase 8: Signal generation (depends on prices + all metrics + scores)
    ("loaders.load_buy_sell_daily", "BUY/SELL signals - depends on all data"),

    # Phase 9: Supporting data (lower dependency priority)
    ("loaders.load_algo_metrics_daily", "Algo performance metrics"),
    ("loaders.load_market_exposure_daily", "Market exposure factors"),
    ("loaders.load_market_sentiment", "Market sentiment (VIX-based)"),
    ("loaders.load_earnings_calendar", "Earnings calendar"),
    ("loaders.load_company_profile", "Company profile (sector, industry)"),
    ("loaders.load_analyst_analysis", "Analyst sentiment and ratings"),
    ("loaders.load_yfinance_snapshot", "yfinance snapshot cache"),

    # Phase 10: Analytics (lowest priority)
    ("loaders.load_trend_criteria_data", "Trend criteria data"),
    ("loaders.load_vcp_patterns", "VCP pattern analysis"),
]

def run_loader(module_path: str, description: str, parallelism: int = 2, timeout_sec: int = 3600) -> bool:
    """Run a single loader and return success status."""
    logger.info(f"Starting: {description}")
    logger.debug(f"  Module: {module_path}")

    try:
        cmd = [
            sys.executable,
            "-m",
            module_path,
            "--parallelism", str(parallelism)
        ]

        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            timeout=timeout_sec,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            logger.info(f"✓ COMPLETED: {description}")
            return True
        else:
            logger.error(f"✗ FAILED: {description}")
            logger.error(f"  Return code: {result.returncode}")
            if result.stdout:
                logger.debug(f"  STDOUT:\n{result.stdout[-500:]}")
            if result.stderr:
                logger.debug(f"  STDERR:\n{result.stderr[-500:]}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"✗ TIMEOUT: {description} (exceeded {timeout_sec}s)")
        return False
    except Exception as e:
        logger.error(f"✗ ERROR: {description} - {e}")
        return False

def main():
    """Run all loaders in sequence."""
    logger.info("="*80)
    logger.info("BOOTSTRAP ALL DATA LOADERS - Complete Database Population")
    logger.info("="*80)
    logger.info("")

    os.chdir(REPO_ROOT)

    success_count = 0
    fail_count = 0
    failed_loaders: List[str] = []

    start_time = time.time()

    for module_path, description in LOADER_SEQUENCE:
        if run_loader(module_path, description):
            success_count += 1
        else:
            fail_count += 1
            failed_loaders.append(description)
        logger.info("")

    elapsed = time.time() - start_time

    logger.info("="*80)
    logger.info("LOADER BOOTSTRAP SUMMARY")
    logger.info("="*80)
    logger.info(f"Total time: {elapsed/60:.1f} minutes")
    logger.info(f"Successful: {success_count}/{len(LOADER_SEQUENCE)}")
    logger.info(f"Failed: {fail_count}/{len(LOADER_SEQUENCE)}")

    if failed_loaders:
        logger.warning("")
        logger.warning("FAILED LOADERS:")
        for loader in failed_loaders:
            logger.warning(f"  - {loader}")

    logger.info("")

    if fail_count == 0:
        logger.info("✓ ALL LOADERS COMPLETED SUCCESSFULLY")
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Verify database has fresh data:")
        logger.info("     SELECT COUNT(*) FROM algo_stock_scores;")
        logger.info("     SELECT MAX(updated_at) FROM algo_stock_scores;")
        logger.info("")
        logger.info("  2. Run orchestrator test:")
        logger.info("     python3 scripts/test_orchestrator_execution.py")
        logger.info("")
        logger.info("  3. Start dashboard:")
        logger.info("     cd webapp && npm run dev")
        logger.info("")
        return 0
    else:
        logger.error("")
        logger.error(f"✗ {fail_count} LOADERS FAILED - System may have incomplete data")
        logger.error("")
        logger.error("Troubleshooting:")
        logger.error("  1. Check loader error logs above for specific failures")
        logger.error("  2. Verify database connection: check DB_HOST, DB_USER, DB_PASSWORD")
        logger.error("  3. Verify API credentials: check APCA_API_KEY_ID, APCA_API_SECRET_KEY")
        logger.error("  4. Check external API availability: yfinance, SEC Edgar, Alpaca")
        logger.error("")
        return 1

if __name__ == "__main__":
    sys.exit(main())
