#!/usr/bin/env python3
"""Local orchestrator scheduler - runs trading sessions at scheduled times.

Usage:
    python scripts/orchestrator_scheduler.py              # Start scheduler (runs continuously)
    python scripts/orchestrator_scheduler.py --once       # Run once (useful for testing)
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

# Trading session times (ET). Must match terraform/modules/services/2x-daily-orchestrator.tf's
# 4 real scheduled sessions (morning/afternoon/preclose/evening) exactly - this dict previously
# had only 3 entries and mislabeled the 3:00 PM slot as "evening", which both ran the wrong
# --{session_name} flag (there was no --preclose) and meant this local scheduler never
# exercised the real 5:30 PM evening run (production's evening is monitor-only/dry_run - see
# LIVE_TRADING_RUN_IDENTIFIERS/MONITOR_ONLY_RUN_IDENTIFIERS in
# lambda/algo_orchestrator/lambda_function.py) at all locally.
TRADING_SESSIONS = {
    "morning": time(9, 30),  # 9:30 AM ET (market open, live trading)
    "afternoon": time(13, 0),  # 1:00 PM ET (rebalance, live trading)
    "preclose": time(15, 0),  # 3:00 PM ET (final entries/exits before close, live trading)
    "evening": time(17, 30),  # 5:30 PM ET (full pipeline, monitor-only - no new entries)
}


def is_market_day() -> bool:
    """Check if today is a market day (Mon-Fri, not holiday)."""
    now = datetime.now(ET)
    # Simple check: Mon-Fri (0-4)
    if now.weekday() >= 5:  # Saturday/Sunday
        return False
    return True


def get_next_session() -> tuple[str, time] | None:
    """Return (session_name, scheduled_time) for next session, or None if all done for day."""
    now = datetime.now(ET)
    current_time = now.time()

    # Check each session in order
    for session_name in ["morning", "afternoon", "preclose", "evening"]:
        session_time = TRADING_SESSIONS[session_name]
        if current_time < session_time:
            return session_name, session_time

    return None


def run_session(session_name: str) -> bool:
    """Run orchestrator for the given session. Return True if successful."""
    logger.info(f"Starting {session_name} session")
    try:
        result = subprocess.run(
            ["python", "scripts/run_local_orchestrator.py", f"--{session_name}"],
            capture_output=False,
            timeout=600,  # 10-minute max runtime
        )
        if result.returncode == 0:
            logger.info(f"✓ {session_name} session completed successfully")
            return True
        else:
            logger.error(f"✗ {session_name} session failed with code {result.returncode}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"✗ {session_name} session timed out (10 minutes)")
        return False
    except Exception as e:
        logger.error(f"✗ {session_name} session error: {e}")
        return False


def scheduler_loop() -> None:
    """Main scheduler loop - runs continuously, executing sessions at scheduled times."""
    logger.info("Orchestrator scheduler started")
    sessions_str = ", ".join(f"{k}={v.strftime('%H:%M')} ET" for k, v in TRADING_SESSIONS.items())
    logger.info(f"Trading sessions scheduled for: {sessions_str}")

    executed_today = set()

    while True:
        now = datetime.now(ET)

        if not is_market_day():
            if now.hour == 0 and now.minute == 0:  # Log once at midnight
                logger.info("Weekend/holiday - no trading sessions today")
            next_check = timedelta(hours=1)
        else:
            session_info = get_next_session()
            if session_info is None:
                # All sessions done for today
                if "all_done" not in executed_today:
                    logger.info("All trading sessions completed for today")
                    executed_today.add("all_done")
                next_check = timedelta(hours=1)
            else:
                session_name, session_time = session_info
                now.time()
                time_until = datetime.combine(now.date(), session_time, tzinfo=ET) - now
                time_until_secs = max(0, int(time_until.total_seconds()))

                if session_name not in executed_today:
                    # Check if it's time to run (within 2 minutes of scheduled time)
                    scheduled_dt = datetime.combine(now.date(), session_time, tzinfo=ET)
                    if abs((now - scheduled_dt).total_seconds()) <= 120:
                        if run_session(session_name):
                            executed_today.add(session_name)
                        next_check = timedelta(minutes=1)
                    else:
                        logger.info(
                            f"Next session: {session_name} at {session_time.strftime('%H:%M')} ET ({time_until_secs}s)"
                        )
                        # Sleep until 5 minutes before the session
                        next_check_secs = max(60, time_until_secs - 300)
                        next_check = timedelta(seconds=next_check_secs)
                else:
                    logger.info(f"{session_name} already executed today, checking next session")
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
            logger.info("Not a market day - no sessions will run")
            return

        session_info = get_next_session()
        if session_info is None:
            logger.info("All sessions already executed for today")
            return

        session_name, session_time = session_info
        logger.info(f"Running {session_name} session (next scheduled for {session_time.strftime('%H:%M')} ET)")
        run_session(session_name)
    else:
        # Run continuous scheduler
        scheduler_loop()


if __name__ == "__main__":
    main()
