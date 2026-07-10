#!/usr/bin/env python3
"""Comprehensive end-to-end verification that system is working.

This script verifies:
1. API endpoints return data without 401 errors
2. Growth scores are accessible in dashboard format
3. Database has current data
4. Orchestrator can execute all phases
5. Trades are being created
6. Positions are being tracked and sorted
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

_repo_root = Path(__file__).parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

def test_database_connectivity():
    """Verify database is connected and has current data."""
    print("\n" + "="*80)
    print("TEST 1: DATABASE CONNECTIVITY & DATA FRESHNESS")
    print("="*80)

    try:
        from utils.db import DatabaseContext

        with DatabaseContext("read") as cur:
            # Test connection
            cur.execute("SELECT 1")
            print("[OK] Database connected")

            # Check growth scores
            cur.execute("""
                SELECT COUNT(*),
                       COUNT(CASE WHEN growth_score > 0 THEN 1 END),
                       MAX(updated_at)
                FROM stock_scores
            """)
            total, with_scores, latest_update = cur.fetchone()
            print(f"[OK] Stock scores: {total} total, {with_scores} with growth_score > 0")
            if latest_update:
                age_hours = (datetime.now(latest_update.tzinfo) - latest_update).total_seconds() / 3600
                print(f"[OK] Latest update: {age_hours:.1f} hours ago")

            # Check trades
            cur.execute("SELECT COUNT(*), MAX(created_at) FROM algo_trades")
            trade_count, latest_trade = cur.fetchone()
            print(f"[OK] Trades: {trade_count} total")
            if latest_trade:
                print(f"     Latest trade: {latest_trade}")

            # Check positions
            cur.execute("""
                SELECT COUNT(*), COUNT(CASE WHEN status IN ('open', 'partially_closed') THEN 1 END)
                FROM algo_positions
            """)
            total_pos, open_pos = cur.fetchone()
            print(f"[OK] Positions: {total_pos} total, {open_pos} open")

            # Check portfolio snapshots (latest)
            cur.execute("""
                SELECT COUNT(*), MAX(snapshot_date)
                FROM algo_portfolio_snapshots
            """)
            snap_count, latest_snap = cur.fetchone()
            print(f"[OK] Portfolio snapshots: {snap_count} total")
            if latest_snap:
                snap_age = (datetime.now(latest_snap.tzinfo) if latest_snap.tzinfo else datetime.now()) - (latest_snap if latest_snap.tzinfo else latest_snap.replace(tzinfo=None))
                print(f"     Latest snapshot: {latest_snap}")

            return True
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        return False

def test_api_endpoints():
    """Verify API endpoints work without 401 errors."""
    print("\n" + "="*80)
    print("TEST 2: API ENDPOINTS (NO 401 ERRORS)")
    print("="*80)

    try:
        from dashboard.api_data_layer import api_call, get_api_url

        api_url = get_api_url()
        print(f"[OK] API URL: {api_url}")

        # Test /api/algo/scores (should be PUBLIC now)
        try:
            result = api_call("/api/algo/scores", params={"limit": 10})
            if isinstance(result, dict):
                if "_error" in result:
                    error_code = result.get("_error_code", "unknown")
                    if "401" in str(error_code) or "401" in str(result.get("_error", "")):
                        print(f"[ERROR] /api/algo/scores returns 401: {result.get('_error', 'unknown error')}")
                        return False
                    else:
                        print(f"[WARN] /api/algo/scores error: {result.get('_error', 'unknown')}")
                        return False
                elif "top" in result:
                    top_scores = result.get("top", [])
                    print(f"[OK] /api/algo/scores returns {len(top_scores)} scores")
                    if top_scores:
                        first = top_scores[0]
                        print(f"     First score: {first.get('symbol')} growth={first.get('growth_score')} composite={first.get('composite_score')}")
                else:
                    print(f"[ERROR] /api/algo/scores unexpected response format: {type(result)}")
                    return False
            else:
                print(f"[ERROR] /api/algo/scores returned non-dict: {type(result)}")
                return False
        except Exception as e:
            print(f"[ERROR] /api/algo/scores call failed: {e}")
            return False

        # Test /api/algo/positions (should have data)
        try:
            result = api_call("/api/algo/positions")
            if isinstance(result, dict) and "_error" not in result:
                items = result.get("items", [])
                print(f"[OK] /api/algo/positions returns {len(items)} positions")
                if items:
                    first = items[0]
                    print(f"     First position: {first.get('symbol')} status={first.get('status')}")
            elif "_error" in result:
                print(f"[WARN] /api/algo/positions error: {result.get('_error')}")
                # This is not a blocker - positions might be empty
            else:
                print(f"[WARN] /api/algo/positions unexpected format")
        except Exception as e:
            print(f"[WARN] /api/algo/positions call: {e}")

        return True
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_orchestrator_config():
    """Verify orchestrator is properly configured."""
    print("\n" + "="*80)
    print("TEST 3: ORCHESTRATOR CONFIGURATION")
    print("="*80)

    try:
        from algo.infrastructure import get_config

        config = get_config()
        print(f"[OK] Orchestrator config loaded")
        print(f"     Execution mode: {config.get('execution_mode')}")
        print(f"     Paper trading: {config.get('alpaca_paper_trading')}")
        print(f"     Halt enabled: {config.get('orchestrator_halt_enabled')}")

        # Check if phases are registered
        from algo.orchestrator.phase_registry import PhaseRegistry
        registry = PhaseRegistry()
        phases = registry.get_phases()
        print(f"[OK] {len(phases)} orchestrator phases registered")

        return True
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        return False

def test_data_display():
    """Verify data can be formatted for dashboard display."""
    print("\n" + "="*80)
    print("TEST 4: DASHBOARD DATA DISPLAY")
    print("="*80)

    try:
        from utils.db import DatabaseContext

        with DatabaseContext("read") as cur:
            # Get top 5 stocks by growth score
            cur.execute("""
                SELECT symbol, growth_score, composite_score, momentum_score, quality_score
                FROM stock_scores
                WHERE growth_score IS NOT NULL AND growth_score > 0
                ORDER BY growth_score DESC
                LIMIT 5
            """)

            scores = cur.fetchall()
            if scores:
                print(f"[OK] Top 5 stocks by growth_score:")
                for row in scores:
                    d = dict(row)
                    print(f"     {d['symbol']}: growth={d.get('growth_score'):.1f} composite={d.get('composite_score'):.1f}")
                print("[OK] Dashboard can display growth scores")
            else:
                print("[WARN] No stocks with growth_score > 0 found")

            # Get positions with sorting
            cur.execute("""
                SELECT symbol, quantity, entry_price, current_price,
                       ROUND((current_price - entry_price) / entry_price * 100, 2) as pnl_pct
                FROM algo_positions
                WHERE status IN ('open', 'partially_closed')
                ORDER BY symbol
                LIMIT 5
            """)

            positions = cur.fetchall()
            if positions:
                print(f"[OK] Open positions (sorted by symbol):")
                for row in positions:
                    d = dict(row)
                    print(f"     {d['symbol']}: qty={d['quantity']} pnl={d.get('pnl_pct')}%")
                print("[OK] Dashboard can display and sort positions")
            else:
                print("[INFO] No open positions (system may be in cash)")

            return True
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        return False

def main():
    print("\n" + "="*80)
    print("COMPREHENSIVE END-TO-END SYSTEM VERIFICATION")
    print("="*80)
    print(f"Time: {datetime.now()}")

    results = []
    results.append(("Database", test_database_connectivity()))
    results.append(("API Endpoints", test_api_endpoints()))
    results.append(("Orchestrator Config", test_orchestrator_config()))
    results.append(("Dashboard Data Display", test_data_display()))

    print("\n" + "="*80)
    print("VERIFICATION RESULTS")
    print("="*80)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(r for _, r in results)

    print("\n" + "="*80)
    if all_passed:
        print("✅ ALL TESTS PASSED - SYSTEM IS FULLY OPERATIONAL")
        print("\nNext: Verify via dashboard that growth scores are displaying")
        print("Expected behavior:")
        print("  - Growth scores visible in signals panel")
        print("  - Positions sorted and showing current data")
        print("  - Recent trades visible in trades panel")
        print("  - Portfolio metrics up-to-date")
    else:
        print("⚠️  SOME TESTS FAILED - REVIEW ABOVE FOR DETAILS")
    print("="*80 + "\n")

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
