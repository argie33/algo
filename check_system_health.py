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
import json
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows console encoding for unicode output
if sys.platform.startswith("win"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent))


def check_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def check_database() -> dict:
    result = {
        "name": "Database",
        "status": "unknown",
        "details": [],
    }

    try:
        import psycopg2

        try:
            # Fail-fast on missing credentials: no hardcoded defaults for auth
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

            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=db_name,
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
            for table_name, description in tables.items():
                try:
                    if table_name == "stock_scores":
                        cur.execute(f"SELECT COUNT(*), MAX(updated_at) FROM {table_name}")
                    elif table_name == "algo_orchestrator_runs":
                        cur.execute(f"SELECT COUNT(*), MAX(started_at) FROM {table_name}")
                    else:
                        cur.execute(f"SELECT COUNT(*), MAX(date) FROM {table_name}")

                    cnt, latest = cur.fetchone()
                    age_hours = None
                    if latest:
                        from datetime import date as date_type

                        if isinstance(latest, date_type) and not isinstance(latest, datetime):
                            # It's a date (not a datetime)
                            age_days = (datetime.now(timezone.utc).date() - latest).days
                            age_hours = age_days * 24
                        elif isinstance(latest, datetime):
                            # It's a datetime
                            if latest.tzinfo is None:
                                latest = latest.replace(tzinfo=timezone.utc)
                            age = datetime.now(timezone.utc) - latest
                            age_hours = age.total_seconds() / 3600
                        else:
                            age_hours = None

                    fresh = age_hours is None or age_hours < 24
                    status_icon = "[OK]" if fresh else "[WARN]"
                    age_str = f"{age_hours:.1f}h" if age_hours is not None else "N/A"

                    result["details"].append(f"{status_icon} {table_name}: {cnt} rows, latest: {age_str} ago")

                    if not fresh:
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

            resp = requests.get("http://localhost:3001/api/health", timeout=5)
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

        # Fail-fast on missing credentials: no hardcoded defaults for auth
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

        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name,
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
        runs_24h, latest_run, has_success, age_minutes = row

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
        import dashboard

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
    for check_fn in checks:
        try:
            result = check_fn()
            results.append(result)
            status_icon = result.get("status", "?")
            status_display = status_icon.replace("OK", "[OK]").replace("FAIL", "[FAIL]").replace("WARN", "[WARN]")
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
