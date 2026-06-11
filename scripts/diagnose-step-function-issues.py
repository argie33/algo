#!/usr/bin/env python3
"""
COMPREHENSIVE STEP FUNCTION & ORCHESTRATOR DIAGNOSTIC

Identifies ALL issues preventing proper algo runs throughout the day.
Run this script to generate a complete health report.

Usage: python scripts/diagnose-step-function-issues.py
"""

import os
import sys
import psycopg2
from datetime import date, timedelta, datetime

sys.path.insert(0, '.')

print("\n" + "="*70)
print("ALGO STEP FUNCTION & ORCHESTRATOR DIAGNOSTIC")
print("="*70 + "\n")

# ============================================================
# 1. DATABASE CONNECTIVITY
# ============================================================
print("[1/8] Database Connectivity")
print("-" * 70)
try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'stocks'),
        connect_timeout=5
    )
    cur = conn.cursor()
    cur.execute("SELECT 1")
    print("[OK] Database connected and responsive\n")

    # ============================================================
    # 2. DATA FRESHNESS CHECK
    # ============================================================
    print("[2/8] Data Freshness")
    print("-" * 70)
    today = date.today()

    # Check all critical tables
    tables_to_check = [
        ('price_daily', 'date'),
        ('market_health_daily', 'date'),
        ('swing_trader_scores', 'date'),
        ('technical_data_daily', 'date'),
    ]

    freshness_ok = True
    for table, date_col in tables_to_check:
        try:
            cur.execute(f"SELECT MAX({date_col}), COUNT(*) FROM {table}")
            max_date, count = cur.fetchone()
            if max_date:
                age = (today - max_date).days
                status = "OK" if age <= 1 else "STALE"
                if age > 1:
                    freshness_ok = False
                print(f"  {table:30s}: {max_date} ({age} days old) [{status}] ({count} rows)")
            else:
                print(f"  {table:30s}: NO DATA [CRITICAL]")
                freshness_ok = False
        except Exception as e:
            print(f"  {table:30s}: ERROR - {str(e)[:50]}")

    print()

    # ============================================================
    # 3. ORCHESTRATOR EXECUTION HISTORY
    # ============================================================
    print("[3/8] Recent Orchestrator Runs")
    print("-" * 70)
    try:
        cur.execute("""
            SELECT DATE(run_date), overall_status, COUNT(*) as count
            FROM orchestrator_execution_log
            WHERE run_date >= CURRENT_DATE - 7
            GROUP BY DATE(run_date), overall_status
            ORDER BY DATE(run_date) DESC
        """)

        runs_by_day = {}
        for run_date, status, count in cur.fetchall():
            if run_date not in runs_by_day:
                runs_by_day[run_date] = {'success': 0, 'halted': 0, 'error': 0}
            runs_by_day[run_date][status] = count

        for run_date in sorted(runs_by_day.keys(), reverse=True):
            stats = runs_by_day[run_date]
            print(f"  {run_date}: SUCCESS={stats.get('success',0):2d} HALTED={stats.get('halted',0):2d} ERROR={stats.get('error',0):2d}")

        print()

        # Get latest run details
        print("[4/8] Latest Orchestrator Execution")
        print("-" * 70)
        cur.execute("""
            SELECT run_id, run_date, overall_status, summary
            FROM orchestrator_execution_log
            ORDER BY run_date DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            run_id, run_date, status, summary = row
            print(f"  Run ID: {run_id}")
            print(f"  Date:   {run_date}")
            print(f"  Status: {status}")
            print(f"  Summary: {summary[:200] if summary else 'N/A'}")
        print()

    except Exception as e:
        print(f"[ERROR] Could not fetch orchestrator history: {e}\n")

    # ============================================================
    # 5. LOADER EXECUTION HISTORY
    # ============================================================
    print("[5/8] Loader Execution Status")
    print("-" * 70)
    try:
        cur.execute("""
            SELECT COUNT(*), COUNT(*) FILTER (WHERE status='COMPLETED')
            FROM loader_execution_history
            WHERE execution_start >= CURRENT_DATE - 1
        """)
        total, completed = cur.fetchone()
        print(f"  Loaders last 24h: {completed}/{total} completed")

        if total == 0:
            print("  [WARNING] No recent loader executions - loaders may not be running!")

        print()
    except Exception as e:
        print(f"  [INFO] Loader history not available: {str(e)[:50]}\n")

    conn.close()

except Exception as e:
    print(f"[ERROR] Database connection failed: {e}\n")
    sys.exit(1)

# ============================================================
# 6. CODE SYNTAX CHECK
# ============================================================
print("[6/8] Code Syntax Verification")
print("-" * 70)
try:
    import py_compile

    files_to_check = [
        'algo/algo_orchestrator.py',
        'algo/orchestrator/phase1_data_freshness.py',
        'algo/orchestrator/phase2_circuit_breakers.py',
        'loaders/load_prices.py',
        'loaders/load_buy_sell_daily.py',
    ]

    all_ok = True
    for filepath in files_to_check:
        try:
            py_compile.compile(filepath, doraise=True)
            print(f"  {filepath:50s} [OK]")
        except py_compile.PyCompileError as e:
            print(f"  {filepath:50s} [ERROR] {str(e)[:50]}")
            all_ok = False

    if all_ok:
        print("\n[OK] All code syntax checks passed\n")
    else:
        print("\n[ERROR] Some files have syntax errors\n")

except Exception as e:
    print(f"[ERROR] Syntax check failed: {e}\n")

# ============================================================
# 7. ORCHESTRATOR FUNCTIONAL TEST
# ============================================================
print("[7/8] Orchestrator Functional Test")
print("-" * 70)
try:
    os.environ['ORCHESTRATOR_DRY_RUN'] = 'true'
    os.environ['SKIP_ORCHESTRATOR_LOCK'] = 'true'

    from algo.algo_orchestrator import Orchestrator

    orch = Orchestrator(dry_run=True, verbose=False)
    result = orch.run()

    if result.get('success'):
        print(f"  Orchestrator dry-run: [OK]")
        print(f"  Phases executed: {len(result.get('phases', {}))} phases")
    else:
        print(f"  Orchestrator dry-run: [HALTED]")
        for phase_num, phase_data in result.get('phases', {}).items():
            if phase_data.get('status') == 'halt':
                print(f"    Phase {phase_num}: {phase_data.get('summary', 'No details')[:80]}")

    print()

except Exception as e:
    print(f"[ERROR] Orchestrator functional test failed: {str(e)[:100]}\n")

# ============================================================
# 8. RECOMMENDED ACTIONS
# ============================================================
print("[8/8] Recommended Actions")
print("-" * 70)

recommendations = []

if not freshness_ok:
    recommendations.append("• Data freshness issue detected - verify step functions are running")
    recommendations.append("  → Run: aws scheduler get-schedule --name algo-morning-pipeline-dev")
    recommendations.append("  → If State=DISABLED, run: terraform apply -var-file=terraform.tfvars")

if total == 0:
    recommendations.append("• No recent loader executions - step functions may not be triggering")
    recommendations.append("  → Verify EventBridge Scheduler state in AWS console")
    recommendations.append("  → Check Step Functions execution history for failures")

recommendations.append("• Monitor morning prep pipeline: Must complete by 9:30 AM ET")
recommendations.append("  → Expected start: 2:00 AM ET")
recommendations.append("  → Expected completion: 5:00-6:00 AM ET")

recommendations.append("• Monitor EOD pipeline: Must complete before next day's orchestrator")
recommendations.append("  → Expected start: 4:05 PM ET")
recommendations.append("  → Expected completion: 5:30-6:00 PM ET")

recommendations.append("• Check orchestrator runs: Should execute 4x daily (9:30 AM, 1 PM, 3 PM, 5:30 PM ET)")
recommendations.append("  → All runs should show success > 90% if data is fresh")

if recommendations:
    print()
    for rec in recommendations:
        try:
            print(rec)
        except (UnicodeEncodeError, UnicodeDecodeError):
            print(rec.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore'))
else:
    print("[OK] No issues detected - system is running normally")

print("\n" + "="*70 + "\n")
