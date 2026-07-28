"""Regression test: Orchestrator._validate_startup_configuration must reject
execution_mode="live" (never a real mode) while accepting execution_mode="review" (a real,
previously-blocked mode) alongside "paper"/"auto".

Found live 2026-07-28: orchestrator.py's startup validation (and compute_run_mode_label's
real-money risk check) accepted "live" as an equally-valid third value alongside "paper"/
"auto" - but algo/trading/executor_strategies.py's create_execution_mode_strategy(), the
only place execution_mode actually turns into trading behavior, has never registered a
"live" strategy (only paper/review/auto). "live" - the single most natural word an
operator/Terraform var would pick for "real money mode" - would pass this startup check
clean, then crash deep inside TradeExecutor.__init__ the moment Phase 6 (exit execution,
always_run) tried to instantiate it. Fixed by rejecting "live" explicitly at startup with
a clear message pointing to "auto" instead of letting it reach that crash.

Same discovery, opposite direction: "review" IS a real, fully-implemented mode (see
executor.py's own `execution_mode == "review"` branch, which creates a distinct "pending"
order for manual review) that this check had never accepted - fixed alongside the "live"
rejection.
"""

import pytest

from algo.orchestration.orchestrator import Orchestrator, compute_run_mode_label


def _fake_self(env_execution_mode, config_execution_mode):
    self = object.__new__(Orchestrator)
    self.execution_mode = env_execution_mode
    self.config = {"execution_mode": config_execution_mode}
    return self


class TestExecutionModeLiveRejected:
    def test_live_config_value_rejected_at_startup(self):
        self = _fake_self("live", "live")
        with pytest.raises(RuntimeError, match="execution_mode must be 'paper', 'review', or 'auto'"):
            Orchestrator._validate_startup_configuration(self)

    def test_auto_config_value_still_accepted(self):
        self = _fake_self("auto", "auto")
        # Should not raise on the execution_mode validity/mismatch checks (may still raise
        # later on credential validation - that's a different, unrelated concern).
        try:
            Orchestrator._validate_startup_configuration(self)
        except RuntimeError as e:
            assert "execution_mode must be" not in str(e)
            assert "execution_mode mismatch" not in str(e)

    def test_paper_config_value_still_accepted(self):
        self = _fake_self("paper", "paper")
        try:
            Orchestrator._validate_startup_configuration(self)
        except RuntimeError as e:
            assert "execution_mode must be" not in str(e)
            assert "execution_mode mismatch" not in str(e)

    def test_review_config_value_now_accepted(self):
        # Previously rejected even though it's a real, fully-implemented mode - see
        # executor.py's own "review" branch and order_manager.py's paper-like early return.
        self = _fake_self("review", "review")
        try:
            Orchestrator._validate_startup_configuration(self)
        except RuntimeError as e:
            assert "execution_mode must be" not in str(e)
            assert "execution_mode mismatch" not in str(e)


class TestRunModeLabelNoLongerTreatsLiveAsAuto:
    def test_live_string_no_longer_triggers_real_money_label(self):
        # "live" should never reach this function post-fix (rejected at startup), but the
        # label function itself must not treat the literal string "live" as equivalent to
        # "auto" either - defense in depth.
        assert compute_run_mode_label(False, "live", False) == "PAPER"

    def test_auto_with_real_alpaca_still_labeled_real_money(self):
        assert compute_run_mode_label(False, "auto", False) == "LIVE - REAL MONEY"
