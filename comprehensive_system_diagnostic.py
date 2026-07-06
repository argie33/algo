#!/usr/bin/env python3
"""Comprehensive system diagnostic to find ALL blocking issues."""

import os
import sys
from pathlib import Path

# Setup imports
_repo_root = Path(__file__).parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

def diagnose_database():
    """Check database connectivity and data state."""
    print("\n" + "="*80)
    print("DATABASE DIAGNOSTICS")
    print("="*80)

    try:
        from utils.db import DatabaseContext

        with DatabaseContext("read") as cur:
            # Check if we can connect
            cur.execute("SELECT 1")
            print("[OK] Database connection: OK")

            # Check stock_scores table
            cur.execute("SELECT COUNT(*) FROM stock_scores WHERE growth_score IS NOT NULL AND growth_score > 0")
            growth_score_count = cur.fetchone()[0]
            print(f"[OK] Stock scores with growth_score > 0: {growth_score_count}")

            # Check if stock_scores has any data
            cur.execute("SELECT COUNT(*) FROM stock_scores")
            total_scores = cur.fetchone()[0]
            print(f"[OK] Total stock_scores rows: {total_scores}")

            # Check composition score
            cur.execute("SELECT COUNT(*) FROM stock_scores WHERE composite_score IS NOT NULL AND composite_score > 0")
            composite_count = cur.fetchone()[0]
            print(f"[OK] Stock scores with composite_score > 0: {composite_count}")

            # Check algo_trades (trades created)
            cur.execute("SELECT COUNT(*) FROM algo_trades")
            trades_count = cur.fetchone()[0]
            print(f"[OK] Total algo_trades: {trades_count}")

            # Check last trade date
            cur.execute("SELECT MAX(created_at) FROM algo_trades")
            last_trade = cur.fetchone()[0]
            print(f"[OK] Last trade created at: {last_trade}")

            # Check algo_positions
            cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status IN ('open', 'partially_closed')")
            open_positions = cur.fetchone()[0]
            print(f"[OK] Open positions: {open_positions}")

            # Check orchestrator_execution_log
            cur.execute("SELECT COUNT(*) FROM orchestrator_execution_log")
            exec_count = cur.fetchone()[0]
            print(f"[OK] Orchestrator execution log entries: {exec_count}")

            # Check latest orchestrator run
            cur.execute("""
                SELECT run_id, run_date, overall_status, phases_completed
                FROM orchestrator_execution_log
                ORDER BY run_date DESC
                LIMIT 1
            """)
            latest_run = cur.fetchone()
            if latest_run:
                print(f"[OK] Latest orchestrator run: {latest_run[1]} status={latest_run[2]} phases_completed={latest_run[3]}")
            else:
                print("[ERROR] NO orchestrator runs found in database")

            # Check data_loader_status
            cur.execute("""
                SELECT loader_name, completion_pct, last_updated
                FROM data_loader_status
                ORDER BY last_updated DESC
                LIMIT 5
            """)
            loaders = cur.fetchall()
            print(f"\n[INFO] Latest 5 data loaders:")
            for loader_name, completion_pct, last_updated in loaders:
                print(f"   {loader_name}: {completion_pct}% at {last_updated}")

    except Exception as e:
        print(f"[ERROR] Database error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

def diagnose_api():
    """Check if API Lambda is deployed and working."""
    print("\n" + "="*80)
    print("API LAMBDA DIAGNOSTICS")
    print("="*80)

    try:
        import boto3

        lambda_client = boto3.client('lambda', region_name='us-east-1')

        # Check if Lambda functions exist
        try:
            response = lambda_client.get_function(FunctionName='algo-api-dev')
            print(f"[OK] Lambda function 'algo-api-dev' exists")
            print(f"   Runtime: {response['Configuration'].get('Runtime')}")
            print(f"   LastModified: {response['Configuration'].get('LastModified')}")
        except lambda_client.exceptions.ResourceNotFoundException:
            print("[ERROR] Lambda function 'algo-api-dev' NOT FOUND in AWS")
            return False
        except Exception as e:
            print(f"[WARN] Cannot check Lambda function: {e}")

        return True
    except ImportError:
        print("[WARN] boto3 not available, skipping AWS checks")
        return True
    except Exception as e:
        print(f"[ERROR] AWS error: {type(e).__name__}: {e}")
        return False

def diagnose_orchestrator():
    """Check orchestrator configuration and execution."""
    print("\n" + "="*80)
    print("ORCHESTRATOR DIAGNOSTICS")
    print("="*80)

    try:
        from algo.config import get_config

        config = get_config()
        print(f"[OK] Orchestrator config loaded")
        print(f"   Execution mode: {config.get('execution_mode')}")
        print(f"   Paper trading: {config.get('alpaca_paper_trading')}")
        print(f"   Halt enabled: {config.get('orchestrator_halt_enabled')}")

        # Check if orchestrator phases are registered
        from algo.orchestrator.phase_registry import PhaseRegistry
        registry = PhaseRegistry()
        phases = registry.get_phases()
        print(f"[OK] Orchestrator phases registered: {len(phases)} phases")
        for phase_id, phase_name in phases.items():
            print(f"   Phase {phase_id}: {phase_name}")

        return True
    except Exception as e:
        print(f"[ERROR] Orchestrator error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def diagnose_loaders():
    """Check if data loaders have recent activity."""
    print("\n" + "="*80)
    print("DATA LOADER DIAGNOSTICS")
    print("="*80)

    try:
        from utils.db import DatabaseContext
        from datetime import datetime, timedelta, timezone

        with DatabaseContext("read") as cur:
            # Get loader status from last 24 hours
            cur.execute("""
                SELECT
                    loader_name,
                    completion_pct,
                    status,
                    last_updated,
                    EXTRACT(EPOCH FROM (NOW() AT TIME ZONE 'UTC' - last_updated)) / 3600 AS hours_ago
                FROM data_loader_status
                WHERE last_updated > NOW() AT TIME ZONE 'UTC' - INTERVAL '24 hours'
                ORDER BY last_updated DESC
            """)

            loaders = cur.fetchall()
            print(f"[OK] Loaders that ran in last 24 hours: {len(loaders)}")
            for loader_name, completion_pct, status, last_updated, hours_ago in loaders:
                status_str = "OK" if completion_pct >= 95 else "WARN"
                print(f"   [{status_str}] {loader_name}: {completion_pct}% ({hours_ago:.1f}h ago)")

            if len(loaders) == 0:
                print("[ERROR] NO loaders have run in the last 24 hours")

            return True
    except Exception as e:
        print(f"[ERROR] Loader diagnostics error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def diagnose_api_endpoints():
    """Test API endpoints to see if they're working."""
    print("\n" + "="*80)
    print("API ENDPOINT DIAGNOSTICS")
    print("="*80)

    try:
        from dashboard.api_data_layer import api_call, get_api_url

        api_url = get_api_url()
        print(f"[OK] API Base URL: {api_url}")

        # Test /api/algo/scores
        try:
            result = api_call("/api/algo/scores", params={"limit": 5})
            if isinstance(result, dict) and "top" in result:
                print(f"[OK] /api/algo/scores returns 'top' field with {len(result.get('top', []))} items")
            elif isinstance(result, dict) and "_error" in result:
                print(f"[ERROR] /api/algo/scores returns error: {result['_error']}")
            else:
                print(f"[WARN] /api/algo/scores returned unexpected format: {type(result)}")
        except Exception as e:
            print(f"[ERROR] /api/algo/scores error: {e}")

        # Test /api/algo/positions
        try:
            result = api_call("/api/algo/positions")
            if isinstance(result, dict) and "_error" not in result:
                print(f"[OK] /api/algo/positions returns data")
            elif isinstance(result, dict) and "_error" in result:
                print(f"[ERROR] /api/algo/positions error: {result['_error']}")
        except Exception as e:
            print(f"[ERROR] /api/algo/positions error: {e}")

        return True
    except Exception as e:
        print(f"[ERROR] API endpoint diagnostics error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    from datetime import datetime

    print("\n" + "="*80)
    print("ALGO SYSTEM COMPREHENSIVE DIAGNOSTIC")
    print("="*80)
    print(f"Time: {datetime.now()}")

    all_ok = True
    all_ok = diagnose_database() and all_ok
    all_ok = diagnose_api() and all_ok
    all_ok = diagnose_orchestrator() and all_ok
    all_ok = diagnose_loaders() and all_ok
    all_ok = diagnose_api_endpoints() and all_ok

    print("\n" + "="*80)
    if all_ok:
        print("[OK] ALL DIAGNOSTICS PASSED")
    else:
        print("[ERROR] SOME DIAGNOSTICS FAILED - REVIEW ABOVE FOR DETAILS")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
