"""Regression test: Orchestrator._validate_startup_configuration must fail fast when
ORCHESTRATOR_EXECUTION_MODE (env var) disagrees with algo_config's execution_mode (DB value).

Found live 2026-07-28: `self.execution_mode` (set in __init__ from the ORCHESTRATOR_EXECUTION_MODE
env var - the value lambda_function.py deliberately sets per EventBridge schedule/event, with an
explicit "orchestrator.__init__ will pick it up" comment) has ZERO effect on actual trading
behavior. Every real order-submission call site (TradeExecutor, HandlerContext,
executor_entry_handler.py/executor_exit_handler.py) reads self.config["execution_mode"] (sourced
from the algo_config DB table) instead - confirmed via exhaustive grep, self.execution_mode is
read in exactly one other place: the startup banner label (compute_run_mode_label in run()).

This means a schedule/operator believing ORCHESTRATOR_EXECUTION_MODE controls whether a run risks
real money is silently overridden by whatever a single global algo_config DB row happens to hold,
with the pre-fix banner ALSO reading the disconnected env var - so it could misreport real-money
risk in either direction with zero warning. Fixed by (1) failing startup fast when the two
disagree, and (2) making the banner read the DB value (the one that actually governs behavior)
instead of the env var.
"""

import pytest

from algo.orchestration.orchestrator import Orchestrator


def _fake_self(env_execution_mode, config_execution_mode):
    self = object.__new__(Orchestrator)
    self.execution_mode = env_execution_mode
    self.config = {"execution_mode": config_execution_mode}
    return self


class TestExecutionModeEnvConfigMismatch:
    def test_matching_env_and_config_passes(self):
        self = _fake_self("paper", "paper")
        # Should not raise past the execution_mode checks (will fail later on credential
        # validation for non-paper modes, or succeed silently for paper - either way, no
        # mismatch RuntimeError).
        try:
            Orchestrator._validate_startup_configuration(self)
        except RuntimeError as e:
            assert "execution_mode mismatch" not in str(e)

    def test_env_var_disagrees_with_db_config_raises(self):
        # The exact dangerous scenario: env var says paper (an operator/schedule believes this
        # run is safe) but the DB config - which actually governs behavior - says auto/live.
        self = _fake_self("paper", "auto")
        with pytest.raises(RuntimeError, match="execution_mode mismatch"):
            Orchestrator._validate_startup_configuration(self)

    def test_reverse_mismatch_also_raises(self):
        # Also dangerous in the other direction: env var says live but DB config says paper -
        # a "go live" deployment that would silently keep trading paper with no indication.
        self = _fake_self("live", "paper")
        with pytest.raises(RuntimeError, match="execution_mode mismatch"):
            Orchestrator._validate_startup_configuration(self)
