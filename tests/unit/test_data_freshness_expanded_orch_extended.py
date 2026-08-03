"""Regression test: panel_data_freshness_expanded's orch_extended failure-patterns block
called _build_failure_pattern_section() (expects per-table health-item dicts keyed
"tbl"/"failure_rate_30d") instead of _build_halt_reason_pattern_section() (expects the
"reason"/"occurrences" shape /api/algo/freshness/extended actually returns, per
lambda/api/routes/algo_handlers/monitoring.py::_get_orchestrator_history_extended). The
wrong helper doesn't crash (both index via .get()) - it silently finds zero matching
keys every time, so the Failure Patterns section built from orch_extended never rendered.
"""

from tests.test_helpers.assertions import render_panel_to_text

from dashboard.panels.health import panel_data_freshness_expanded

HLTH = {"sources": [{"tbl": "price_daily", "st": "ok", "age": 0.1}]}

ORCH_EXTENDED = {
    "run_history": [],
    "phase_health": {},
    "failure_patterns": [
        {"reason": "phase_6_exit_execution halted: concentration check failed", "occurrences": 7},
    ],
    "loader_health": [],
    "trend_summary": {},
}


def test_orch_extended_failure_patterns_render_in_freshness_expanded():
    panel = panel_data_freshness_expanded(HLTH, orch_extended=ORCH_EXTENDED)
    text = render_panel_to_text(panel)

    assert "phase_6_exit_execution halted" in text
    assert "7x" in text
