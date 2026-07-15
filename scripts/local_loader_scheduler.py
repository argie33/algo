#!/usr/bin/env python3
"""Local data loader scheduler - runs loaders on a schedule for local development.

For local dev environments where AWS EventBridge isn't available.
Runs key loaders at scheduled times to keep data fresh:
- 2:00 AM ET: Morning pipeline (prices, technicals, market health)
- 7:00 PM ET: Evening metrics refresh (scores, quality, growth, etc.)
- 4:05 PM ET: EOD pipeline (end-of-day analysis)

Usage:
  python3 scripts/local_loader_scheduler.py                # Run scheduler daemon
  python3 scripts/local_loader_scheduler.py --now morning  # Run morning pipeline now
  python3 scripts/local_loader_scheduler.py --now eod      # Run EOD pipeline now
"""

import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

# Configure logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

EASTERN_TZ = ZoneInfo("America/New_York")

# Loader definitions for each pipeline
LOADERS = {
    "morning": {
        "description": "Morning pipeline (2:00 AM ET): prices + technicals + market health",
        "loaders": ["load_prices.py", "load_technical_indicators.py", "load_market_health_daily.py"],
        "interval_hours": 24,
        "target_hour": 2,
        "target_minute": 0,
    },
    "reference": {
        "description": "Reference data (9:15 AM ET): yfinance snapshot + derived metrics (company profile, earnings)",
        "loaders": ["load_yfinance_snapshot.py", "load_yfinance_derived_metrics.py"],
        "interval_hours": 24,
        "target_hour": 9,
        "target_minute": 15,
    },
    "metrics": {
        "description": "Metrics pipeline (7:00 PM ET): quality, growth, value, risk (stability+momentum), stock scores",
        "loaders": [
            "load_financial_statements.py",
            "load_quality_growth_metrics.py",
            "load_risk_metrics_daily.py",
            "load_stock_scores.py",
        ],
        "interval_hours": 24,
        "target_hour": 19,
        "target_minute": 0,
    },
}


def run_loader_now(loader_name):
    """Run a single loader immediately."""
    logger.info(f"Running loader: {loader_name}")

    loader_path = f"loaders/{loader_name}"
    if not os.path.exists(loader_path):
        logger.error(f"Loader not found: {loader_path}")
        return False

    try:
        result = subprocess.run(
            ["python3", loader_path],
            timeout=3600,  # 1 hour timeout
            check=False,
        )
        if result.returncode == 0:
            logger.info(f"✓ Loader succeeded: {loader_name}")
            return True
        else:
            logger.error(f"✗ Loader failed: {loader_name} (exit code {result.returncode})")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"✗ Loader timeout: {loader_name}")
        return False
    except Exception as e:
        logger.error(f"✗ Loader error: {loader_name} - {e}")
        return False


def run_pipeline(pipeline_name):
    """Run all loaders in a pipeline."""
    if pipeline_name not in LOADERS:
        logger.error(f"Unknown pipeline: {pipeline_name}")
        return False

    pipeline = LOADERS[pipeline_name]
    logger.info(f"\n{'=' * 70}")
    logger.info(f"Starting pipeline: {pipeline['description']}")
    logger.info(f"{'=' * 70}\n")

    success_count = 0
    for loader in pipeline["loaders"]:
        if run_loader_now(loader):
            success_count += 1
        time.sleep(2)  # Brief pause between loaders

    logger.info(f"\nPipeline {pipeline_name} completed: {success_count}/{len(pipeline['loaders'])} loaders succeeded\n")
    return success_count == len(pipeline["loaders"])


def time_until_next_run(target_hour, target_minute):
    now = datetime.now(EASTERN_TZ)
    next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

    # If the time has already passed today, schedule for tomorrow
    if next_run <= now:
        from datetime import timedelta

        next_run += timedelta(days=1)

    seconds_until = (next_run - now).total_seconds()
    return int(seconds_until), next_run


def is_trading_day(date_obj):
    # Simple check: Mon-Fri only (not considering holidays for now)
    return date_obj.weekday() < 5  # 0-4 = Mon-Fri


def scheduler_daemon():
    """Run as a daemon, checking every minute for scheduled runs."""
    logger.info("Local data loader scheduler started")
    logger.info(f"Timezone: {EASTERN_TZ}")
    logger.info("\nScheduled pipelines:")
    for name, config in LOADERS.items():
        logger.info(f"  {name}: {config['description']}")

    last_run = {}

    while True:
        try:
            now = datetime.now(EASTERN_TZ)

            # Check each pipeline
            for pipeline_name, pipeline in LOADERS.items():
                target_hour = pipeline["target_hour"]
                target_minute = pipeline["target_minute"]

                # Check if it's time to run
                if now.hour == target_hour and now.minute == target_minute:
                    # Make sure we only run once per day
                    last_key = f"{pipeline_name}_{now.date()}"
                    if last_key not in last_run:
                        # Check if today is a trading day
                        if is_trading_day(now):
                            logger.info(f"Running scheduled pipeline: {pipeline_name}")
                            run_pipeline(pipeline_name)
                            last_run[last_key] = True
                        else:
                            logger.info(f"Skipping {pipeline_name} - non-trading day")
                            last_run[last_key] = True

            # Clean up old entries (keep last 7 days)
            cutoff_date = (now - __import__("datetime").timedelta(days=7)).date()
            for key in list(last_run.keys()):
                if key.split("_")[1] < str(cutoff_date):
                    del last_run[key]

            # Sleep for 30 seconds before checking again
            time.sleep(30)

        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            break
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            time.sleep(60)


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        if sys.argv[1] == "--now":
            if len(sys.argv) < 3:
                logger.error("Usage: --now <pipeline_name>")
                sys.exit(1)
            pipeline_name = sys.argv[2]
            if run_pipeline(pipeline_name):
                sys.exit(0)
            else:
                sys.exit(1)
        else:
            logger.error(f"Unknown option: {sys.argv[1]}")
            sys.exit(1)
    else:
        # Run scheduler daemon
        scheduler_daemon()


if __name__ == "__main__":
    main()
