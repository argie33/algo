#!/usr/bin/env python3
"""Manual operator control over the orchestrator's persistent halt flag.

BUILT 2026-08-10 alongside halt_flag_cleared_by_unrelated_phase_fix_20260810: before this,
there was NO way for a human operator to durably halt or resume trading - the only writers
were the orchestrator's own automated checks (Phase 1 data freshness, Phase 2 circuit
breaker, Phase 9 reconciliation governance), and Phase 1 used to unconditionally clear
whatever halt was active whenever its own check passed, regardless of who set it or why.

Now that halts are tagged with `triggered_by` and Phase 1 only auto-clears its own, a halt
set by this script (triggered_by="manual_operator") is guaranteed to survive Phase 1's
freshness check indefinitely - it will only ever be cleared by an explicit `--clear` here.

Usage:
    python scripts/manage_halt_flag.py --status
    python scripts/manage_halt_flag.py --set "Stopping trading: investigating anomaly in signal quality"
    python scripts/manage_halt_flag.py --clear "Investigated - false alarm, resuming trading"
"""

import argparse
import sys

from algo.orchestration.halt_flag_manager import HaltFlagManager
from algo.reporting import AlertManager


def _noop_log_phase_result(*args: object, **kwargs: object) -> None:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Manually set or clear the orchestrator's persistent halt flag")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true", help="Show current halt flag status")
    group.add_argument("--set", metavar="REASON", help="Manually halt trading with the given reason")
    group.add_argument("--clear", metavar="REASON", help="Manually clear an active halt with the given reason")
    args = parser.parse_args()

    halt_manager = HaltFlagManager(AlertManager(), _noop_log_phase_result)

    if args.status:
        is_halted = halt_manager.check_halt_flag()
        triggered_by = halt_manager.get_halt_triggered_by() if is_halted else None
        print(f"Halted: {is_halted}")
        if is_halted:
            print(f"Triggered by: {triggered_by or 'unknown'}")
            if triggered_by and triggered_by != "manual_operator":
                print(
                    f"NOTE: this halt was set automatically by {triggered_by}, not a human operator. "
                    "Investigate the underlying condition before clearing it - see that phase's own "
                    "logic/logs for what triggered it."
                )
        return 0

    if args.set:
        print(f"Setting halt flag: {args.set}")
        result = halt_manager.set_halt_flag(args.set, triggered_by="manual_operator")
        if not result:
            print("ERROR: Failed to set halt flag (both DynamoDB and RDS unavailable).", file=sys.stderr)
            return 1
        print("Halt flag set. Trading is now halted until explicitly cleared with --clear.")
        return 0

    if args.clear:
        current_trigger = halt_manager.get_halt_triggered_by()
        if current_trigger and current_trigger not in ("manual_operator", "phase1_data_freshness"):
            print(
                f"WARNING: the active halt was set automatically by '{current_trigger}', not manually. "
                "Make sure you've actually verified and resolved the underlying condition (see that "
                "phase's own code/logs) before clearing - this is not a routine 'unstick' action.",
                file=sys.stderr,
            )
        print(f"Clearing halt flag: {args.clear}")
        halt_manager.clear_halt_flag(f"Manually cleared: {args.clear}")
        print("Halt flag cleared. Trading may resume on the next orchestrator run.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
