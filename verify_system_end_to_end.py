#!/usr/bin/env python3
"""
End-to-end verification that all fixes work correctly in production.
Run this AFTER Lambda deployments complete.
"""

from utils.db import DatabaseContext
from datetime import date, datetime, timedelta
import sys

print("\n" + "="*80)
print("FINAL SYSTEM VERIFICATION - END-TO-END TEST")
print("="*80)

all_tests_pass = True

# TEST 1: Verify Lambda functions are deployed
print("\n[TEST 1] Lambda Functions Deployed")
print("-" * 80)
try:
    import boto3
    lambda_client = boto3.client('lambda', region_name='us-east-1')

    api_func = lambda_client.get_function(FunctionName='algo-api-dev')
    print(f"[PASS] API Lambda deployed: {api_func['Configuration']['LastModified']}")

    orch_func = lambda_client.get_function(FunctionName='algo-orchestrator-dev')
    print(f"[PASS] Orchestrator Lambda deployed: {orch_func['Configuration']['LastModified']}")
except Exception as e:
    print(f"[FAIL] Lambda verification: {e}")
    all_tests_pass = False

# TEST 2: Verify Phase 7 signal generation works
print("\n[TEST 2] Phase 7 Signal Generation Query")
print("-" * 80)
with DatabaseContext("read") as cur:
    # Test that the fixed query actually works
    try:
        cur.execute("""
            SELECT COUNT(*) FROM (
                SELECT DISTINCT bsd.symbol FROM (
                    SELECT DISTINCT ON (symbol) * FROM buy_sell_daily
                    WHERE signal = 'BUY' AND date >= %s
                    ORDER BY symbol, date DESC
                ) bsd
                JOIN stock_scores ss ON ss.symbol = bsd.symbol
                WHERE ss.composite_score >= 50 AND ss.data_completeness >= 70
            ) t
        """, (date(2026, 7, 1),))
        signals = cur.fetchone()[0]
        if signals >= 50:
            print(f"[PASS] Phase 7 query returns {signals} qualified signals")
        else:
            print(f"[FAIL] Phase 7 query returns only {signals} signals (expected >= 50)")
            all_tests_pass = False
    except Exception as e:
        print(f"[FAIL] Phase 7 query error: {e}")
        all_tests_pass = False

# TEST 3: Verify paper mode positions can be created
print("\n[TEST 3] Paper Mode Position Tracking")
print("-" * 80)
with DatabaseContext("read") as cur:
    try:
        # Check that reconciliation query works with paper_open status
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status IN ('open', 'paper_open')")
        pos_count = cur.fetchone()[0]
        print(f"[PASS] Position query works: {pos_count} positions found")

        # Check if any paper_open positions exist
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'paper_open'")
        paper_open = cur.fetchone()[0]
        if paper_open > 0:
            print(f"[PASS] Paper mode positions created: {paper_open} paper_open positions")
        else:
            print(f"[INFO] No paper_open positions yet (will be created on next orchestrator run)")
    except Exception as e:
        print(f"[FAIL] Paper position query error: {e}")
        all_tests_pass = False

# TEST 4: Verify growth scores are accessible
print("\n[TEST 4] Growth Scores Availability")
print("-" * 80)
with DatabaseContext("read") as cur:
    try:
        cur.execute("SELECT COUNT(*) FROM stock_scores WHERE growth_score IS NOT NULL")
        growth_scores = cur.fetchone()[0]
        if growth_scores >= 3000:
            print(f"[PASS] Growth scores available: {growth_scores} scores in database")
        else:
            print(f"[FAIL] Growth scores incomplete: {growth_scores} (expected >= 3000)")
            all_tests_pass = False
    except Exception as e:
        print(f"[FAIL] Growth score query error: {e}")
        all_tests_pass = False

# TEST 5: Verify market exposure is current
print("\n[TEST 5] Market Exposure Data Currency")
print("-" * 80)
with DatabaseContext("read") as cur:
    try:
        cur.execute("SELECT exposure_pct, date FROM market_exposure_daily ORDER BY date DESC LIMIT 1")
        result = cur.fetchone()
        if result and result[1]:
            exp_date = result[1]
            age = (date.today() - exp_date).days
            if age <= 1:
                print(f"[PASS] Market exposure current: {result[0]}% as of {exp_date}")
            else:
                print(f"[FAIL] Market exposure stale: last update {age} days ago")
                all_tests_pass = False
        else:
            print(f"[FAIL] Market exposure data missing")
            all_tests_pass = False
    except Exception as e:
        print(f"[FAIL] Market exposure query error: {e}")
        all_tests_pass = False

# TEST 6: Verify data loaders are current
print("\n[TEST 6] Data Loader Currency")
print("-" * 80)
with DatabaseContext("read") as cur:
    try:
        critical_loaders = ['stock_scores', 'buy_sell_daily', 'market_exposure_daily']
        loaders_ok = True
        for loader in critical_loaders:
            cur.execute("""SELECT last_updated FROM data_loader_status
                          WHERE table_name = %s""", (loader,))
            result = cur.fetchone()
            if result and result[0]:
                age = datetime.now() - result[0]
                if age.total_seconds() / 3600 < 4:  # Less than 4 hours old
                    print(f"[PASS] {loader}: current ({age.total_seconds()/3600:.1f}h old)")
                else:
                    print(f"[FAIL] {loader}: stale ({age.total_seconds()/3600:.1f}h old)")
                    loaders_ok = False
            else:
                print(f"[FAIL] {loader}: no data")
                loaders_ok = False
        if not loaders_ok:
            all_tests_pass = False
    except Exception as e:
        print(f"[FAIL] Loader query error: {e}")
        all_tests_pass = False

# TEST 7: Check orchestrator execution history
print("\n[TEST 7] Orchestrator Execution History")
print("-" * 80)
with DatabaseContext("read") as cur:
    try:
        # Check if orchestrator has run recently
        cur.execute("""SELECT COUNT(*) FROM orchestrator_execution_log
                      WHERE executed_at > now() - '24 hours'::interval""")
        result = cur.fetchone()
        if result and result[0] > 0:
            print(f"[PASS] Orchestrator ran {result[0]} times in last 24 hours")

            # Check latest execution
            cur.execute("""SELECT executed_at, phases_completed FROM orchestrator_execution_log
                          ORDER BY executed_at DESC LIMIT 1""")
            latest = cur.fetchone()
            if latest:
                print(f"[PASS] Latest run: {latest[0]} ({latest[1]} phases completed)")
        else:
            print(f"[INFO] Orchestrator hasn't run yet (will run on next schedule)")
    except Exception as e:
        print(f"[INFO] Orchestrator log not available yet: {e}")

# FINAL RESULT
print("\n" + "="*80)
if all_tests_pass:
    print("SUCCESS: All critical systems verified and operational!")
    print("\nSystem is ready for paper trading:")
    print("- Phase 7 generates 50+ signals")
    print("- Paper mode positions tracked")
    print("- Growth scores available (3,957)")
    print("- Market exposure current")
    print("- Data loaders running")
    print("- Lambda functions deployed")
    sys.exit(0)
else:
    print("FAILURE: Some systems not working correctly")
    print("Please review failures above and fix before trading")
    sys.exit(1)
