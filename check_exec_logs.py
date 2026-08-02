#!/usr/bin/env python3
import os
import psycopg2

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

    print("=" * 100)
    print("NON-SKIPPED RUNS")
    print("=" * 100)
    cur.execute("""SELECT run_id, overall_status, completed_at, halt_reason
                   FROM orchestrator_execution_log
                   WHERE overall_status != 'skipped'
                   ORDER BY completed_at DESC LIMIT 20""")
    rows = cur.fetchall()
    print(f"Found {len(rows)} non-skipped runs:")
    for row in rows:
        run_id, status, completed, reason = row
        print(f"{run_id:<40} | {status:<10} | {completed} | {reason}")

    print("\n" + "=" * 100)
    print("PHASE RESULTS FOR MOST RECENT NON-SKIPPED RUN")
    print("=" * 100)
    if rows:
        most_recent_run = rows[0][0]
        cur.execute("""SELECT phase_results FROM orchestrator_execution_log
                       WHERE run_id = %s""", (most_recent_run,))
        result = cur.fetchone()
        if result and result[0]:
            import json
            # CRITICAL: phase_results is stored as JSONB, so psycopg2 returns it as
            # a Python object (list/dict), not a string. Don't call json.loads().
            phases_data = result[0]
            if isinstance(phases_data, str):
                # If somehow it's a string, parse it
                phases = json.loads(phases_data)
            else:
                # Already a Python object from JSONB fetch
                phases = phases_data if isinstance(phases_data, dict) else {i: p for i, p in enumerate(phases_data)}

            if isinstance(phases, list):
                # phase_results_array is a list - convert to dict for easier access
                for phase in phases:
                    phase_num = phase.get('phase', '?')
                    print(f"\nPhase {phase_num}: {phase.get('name')}")
                    print(f"  Status: {phase.get('status')}")
                    print(f"  Summary: {phase.get('summary')}")
            else:
                # phases is a dict
                for phase_num in sorted(phases.keys(), key=lambda x: int(x)):
                    phase = phases[phase_num]
                    print(f"\nPhase {phase_num}: {phase.get('name')}")
                    print(f"  Status: {phase.get('status')}")
                    print(f"  Summary: {phase.get('summary')}")

    conn.close()
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
