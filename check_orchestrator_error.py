#!/usr/bin/env python3
"""Check what's causing the orchestrator to fail."""

import os
import sys
import json
from pathlib import Path

_repo_root = Path(__file__).parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

try:
    from utils.db import DatabaseContext

    with DatabaseContext("read") as cur:
        # Get latest orchestrator run with error details
        cur.execute("""
            SELECT
                run_id,
                run_date,
                overall_status,
                phases_completed,
                phases_halted,
                phases_errored,
                summary,
                halt_reason,
                phase_results
            FROM orchestrator_execution_log
            ORDER BY run_date DESC
            LIMIT 5
        """)

        runs = cur.fetchall()
        for run in runs:
            run_id, run_date, status, phases_completed, phases_halted, phases_errored, summary, halt_reason, phase_results = run
            print(f"\n{'='*80}")
            print(f"Run ID: {run_id}")
            print(f"Date: {run_date}")
            print(f"Status: {status}")
            print(f"Phases: {phases_completed} completed, {phases_halted} halted, {phases_errored} errored")
            if summary:
                print(f"Summary: {summary}")
            if halt_reason:
                print(f"Halt Reason: {halt_reason}")
            if phase_results:
                print(f"\nPhase Results:")
                try:
                    if isinstance(phase_results, str):
                        results_dict = json.loads(phase_results)
                    else:
                        results_dict = phase_results
                    for phase_id, phase_info in sorted(results_dict.items()):
                        if isinstance(phase_info, dict):
                            status = phase_info.get('status', '?')
                            error = phase_info.get('error', '')
                            print(f"  Phase {phase_id}: {status}")
                            if error:
                                print(f"    Error: {error[:200]}")
                        else:
                            print(f"  Phase {phase_id}: {phase_info}")
                except Exception as e:
                    print(f"  (Could not parse phase results: {e})")

except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
