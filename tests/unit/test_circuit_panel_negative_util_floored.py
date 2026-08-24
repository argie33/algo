"""Regression: circuit breaker panels showed a negative utilization percentage.

BUG FOUND 2026-08-24 (real-money-readiness goal, dashboard.py panel sweep): unlike the
shared hbar() utility (dashboard/formatters.py, `max(0.0, min(cur_f / thr_f, 1.0))`), both
panel_circuit's fmt_b() and panel_circuit_expanded's per-breaker loop duplicated the
utilization calculation without a floor - a negative `current` value against a positive
`threshold` (a data glitch, not a real breaker state) produced a negative util, which
rendered as e.g. "-40%" in the compact view's percentage text, and fed a negative bar_f in
the expanded view (silently rendering an empty bar via Python's negative-multiplier
behavior). No safety impact either way - breaker firing comes from the backend's own
`triggered` bool, never from this locally recomputed percentage - a display-correctness
fix only.
"""

from rich.console import Console

from dashboard.panels.circuit import panel_circuit, panel_circuit_expanded


def _render(panel) -> str:
    console = Console(width=120, record=True)
    console.print(panel)
    return console.export_text()


def _cb(breakers):
    return {"triggered_count": 0, "any_triggered": False, "breakers": breakers}


class TestNegativeUtilFloored:
    def test_compact_view_floors_negative_util_at_zero_percent(self):
        cb = _cb(
            [
                {
                    "label": "Test Breaker",
                    "triggered": False,
                    "current": -5.0,
                    "threshold": 10.0,
                    "unit": "%",
                }
            ]
        )
        rendered = _render(panel_circuit(cb))
        # cur_fmt legitimately shows the raw current value ("-5") - it's the *utilization*
        # percentage (rendered after the bar, e.g. " 0%") that must be floored, not negative
        # ("-40%" would be the pre-fix bug for -5/10).
        assert "-40%" not in rendered
        assert "0%" in rendered

    def test_expanded_view_floors_negative_util_at_zero_percent(self):
        cb = _cb(
            [
                {
                    "label": "Test Breaker",
                    "triggered": False,
                    "current": -5.0,
                    "threshold": 10.0,
                    "unit": "%",
                }
            ]
        )
        rendered = _render(panel_circuit_expanded(cb))
        assert "-40%" not in rendered
        assert "0%" in rendered

    def test_normal_positive_utilization_unaffected(self):
        cb = _cb(
            [
                {
                    "label": "Test Breaker",
                    "triggered": False,
                    "current": 7.5,
                    "threshold": 10.0,
                    "unit": "%",
                }
            ]
        )
        rendered = _render(panel_circuit(cb))
        assert "75%" in rendered
