#!/usr/bin/env python3
"""
Fast Morning Prep Pipeline (2:00 AM - 3:00 AM ET)

NEW APPROACH: Load ONLY what's critical for signal generation.
- stock_prices_daily: Load today's prices (15 min)
- That's it. Everything else computed on-demand.

Old approach (removed):
- technical_data_daily: 180 min (now computed on-demand in Phase 5/6)
- buy_sell_daily: 30 min (now computed inline in Phase 5)
- signal_quality_scores: 30 min (now computed inline in Phase 5)
- swing_trader_scores: 30 min (now computed async or on-demand)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def run_morning_prep():
    """Execute fast morning prep pipeline."""
    pipeline_start = time.time()
    now_et = datetime.now(ZoneInfo("America/New_York"))

    logger.info("=" * 80)
    logger.info("MORNING PREP PIPELINE (Fast)")
    logger.info(f"Start: {now_et.strftime('%H:%M:%S %Z')}")
    logger.info("=" * 80)

    success_count = 0
    failure_count = 0

    # STEP 1: Load stock prices
    logger.info("\n[1/1] Loading stock prices...")
    try:
        from loaders.load_prices import main as load_prices
        result = load_prices()
        if result == 0:
            logger.info("✓ stock_prices_daily: SUCCESS")
            success_count += 1
        else:
            logger.error("✗ stock_prices_daily: FAILED")
            failure_count += 1
    except Exception as e:
        logger.error(f"✗ stock_prices_daily: ERROR - {e}", exc_info=True)
        failure_count += 1

    # That's it! Done.
    # Everything else will be computed on-demand by Phase 5/6.

    elapsed = time.time() - pipeline_start
    now_et_end = datetime.now(ZoneInfo("America/New_York"))

    logger.info("\n" + "=" * 80)
    logger.info("MORNING PREP COMPLETE")
    logger.info(f"End: {now_et_end.strftime('%H:%M:%S %Z')}")
    logger.info(f"Duration: {elapsed/60:.1f} minutes")
    logger.info(f"Result: {success_count} successful, {failure_count} failed")
    logger.info("=" * 80)

    if failure_count > 0:
        logger.error(f"MORNING PREP FAILED: {failure_count} loader(s) failed")
        return 1

    logger.info("MORNING PREP SUCCESS: Ready for 9:30 AM orchestrator")
    return 0


if __name__ == "__main__":
    exit_code = run_morning_prep()
    sys.exit(exit_code)
