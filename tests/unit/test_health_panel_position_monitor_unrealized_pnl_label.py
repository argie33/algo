"""Regression: dashboard/panels/health.py's Phase 3 (Position Monitor) detail rows labeled
a field sourced from `total_unrealized_pnl` as "Total P&L:" in two separate rendering spots
(_build_phase_execution_panel and _build_results_panel). Phase 3 only monitors OPEN
positions - there are no closed/realized trades in this phase's data at all - so "Total P&L"
falsely implied it was a combined realized+unrealized figure. Fixed 2026-08-23 (goal session)
to "Unrealized P&L:" in both spots.
"""

from io import StringIO

from rich.console import Console

from dashboard.panels.health import _build_phase_execution_panel


def _render_text(renderable: object) -> str:
    buf = StringIO()
    Console(file=buf, width=200, force_terminal=False, no_color=True).print(renderable)
    return buf.getvalue()


def test_phase_execution_panel_labels_position_monitor_pnl_unrealized_not_total():
    execution_health = {"phase_3_position_monitor": {"total_unrealized_pnl": -123.0, "open_positions": 4}}
    panel = _build_phase_execution_panel(execution_health, run=None, hlth_items=None)
    assert panel is not None
    text = _render_text(panel)
    assert "Unrealized P&L" in text
    assert "Total P&L" not in text
