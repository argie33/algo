#!/usr/bin/env python3
"""Find actual runtime issues from execution logs."""

import json
from utils.db.context import DatabaseContext

with DatabaseContext('read') as cur:
    # Get runs with halts/degraded status
    cur.execute('''
        SELECT
            run_id,
            overall_status,
            phase_results,
            created_at
        FROM orchestrator_execution_log
        WHERE overall_status IN ('halted', 'degraded', 'error')
        ORDER BY created_at DESC
        LIMIT 10
    ''')

    halted_runs = cur.fetchall()

print(f"\n{'='*100}")
print(f"HALTED/DEGRADED RUNS ANALYSIS")
print(f"{'='*100}\n")

if not halted_runs:
    print("No halted or degraded runs found in last 20 executions.")
else:
    for run_id, overall_status, phase_results, created_at in halted_runs:
        print(f"\nRun: {run_id}")
        print(f"Status: {overall_status} | Time: {created_at}")
        print(f"{'-'*80}")

        # phase_results is already a list
        if phase_results:
            try:
                # It might be a JSON string or already a list
                phases = phase_results if isinstance(phase_results, list) else json.loads(phase_results)

                for phase in phases:
                    if not isinstance(phase, dict):
                        continue

                    phase_num = phase.get('phase_num', '?')
                    status = phase.get('status', '?')
                    info = phase.get('info', '')
                    error_msg = phase.get('error', '')

                    if status in ('error', 'halted', 'halt', 'degraded', 'alert'):
                        print(f"  Phase {phase_num}: {status}")
                        if info:
                            print(f"    Info: {info}")
                        if error_msg:
                            print(f"    Error: {error_msg}")
            except Exception as e:
                print(f"  Parse error: {e}")
                print(f"  Raw data type: {type(phase_results)}")

# Now check for any ERROR level logs in the last trading day
print(f"\n{'='*100}")
print(f"CHECKING FOR CRITICAL/ERROR LEVEL LOGS")
print(f"{'='*100}\n")

with DatabaseContext('read') as cur:
    # Check application logs for CRITICAL/ERROR
    cur.execute('''
        SELECT DISTINCT
            level,
            COUNT(*) as count
        FROM application_logs
        WHERE
            level IN ('CRITICAL', 'ERROR')
            AND created_at > NOW() - INTERVAL '24 hours'
        GROUP BY level
        ORDER BY count DESC
    ''')

    log_levels = cur.fetchall()

if log_levels:
    print("Critical/Error logs found in last 24 hours:")
    for level, count in log_levels:
        print(f"  {level}: {count} occurrences")

    # Get some examples
    cur.execute('''
        SELECT
            level,
            message,
            created_at
        FROM application_logs
        WHERE
            level IN ('CRITICAL', 'ERROR')
            AND created_at > NOW() - INTERVAL '24 hours'
        ORDER BY created_at DESC
        LIMIT 10
    ''')

    print(f"\nSample errors:")
    for level, message, created_at in cur.fetchall():
        msg_preview = message[:100] if message else "(empty)"
        print(f"  {level}: {msg_preview}")
else:
    print("No critical or error logs in last 24 hours.")

print(f"\n{'='*100}\n")
