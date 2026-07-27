#!/usr/bin/env python3
"""Comprehensive system health check for dashboard and orchestrator.

Verifies all prerequisites for dashboard to work:
1. Database connectivity and data freshness
2. Dev server availability
3. API lambda function
4. Orchestrator execution
5. Data loader status

Run: python check_system_health.py
"""

import io
import logging
import os
import socket
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent))


def check_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        # Socket errors are expected (port unreachable), log at debug level
        logger.debug(f"[DEBUG] Port check failed for {host}:{port}: {type(e).__name__}: {e}")
        return False


def _get_db_credentials() -> dict[str, str | int]:
    """Get database credentials from environment, fail-fast on missing required vars."""
    db_host = os.getenv("DB_HOST") or "localhost"
    db_port = int(os.getenv("DB_PORT") or 5432)
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_name = os.getenv("DB_NAME")

    if not db_user:
        raise ValueError("DB_USER environment variable not set")
    if not db_password:
        raise ValueError("DB_PASSWORD environment variable not set")
    if not db_name:
        raise ValueError("DB_NAME environment variable not set")

    return {"host": db_host, "port": db_port, "user": db_user, "password": db_password, "name": db_name}


def check_database() -> dict:
    result = {
        "name": "Database",
        "status": "unknown",
        "details": [],
    }

    try:
        import psycopg2

        try:
            creds = _get_db_credentials()
            conn = psycopg2.connect(
                host=creds["host"],
                port=creds["port"],
                user=creds["user"],
                password=creds["password"],
                database=creds["name"],
                connect_timeout=5,
            )
            cur = conn.cursor()

            # Check key tables
            tables = {
                "price_daily": "Latest price data",
                "stock_scores": "Stock scoring data (used by dashboard)",
                "algo_orchestrator_runs": "Orchestrator execution history",
                "market_exposure_daily": "Market exposure metrics",
                "technical_data_daily": "Technical indicators",
            }

            all_fresh = True
            for table_name, _description in tables.items():
                try:
                    # Use SQL to calculate age for accurate timezone handling
                    # (database may store naive datetimes in local timezone)
                    if table_name == "stock_scores":
                        # stock_scores.updated_at is `timestamp without time zone`, written via
                        # datetime.now(timezone.utc) in load_stock_scores.py. Historically this
                        # loader's COPY/CSV path (BulkInsertManager) silently dropped the UTC
                        # offset before a fix (see migration history), so `AT TIME ZONE 'UTC'`
                        # was added here to compensate. That underlying bug is now fixed the
                        # other way: BulkInsertManager converts tz-aware datetimes to
                        # session-local (America/Chicago) wall-clock before storage, matching
                        # what a plain parameterized INSERT already produces - so the stored
                        # digits are session-local, same as every other naive timestamp column.
                        # Verified live: bare NOW() - MAX(updated_at) matches real elapsed time;
                        # `AT TIME ZONE 'UTC'` now overstates age by the UTC/Chicago offset
                        # (~5-6h), which is what re-broke this after the BulkInsertManager fix
                        # landed. No special-case needed - treat it like every other column.
                        cur.execute(
                            f"SELECT COUNT(*), MAX(updated_at), "
                            f"EXTRACT(EPOCH FROM (NOW() - MAX(updated_at))) / 3600 as age_hours "
                            f"FROM {table_name}"
                        )
                    elif table_name == "algo_orchestrator_runs":
                        cur.execute(
                            f"SELECT COUNT(*), MAX(started_at), "
                            f"EXTRACT(EPOCH FROM (NOW() - MAX(started_at))) / 3600 as age_hours "
                            f"FROM {table_name}"
                        )
                    elif table_name in ("market_exposure_daily", "technical_data_daily"):
                        cur.execute(
                            f"SELECT COUNT(*), MAX(updated_at), "
                            f"EXTRACT(EPOCH FROM (NOW() - MAX(updated_at))) / 3600 as age_hours "
                            f"FROM {table_name}"
                        )
                    elif table_name == "price_daily":
                        # Use created_at (actual load time), not date::timestamp (midnight of
                        # the trading date). The latter overstates age by up to ~24h: a row
                        # for trading date D loaded at 11pm on D already reads as ~23h "stale"
                        # under date::timestamp even though it loaded minutes after close.
                        # Confirmed live 2026-07-21: date::timestamp reported 27.0h stale on
                        # data actually loaded 3.5h earlier (created_at 2026-07-20 23:29).
                        cur.execute(
                            f"SELECT COUNT(*), MAX(created_at), "
                            f"EXTRACT(EPOCH FROM (NOW() - MAX(created_at))) / 3600 as age_hours "
                            f"FROM {table_name}"
                        )
                    else:
                        # For date columns, convert to timestamp at midnight for comparison
                        cur.execute(
                            f"SELECT COUNT(*), MAX(date), "
                            f"EXTRACT(EPOCH FROM (NOW() - MAX(date)::timestamp)) / 3600 as age_hours "
                            f"FROM {table_name}"
                        )

                    query_result = cur.fetchone()
                    if not query_result:
                        raise RuntimeError(f"Failed to query {table_name} stats")
                    cnt, _, age_hours = query_result
                    age_hours = float(age_hours) if age_hours is not None else None

                    # Use market-calendar-aware thresholds (consistent with monitor_data_staleness.py).
                    # CRITICAL: "is today a trading day" is the wrong question - on a Monday morning
                    # before the loader has run, the most recent data is Friday's close, 3 calendar days
                    # back, even though today trades. That previously made this check use the tight 24h
                    # trading-day threshold on every Monday/post-holiday morning and false-WARN on data
                    # that is exactly as fresh as expected. What matters is whether there's a weekend/
                    # holiday gap since the last completed trading day - shift the threshold by that
                    # gap's size, mirroring monitor_data_staleness.py's check_all_tables().
                    from datetime import date, datetime, timedelta, timezone

                    from algo.infrastructure.market_calendar import MarketCalendar

                    now = datetime.now(timezone.utc)
                    is_trading_day = MarketCalendar.is_trading_day(now.date())

                    today = date.today()
                    prev_trading_day = MarketCalendar.get_previous_trading_day(today - timedelta(days=1))
                    if prev_trading_day is None:
                        # Fallback if trading day lookup fails (shouldn't happen)
                        prev_trading_day = today - timedelta(days=1)
                    gap_days = (today - prev_trading_day).days

                    if table_name in ("price_daily", "technical_data_daily", "market_exposure_daily", "stock_scores"):
                        # On trading days with no gap: 24h (one trading day's normal loader lag).
                        # Across a weekend/holiday gap, add a full day per gap day so Friday's close on
                        # Monday morning (a 3-calendar-day gap, expected and not actionable) doesn't
                        # trip this WARN - only a loader that's actually stuck past that should.
                        # stock_scores shares the identical once-per-trading-day cadence as the other
                        # three (confirmed: monitor_data_staleness.py's THRESHOLDS applies the same
                        # gap-awareness to it) - omitting it here left this tool's own comment's claim
                        # of parity with monitor_data_staleness.py false for this one table, producing
                        # a false WARN every Monday/post-holiday morning.
                        threshold = 24 + gap_days * 24 if gap_days > 1 else 24
                    else:
                        # Always use 24h for other tables
                        threshold = 24

                    # A negative age means the stored timestamp is after NOW() - not
                    # legitimate staleness, but a data-integrity problem (e.g. a clock
                    # glitch on the writer at insert time). Surface it explicitly instead
                    # of silently reporting "fresh" with a nonsensical "-2.1h ago".
                    is_future = age_hours is not None and age_hours < 0
                    fresh = age_hours is None or (0 <= age_hours < threshold)
                    status_icon = "[WARN]" if (is_future or not fresh) else "[OK]"
                    if is_future:
                        age_str = f"{-age_hours:.1f}h in the FUTURE (clock/data-integrity issue, not stale)"
                    elif age_hours is not None:
                        age_str = f"{age_hours:.1f}h ago"
                    else:
                        age_str = "N/A"
                    day_type = "(trading)" if is_trading_day else "(non-trading)"

                    result["details"].append(f"{status_icon} {table_name}: {cnt} rows, latest: {age_str} {day_type}")

                    if not fresh or is_future:
                        all_fresh = False

                except Exception as e:
                    result["details"].append(f"[ERR] {table_name}: {str(e)[:80]}")
                    all_fresh = False

            result["status"] = "OK" if all_fresh else "WARN"
            conn.close()

        except psycopg2.OperationalError as e:
            result["status"] = "FAIL"
            result["details"].append(f"Connection failed: {e}")

    except ImportError:
        result["status"] = "FAIL"
        result["details"].append("psycopg2 not installed")

    return result


def check_dev_server() -> dict:
    result = {
        "name": "Dev Server (localhost:3001)",
        "status": "unknown",
        "details": [],
    }

    is_open = check_port_open("127.0.0.1", 3001)

    if is_open:
        result["status"] = "OK"
        result["details"].append("Dev server is running and responding")

        # Try health check
        try:
            import requests

            resp = requests.get("http://127.0.0.1:3001/api/health", timeout=5)
            if resp.status_code == 200:
                result["details"].append("Health check: OK")
            else:
                result["details"].append(f"Health check: {resp.status_code}")
        except Exception as e:
            result["details"].append(f"Health check failed: {str(e)[:60]}")
    else:
        result["status"] = "FAIL"
        result["details"].append("Dev server NOT responding on port 3001")
        result["details"].append("Fix: Run: python start_dashboard_dev.py")

    return result


def check_orchestrator() -> dict:
    result = {
        "name": "Orchestrator Status",
        "status": "unknown",
        "details": [],
    }

    try:
        import psycopg2

        creds = _get_db_credentials()
        conn = psycopg2.connect(
            host=creds["host"],
            port=creds["port"],
            user=creds["user"],
            password=creds["password"],
            database=creds["name"],
            connect_timeout=5,
        )
        cur = conn.cursor()

        # Check latest runs.
        # NOTE: started_at is `timestamp without time zone` and this session's
        # timezone is America/Chicago, so naive Python datetimes written here
        # are silently stored as Chicago local time (not UTC) despite call
        # sites using datetime.now(timezone.utc). Computing the age via NOW()
        # in the same SQL session avoids relabeling that naive value as UTC
        # (which previously inflated staleness by the UTC/Chicago offset).
        cur.execute(
            """
            SELECT COUNT(*) as runs_last_24h,
                   MAX(started_at) as latest_run,
                   MAX(CASE WHEN overall_status = 'success' THEN 1 ELSE 0 END) as has_success,
                   EXTRACT(EPOCH FROM (NOW() - MAX(started_at))) / 60 as age_minutes
            FROM algo_orchestrator_runs
            WHERE started_at > NOW() - INTERVAL '24 hours'
            """
        )

        row = cur.fetchone()
        if not row:
            raise RuntimeError("Failed to query orchestrator run stats")
        runs_24h, _latest_run, _has_success, age_minutes = row

        if runs_24h > 0:
            age_minutes = float(age_minutes)
            if age_minutes < 120:
                result["status"] = "OK"
                result["details"].append(f"[OK] Latest run: {age_minutes:.0f} minutes ago")
            else:
                result["status"] = "WARN"
                result["details"].append(f"[WARN] Latest run: {age_minutes:.0f} minutes ago (stale)")

            result["details"].append(f"  Runs in last 24h: {runs_24h}")
        else:
            result["status"] = "FAIL"
            result["details"].append("[FAIL] No orchestrator runs in last 24 hours")

        conn.close()

    except Exception as e:
        result["status"] = "FAIL"
        result["details"].append(f"Cannot query orchestrator status: {str(e)[:80]}")

    return result


def check_dashboard_module() -> dict:
    result = {
        "name": "Dashboard Module",
        "status": "unknown",
        "details": [],
    }

    try:
        import dashboard  # noqa: F401

        result["status"] = "OK"
        result["details"].append("Dashboard module imports successfully")
    except ImportError as e:
        result["status"] = "FAIL"
        result["details"].append(f"Import error: {e}")
    except Exception as e:
        result["status"] = "FAIL"
        result["details"].append(f"Error: {e}")

    return result


def main() -> int:
    """Run all health checks."""
    # Fix Windows console encoding for unicode output. Must only happen when this
    # script is actually run directly - doing it at module import time permanently
    # replaces pytest's own capture streams for the rest of the test process the
    # first time anything imports this module, crashing pytest's capture teardown
    # with "ValueError: I/O operation on closed file" (same bug class already fixed
    # in monitor_data_staleness.py and verify_eventbridge_scheduler.py).
    if sys.platform.startswith("win"):
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        except Exception as e:
            # Log but don't crash - console encoding issues are non-fatal but should be visible
            logger.warning(f"[STARTUP] Failed to set UTF-8 console encoding: {type(e).__name__}: {e}")

    print("\n" + "=" * 70)
    print("ALGO SYSTEM HEALTH CHECK")
    print("=" * 70 + "\n")

    checks = [
        check_database,
        check_orchestrator,
        check_dev_server,
        check_dashboard_module,
    ]

    results = []
    status_map = {"OK": "[OK]", "FAIL": "[FAIL]", "WARN": "[WARN]", "unknown": "[?]"}
    for check_fn in checks:
        try:
            result = check_fn()
            results.append(result)
            status_icon = result.get("status", "unknown")
            status_display = status_map.get(status_icon, status_icon)
            print(f"{status_display} {result['name']}")
            for detail in result.get("details", []):
                print(f"    {detail}")
            print()
        except Exception as e:
            print(f"[FAIL] {check_fn.__name__}: {e}\n")

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed = sum(1 for r in results if r.get("status") == "OK")
    failed = sum(1 for r in results if r.get("status") == "FAIL")
    warning = sum(1 for r in results if r.get("status") == "WARN")

    print(f"[OK]   Passed: {passed}")
    print(f"[WARN] Warning: {warning}")
    print(f"[FAIL] Failed: {failed}")
    print()

    if failed == 0 and warning == 0:
        print("[OK] ALL SYSTEMS OPERATIONAL")
        print("\nReady to run dashboard:")
        print("  python start_dashboard_dev.py")
        print("  or")
        print("  python start_dashboard_dev.py -w 30   (with auto-refresh)")
        return 0
    else:
        print("[WARN] ISSUES FOUND - See details above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
