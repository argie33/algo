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
from datetime import date, datetime, timedelta, timezone

# Windows encoding fix
if sys.platform.startswith("win"):
    import io

    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algo.infrastructure.market_calendar import MarketCalendar
from utils.db.context import DatabaseContext
from utils.logging import logger

# Freshness thresholds (max age before each status)
# For price/technical tables: thresholds differ on trading vs non-trading days
# On non-trading days (weekends/holidays), data from last trading day is fresh
THRESHOLDS = {
    # price_daily/technical_data_daily/market_exposure_daily were previously tuned
    # for continuous intraday polling ("fresh: 30 min during trading hours") - a
    # feature this system has never had. The actual loader is a single once-daily
    # EOD batch (see CLAUDE.md's documented 2:00 AM ET morning schedule). That
    # mismatch was invisible while get_table_age_minutes() measured age via
    # calendar-day arithmetic (see its docstring), which never produced a value
    # between 0 and 1440 min for these tables regardless of the thresholds below.
    # Now that age reflects real elapsed time since load, thresholds must match the
    # real once-per-trading-day cadence - same 24h/36h/48h convention already used
    # for algo_signals/growth_metrics/quality_metrics/value_metrics below.
    "price_daily": {
        "fresh": 1440,  # 24 hours - one trading day's normal loader lag
        "stale": 2160,  # 36 hours
        "critical": 2880,  # 48 hours
    },
    "technical_data_daily": {
        "fresh": 1440,
        "stale": 2160,
        "critical": 2880,
    },
    "stock_scores": {
        "fresh": 240,  # 4 hours
        "stale": 480,  # 8 hours
        "critical": 1440,  # 24 hours
    },
    "market_exposure_daily": {
        "fresh": 1440,
        "stale": 2160,
        "critical": 2880,
    },
    "algo_signals": {
        # Signals are generated once per trading day (with the orchestrator's morning
        # run), not continuously - a 1-trading-day-old row is the expected steady state
        # every single morning before today's run has executed, not an incident. The
        # previous 8h/24h thresholds guaranteed a false CRITICAL every single weekday
        # (1 calendar day = 1440min already exceeds the old 1440min "stale" cutoff).
        "fresh": 1440,  # 24 hours - one full trading day is the normal cadence
        "stale": 2160,  # 36 hours
        "critical": 2880,  # 48 hours
    },
    "growth_metrics": {
        # Same once-per-trading-day cadence mismatch as algo_signals above: these are
        # computed by the EOD metrics pipeline once daily, so the old 4h/24h thresholds
        # falsely reported CRITICAL every single morning regardless of actual health.
        "fresh": 1440,
        "stale": 2160,
        "critical": 2880,
    },
    "quality_metrics": {
        "fresh": 1440,
        "stale": 2160,
        "critical": 2880,
    },
    "value_metrics": {
        "fresh": 1440,
        "stale": 2160,
        "critical": 2880,
    },
    "algo_trades": {
        "fresh": 1440,
        "stale": 2880,
        "critical": 5760,
    },
    "algo_positions": {
        "fresh": 480,
        "stale": 1440,
        "critical": 2880,
    },
    "algo_reconciliation_log": {
        # Same once-per-trading-day cadence mismatch as algo_signals above.
        "fresh": 1440,
        "stale": 2160,
        "critical": 2880,
    },
    "industry_ranking": {
        "fresh": 1440,
        "stale": 5040,
        "critical": 10080,
    },
    "sector_rotation_signal": {
        "fresh": 1440,
        "stale": 5040,
        "critical": 10080,
    },
    "trend_template_data": {
        "fresh": 1440,
        "stale": 5040,
        "critical": 10080,
    }
}


def get_table_age_minutes(table_name: str) -> float | None:
    """Get age of latest data in table (minutes), from the real load timestamp.

    Previously the trading-cadence tables (price_daily, technical_data_daily,
    etc.) were keyed off their `date` column (the *trading* date, not when the
    row was written) and measured age via `CURRENT_DATE - MAX(date)`, i.e.
    calendar-day arithmetic. That collapses to exactly 0 or a multiple of 1440
    minutes with zero intraday resolution - a row loaded at 11pm on trading day
    D reads as "0 minutes old" all evening, then the instant the calendar rolls
    past midnight it jumps straight to a flat 1440 minutes (>= every table's
    "critical" threshold here), reporting DEAD even though the data is only a
    few hours old and loaded exactly on schedule. Confirmed live 2026-07-21:
    price_daily/technical_data_daily/market_exposure_daily all showed DEAD
    (1.0d) at ~4am with data actually loaded 2-4h earlier. All of these tables
    carry a real `created_at`/`updated_at` load timestamp - use that directly
    for true elapsed time; the trading-day gap logic in check_all_tables()
    still relaxes the thresholds across weekends/holidays.
    """
    try:
        with DatabaseContext("read") as cur:
            # Map table names to their actual load-timestamp columns (not the
            # trading-date column) so age reflects real elapsed time.
            timestamp_cols = {
                "price_daily": "updated_at",
                "technical_data_daily": "updated_at",
                "stock_scores": "updated_at",
                "market_exposure_daily": "updated_at",
                "algo_signals": "updated_at",
                "growth_metrics": "created_at",
                "quality_metrics": "created_at",
                "value_metrics": "created_at",
                "algo_trades": "updated_at",
                "algo_positions": "updated_at",
                "algo_reconciliation_log": "created_at",
                "industry_ranking": "updated_at",
                "sector_rotation_signal": "created_at",
                "trend_template_data": "created_at",
            }

            if table_name not in timestamp_cols:
                return None

            ts_col = timestamp_cols[table_name]

            # stock_scores.updated_at is `timestamp without time zone`, written via
            # datetime.now(timezone.utc) in load_stock_scores.py. It used to need an explicit
            # `AT TIME ZONE 'UTC'` treatment here because BulkInsertManager's COPY/CSV path
            # silently dropped the UTC offset (storing true-UTC digits uncorrected). That bug
            # is now fixed the other way: BulkInsertManager converts tz-aware datetimes to
            # session-local (America/Chicago) wall-clock before storage, matching a plain
            # parameterized INSERT - so the stored digits are session-local like every other
            # naive timestamp column. Verified live: bare NOW() - MAX(updated_at) matches real
            # elapsed time; `AT TIME ZONE 'UTC'` now overstates age by the UTC/Chicago offset
            # (~5-6h) - exactly what re-broke this (reported ~5h stale on data written minutes
            # earlier) after the BulkInsertManager fix landed. No special-case needed.
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
    today = date.today()

    # Whether today is itself a trading day is the wrong question for freshness: on a
    # Monday morning before the loader has run, the most recent data is Friday's close,
    # 3 calendar days back, even though today trades. What matters is whether there is a
    # weekend/holiday gap since the last completed trading day - if so, that gap's data
    # is legitimately fresh and should get the relaxed threshold regardless of whether
    # today happens to be a trading day.
    prev_trading_day = today - timedelta(days=1)
    for _ in range(10):
        if MarketCalendar.is_trading_day(prev_trading_day):
            break
        prev_trading_day -= timedelta(days=1)
    spans_gap = (today - prev_trading_day).days > 1

    for table, thresholds in THRESHOLDS.items():
        age = get_table_age_minutes(table)

        if age is None:
            status = "❓ NO DATA"
            level = "unknown"
        else:
            formatted = format_age(age)

            # When there's a weekend/holiday gap, shift ALL tiers (including "fresh", not
            # just stale/critical) by the size of that gap for tables tied to the trading
            # calendar. A fixed "fresh_non_trading" cap (previously a static 48h) breaks as
            # soon as the actual gap exceeds it: every ordinary Friday->Monday gap is itself
            # 3 calendar days (4320min), so a static 48h (2880min) cap falsely read Monday
            # morning's still-fresh Friday data as WARNING before intraday updates began.
            # Scaling "fresh" by the same gap_minutes used for stale/critical below fixes
            # that for any gap length (weekend, holiday, or multi-day holiday weekend alike).
            # Applies to every table that updates once per trading day - both plain `date`
            # columns (one row per trading day: price_daily, technical_data_daily,
            # market_exposure_daily, sector_rotation_signal, trend_template_data,
            # algo_signals, algo_reconciliation_log, industry_ranking) and once-daily
            # `created_at`/`updated_at` batch tables (growth_metrics, quality_metrics,
            # value_metrics) whose EOD write is exactly as stale after a weekend as these.
            if (
                table
                in (
                    "price_daily",
                    "technical_data_daily",
                    "market_exposure_daily",
                    "sector_rotation_signal",
                    "trend_template_data",
                    "algo_signals",
                    "algo_reconciliation_log",
                    "industry_ranking",
                    "growth_metrics",
                    "quality_metrics",
                    "value_metrics",
                )
                and spans_gap
            ):
                gap_minutes = (today - prev_trading_day).days * 1440
                fresh_threshold = thresholds["fresh"] + gap_minutes
                stale_threshold = thresholds["stale"] + gap_minutes
                critical_threshold = thresholds["critical"] + gap_minutes
            else:
                fresh_threshold = thresholds["fresh"]
                stale_threshold = thresholds["stale"]
                critical_threshold = thresholds["critical"]

            emoji = "✅" if age < fresh_threshold else "⚠️ " if age < stale_threshold else "🔴" if age < critical_threshold else "💀"

            if age < fresh_threshold:
                status = f"{emoji} FRESH ({formatted})"
                level = "ok"
            elif age < stale_threshold:
                status = f"{emoji} STALE ({formatted})"
                level = "warning"
            elif age < critical_threshold:
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
    warning_tables = [t for t, d in results.items() if d["level"] == "warning"]
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
        if warning_tables:
            print(f"\n⚠️  Also approaching staleness (not yet critical): {', '.join(warning_tables)}")
    elif warning_tables:
        print(f"\n⚠️  STALE (WARNING) DATA: {', '.join(warning_tables)}")
        print("\nNot yet critical, but past the fresh threshold - check soon:")
        print("  1. Local dev - run orchestrator/loaders to refresh:")
        print("     python scripts/run_local_orchestrator.py --morning")
        print("  2. If this persists across checks, treat it like critical staleness above.")
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
