#!/usr/bin/env python3
from datetime import datetime, timezone, timedelta
from utils.db.connection import get_db_connection
import json

et = timezone(timedelta(hours=-4))
today = datetime.now(et).date()

print("\n=== RECENT ORCHESTRATOR RUNS ===\n")

conn = get_db_connection()
try:
    cur = conn.cursor()
    cur.execute("""
        SELECT
          run_id,
          run_date,
          overall_status,
          started_at,
          completed_at,
          execution_time_seconds,
          halt_reason
        FROM algo_orchestrator_runs
        ORDER BY started_at DESC
        LIMIT 10
    """)

    runs = cur.fetchall()
    print(f"Found {len(runs)} runs\n")
    for run in runs:
        print(f"Run ID: {run[0]}")
        print(f"  Date: {run[1]}")
        print(f"  Status: {run[2]}")
        print(f"  Started: {run[3]}")
        print(f"  Completed: {run[4]}")
        print(f"  Duration: {run[5]}s")
        print(f"  Halt Reason: {run[6]}")
        print()
finally:
    conn.close()

print("\n=== EXECUTION LOG FOR LATEST RUN ===\n")

conn = get_db_connection()
try:
    cur = conn.cursor()
    cur.execute("""
        SELECT
          run_id,
          overall_status,
          phases_completed,
          phases_halted,
          phases_errored,
          phase_results,
          summary
        FROM orchestrator_execution_log
        ORDER BY started_at DESC
        LIMIT 1
    """)

    log = cur.fetchone()
    if log:
        print(f"Run ID: {log[0]}")
        print(f"Overall Status: {log[1]}")
        print(f"Phases Completed: {log[2]}")
        print(f"Phases Halted: {log[3]}")
        print(f"Phases Errored: {log[4]}")
        print(f"\nSummary:\n{log[6]}")

        if log[5]:
            print(f"\nPhase Results:")
            results = log[5] if isinstance(log[5], dict) else json.loads(str(log[5]))
            for phase_name, phase_detail in results.items():
                if isinstance(phase_detail, dict):
                    print(f"  {phase_name}: {phase_detail.get('status', 'unknown')}")
                    if 'error' in phase_detail:
                        print(f"    ERROR: {phase_detail['error']}")
                else:
                    print(f"  {phase_name}: {phase_detail}")
finally:
    conn.close()

print("\n=== ORACLE LOG (Last 50 records) ===\n")

conn = get_db_connection()
try:
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'oracle_log'
    """)
    if cur.fetchone():
        cur.execute("""
            SELECT
              action,
              symbol,
              status,
              execution_time,
              error_message
            FROM oracle_log
            ORDER BY execution_time DESC
            LIMIT 50
        """)

        records = cur.fetchall()
        print(f"Total oracle_log records: {len(records)}\n")

        # Group by action
        actions = {}
        for rec in records:
            action = rec[0]
            if action not in actions:
                actions[action] = []
            actions[action].append(rec)

        for action in ['exit', 'entry']:
            if action in actions:
                print(f"\n{action.upper()} actions ({len(actions[action])}):")
                for rec in actions[action][:10]:
                    print(f"  {rec[1]}: status={rec[2]}, time={rec[3]}")
                    if rec[4]:
                        print(f"    ERROR: {rec[4]}")
finally:
    conn.close()
