#!/usr/bin/env python3
"""Comprehensive system audit to identify issues preventing data display."""

import os
import sys
from datetime import date, datetime
from pathlib import Path

# Add repo to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

def check_orchestrator_status():
    """Check if orchestrator has run recently."""
    import psycopg2

    try:
        conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
        cur = conn.cursor()

        # Get last orchestrator run
        cur.execute("""
        SELECT started_at, completed_at, overall_status, halt_reason
        FROM algo_orchestrator_runs
        ORDER BY started_at DESC
        LIMIT 1
        """)

        row = cur.fetchone()
        conn.close()

        if not row:
            return "ERROR", "No orchestrator runs found"

        started, completed, status, halt_reason = row
        hours_ago = (datetime.now() - started).total_seconds() / 3600

        if status == 'failed' or status == 'error':
            return "ERROR", f"Last run failed: {status} - {halt_reason or 'no reason'}"

        if hours_ago > 24:
            return "WARN", f"Last run was {hours_ago:.1f} hours ago (>24h old)"

        return "OK", f"Last run {hours_ago:.1f}h ago"

    except Exception as e:
        return "ERROR", str(e)

def check_data_freshness():
    """Check if critical data tables are fresh."""
    import psycopg2

    try:
        conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
        cur = conn.cursor()

        tables = [
            ('price_daily', 'date'),
            ('technical_data_daily', 'date'),
            ('market_exposure_daily', 'date'),
            ('stock_scores', 'updated_at'),
            ('buy_sell_daily', 'date'),
        ]

        issues = []
        for table, date_col in tables:
            try:
                c2 = psycopg2.connect('dbname=stocks user=stocks host=localhost')
                cur2 = c2.cursor()
                cur2.execute(f'SELECT MAX({date_col}) FROM {table}')
                latest = cur2.fetchone()[0]
                c2.close()
                if not latest:
                    issues.append(f"{table}: EMPTY")
                    continue

                if isinstance(latest, date) and not isinstance(latest, datetime):
                    days_old = (date.today() - latest).days
                    if days_old > 2:
                        issues.append(f"{table}: {days_old} days old")
                else:
                    hours_old = (datetime.now() - latest).total_seconds() / 3600
                    if hours_old > 48:
                        issues.append(f"{table}: {hours_old:.1f}h old")
            except Exception as e:
                issues.append(f"{table}: ERROR - {str(e)[:80]}")

        conn.close()

        if issues:
            return "WARN", "; ".join(issues)
        return "OK", "All tables fresh"

    except Exception as e:
        return "ERROR", str(e)

def check_api_endpoints():
    """Test API endpoints."""
    import requests

    base_url = "http://localhost:3001"
    headers = {"Authorization": "Bearer dev-admin"}

    endpoints = [
        "/api/algo/portfolio",
        "/api/algo/positions",
        "/api/algo/config",
        "/api/health",
    ]

    issues = []
    for endpoint in endpoints:
        try:
            resp = requests.get(f"{base_url}{endpoint}", headers=headers, timeout=5)
            if resp.status_code != 200:
                issues.append(f"{endpoint}: {resp.status_code}")
                continue

            data = resp.json()
            if "_error" in data:
                issues.append(f"{endpoint}: {data['_error'][:50]}")
            elif "data" not in data and "statusCode" in data:
                # Wrapped response - check if it has data
                if data.get("statusCode") != 200:
                    issues.append(f"{endpoint}: Status {data['statusCode']}")
        except Exception as e:
            issues.append(f"{endpoint}: {str(e)[:50]}")

    if issues:
        return "WARN", "; ".join(issues)
    return "OK", "All endpoints responding"

def check_alpaca_integration():
    """Check if Alpaca credentials and connection work."""
    try:
        from config.alpaca_config import get_alpaca_config
        from utils.external.alpaca import AlpacaClient

        config = get_alpaca_config()
        client = AlpacaClient(config)

        # Test connection
        account = client.get_account()
        if not account:
            return "ERROR", "Cannot fetch account info"

        return "OK", f"Alpaca connected (portfolio value: {account.get('portfolio_value', 'N/A')})"

    except Exception as e:
        return "WARN", f"Alpaca integration issue: {str(e)[:80]}"

def check_dashboard_fetchers():
    """Test dashboard fetchers."""
    try:
        # Set up environment for local dev
        os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
        os.environ['LOCAL_MODE'] = 'true'

        from dashboard.fetchers import load_all

        # Try to load all data
        data = load_all()

        if not data:
            return "ERROR", "No data returned from fetchers"

        errors = {k: v for k, v in data.items() if isinstance(v, dict) and "_error" in v}
        if errors:
            error_count = len(errors)
            first_error = list(errors.values())[0].get("_error", "unknown")[:50]
            return "WARN", f"{error_count} fetchers failed: {first_error}"

        return "OK", f"All {len(data)} fetchers loaded"

    except Exception as e:
        return "ERROR", str(e)[:100]

def main():
    """Run all checks."""
    print("=" * 70)
    print("SYSTEM AUDIT")
    print("=" * 70)

    checks = [
        ("Orchestrator Status", check_orchestrator_status),
        ("Data Freshness", check_data_freshness),
        ("API Endpoints", check_api_endpoints),
        ("Dashboard Fetchers", check_dashboard_fetchers),
    ]

    results = {}
    for name, check_fn in checks:
        print(f"\n{name}...", end=" ", flush=True)
        status, message = check_fn()
        results[name] = {"status": status, "message": message}
        print(f"{status}: {message}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    statuses = {r["status"] for r in results.values()}

    if "ERROR" in statuses:
        print("[CRITICAL] CRITICAL ISSUES FOUND - System cannot operate")
        for name, result in results.items():
            if result["status"] == "ERROR":
                print(f"   - {name}: {result['message']}")
    elif "WARN" in statuses:
        print("[WARNING] WARNINGS - Some functionality may be degraded")
        for name, result in results.items():
            if result["status"] == "WARN":
                print(f"   - {name}: {result['message']}")
    else:
        print("[OK] All systems operational")

    return 0 if "ERROR" not in statuses else 1

if __name__ == "__main__":
    sys.exit(main())
