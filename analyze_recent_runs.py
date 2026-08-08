#!/usr/bin/env python3
"""Analyze recent orchestrator runs to identify issues."""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

os.environ.setdefault('ENVIRONMENT', 'local')
sys.path.insert(0, str(Path(__file__).parent))

from utils.db.context import DatabaseContext

def main():
    with DatabaseContext() as cur:

        print("\n" + "="*100)
        print("ORCHESTRATOR EXECUTION LOG (Recent Runs)")
        print("="*100)

        # Get last 20 orchestrator runs
        cur.execute("""
            SELECT run_id, run_date, overall_status, phases_completed, phases_halted,
                   phases_errored, halt_reason, started_at, completed_at
            FROM orchestrator_execution_log
            ORDER BY started_at DESC
            LIMIT 20
        """)
        runs = cur.fetchall()
        for run in runs:
            started = run[7].strftime('%Y-%m-%d %H:%M:%S') if run[7] else 'N/A'
            halt_reason = (run[6][:40] + "...") if run[6] and len(run[6]) > 40 else run[6]
            print(f"{started:20} | {run[0]:40} | {run[2]:12} | Completed: {run[3]:2} | Halted: {run[4]:2} | Errored: {run[5]:2}")
            if halt_reason:
                print(f"{'':20} | Halt reason: {halt_reason}")

        print("\n" + "="*100)
        print("DETAILED PHASE RESULTS FROM LATEST RUN")
        print("="*100)

        cur.execute("""
            SELECT run_id, started_at, phase_results
            FROM orchestrator_execution_log
            ORDER BY started_at DESC
            LIMIT 1
        """)
        latest = cur.fetchone()
        if latest:
            run_id, started, phase_results_data = latest
            print(f"Latest Run: {run_id} at {started}")
            # phase_results is already a dict or list
            if isinstance(phase_results_data, str):
                phase_results = json.loads(phase_results_data)
            else:
                phase_results = phase_results_data

            if isinstance(phase_results, dict):
                for phase_num in sorted(phase_results.keys(), key=lambda x: int(x)):
                    phase_data = phase_results[phase_num]
                    print(f"\n  Phase {phase_num}:")
                    if isinstance(phase_data, dict):
                        for key, val in phase_data.items():
                            if key == 'error_msg' and val:
                                print(f"    {key}: {val[:80] if len(str(val)) > 80 else val}")
                            elif key not in ['error_details', 'traceback']:
                                print(f"    {key}: {val}")
            elif isinstance(phase_results, list):
                for idx, phase_data in enumerate(phase_results):
                    if isinstance(phase_data, dict):
                        print(f"\n  Phase {idx}:")
                        for key, val in phase_data.items():
                            if key == 'error_msg' and val:
                                print(f"    {key}: {val[:80] if len(str(val)) > 80 else val}")
                            elif key not in ['error_details', 'traceback']:
                                print(f"    {key}: {val}")

        print("\n" + "="*100)
        print("POSITION STATUS (Current)")
        print("="*100)

        cur.execute("""
            SELECT COUNT(*), COUNT(CASE WHEN exit_time IS NULL THEN 1 END),
                   COUNT(CASE WHEN entry_time IS NOT NULL AND exit_time IS NOT NULL AND entry_time > exit_time THEN 1 END)
            FROM algo_trades
            WHERE status = 'closed'
        """)
        pos_counts = cur.fetchone()
        print(f"Total closed positions: {pos_counts[0]}")
        print(f"Closed positions with NULL exit_time: {pos_counts[1]}")
        print(f"Closed positions with entry_time > exit_time (IMPOSSIBLE!): {pos_counts[2]}")

        cur.execute("""
            SELECT COUNT(*)
            FROM algo_positions
            WHERE status = 'open'
        """)
        open_count = cur.fetchone()[0]
        print(f"\nCurrent open positions: {open_count}/15 limit")

        if open_count >= 15:
            print("[CRITICAL] System is at hard position limit!")

        # Get recent exits
        cur.execute("""
            SELECT symbol, entry_time, exit_time, exit_reason, profit_loss_dollars
            FROM algo_trades
            WHERE status = 'closed'
            ORDER BY exit_time DESC
            LIMIT 15
        """)
        recent_exits = cur.fetchall()
        print("\nRecent exits (last 15):")
        for exit_rec in recent_exits:
            symbol, entry, exit_t, reason, pnl = exit_rec
            entry_str = entry.strftime('%Y-%m-%d %H:%M') if entry else 'NULL'
            exit_str = exit_t.strftime('%Y-%m-%d %H:%M') if exit_t else 'NULL'
            pnl_str = f"${pnl:7.2f}" if pnl else "NULL"
            print(f"  {symbol:6} | Entry: {entry_str} | Exit: {exit_str} | Reason: {reason or 'N/A':20} | P/L: {pnl_str}")

        print("\n" + "="*100)
        print("CHECKING FOR ISSUES")
        print("="*100)

        # Check for infinite rotation
        cur.execute("""
            SELECT symbol, COUNT(*) as entry_count, MAX(entry_time)
            FROM algo_trades
            WHERE status = 'closed'
            GROUP BY symbol
            HAVING COUNT(*) > 5
            ORDER BY COUNT(*) DESC
            LIMIT 10
        """)
        rotations = cur.fetchall()
        if rotations:
            print("\n[WARNING] Symbols with excessive rotation cycles:")
            for symbol, count, last_entry in rotations:
                print(f"  {symbol:6}: {count} entries (last: {last_entry})")

        # Check for positions with bad exit_time
        cur.execute("""
            SELECT COUNT(*)
            FROM algo_trades
            WHERE status = 'closed' AND exit_time IS NULL
        """)
        null_exit_time = cur.fetchone()[0]
        if null_exit_time > 0:
            print(f"\n[CRITICAL] {null_exit_time} closed positions have NULL exit_time!")

        # Check for impossible exit times
        cur.execute("""
            SELECT symbol, entry_time, exit_time, (exit_time - entry_time) as duration
            FROM algo_trades
            WHERE status = 'closed' AND entry_time > exit_time
            LIMIT 10
        """)
        bad_times = cur.fetchall()
        if bad_times:
            print(f"\n[CRITICAL] {len(bad_times)} positions have entry_time > exit_time (data corruption!):")
            for symbol, entry, exit_t, dur in bad_times:
                print(f"  {symbol:6} | Entry: {entry} | Exit: {exit_t} (impossible!)")

if __name__ == '__main__':
    main()
