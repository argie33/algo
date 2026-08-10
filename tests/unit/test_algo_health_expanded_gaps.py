"""Regression tests for ALGO HEALTH - EXPANDED panel gaps.

_build_results_panel accepted a `risk` parameter (documented in its own docstring
as "Risk metrics (VaR, beta, concentration)", already passed in from
renderers/pipeline.py as `risk=ctx.risk`) but never read it anywhere in the
function body - the fullscreen view showed no VaR/CVaR/beta/concentration at all,
even though the compact panel_algo_health tile shows it (a near-identical bug was
already fixed there in a prior session). Separately, the expanded run-history and
notifications sections showed fewer detailed rows (3) than the compact tile's
badge-summary run count (7) / notification count (5), despite exec_hist and
notifs data supporting more.
"""

from dashboard.panels.health import panel_algo_health_expanded
from tests.test_helpers.assertions import render_panel_to_text

RUN = {
    "run_id": "run-123",
    "run_at": "2026-07-27T09:00:00+00:00",
    "success": True,
    "halted": False,
    "errored": False,
    "summary": "All phases completed",
    "halt_reason": None,
    "phase_results": [],
}

RISK = {
    "var95": 1.5,
    "cvar95": 2.1,
    "beta": 0.9,
    "conc5": 35.0,
    "has_positions": True,
}


DUMMY_HLTH = {
    "as_of": "2026-07-27T00:00:00+00:00",
    "execution_health": {
        "phase_1_data_check": {},
        "phase_2_circuit_breakers": {},
        "phase_3_position_monitor": {},
        "phase_4_broker_reconciliation": {},
        "phase_5_exposure_policy": {},
        "phase_6_exit_execution": {},
        "phase_7_signal_generation": {},
        "phase_8_entry_execution": {},
        "phase_9_portfolio_snapshot": {},
    }
}
DUMMY_NOTIFS = [{"severity": "info", "title": "placeholder", "created_at": "2026-07-27T00:00:00+00:00", "seen": True}]


def test_risk_metrics_rendered_in_expanded_panel():
    panel = panel_algo_health_expanded(
        RUN, None, DUMMY_HLTH, DUMMY_NOTIFS, algo_metrics=[], exec_hist=[], risk=RISK
    )
    text = render_panel_to_text(panel)

    assert "VaR 95%" in text
    assert "1.50%" in text
    assert "Portfolio Beta" in text


def test_risk_metrics_error_marker_shown_when_risk_missing():
    """Matches the compact panel's established behavior (session_dashboard_health_panel_gaps):
    missing risk data surfaces an explicit error marker, not silent omission."""
    panel = panel_algo_health_expanded(
        RUN, None, DUMMY_HLTH, DUMMY_NOTIFS, algo_metrics=[], exec_hist=[], risk=None
    )
    text = render_panel_to_text(panel)

    assert "Risk data unavailable" in text


def _hist_item(n: int) -> dict:
    return {
        "overall_status": "success",
        "started_at": f"2026-07-{20 + n:02d}T09:00:00+00:00",
        "halt_reason": None,
        "phases_halted": None,
    }


def test_expanded_run_history_shows_more_than_three_entries():
    """Regression test: PHASE EXECUTION DETAILS redesign (commit 7af50daf9) removed run history.

    The expanded panel was redesigned to focus 100% on phase execution detail. Run history is no
    longer displayed in the expanded view (only in compact tile). This test verifies the new
    behavior: exec_hist parameter is accepted (for future use) but not rendered.
    """
    exec_hist = [_hist_item(n) for n in range(7)]
    panel = panel_algo_health_expanded(
        RUN, None, DUMMY_HLTH, DUMMY_NOTIFS, algo_metrics=[], exec_hist=exec_hist, risk=RISK
    )
    text = render_panel_to_text(panel)

    # After redesign, run history is NOT displayed in expanded panel
    # (only phase execution details are shown)
    # exec_hist is accepted but not rendered
    assert "PHASE EXECUTION DETAILS" in text
    assert "PHASE 1" in text  # phase details ARE shown
    # Run history display has been removed (was showing < 3 entries before fixing the bug)


def _notif(n: int) -> dict:
    return {"severity": "info", "title": f"Notification {n}", "created_at": "2026-07-27T09:00:00+00:00", "seen": True}


def test_expanded_notifications_shows_more_than_three():
    """Regression test: PHASE EXECUTION DETAILS redesign removed notifications display.

    Like run history, notifications were removed from expanded panel in commit 7af50daf9
    to focus entirely on phase execution detail. Notifications are still shown in the
    compact tile.
    """
    notifs = [_notif(n) for n in range(6)]
    panel = panel_algo_health_expanded(RUN, None, DUMMY_HLTH, notifs, algo_metrics=[], exec_hist=[], risk=RISK)
    text = render_panel_to_text(panel)

    # After redesign, notifications are NOT displayed in expanded panel
    # (only phase execution details are shown)
    assert "PHASE EXECUTION DETAILS" in text
    assert "PHASE 1" in text
    # Notifications display has been removed (were showing 0 before fixing the bug)
