#!/usr/bin/env python3
"""Local data loader scheduler - runs data fetches at scheduled times.

Mirrors the production EventBridge Scheduler pipeline:
- Morning: 2:00 AM ET (prices + technicals for market open)
- Signals/EOD: 4:05 PM ET (closing prices + buy/sell signals)
- Metrics: 7:00 PM ET (slow financials: statements, 13F, positioning)

Usage:
    python scripts/data_loader_scheduler.py              # Start scheduler (runs continuously)
    python scripts/data_loader_scheduler.py --once       # Run once (useful for testing)
"""

import logging
import subprocess
import sys
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# Data loading pipeline times (ET)
LOAD_PIPELINES = {
    "morning": time(2, 0),  # 2:00 AM ET (pre-market)
    "signals": time(16, 5),  # 4:05 PM ET (post-market close)
    "metrics": time(19, 0),  # 7:00 PM ET (after-hours, slow financials)
}


def is_market_day() -> bool:
    """Check if today is a market day (Mon-Fri)."""
    now = datetime.now(ET)
    if now.weekday() >= 5:  # Saturday/Sunday
        return False
    return True


def get_next_pipeline() -> tuple[str, time] | None:
    """Return (pipeline_name, scheduled_time) for next pipeline, or None if all done for day."""
    now = datetime.now(ET)
    current_time = now.time()

    # Check each pipeline in order
    for pipeline_name in ["morning", "signals", "metrics"]:
        pipeline_time = LOAD_PIPELINES[pipeline_name]
        if current_time < pipeline_time:
            return pipeline_name, pipeline_time

    return None


def run_pipeline(pipeline_name: str) -> bool:
    """Run data loader for the given pipeline. Return True if successful."""
    logger.info(f"Starting {pipeline_name} data pipeline")
    try:
        result = subprocess.run(
            ["python", "scripts/local_loader_scheduler.py", "--now", pipeline_name],
            capture_output=False,
            timeout=1800,  # 30-minute max runtime
        )
        if result.returncode == 0:
            logger.info(f"SUCCESS: {pipeline_name} pipeline completed")
            return True
        else:
            logger.error(f"FAILED: {pipeline_name} pipeline exited with code {result.returncode}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"FAILED: {pipeline_name} pipeline timed out (30 minutes)")
        return False
    except Exception as e:
        logger.error(f"FAILED: {pipeline_name} pipeline error: {e}")
        return False


def scheduler_loop() -> None:
    """Main scheduler loop - runs continuously, executing pipelines at scheduled times."""
    logger.info("Data loader scheduler started")
    pipelines_str = ", ".join(f"{k}={v.strftime('%H:%M')} ET" for k, v in LOAD_PIPELINES.items())
    logger.info(f"Data pipelines scheduled for: {pipelines_str}")

    executed_today = set()

    while True:
        now = datetime.now(ET)

        if not is_market_day():
            if now.hour == 0 and now.minute == 0:  # Log once at midnight
                logger.info("Weekend/holiday - no data pipelines run today")
            next_check = timedelta(hours=1)
        else:
            pipeline_info = get_next_pipeline()
            if pipeline_info is None:
                # All pipelines done for today
                if "all_done" not in executed_today:
                    logger.info("All data pipelines completed for today")
                    executed_today.add("all_done")
                next_check = timedelta(hours=1)
            else:
                pipeline_name, pipeline_time = pipeline_info
                now.time()
                time_until = datetime.combine(now.date(), pipeline_time, tzinfo=ET) - now
                time_until_secs = max(0, int(time_until.total_seconds()))

                if pipeline_name not in executed_today:
                    # Check if it's time to run (within 5 minutes of scheduled time)
                    scheduled_dt = datetime.combine(now.date(), pipeline_time, tzinfo=ET)
                    if abs((now - scheduled_dt).total_seconds()) <= 300:
                        if run_pipeline(pipeline_name):
                            executed_today.add(pipeline_name)
                        next_check = timedelta(minutes=5)
                    else:
                        logger.info(
                            f"Next pipeline: {pipeline_name} at {pipeline_time.strftime('%H:%M')} ET ({time_until_secs}s)"
                        )
                        # Sleep until 10 minutes before the pipeline
                        next_check_secs = max(60, time_until_secs - 600)
                        next_check = timedelta(seconds=next_check_secs)
                else:
                    logger.info(f"{pipeline_name} already executed today, checking next pipeline")
                    next_check = timedelta(minutes=1)

        logger.debug(f"Next check in {int(next_check.total_seconds())}s")
        try:
            import time

            time.sleep(min(next_check.total_seconds(), 60))  # Max 1-min sleep intervals
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            break


def main() -> None:
    """Entry point."""
    if "--once" in sys.argv:
        # Run once (useful for testing)
        if not is_market_day():
            logger.info("Not a market day - no pipelines will run")
            return

        pipeline_info = get_next_pipeline()
        if pipeline_info is None:
            logger.info("All pipelines already executed for today")
            return

        pipeline_name, pipeline_time = pipeline_info
        logger.info(f"Running {pipeline_name} pipeline (next scheduled for {pipeline_time.strftime('%H:%M')} ET)")
        run_pipeline(pipeline_name)
    else:
        # Run continuous scheduler
        scheduler_loop()


if __name__ == "__main__":
    main()
