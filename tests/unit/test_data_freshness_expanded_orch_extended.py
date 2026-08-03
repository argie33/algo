"""Regression test: orch_extended's failure-patterns block (the "reason"/"occurrences"
shape /api/algo/freshness/extended actually returns, per
lambda/api/routes/algo_handlers/monitoring.py::_get_orchestrator_history_extended) must be
rendered via _build_halt_reason_pattern_section(), not _build_failure_pattern_section()
(which expects per-table health-item dicts keyed "tbl"/"failure_rate_30d" instead). The
wrong helper doesn't crash (both index via .get()) - it silently finds zero matching keys
every time, so the Failure Patterns section built from orch_extended never rendered.

Run history / phase health / failure patterns moved from panel_data_freshness_expanded
(the [l] panel) to panel_algo_health_expanded (the [h] panel) - they're phase/run health,
not per-table data freshness, and prepending them to the [l] panel crowded out the
per-table freshness detail that panel exists to show.
"""

from tests.test_helpers.assertions import render_panel_to_text

from dashboard.panels.health import panel_algo_health_expanded, panel_data_freshness_expanded

HLTH = {"sources": [{"tbl": "price_daily", "st": "ok", "age": 0.1}]}

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

DUMMY_NOTIFS = [{"severity": "info", "title": "placeholder", "created_at": "2026-07-27T00:00:00+00:00", "seen": True}]

ORCH_EXTENDED = {
    "run_history": [],
    "phase_health": {},
    "failure_patterns": [
        {"reason": "phase_6_exit_execution halted: concentration check failed", "occurrences": 7},
    ],
    "loader_health": [],
    "trend_summary": {},
}


def test_orch_extended_failure_patterns_render_in_algo_health_expanded() -> None:
    panel = panel_algo_health_expanded(
        RUN, None, HLTH, DUMMY_NOTIFS, algo_metrics=[], exec_hist=[], orch_extended=ORCH_EXTENDED
    )
    text = render_panel_to_text(panel)

    assert "phase_6_exit_execution halted" in text
    assert "7x" in text


def test_orch_extended_failure_patterns_no_longer_render_in_freshness_expanded() -> None:
    panel = panel_data_freshness_expanded(HLTH, orch_extended=ORCH_EXTENDED)
    text = render_panel_to_text(panel)

    assert "phase_6_exit_execution halted" not in text
