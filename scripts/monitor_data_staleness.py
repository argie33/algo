#!/usr/bin/env python3
"""Data staleness monitor with alerts

Monitors key data tables for freshness and alerts when data is getting stale.
Runs on a schedule or manually to catch gaps in loader execution.

This script monitors ONLY the tables that have active loaders and are critical for trading.
It does NOT monitor these orphaned tables (no active writers, design debt):
- algo_daily_return_histogram (designed but never implemented)
- algo_data_patrol (no writer)
- algo_holding_period_histogram (designed but never implemented)
- earnings_history (never populated)
- equity_curve_daily (never populated)
- portfolio_holdings (never populated)
- price_extremes_52week (deprecated loader deleted)
- market_cap_computed (deprecated loader deleted)
These are known design debt and will not cause false staleness alerts.

Usage:
  python scripts/monitor_data_staleness.py                 # Check current staleness
  python scripts/monitor_data_staleness.py --watch 60      # Poll every 60 seconds
  python scripts/monitor_data_staleness.py --alert slack   # Send Slack alerts on stale data
"""

import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algo.infrastructure.market_calendar import MarketCalendar
from utils.db.context import DatabaseContext
from utils.logging.logger import get_logger

logger = get_logger(__name__)

# Track which loaders have already been alerted to avoid alert spam
_alert_history: dict[str, dict[str, Any]] = {}

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
        # Computed once per trading day by the signals pipeline (4:05 PM ET, after market
        # close) - same once-per-trading-day cadence as algo_signals/growth_metrics/etc.
        # below, not continuous intraday polling. The old 4h/8h/24h thresholds guaranteed a
        # false CRITICAL every single morning before the next EOD run (confirmed live
        # 2026-07-28: 10.9h age reported "[OK]" by check_system_health.py's own already-
        # fixed 24h gap-aware bar, but "CRITICAL" here for the identical real age).
        "fresh": 1440,  # 24 hours
        "stale": 2160,  # 36 hours
        "critical": 2880,  # 48 hours
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
    },
    "buy_sell_daily": {
        # Same once-per-trading-day cadence as algo_signals - and the same table
        # whose staleness triggers a live "[PHASE 7 CRITICAL HALT]" in the
        # orchestrator (see algo/orchestrator/phase7_signal_generation.py), yet it
        # was never added here, so the one dedicated staleness tool operators are
        # told to run (CLAUDE.md) would never have caught it going stale.
        "fresh": 1440,
        "stale": 2160,
        "critical": 2880,
    },
    "algo_performance_metrics": {
        # Legacy table synced daily from algo_performance_daily by orchestrator post-run.
        # Should be updated after each orchestrator run (Phase 9 completion).
        "fresh": 1440,
        "stale": 2160,
        "critical": 2880,
    },
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
                # growth_metrics/quality_metrics/value_metrics are UPSERT tables (ON CONFLICT
                # DO UPDATE in load_value_quality_growth_metrics.py) whose SET clause updates
                # `updated_at` on every write but never touches `created_at` - created_at is
                # INSERT-only, frozen at whenever a symbol was FIRST ever loaded. Using it here
                # produced false CRITICAL/DEAD alarms on tables the loader was updating daily
                # (confirmed live 2026-07-28: growth_metrics/quality_metrics showed 2.7d DEAD via
                # created_at while updated_at showed 4823/5508 rows freshly upserted yesterday).
                "growth_metrics": "updated_at",
                "quality_metrics": "updated_at",
                "value_metrics": "updated_at",
                "algo_trades": "updated_at",
                "algo_positions": "updated_at",
                "algo_reconciliation_log": "created_at",
                "industry_ranking": "updated_at",
                "sector_rotation_signal": "created_at",
                "trend_template_data": "created_at",
                "buy_sell_daily": "updated_at",
                "algo_performance_metrics": "updated_at",
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


def get_loader_failed(table_name: str) -> bool:
    """Check whether data_loader_status's CURRENT row for this table reports 'failed'.

    get_table_age_minutes() only measures when a row was last touched - it can't tell a
    complete, successful load apart from a crashed one that only wrote a handful of rows
    before dying (e.g. lock contention against a concurrent backfill). Confirmed live
    2026-07-28: price_daily's data_loader_status row showed status='failed',
    completion_pct=0.00, symbols_loaded=1 of 5471 - yet because that single row happened
    to include today's date, updated_at looked recent enough to report a plain green
    "FRESH" here, hiding a load that had essentially not happened. status='failed' always
    reflects the outcome of the MOST RECENT attempt (a later successful retry overwrites
    it back to 'ok'/'HEALTHY'), so this adds a real-failure signal age alone can't see.
    """
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT status FROM data_loader_status WHERE table_name = %s",
                (table_name,),
            )
            row = cur.fetchone()
            if row is None:
                return False
            status = row[0] if not isinstance(row, dict) else row["status"]
            return str(status).lower() == "failed"
    except Exception as e:
        logger.error(f"Error checking loader status for {table_name}: {e}")
        return False


def get_price_symbol_coverage() -> tuple[int, int, float] | None:
    """Return (symbols_loaded, total_active_symbols, coverage_pct) for the most recent
    trading day's price_daily rows, scoped to symbols currently active in stock_symbols -
    or None if the query fails.

    check_all_tables()'s age-based check only looks at MAX(updated_at) across the *whole*
    table - if 90%+ of symbols got today's row, the table reads FRESH even while a
    meaningful chunk of individual symbols have been silently stuck for days (a run that
    crashes mid-batch leaves whichever symbols hadn't been processed yet frozen at their
    last successful date, with no per-symbol alert; see
    steering/LOADER_RECOVERY_GUIDE.md, gap found 2026-07-20 - 497 active symbols stuck 3+
    trading days behind after exactly this kind of crash, invisible to this script the
    whole time). Phase 1 already fails-closed on this for trading itself (see
    algo/orchestrator/phase1_data_freshness.py) but that only halts the orchestrator - the
    diagnostic tools operators run *before* trading hours to sanity-check data were blind
    to it. Mirrors Phase 1's own query (same active-symbol scoping, same non-NULL
    open/close requirement) so the two report the same number.
    """
    try:
        today = date.today()
        # Price data is only available after EOD load - find the most recent date with data
        d = today - timedelta(days=1)  # Start with yesterday
        last_trading_day = None
        for _ in range(10):
            if MarketCalendar.is_trading_day(d):
                last_trading_day = d
                break
            d -= timedelta(days=1)

        with DatabaseContext("read") as cur:
            cur.execute(
                """SELECT COUNT(DISTINCT pd.symbol)
                   FROM price_daily pd
                   JOIN stock_symbols ss ON ss.symbol = pd.symbol AND ss.active = true
                   WHERE pd.date = %s AND pd.close IS NOT NULL AND pd.open IS NOT NULL""",
                (last_trading_day,),
            )
            row = cur.fetchone()
            symbols_loaded = row[0] if row and row[0] is not None else 0

            cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = true")
            row = cur.fetchone()
            total_active = row[0] if row and row[0] is not None else 0

        coverage_pct = (symbols_loaded / max(total_active, 1)) * 100
        return symbols_loaded, total_active, coverage_pct
    except Exception as e:
        logger.error(f"Error checking price_daily symbol coverage: {e}")
        return None


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
                    "buy_sell_daily",
                    # stock_scores/algo_trades/algo_positions share the identical once-
                    # per-trading-day cadence as the tables above (stock_scores via the
                    # signals pipeline; algo_trades/algo_positions only change when an
                    # entry/exit actually executes, which can't happen when markets are
                    # closed). Omitting them here meant every weekend/holiday this
                    # script reported them CRITICAL and told operators to "FIX
                    # IMMEDIATELY" by manually triggering the morning pipeline - a false
                    # alarm for data that is legitimately fine, confirmed live 2026-07-26
                    # (a Sunday): all three flagged STALE/CRITICAL purely from the
                    # Friday->Sunday gap, with no actual loader problem.
                    "stock_scores",
                    "algo_trades",
                    "algo_positions",
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

        # A recent-looking updated_at can't distinguish a real refresh from a crashed run
        # that only wrote a handful of rows - cross-check the loader's own reported outcome.
        if get_loader_failed(table):
            status = f"🔴 LOAD FAILED (last touch {format_age(age) if age is not None else 'unknown'})"
            level = "critical"

        results[table] = {
            "status": status,
            "level": level,
            "age_minutes": age,
        }

    # Table-wide age can't see a partial-batch crash that leaves a subset of symbols
    # stuck for days - cross-check per-symbol coverage the same way Phase 1 does.
    coverage = get_price_symbol_coverage()
    if coverage is not None:
        symbols_loaded, total_active, coverage_pct = coverage
        try:
            from algo.infrastructure.config.main import get_config

            config = get_config()
            min_coverage_pct = config["phase1_min_coverage_pct"]
            min_symbol_count = config["phase1_min_symbol_count"]
        except Exception as e:
            logger.warning(f"Could not load phase1 coverage thresholds, using defaults: {e}")
            min_coverage_pct, min_symbol_count = 75, 5000

        if symbols_loaded < min_symbol_count or coverage_pct < min_coverage_pct:
            status = f"🔴 SYMBOL COVERAGE INSUFFICIENT ({symbols_loaded}/{total_active} = {coverage_pct:.1f}%)"
            level = "critical"
        else:
            status = f"✅ {symbols_loaded}/{total_active} symbols ({coverage_pct:.1f}%)"
            level = "ok"

        results["price_daily_symbol_coverage"] = {
            "status": status,
            "level": level,
            "age_minutes": None,
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


def send_slack_alert(table_name: str, level: str, age_minutes: int, threshold_minutes: int) -> None:
    """Send Slack alert for stale data.

    Args:
        table_name: Name of stale table
        level: Severity level (critical, dead, stale)
        age_minutes: Age of data in minutes
        threshold_minutes: Threshold for this level
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.warning(f"[ALERT] SLACK_WEBHOOK_URL not set - cannot send Slack alert for {table_name}")
        return

    try:
        import requests

        hours = age_minutes // 60
        message = {
            "text": f"⚠️ Data Staleness Alert: {table_name}",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "🚨 Data Staleness Alert"},
                }
            ],
            "attachments": [
                {
                    "color": {"critical": "danger", "dead": "danger", "stale": "warning"}.get(level, "warning"),
                    "fields": [
                        {"title": "Table", "value": table_name, "short": True},
                        {"title": "Severity", "value": level.upper(), "short": True},
                        {"title": "Age", "value": f"{age_minutes} minutes ({hours}h)", "short": True},
                        {"title": "Threshold", "value": f"{threshold_minutes} minutes", "short": True},
                        {"title": "Timestamp", "value": datetime.now(timezone.utc).isoformat(), "short": False},
                    ],
                    "footer": "Data Staleness Monitor",
                    "ts": int(datetime.now(timezone.utc).timestamp()),
                }
            ],
        }

        response = requests.post(webhook_url, json=message, timeout=5)
        if response.status_code == 200:
            logger.info(f"[ALERT] Slack alert sent for {table_name}")
        else:
            logger.warning(f"[ALERT] Slack webhook returned {response.status_code}: {response.text}")

    except Exception as e:
        logger.error(f"[ALERT] Failed to send Slack alert for {table_name}: {e}")


def should_send_alert(table_name: str, level: str) -> bool:
    """Determine if alert should be sent (avoid spam).

    Sends alert only if:
    1. This is the first time we're seeing this table/level combo
    2. OR at least 1 hour has passed since last alert for this table

    Args:
        table_name: Name of the table
        level: Severity level

    Returns:
        True if alert should be sent
    """
    now = datetime.now(timezone.utc)
    key = f"{table_name}:{level}"

    if key not in _alert_history:
        _alert_history[key] = {"first_alert": now, "last_alert": now, "count": 1}
        return True

    history = _alert_history[key]
    time_since_last = (now - history["last_alert"]).total_seconds() / 3600  # Convert to hours

    if time_since_last >= 1:  # Only re-alert after 1 hour
        history["last_alert"] = now
        history["count"] += 1
        return True

    return False


def send_alert(table_name: str, level: str, age_minutes: int, threshold_minutes: int, method: str = "log") -> None:
    """Send alert for stale data using specified method.

    Args:
        table_name: Name of stale table
        level: Severity level (critical, dead, stale)
        age_minutes: Age of data in minutes
        threshold_minutes: Threshold for this level
        method: Alert method (slack, email, log)
    """
    if not should_send_alert(table_name, level):
        return  # Alert already sent recently

    if method == "slack":
        send_slack_alert(table_name, level, age_minutes, threshold_minutes)
    elif method == "email":
        # Email alerting not yet implemented - fall back to log
        logger.warning(
            f"[ALERT] Email alerting not yet implemented. "
            f"Table: {table_name}, Level: {level}, Age: {age_minutes}min"
        )
    elif method == "log":
        logger.warning(
            f"[ALERT] Data staleness: {table_name} is {level.upper()} "
            f"(age={age_minutes}min, threshold={threshold_minutes}min)"
        )


def watch_mode(interval: int, alert_method: str | None = None) -> None:
    """Continuous monitoring mode.

    Args:
        interval: Check interval in seconds
        alert_method: Alert method (slack, email, log, or None to disable)
    """
    print(f"[WATCH MODE] Checking every {interval}s. Press Ctrl+C to exit.")
    if alert_method:
        print(f"[WATCH MODE] Alerts enabled: {alert_method}")
    try:
        while True:
            results = check_all_tables()
            print_report(results)

            # Check for critical staleness and send alerts
            critical = [t for t, d in results.items() if d["level"] in ("critical", "dead")]
            if critical:
                print(f"⚠️  ALERT: {len(critical)} table(s) critically stale!")
                if alert_method:
                    for table in critical:
                        data = results[table]
                        send_alert(table, data["level"], data["age_minutes"], data["stale_threshold"], alert_method)

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[WATCH MODE] Stopped by user.")
        sys.exit(0)


if __name__ == "__main__":
    import argparse

    # Windows console encoding fix. Reassigning sys.stdout/sys.stderr must only happen
    # when this script is actually run directly - doing it at module import time (as
    # this previously did) permanently replaces pytest's own capture streams for the
    # rest of the test process the first time anything imports this module, eventually
    # crashing pytest's capture teardown with "ValueError: I/O operation on closed
    # file" (confirmed live 2026-07-26 after adding a test that imports this module).
    if sys.platform.startswith("win"):
        import io

        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except (AttributeError, TypeError, OSError):
            # Non-critical: Ignore if stdout/stderr redirection fails (Windows console encoding issue)
            # The script will continue with system default encoding
            pass

    parser = argparse.ArgumentParser(description="Monitor data table freshness and alert on staleness")
    parser.add_argument("--watch", type=int, help="Continuous watch mode (check every N seconds)", metavar="SECONDS")
    parser.add_argument(
        "--alert",
        choices=["slack", "email", "log"],
        help="Alert method for critical staleness (slack requires SLACK_WEBHOOK_URL env var)",
    )

    args = parser.parse_args()

    if args.watch:
        watch_mode(args.watch, alert_method=args.alert)
    else:
        results = check_all_tables()
        print_report(results)

        # Send alerts if requested
        if args.alert:
            for table, data in results.items():
                if data["level"] in ("critical", "dead"):
                    send_alert(table, data["level"], data["age_minutes"], data["stale_threshold"], args.alert)

        # Exit with error code if critical staleness detected
        critical = [t for t, d in results.items() if d["level"] in ("critical", "dead")]
        sys.exit(len(critical))
