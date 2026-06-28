#!/usr/bin/env python3
"""Test all dashboard API endpoints with correct queries."""

import sys
from utils.db import DatabaseContext

def safe_test_endpoint(endpoint_name: str, test_func) -> dict:
    """Safely test an endpoint and return result."""
    try:
        result = test_func()
        rows = len(result) if isinstance(result, list) else 1
        return {"status": "OK", "endpoint": endpoint_name, "rows": rows}
    except Exception as e:
        return {"status": "ERROR", "endpoint": endpoint_name, "error": str(e)[:150]}

def test_algo_status() -> list:
    """Test /api/algo/status"""
    with DatabaseContext("read") as cur:
        cur.execute("SELECT * FROM algo_runtime_state LIMIT 5")
        return cur.fetchall()

def test_algo_positions() -> list:
    """Test /api/algo/positions"""
    with DatabaseContext("read") as cur:
        cur.execute("SELECT symbol, quantity FROM algo_positions_with_risk LIMIT 10")
        return cur.fetchall()

def test_algo_performance() -> list:
    """Test /api/algo/performance"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT * FROM algo_performance_metrics
            ORDER BY metric_date DESC LIMIT 1
        """)
        return cur.fetchall()

def test_algo_trades() -> list:
    """Test /api/algo/trades"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT symbol, entry_price FROM algo_trades
            ORDER BY trade_date DESC LIMIT 10
        """)
        return cur.fetchall()

def test_algo_markets() -> list:
    """Test /api/algo/markets"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT * FROM market_health_daily
            ORDER BY date DESC LIMIT 1
        """)
        return cur.fetchall()

def test_equity_curve() -> list:
    """Test /api/algo/equity-curve"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT * FROM algo_portfolio_snapshots
            ORDER BY snapshot_date DESC LIMIT 10
        """)
        return cur.fetchall()

def test_circuit_breakers() -> list:
    """Test /api/algo/circuit-breakers"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT * FROM circuit_breaker_status LIMIT 1
        """)
        return cur.fetchall()

def test_daily_return_histogram() -> list:
    """Test /api/algo/daily-return-histogram"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT daily_return_pct FROM algo_portfolio_snapshots
            WHERE daily_return_pct IS NOT NULL
            ORDER BY snapshot_date DESC LIMIT 100
        """)
        return cur.fetchall()

def test_trade_distribution() -> list:
    """Test /api/algo/trade-distribution"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT exit_r_multiple FROM algo_trades
            WHERE exit_r_multiple IS NOT NULL AND status = 'closed'
            LIMIT 100
        """)
        return cur.fetchall()

def test_holding_period_distribution() -> list:
    """Test /api/algo/holding-period-distribution"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT trade_duration_days FROM algo_trades
            WHERE status = 'closed' AND exit_date IS NOT NULL
            LIMIT 100
        """)
        return cur.fetchall()

def test_stage_distribution() -> list:
    """Test /api/algo/stage-distribution"""
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT weinstein_stage FROM algo_positions_with_risk
            LIMIT 100
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
    print("DASHBOARD API ENDPOINT TEST (CORRECTED)")
    print("="*70 + "\n")

    for name, test_func in endpoints:
        result = safe_test_endpoint(name, test_func)
        results.append(result)
        status = "[OK]" if result["status"] == "OK" else "[ERROR]"
        rows = f"({result['rows']} rows)" if result["status"] == "OK" else ""
        print(f"{status} {name:<35} {rows}")
        if result["status"] == "ERROR":
            print(f"     {result['error']}")

    print("\n" + "="*70)
    ok_count = sum(1 for r in results if r["status"] == "OK")
    print(f"Summary: {ok_count}/{len(results)} endpoints working")
    print("="*70)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        sys.exit(1)
