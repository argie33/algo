#!/usr/bin/env python3
"""Focused audit of the problematic orchestrator run."""
import sys
import json
from pathlib import Path

_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db import DatabaseContext

with DatabaseContext('read') as cur:
    print("="*80)
    print("FOCUSED AUDIT - Finding Issues in Latest Run")
    print("="*80)

    # Get the problematic run details
    run_id = 'LOCAL-AFTERNOON-20260805-051013-124684'
    cur.execute('''
        SELECT run_id, run_date, started_at, completed_at, overall_status, phase_results
        FROM orchestrator_execution_log
        WHERE run_id = %s
    ''', (run_id,))

    run = cur.fetchone()
    if not run:
        print(f"Run {run_id} not found!")
        sys.exit(1)

    print(f"\nRun: {run['run_id']}")
    print(f"Date: {run['run_date']}, Time: {run['started_at']} - {run['completed_at']}")
    print(f"Status: {run['overall_status']}")

    # Parse phase results to find which phase had the error
    phase_results = json.loads(run['phase_results']) if isinstance(run['phase_results'], str) else run['phase_results']

    print("\nPhase Results:")
    for phase in phase_results:
        phase_num = phase.get('phase')
        phase_name = phase.get('name')
        status = phase.get('status')
        summary = phase.get('summary', '')

        marker = "❌" if 'error' in status.lower() else "✓ " if status == 'ok' else "⚠ "
        print(f"  {marker} Phase {phase_num}: {phase_name:20} {status:10} | {summary[:80]}")

    # Now check for data issues at the time of the run
    print("\n" + "="*80)
    print("DATA STATE AT TIME OF RUN")
    print("="*80)

    # 1. Check positions
    print("\n1. POSITIONS:")
    cur.execute("""
        SELECT COUNT(*) as cnt, status
        FROM algo_positions
        GROUP BY status
        ORDER BY status
    """)
    for row in cur.fetchall():
        print(f"  {row['status']:10} {row['cnt']:5} positions")

    # 2. Check trades
    print("\n2. TRADES:")
    cur.execute("""
        SELECT COUNT(*) as cnt, status
        FROM algo_trades
        GROUP BY status
        ORDER BY status
    """)
    for row in cur.fetchall():
        print(f"  {row['status']:10} {row['cnt']:5} trades")

    # 3. Check for position-trade mismatches
    print("\n3. SYNC ISSUES:")

    # Open positions without matching trade
    cur.execute("""
        SELECT COUNT(*) as cnt
        FROM algo_positions p
        LEFT JOIN algo_trades t ON p.id::text = t.position_id AND t.status = 'open'
        WHERE p.status = 'open' AND t.id IS NULL
    """)
    row = cur.fetchone()
    orphan_pos_count = row.get('cnt', 0) if row else 0
    print(f"  Open positions without matching trade: {orphan_pos_count}")

    # Trades in trades table but position status is closed
    cur.execute("""
        SELECT COUNT(*) as cnt
        FROM algo_trades t
        LEFT JOIN algo_positions p ON t.position_id = p.id::text
        WHERE t.status = 'open' AND (p.id IS NULL OR p.status = 'closed')
    """)
    row = cur.fetchone()
    orphan_trade_count = row.get('cnt', 0) if row else 0
    print(f"  Open trades without matching open position: {orphan_trade_count}")

    # 4. Check for circuit breaker status
    print("\n4. CIRCUIT BREAKER:")
    cur.execute("""
        SELECT is_halted, halt_reason, updated_at
        FROM circuit_breaker_status
        ORDER BY updated_at DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    if row:
        print(f"  Halted: {row.get('is_halted', False)}")
        if row.get('halt_reason'):
            print(f"  Reason: {row['halt_reason'][:200]}")

    # 5. Check configuration
    print("\n5. CONFIGURATION:")
    cur.execute("""
        SELECT key, value
        FROM algo_config
        WHERE key IN ('execution_mode', 'alpaca_paper_trading', 'max_total_risk_pct', 'max_position_size_pct')
        ORDER BY key
    """)
    for row in cur.fetchall():
        print(f"  {row['key']:30} {row['value']}")

print("\nDone!")
