"""Regression: dashboard/panels/portfolio.py's expanded performance panel labeled
perf["pnl"] "Total P&L:" while the compact panel (panel_performance_spark) correctly labels
the identical field "Realized P&L:" (see dashboard/fetchers_portfolio.py: perf["pnl"] comes
from total_pnl_dollars, computed alongside win/loss/profit-factor from CLOSED trades only).

"Total P&L:" sat directly above a separate "Unrealized P&L:" row, falsely implying the two
summed to a real portfolio total. They don't - the mislabeled row IS the realized figure,
duplicated under a different name. Fixed 2026-08-23 (goal session) to match the compact
panel's correct label.
"""

from dashboard.panels.portfolio import panel_portfolio_perf_expanded


def _render_text(panel: object) -> str:
    from io import StringIO

    from rich.console import Console

    buf = StringIO()
    Console(file=buf, width=200, force_terminal=False, no_color=True).print(panel)
    return buf.getvalue()


def test_expanded_panel_labels_pnl_realized_not_total():
    port = {"total_portfolio_value": 100000.0, "total_cash": 50000.0, "position_count": 1}
    perf = {"pnl": 250.0, "n": 10, "w": 5, "l": 2, "unrealized_pnl": -50.0}
    pos = {"items": []}
    panel = panel_portfolio_perf_expanded(port, {}, None, perf, {}, pos)
    text = _render_text(panel)
    assert "Realized P&L" in text
    assert "Total P&L" not in text
    assert "Unrealized P&L" in text
