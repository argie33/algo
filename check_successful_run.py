#!/usr/bin/env python3
import os
import psycopg2
import json

os.environ.update({
    'DB_HOST': 'localhost',
    'DB_PORT': '5432',
    'DB_NAME': 'stocks',
    'DB_USER': 'stocks',
    'DB_PASSWORD': 'stocks',
    'LOCAL_MODE': 'true'
})

try:
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        database='stocks',
        user='stocks',
        password='stocks'
    )
    cur = conn.cursor()

    # Get the most recent successful run
    cur.execute("""SELECT run_id, overall_status, completed_at, halt_reason, phase_results
                   FROM orchestrator_execution_log
                   WHERE overall_status = 'ok'
                   ORDER BY completed_at DESC
                   LIMIT 1""")

    row = cur.fetchone()
    if row:
        run_id, status, completed, reason, phase_results_json = row
        print(f"Most recent successful run: {run_id}")
        print(f"Completed: {completed}")
        print(f"Status: {status}")
        print(f"Reason: {reason}")
        print("\nPhase Results:")
        print("=" * 100)

        if phase_results_json:
            try:
                phases = json.loads(phase_results_json) if isinstance(phase_results_json, str) else phase_results_json
                for phase_num in sorted(phases.keys(), key=lambda x: int(x) if x.isdigit() else 999):
                    p = phases[phase_num]
                    print(f"\nPhase {phase_num}: {p.get('name')}")
                    print(f"  Status: {p.get('status')}")
                    print(f"  Summary: {p.get('summary')}")
            except Exception as e:
                print(f"Error parsing phase results: {e}")
                print(f"Raw data: {phase_results_json}")
    else:
        print("No successful runs found")

    conn.close()
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
