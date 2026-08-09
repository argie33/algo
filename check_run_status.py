#!/usr/bin/env python3
from datetime import datetime, timezone, timedelta
from utils.db.connection import get_db_connection
import json

et = timezone(timedelta(hours=-4))
today = datetime.now(et).date()

print("\n=== TODAY'S ORCHESTRATOR RUNS ===\n")

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
          halt_reason,
          phases_completed,
          phases_halted,
          phases_errored,
          phase_results
        FROM algo_orchestrator_runs
        WHERE run_date >= %s
        ORDER BY started_at DESC
        LIMIT 10
    """, (today,))

    runs = cur.fetchall()
    print(f"Found {len(runs)} runs\n")
    for run in runs:
        print(f"Run ID: {run[0]}")
        print(f"  Date: {run[1]}")
        print(f"  Overall Status: {run[2]}")
        print(f"  Started: {run[3]}")
        print(f"  Completed: {run[4]}")
        print(f"  Duration: {run[5]}s")
        print(f"  Halt Reason: {run[6]}")
        print(f"  Phases Completed: {run[7]}")
        print(f"  Phases Halted: {run[8]}")
        print(f"  Phases Errored: {run[9]}")
        if run[10]:
            print(f"\n  Phase Results:")
            results = run[10] if isinstance(run[10], dict) else json.loads(str(run[10]))
            for phase_name, phase_status in results.items():
                print(f"    {phase_name}: {phase_status}")
        print()
finally:
    conn.close()

print("\n=== EXIT-RELATED TABLES ===\n")

conn = get_db_connection()
try:
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name LIKE '%exit%'
        ORDER BY table_name
    """)
    tables = cur.fetchall()
    print("Exit-related tables:")
    for table in tables:
        print(f"  {table[0]}")
finally:
    conn.close()

# Check if there's an algo_exit_execution_log table and show recent records
print("\n=== RECENT EXIT EXECUTIONS ===\n")

conn = get_db_connection()
try:
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        AND (table_name LIKE '%exit%' OR table_name LIKE '%position%')
        AND table_name NOT LIKE '%phase%'
        ORDER BY table_name
    """)
    tables = [t[0] for t in cur.fetchall()]

    if 'algo_exit_execution_log' in tables:
        cur.execute("""
            SELECT COUNT(*), MAX(executed_at) FROM algo_exit_execution_log
            WHERE executed_at >= %s
        """, (datetime.combine(today, datetime.min.time()).replace(tzinfo=et),))
        result = cur.fetchone()
        print(f"Exit executions today: {result[0]} (latest: {result[1]})")
    elif tables:
        print(f"Available tables: {tables}")
        # Try to look at oracle_log for exits
        if 'oracle_log' in tables:
            cur.execute("""
                SELECT COUNT(*), MAX(execution_time) FROM oracle_log
                WHERE DATE(execution_time) >= %s
                AND action = 'exit'
            """, (today,))
            result = cur.fetchone()
            print(f"Oracle exit actions today: {result[0]}")
finally:
    conn.close()
