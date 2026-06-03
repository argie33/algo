#!/usr/bin/env python3
"""Test run of orchestrator with 2026-06-02 data."""
import sys
from datetime import date
import logging

logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)-8s | %(message)s'
)

print("\n" + "="*70)
print("ORCHESTRATOR TEST: 2026-06-02 (LIVE MODE)")
print("="*70 + "\n")

try:
    from algo.algo_orchestrator import Orchestrator

    orch = Orchestrator(run_date=date(2026, 6, 2), dry_run=False, verbose=False)

    print("[INIT] Orchestrator initialized")
    print("[INIT] Running orchestrator for 2026-06-02...\n")

    result = orch.run()

    print("\n" + "="*70)
    print("ORCHESTRATOR EXECUTION COMPLETE")
    print("="*70)

    # Print phase results
    print("\nPhase Execution Summary:")
    print("-"*70)

    for phase_name in ['phase_1_data_freshness', 'phase_2_circuit_breaker', 'phase_3_position_monitor',
                       'phase_4_exit_execution', 'phase_5_signal_generation', 'phase_6_trade_entries',
                       'phase_7_reconciliation']:
        if phase_name in orch.phase_results:
            result = orch.phase_results[phase_name]
            if isinstance(result, dict):
                status = result.get('status', 'UNKNOWN')
                details = result.get('details', '')
                if details:
                    print(f"  {phase_name:35} => {status:10} | {str(details)[:40]}")
                else:
                    print(f"  {phase_name:35} => {status:10}")
            else:
                print(f"  {phase_name:35} => {str(result)[:50]}")

    print("-"*70)
    print(f"\nHalt flag state: {orch._halt_flag_checked}")
    print(f"Degraded mode: {orch.degraded_mode}")

    print("\n[SUCCESS] Orchestrator run completed")

except Exception as e:
    print(f"\n[FATAL ERROR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
