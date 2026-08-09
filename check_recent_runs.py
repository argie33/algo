import psycopg2
from datetime import datetime, timedelta
import json

with psycopg2.connect('dbname=algo user=postgres password=postgres host=localhost') as conn:
    with conn.cursor() as cur:
        # Get recent orchestrator runs
        cur.execute('''
            SELECT
                run_id, run_date, status, phase_results, error_message,
                started_at, completed_at
            FROM orchestration_runs
            ORDER BY started_at DESC
            LIMIT 15
        ''')
        runs = cur.fetchall()
        print('RECENT ORCHESTRATOR RUNS:')
        print('=' * 120)
        for run in runs:
            run_id, run_date, status, phase_results, error_msg, started, completed = run
            print(f'\nRun ID: {run_id}')
            print(f'  Date: {run_date}, Status: {status}')
            print(f'  Started: {started}, Completed: {completed}')
            if error_msg:
                print(f'  ERROR: {error_msg[:200]}')
            if phase_results:
                try:
                    phases = json.loads(phase_results)
                    for phase_num in sorted(phases.keys(), key=lambda x: int(x)):
                        phase_data = phases[phase_num]
                        print(f'  Phase {phase_num}: {phase_data.get("status", "unknown")} ({phase_data.get("duration_sec", 0):.2f}s)', end='')
                        if 'error' in phase_data:
                            print(f' | Error: {phase_data["error"][:100]}')
                        else:
                            print()
                except:
                    print(f'  Phases: (unparseable)')
            print()
