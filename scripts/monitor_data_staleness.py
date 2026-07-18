#!/usr/bin/env python3
"""Data staleness monitor with alerts

Monitors key data tables for freshness and alerts when data is getting stale.
Runs on a schedule or manually to catch gaps in loader execution.

Usage:
  python scripts/monitor_data_staleness.py                 # Check current staleness
  python scripts/monitor_data_staleness.py --watch 60      # Poll every 60 seconds
  python scripts/monitor_data_staleness.py --alert slack   # Send Slack alerts on stale data
"""

import os
import sys
import time
from datetime import datetime, timezone, date

# Windows encoding fix
if sys.platform.startswith("win"):
    import io

    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db.context import DatabaseContext
from utils.logging import logger
from algo.infrastructure.market_calendar import MarketCalendar

# Freshness thresholds (max age before each status)
# For price/technical tables: thresholds differ on trading vs non-trading days
# On non-trading days (weekends/holidays), data from last trading day is fresh
THRESHOLDS = {
    "price_daily": {
        "fresh": 30,  # 30 min during trading hours
        "stale": 240,  # 4 hours - need immediate attention
        "critical": 1440,  # 24 hours - major issue
        "fresh_non_trading": 2880,  # 48 hours on weekends/holidays (data from last trading day OK)
    },
    "technical_data_daily": {
        "fresh": 60,  # 1 hour
        "stale": 240,  # 4 hours
        "critical": 1440,  # 24 hours
        "fresh_non_trading": 2880,  # 48 hours on weekends/holidays
    },
    "stock_scores": {
        "fresh": 240,  # 4 hours
        "stale": 480,  # 8 hours
        "critical": 1440,  # 24 hours
    },
    "market_exposure_daily": {
        "fresh": 240,  # 4 hours
        "stale": 480,  # 8 hours
        "critical": 1440,  # 24 hours
    },
    "algo_signals": {
        "fresh": 480,  # 8 hours (signals only update with orchestrator)
        "stale": 1440,  # 24 hours
        "critical": 2880,  # 48 hours
    },
}


def get_table_age_minutes(table_name: str) -> float | None:
    """Get age of latest data in table (minutes).

    DATE columns (no time component) are compared by calendar day, not
    wall-clock time: same-day data is fresh regardless of what time it is
    right now. Comparing `NOW() - MAX(date_col)` directly would falsely
    report same-day data as increasingly stale as the day progresses,
    since DATE values are implicitly midnight.
    """
    try:
        with DatabaseContext("read") as cur:
            # Map table names to their timestamp columns
            timestamp_cols = {
                "price_daily": "date",
                "technical_data_daily": "date",
                "stock_scores": "updated_at",
                "market_exposure_daily": "date",
                "algo_signals": "signal_date",
            }

            if table_name not in timestamp_cols:
                return None

            ts_col = timestamp_cols[table_name]

            cur.execute(
                "SELECT data_type FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
                (table_name, ts_col),
            )
            col_row = cur.fetchone()
            is_date_col = bool(col_row and col_row[0] == "date")

            if is_date_col:
                cur.execute(f"""
                    SELECT GREATEST(CURRENT_DATE - MAX({ts_col}), 0)
                    FROM {table_name}
                """)
                row = cur.fetchone()
                if row and row[0] is not None:
                    return float(row[0]) * 1440
                return None

            cur.execute(f"""
                SELECT EXTRACT(EPOCH FROM (NOW() - MAX({ts_col}))) / 60 as age_minutes
                FROM {table_name}
            """)
            row = cur.fetchone()
            if row and row[0] is not None:
                return float(row[0])
            return None
    except Exception as e:
        logger.error(f"Error checking {table_name}: {e}")
        return None


def get_status_emoji(age_minutes: float, thresholds: dict, is_trading_day: bool = True) -> str:
    # For market data tables on non-trading days, use relaxed thresholds
    fresh_threshold = thresholds.get("fresh_non_trading", thresholds["fresh"]) if not is_trading_day else thresholds["fresh"]

    if age_minutes < fresh_threshold:
        return "✅"
    elif age_minutes < thresholds["stale"]:
        return "⚠️ "
    elif age_minutes < thresholds["critical"]:
        return "🔴"
    else:
        return "💀"


def format_age(minutes: float) -> str:
    if minutes < 60:
        return f"{minutes:.0f}m"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f}h"
    days = hours / 24
    return f"{days:.1f}d"


def check_all_tables() -> dict:
    results = {}
    is_trading_day = MarketCalendar.is_trading_day(date.today())

    for table, thresholds in THRESHOLDS.items():
        age = get_table_age_minutes(table)

        if age is None:
            status = "❓ NO DATA"
            level = "unknown"
        else:
            emoji = get_status_emoji(age, thresholds, is_trading_day)
            formatted = format_age(age)

            # Use relaxed thresholds on non-trading days for market data tables
            if table in ("price_daily", "technical_data_daily") and not is_trading_day:
                fresh_threshold = thresholds.get("fresh_non_trading", thresholds["fresh"])
            else:
                fresh_threshold = thresholds["fresh"]

            if age < fresh_threshold:
                status = f"{emoji} FRESH ({formatted})"
                level = "ok"
            elif age < thresholds["stale"]:
                status = f"{emoji} STALE ({formatted})"
                level = "warning"
            elif age < thresholds["critical"]:
                status = f"{emoji} CRITICAL ({formatted})"
                level = "critical"
            else:
                status = f"{emoji} DEAD ({formatted})"
                level = "dead"

        results[table] = {
            "status": status,
            "level": level,
            "age_minutes": age,
        }

    return results


def print_report(results: dict) -> None:
    """Print formatted report."""
    is_trading_day = MarketCalendar.is_trading_day(date.today())
    day_type = "Trading Day" if is_trading_day else "Non-Trading Day (Weekend/Holiday)"

    print("\n" + "=" * 70)
    print("DATA STALENESS REPORT")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Market Status: {day_type}")
    print("=" * 70 + "\n")

    # Count by level
    levels = {}
    for table, data in results.items():
        level = data["level"]
        levels[level] = levels.get(level, 0) + 1
        print(f"{table:30} | {data['status']}")

    print("\n" + "-" * 70)
    print("SUMMARY:")
    print(f"  ✅ OK:       {levels.get('ok', 0)}")
    print(f"  ⚠️  WARNING: {levels.get('warning', 0)}")
    print(f"  🔴 CRITICAL:{levels.get('critical', 0)}")
    print(f"  💀 DEAD:    {levels.get('dead', 0)}")
    print(f"  ❓ NO DATA:  {levels.get('unknown', 0)}")

    # Recommendations
    print("\n" + "-" * 70)
    print("ACTIONS:")

    critical_tables = [t for t, d in results.items() if d["level"] in ("critical", "dead", "unknown")]
    if critical_tables:
        print(f"\n🚨 STALE DATA DETECTED: {', '.join(critical_tables)}")
        print("\nFIX IMMEDIATELY:")
        print("  1. Check if EventBridge Scheduler is running:")
        print("     aws events list-rules --query 'Rules[?contains(Name, `pipeline`)]' --region us-east-1")
        print("\n  2. Manually trigger morning pipeline:")
        print("     aws stepfunctions start-execution \\")
        print("       --state-machine-arn 'arn:aws:states:us-east-1:xxx:stateMachine:algo-morning-pipeline' \\")
        print("       --name 'manual-refresh-$(date +%s)'")
        print("\n  3. Local dev - run orchestrator:")
        print("     python scripts/run_local_orchestrator.py --morning")
    else:
        print("\n✅ All data is fresh. No action needed.")

    print("\n" + "=" * 70 + "\n")


def watch_mode(interval: int) -> None:
    """Continuous monitoring mode."""
    print(f"[WATCH MODE] Checking every {interval}s. Press Ctrl+C to exit.")
    try:
        while True:
            results = check_all_tables()
            print_report(results)

            # Check for critical staleness
            critical = [t for t, d in results.items() if d["level"] in ("critical", "dead")]
            if critical:
                print(f"⚠️  ALERT: {len(critical)} table(s) critically stale!")

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[WATCH MODE] Stopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Monitor data table freshness and alert on staleness")
    parser.add_argument("--watch", type=int, help="Continuous watch mode (check every N seconds)", metavar="SECONDS")
    parser.add_argument(
        "--alert",
        choices=["slack", "email", "log"],
        help="Alert method for critical staleness (not yet implemented)",
    )

    args = parser.parse_args()

    if args.watch:
        watch_mode(args.watch)
    else:
        results = check_all_tables()
        print_report(results)

        # Exit with error code if critical staleness detected
        critical = [t for t, d in results.items() if d["level"] in ("critical", "dead")]
        sys.exit(len(critical))
