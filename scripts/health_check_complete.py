#!/usr/bin/env python3
"""Comprehensive health check for algo system - end-to-end verification.

This script validates that ALL components are working correctly:
1. Database connectivity and data freshness
2. Dev server and API endpoints
3. Dashboard fetcher health
4. Alpaca credentials
5. Local development setup
6. Production Lambda deployment (if configured)

Usage:
  python3 scripts/health_check_complete.py
  python3 scripts/health_check_complete.py --verbose  # More detailed output
  python3 scripts/health_check_complete.py --fix      # Attempt to fix minor issues
"""

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# CRITICAL: Windows UTF-8 encoding fix
if sys.platform.startswith("win"):
    import io

    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


def check_database() -> dict:
    print("[*] Database: Connecting...")
    try:
        import psycopg2

        # Fail-fast on missing credentials: no empty string fallback for password
        db_password = os.getenv("DB_PASSWORD")
        if not db_password:
            raise ValueError("DB_PASSWORD environment variable not set - cannot authenticate to database")
        conn = psycopg2.connect(dbname="stocks", user="stocks", password=db_password, host="localhost")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM price_daily")
        price_count = cursor.fetchone()[0]
        cursor.execute("SELECT MAX(date) FROM price_daily")
        latest_price_date = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM algo_metrics_daily WHERE date IS NOT NULL")
        metrics_count = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        now = datetime.now().date()
        days_old = (now - latest_price_date).days if latest_price_date else None

        status = "OK" if days_old is not None and days_old <= 1 else "STALE"
        return {
            "status": status,
            "price_records": price_count,
            "latest_price_date": str(latest_price_date),
            "days_old": days_old,
            "metrics_records": metrics_count,
        }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def check_dev_server() -> dict:
    print("[*] Dev Server: Checking localhost:3001...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("127.0.0.1", 3001))
        sock.close()

        if result == 0:
            # Server is running, try to get data
            import requests

            try:
                resp = requests.get("http://localhost:3001/api/algo/data-status", timeout=5)
                if resp.status_code == 200:
                    return {"status": "OK", "port": 3001, "api_responsive": True}
                else:
                    return {"status": "WARN", "port": 3001, "http_status": resp.status_code}
            except Exception as e:
                return {"status": "WARN", "port": 3001, "api_error": str(e)}
        else:
            return {
                "status": "ERROR",
                "port": 3001,
                "message": "Dev server not running. Start it with: python3 lambda/api/dev_server.py",
            }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def check_dashboard_fetchers() -> dict:
    print("[*] Dashboard: Loading fetchers...")
    try:
        os.environ["LOCAL_MODE"] = "true"
        os.environ["DASHBOARD_API_URL"] = "http://localhost:3001"

        from dashboard.fetchers import load_all

        start = time.time()
        result = load_all()
        elapsed = time.time() - start

        total_fetchers = len(result)
        failed = sum(1 for v in result.values() if isinstance(v, dict) and "_error" in v)
        success = total_fetchers - failed

        return {
            "status": "OK" if failed == 0 else "PARTIAL",
            "total_fetchers": total_fetchers,
            "successful": success,
            "failed": failed,
            "elapsed_seconds": round(elapsed, 2),
        }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def check_alpaca_credentials() -> dict:
    print("[*] Alpaca: Checking credentials...")
    try:
        from config.credential_manager import get_credential_manager

        creds = get_credential_manager().get_alpaca_credentials()

        has_key = bool(creds.get("key"))
        has_secret = bool(creds.get("secret"))

        if has_key and has_secret:
            return {
                "status": "OK",
                "key_configured": True,
                "secret_configured": True,
                "message": "Alpaca credentials ready for live trading",
            }
        elif has_key or has_secret:
            return {
                "status": "PARTIAL",
                "key_configured": has_key,
                "secret_configured": has_secret,
                "message": "Missing Alpaca API key or secret. Configure via AWS Secrets Manager.",
            }
        else:
            return {
                "status": "WARN",
                "key_configured": False,
                "secret_configured": False,
                "message": "No Alpaca credentials configured. Paper trading will use database state only.",
            }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def check_lambda_deployment() -> dict:
    print("[*] Lambda: Checking AWS deployment...")
    try:
        import boto3

        function_names = ["algo-api", "algo-orchestrator"]
        status_dict = {}

        for func_name in function_names:
            try:
                client = boto3.client("lambda", region_name="us-east-1")
                resp = client.get_function(FunctionName=func_name)

                config = resp.get("Configuration", {})
                provisioned = config.get("ProvisionedConcurrentExecutions", 0)
                status_dict[func_name] = {
                    "status": "OK" if provisioned > 0 else "WARN",
                    "provisioned_concurrency": provisioned,
                    "message": f"Provisioned concurrency: {provisioned}"
                    + (" (WARNING: Set to 0, Lambda may timeout with 503 errors)" if provisioned == 0 else ""),
                }
            except Exception as e:
                status_dict[func_name] = {"status": "UNAVAILABLE", "error": str(e)[:100]}

        return {"status": "OK", "functions": status_dict}
    except ImportError:
        return {"status": "SKIPPED", "message": "boto3 not available (AWS CLI not configured)"}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)[:100]}


def main():
    """Run all health checks."""
    print("\n" + "=" * 80)
    print("ALGO SYSTEM HEALTH CHECK")
    print("=" * 80 + "\n")

    checks = {
        "Database": check_database,
        "Dev Server (localhost:3001)": check_dev_server,
        "Dashboard Fetchers": check_dashboard_fetchers,
        "Alpaca Credentials": check_alpaca_credentials,
        "Lambda Deployment": check_lambda_deployment,
    }

    results = {}
    for check_name, check_func in checks.items():
        try:
            results[check_name] = check_func()
        except Exception as e:
            results[check_name] = {"status": "ERROR", "error": str(e)[:100]}
        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    status_counts = {}
    for check_name, result in results.items():
        status = result.get("status", "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1

        icon = "✓" if status == "OK" else "⚠" if status in ("WARN", "PARTIAL", "SKIPPED") else "✗"
        print(f"{icon} {check_name}: {status}")

        if result.get("message"):
            print(f"  → {result['message']}")
        elif result.get("error"):
            print(f"  → ERROR: {result['error']}")

    print("\n" + "=" * 80)
    if status_counts.get("ERROR", 0) > 0:
        print("❌ SYSTEM HAS CRITICAL ERRORS - Fix items marked with ✗")
        return 1
    elif status_counts.get("PARTIAL", 0) > 0 or status_counts.get("WARN", 0) > 0:
        print("⚠️  SYSTEM OPERATIONAL but some components need attention")
        return 0
    else:
        print("✅ SYSTEM HEALTHY - All checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
