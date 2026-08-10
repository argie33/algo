#!/usr/bin/env python3
"""Regression test: Phase 9 reconciliation failures must actually halt trading in
execution_mode="auto" (real money), not just log and continue.

Before this fix, phase9_reconciliation.py's run() hardcoded `halted=False` on every
PhaseResult it returned, regardless of whether reconciliation succeeded. Combined with
algo/infrastructure/reconciliation.py's run_daily_reconciliation() catching genuinely
critical checks (negative broker cash, corrupted account state, missing account fields -
all only reachable when execution_mode="auto" since self.broker is None otherwise) and
converting them to a plain {"success": False, ...} dict instead of raising, this meant:

  1. orchestrator.py's phase_9_reconcile() computed `not result.halted` = True unconditionally
  2. Unlike Phase 1/2 (which call self.halt_manager.set_halt_flag() when their result is
     halted), Phase 9 never called set_halt_flag() at all - the mechanism Phase 8 actually
     checks before submitting real orders.

Net effect: a real, unrecoverable broker/DB reconciliation failure in live trading produced
only a logged "critical" message and an "error" status row - Phase 8 would submit new real
orders on the very next run despite an unverified portfolio state. This bug was invisible
during all paper-mode testing because paper mode takes an entirely different (self.broker is
None) code path that doesn't hit these checks at all.

Static source check rather than a full mocked run(): run() has a very large dependency graph
(orphan cleanup, signal attribution, weight optimization, circuit breaker metrics, etc. all
run unconditionally before the branch under test) - see
test_exit_handler_clears_pending_client_order_id.py for the established precedent of testing
this kind of function via source structure instead.
"""

from pathlib import Path

ORCHESTRATOR_SOURCE = (Path(__file__).parent.parent.parent / "algo" / "orchestration" / "orchestrator.py").read_text()
PHASE9_SOURCE = (Path(__file__).parent.parent.parent / "algo" / "orchestrator" / "phase9_reconciliation.py").read_text()


def _reconciliation_failure_branch(source: str) -> str:
    start = source.index('else:\n            # Reconciliation failed - fail-fast')
    end = source.index("# Validate schema contract before returning", start)
    return source[start:end]


def test_reconciliation_failure_escalates_to_halt_only_in_auto_mode():
    branch = _reconciliation_failure_branch(PHASE9_SOURCE)
    assert 'is_governance_halt = execution_mode == "auto"' in branch, (
        "Reconciliation failure must only escalate to a real halt in execution_mode='auto' "
        "(real money) - non-auto (paper/dry/review) failures should keep degrading gracefully, "
        "matching Phase 2's identical is_credential_error-in-paper-mode distinction."
    )


def test_phase_result_halted_field_is_not_hardcoded_false():
    assert 'return PhaseResult(9, "reconciliation", phase_status, data, is_governance_halt, phase_error)' in PHASE9_SOURCE, (
        "PhaseResult's halted field must be driven by is_governance_halt, not hardcoded False - "
        "a hardcoded False silently defeats set_halt_flag() for every Phase 9 failure, "
        "including genuine execution_mode='auto' governance violations."
    )


def test_orchestrator_sets_halt_flag_on_phase9_halt():
    start = ORCHESTRATOR_SOURCE.index("def phase_9_reconcile")
    end = ORCHESTRATOR_SOURCE.index("\n    def ", start + 1)
    method_source = ORCHESTRATOR_SOURCE[start:end]
    assert "if result.halted:" in method_source and "self.halt_manager.set_halt_flag(" in method_source, (
        "phase_9_reconcile() must call self.halt_manager.set_halt_flag() when result.halted is "
        "True, mirroring phase_2_circuit_breakers()'s identical pattern - otherwise a Phase 9 "
        "governance halt has no actual effect on subsequent runs' Phase 8 halt-flag check."
    )
    assert 'triggered_by="phase9_reconciliation_governance"' in method_source, (
        "phase_9_reconcile()'s set_halt_flag() call must tag itself as "
        "'phase9_reconciliation_governance' (see halt_flag_cleared_by_unrelated_phase_fix_20260810) - "
        "untagged, Phase 1's freshness check would silently clear this halt on the very next "
        "run before Phase 8 (or anything else) ever got a chance to re-verify the underlying "
        "reconciliation failure was actually resolved, exactly the bug this tag exists to prevent. "
        "This halt deliberately has NO automatic clearing path of its own (unlike Phase 2's "
        "self-clear) - a real broker/DB state-verification failure in execution_mode='auto' "
        "requires a human to look, not an automatic re-check that could pass by coincidence on a "
        "transient blip. Use `scripts/manage_halt_flag.py --clear` after manually confirming the "
        "underlying reconciliation issue is actually resolved."
    )
