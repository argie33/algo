"""Regression test: Phase 9's _compute_risk_metrics() must actually deliver VaR/concentration/
beta alerts via notify(), not just fold them into the phase-result log line.

BUG FOUND 2026-09-01 (/goal session, risk-mgmt review pass): generate_daily_risk_report() builds
an `alerts` list (VaR>2%, concentration>30%, beta>2.0) but nothing ever delivered it anywhere
actionable - it was only counted into the "N alerts" summary string logged via
log_phase_result_fn. A real VaR/beta/concentration breach was invisible unless someone went and
read algo_risk_daily or the phase 9 log by hand, unlike every other portfolio-level risk breach
in this codebase (phase2_circuit_breakers.py's alerts.send_position_alert() for halts,
notify_signal_staleness() for stale signals). Fixed by wiring the existing `notify()` channel in,
matching this same file's own convention at its P&L-divergence call site.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase9_reconciliation import _compute_risk_metrics


def _make_risk_report(alerts: list[str]) -> dict:
    return {
        "status": "ok",
        "var_metrics": {"var_pct": 2.5},
        "concentration": {"top_5_concentration_pct": 35.0},
        "beta_exposure": {"portfolio_beta": 2.1},
        "alerts": alerts,
    }


def test_risk_alerts_delivered_via_notify() -> None:
    log_calls = []

    def fake_log(*args):
        log_calls.append(args)

    with (
        patch("algo.risk.ValueAtRisk") as mock_var_cls,
        patch("algo.reporting.notify") as mock_notify,
    ):
        mock_var_cls.return_value.generate_daily_risk_report.return_value = _make_risk_report(
            ["VaR 2.50% exceeds 2% limit", "Top-5 concentration 35.0% exceeds 30% limit"]
        )

        _compute_risk_metrics(MagicMock(), date(2026, 8, 31), fake_log)

    mock_notify.assert_called_once()
    _, kwargs = mock_notify.call_args
    assert kwargs["severity"] == "warning"
    assert kwargs["title"] == "Portfolio Risk Report Alert"
    assert "VaR 2.50%" in kwargs["message"]
    assert "concentration 35.0%" in kwargs["message"]
    assert kwargs["details"]["alerts"] == [
        "VaR 2.50% exceeds 2% limit",
        "Top-5 concentration 35.0% exceeds 30% limit",
    ]


def test_no_alerts_means_no_notification() -> None:
    log_calls = []

    def fake_log(*args):
        log_calls.append(args)

    with (
        patch("algo.risk.ValueAtRisk") as mock_var_cls,
        patch("algo.reporting.notify") as mock_notify,
    ):
        mock_var_cls.return_value.generate_daily_risk_report.return_value = _make_risk_report([])

        _compute_risk_metrics(MagicMock(), date(2026, 8, 31), fake_log)

    mock_notify.assert_not_called()


def test_notify_failure_does_not_crash_phase9() -> None:
    """A notification-delivery failure must be swallowed (logged), not propagate and
    abort Phase 9 reconciliation - alerting is best-effort here, not a governance gate."""
    log_calls = []

    def fake_log(*args):
        log_calls.append(args)

    with (
        patch("algo.risk.ValueAtRisk") as mock_var_cls,
        patch("algo.reporting.notify", side_effect=RuntimeError("smtp down")),
    ):
        mock_var_cls.return_value.generate_daily_risk_report.return_value = _make_risk_report(
            ["VaR 2.50% exceeds 2% limit"]
        )

        # Must not raise despite notify() failing internally.
        _compute_risk_metrics(MagicMock(), date(2026, 8, 31), fake_log)

    assert log_calls
    assert log_calls[0][0] == 9
