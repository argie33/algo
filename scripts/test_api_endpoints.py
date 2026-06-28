#!/usr/bin/env python3
"""Test all dashboard API endpoints to identify issues."""

import sys
import json
from typing import Any

import psycopg2
import psycopg2.extras

from utils.db import DatabaseContext

def safe_test_endpoint(endpoint_name: str, test_func) -> dict[str, Any]:
    """Safely test an endpoint and return result."""
    try:
        result = test_func()
        return {"status": "OK", "endpoint": endpoint_name, "message": "Data available", "rows": len(result) if isinstance(result, list) else 1}
    except Exception as e:
        return {"status": "ERROR", "endpoint": endpoint_name, "message": str(e)[:200]}

def test_algo_status() -> dict[str, Any]:
    """Test /api/algo/status"""
    with DatabaseContext("read") as cur:
        cur.execute("SELECT * FROM algo_runtime_state LIMIT 1")
        return cur.fetchall()

def test_algo_positions() -> list:
    """Test /api/algo/positions"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT symbol, quantity, current_price FROM algo_positions_with_risk LIMIT 10
        """)
        return cur.fetchall()

def test_algo_performance() -> dict:
    """Test /api/algo/performance"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT * FROM algo_performance_daily ORDER BY date DESC LIMIT 1
        """)
        result = cur.fetchone()
        return result if result else {}

def test_algo_trades() -> list:
    """Test /api/algo/trades"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT symbol, entry_date, exit_date FROM trade_history
            WHERE status IN ('closed', 'open') ORDER BY entry_date DESC LIMIT 10
        """)
        return cur.fetchall()

def test_algo_markets() -> dict:
    """Test /api/algo/markets"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT * FROM market_health_daily ORDER BY date DESC LIMIT 1
        """)
        result = cur.fetchone()
        return result if result else {}

def test_equity_curve() -> list:
    """Test /api/algo/equity-curve"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT * FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 10
        """)
        return cur.fetchall()

def test_circuit_breakers() -> list:
    """Test /api/algo/circuit-breakers"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT * FROM circuit_breaker_state LIMIT 1
        """)
        return cur.fetchall()

def test_daily_return_histogram() -> list:
    """Test /api/algo/daily-return-histogram"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT return_pct, day_count FROM daily_return_histogram LIMIT 1
        """)
        return cur.fetchall()

def test_trade_distribution() -> list:
    """Test /api/algo/trade-distribution"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT holding_days, trade_count FROM trade_distribution LIMIT 1
        """)
        return cur.fetchall()

def test_holding_period_distribution() -> list:
    """Test /api/algo/holding-period-distribution"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT holding_days, trade_count FROM trade_distribution LIMIT 1
        """)
        return cur.fetchall()

def test_stage_distribution() -> list:
    """Test /api/algo/stage-distribution"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT stage_in_exit_plan, trade_count FROM stage_distribution LIMIT 1
        """)
        return cur.fetchall()

def main():
    """Test all API endpoints."""
    endpoints = [
        ("Status", test_algo_status),
        ("Positions", test_algo_positions),
        ("Performance", test_algo_performance),
        ("Trades", test_algo_trades),
        ("Markets", test_algo_markets),
        ("Equity Curve", test_equity_curve),
        ("Circuit Breakers", test_circuit_breakers),
        ("Daily Return Histogram", test_daily_return_histogram),
        ("Trade Distribution", test_trade_distribution),
        ("Holding Period Distribution", test_holding_period_distribution),
        ("Stage Distribution", test_stage_distribution),
    ]

    results = []
    print("\n" + "="*70)
    print("DASHBOARD API ENDPOINT TEST")
    print("="*70 + "\n")

    for name, test_func in endpoints:
        result = safe_test_endpoint(name, test_func)
        results.append(result)
        status_icon = "[OK]" if result["status"] == "OK" else "[ERROR]"
        print(f"{status_icon} {name:<35} {result['status']:<10} {result.get('message', '')[:40]}")
        if result["status"] == "ERROR":
            print(f"   Error: {result['message']}")

    print("\n" + "="*70)
    print(f"Summary: {sum(1 for r in results if r['status'] == 'OK')}/{len(results)} endpoints working")
    print("="*70 + "\n")

    # Print detailed errors
    errors = [r for r in results if r["status"] == "ERROR"]
    if errors:
        print("\nDETAILED ERRORS:")
        for error in errors:
            print(f"\n{error['endpoint']}:")
            print(f"  {error['message']}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        sys.exit(1)
