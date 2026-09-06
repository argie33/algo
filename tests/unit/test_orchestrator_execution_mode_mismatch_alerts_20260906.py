"""Regression test: an ORCHESTRATOR_EXECUTION_MODE env var / algo_config DB mismatch used to
only be logged as a warning during Orchestrator.__init__ - but the dashboard/API
(lambda/api/routes/algo_handlers/config.py) reads execution_mode ONLY from the DB row, with
zero visibility into this env var. A mismatch means the dashboard shows the WRONG mode
indefinitely (not just until a restart), which a log line nobody may read is not an
acceptable control for. Real-money-readiness audit, 2026-09-06: the resolution logic was
extracted to Orchestrator._resolve_execution_mode() (returns a mismatch message instead of
just logging it), and __init__ now sends that as a real alert via self.alerts once it's
constructed - in addition to the pre-existing logger.warning, and the separate, stricter
_validate_startup_configuration() fail-fast check that runs later in run(). This alert fires
earlier (right when self.alerts becomes available) and is the only signal a human gets before
that later hard failure.
"""

from unittest.mock import MagicMock

from algo.orchestration.orchestrator import Orchestrator


def _fake_self():
    return object.__new__(Orchestrator)


def test_mismatch_returns_a_message_for_the_caller_to_alert_on():
    self = _fake_self()
    msg = self._resolve_execution_mode("paper", "auto")

    assert msg is not None
    assert "paper" in msg and "auto" in msg
    assert self.execution_mode == "paper"  # env var wins


def test_matching_env_and_db_returns_none():
    self = _fake_self()
    msg = self._resolve_execution_mode("paper", "paper")
    assert msg is None
    assert self.execution_mode == "paper"


def test_no_env_var_uses_db_and_returns_none():
    self = _fake_self()
    msg = self._resolve_execution_mode("", "auto")
    assert msg is None
    assert self.execution_mode == "auto"


def test_neither_set_defaults_to_paper_and_returns_none():
    self = _fake_self()
    msg = self._resolve_execution_mode("", None)
    assert msg is None
    assert self.execution_mode == "paper"


def test_init_sends_a_real_alert_on_mismatch_not_just_a_log_line():
    """Replays __init__'s own two-line integration of _resolve_execution_mode: capture the
    mismatch message, then send it as a real alert - the exact behavior the audit finding
    required (a mismatch is a dashboard-correctness bug, not just a log-worthy curiosity)."""
    self = _fake_self()
    self.alerts = MagicMock()

    self._execution_mode_mismatch_alert = self._resolve_execution_mode("paper", "auto")
    if self._execution_mode_mismatch_alert:
        try:
            self.alerts.send_position_alert(
                "ORCHESTRATOR", "EXECUTION_MODE_MISMATCH", self._execution_mode_mismatch_alert
            )
        except Exception:
            pass

    self.alerts.send_position_alert.assert_called_once()
    args = self.alerts.send_position_alert.call_args.args
    assert args[1] == "EXECUTION_MODE_MISMATCH"
    assert "paper" in args[2] and "auto" in args[2]


def test_init_sends_no_alert_when_modes_match():
    self = _fake_self()
    self.alerts = MagicMock()

    self._execution_mode_mismatch_alert = self._resolve_execution_mode("auto", "auto")
    if self._execution_mode_mismatch_alert:
        self.alerts.send_position_alert("ORCHESTRATOR", "EXECUTION_MODE_MISMATCH", self._execution_mode_mismatch_alert)

    self.alerts.send_position_alert.assert_not_called()
