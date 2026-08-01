#!/usr/bin/env python3
"""Comprehensive diagnostics of orchestrator state."""

from utils.db import DatabaseContext
import json

print("=" * 100)
print("ORCHESTRATOR STATE DIAGNOSTIC")
print("=" * 100)

with DatabaseContext('read') as cur:
    # Find successful runs
    cur.execute('''
        SELECT run_id, overall_status, started_at, phases_completed, phases_halted, phases_errored
        FROM orchestrator_execution_log
        WHERE overall_status NOT IN ('skipped', 'degraded')
        ORDER BY started_at DESC
        LIMIT 10
    ''')

    print("\nRECENT SUCCESSFUL/HALTED RUNS:")
    print("=" * 100)
    runs = cur.fetchall()
    for row in runs:
        print(f'{row[0]:50} | {row[1]:10} | {row[2]} | Phases: {row[3]}OK/{row[4]}HALTED/{row[5]}ERR')

    if runs:
        latest_run = runs[0][0]
        print(f'\nDETAILED PHASE RESULTS FOR: {latest_run}')
        print("=" * 100)

        cur.execute('SELECT phase_results, halt_reason FROM orchestrator_execution_log WHERE run_id = %s', (latest_run,))
        result = cur.fetchone()
        if result:
            phases = result[0]
            if isinstance(phases, str):
                phases = json.loads(phases)
            halt_reason = result[1]
            for i, phase in enumerate(phases, 1):
                status = phase.get('status', 'UNKNOWN')
                summary = phase.get('summary', '')[:60]
                print(f'  Phase {i}: {status:10} | {summary}...')
            if halt_reason:
                print(f"\nHALT REASON: {halt_reason}")

# Check signal quality scores
print("\n\nSIGNAL QUALITY SCORE DISTRIBUTION:")
print("=" * 100)
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT
            MIN(signal_quality_score) as min_score,
            MAX(signal_quality_score) as max_score,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY signal_quality_score) as p25,
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY signal_quality_score) as p50,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY signal_quality_score) as p75,
            COUNT(*) as total_signals
        FROM algo_signals
        WHERE signal_date >= CURRENT_DATE - INTERVAL '7 days'
    ''')

    row = cur.fetchone()
    if row:
        print(f"  Min: {row[0]}, Max: {row[1]}")
        print(f"  P25: {row[2]}, P50: {row[3]}, P75: {row[4]}")
        print(f"  Total signals (last 7d): {row[5]}")

# Check position limits
print("\n\nPOSITION STATE:")
print("=" * 100)
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT COUNT(*) as open_positions, SUM(quantity) as total_qty
        FROM portfolio_positions
        WHERE status = 'open'
    ''')
    row = cur.fetchone()
    if row:
        print(f"  Open positions: {row[0]}")
        print(f"  Total quantity: {row[1]}")

print("\n\nLOADER STATUS (LAST 24H):")
print("=" * 100)
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT
            loader_name,
            status,
            completion_pct,
            last_run_at
        FROM data_loader_status
        WHERE last_run_at >= NOW() - INTERVAL '24 hours'
        ORDER BY loader_name
    ''')

    for row in cur.fetchall():
        print(f"  {row[0]:40} | {row[1]:8} | {row[2]:6.1f}% | {row[3]}")
