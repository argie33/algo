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

from tests.test_helpers.assertions import render_panel_to_text

from dashboard.panels.health import panel_algo_health_expanded

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


DUMMY_HLTH = {"as_of": "2026-07-27T00:00:00+00:00"}
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
    exec_hist = [_hist_item(n) for n in range(7)]
    panel = panel_algo_health_expanded(
        RUN, None, DUMMY_HLTH, DUMMY_NOTIFS, algo_metrics=[], exec_hist=exec_hist, risk=RISK
    )
    text = render_panel_to_text(panel)

    # Count how many per-run detail lines appear (one per shown run, each rendered
    # with its own "success" status word - see _build_results_panel's per-run loop).
    detail_lines = [line for line in text.split("\n") if "success" in line.lower()]
    assert len(detail_lines) >= 4  # more than the old hard cap of 3


def _notif(n: int) -> dict:
    return {"severity": "info", "title": f"Notification {n}", "created_at": "2026-07-27T09:00:00+00:00", "seen": True}


def test_expanded_notifications_shows_more_than_three():
    notifs = [_notif(n) for n in range(6)]
    panel = panel_algo_health_expanded(RUN, None, DUMMY_HLTH, notifs, algo_metrics=[], exec_hist=[], risk=RISK)
    text = render_panel_to_text(panel)

    shown = sum(1 for n in range(6) if f"Notification {n}" in text)
    assert shown > 3
