#!/usr/bin/env python3
"""Regression test: Orchestrator._executor_phase_1 must actually deliver an alert when
validate_position_count() fails, not just log a warning.

Before this fix, a `missing_in_positions` finding (a symbol with a real open trade in
algo_trades but no corresponding row in algo_positions) only reached
validate_position_count()'s own logger.error/logger.critical calls - never a real alert
channel (email/SNS/DB-persisted alert). This matters because circuit_breaker.py's
portfolio-risk/total-risk checks read from algo_positions, not algo_trades: a position
missing from algo_positions is invisible to risk management, so its risk silently isn't
counted against any exposure/drawdown limit at all, with no operator ever notified.

Same "computed but never delivered" bug class already found and fixed for Phase 9's
VaR/concentration/beta alerts (commit 5ac092eea) - see MEMORY.md.

Follows this repo's own precedent for testing this exact method
(tests/test_orchestrator_critical_paths_audit.py's TestPositionSyncPhase1), which uses
source inspection rather than instantiating Orchestrator directly, since Orchestrator.__init__
requires live AWS/DB resources.
"""

import inspect


class TestPositionSyncValidationFailureAlerts:
    def test_executor_phase_1_calls_alerts_critical_on_validation_failure(self):
        from algo.orchestration.orchestrator import Orchestrator

        source = inspect.getsource(Orchestrator._executor_phase_1)
        assert "if not validate_position_count():" in source
        # The alert call must be inside the validation-failure branch, not merely present
        # anywhere in the method.
        branch = source.split("if not validate_position_count():", 1)[1]
        # Stop at the next top-level statement in the try block (the except clause) so we
        # only inspect the failure branch itself.
        branch = branch.split("except RuntimeError", 1)[0]
        assert "self.alerts.critical(" in branch, (
            "validate_position_count() failing must trigger a real alert (self.alerts.critical), "
            "not just a log line - a symbol missing from algo_positions is invisible to "
            "circuit_breaker.py's risk checks and must reach an operator"
        )
