"""Regression: three more instances of the same bug class already fixed in
positions.py/portfolio.py/sectors.py/trades.py (see test_trades_panel_unknown_pnl_styling.py) -
a color ternary defaulted to a definite-looking color (bright_red or bright_green) whenever
its underlying value was None/incomparable, painting "no data" the same as a genuine reading:

- dashboard/panels/market.py (panel_market_expanded): SPY daily change, when spy_chg is
  None - previously rendered "--" in red.
- dashboard/panels/trades.py (panel_trades_expanded): win-rate summary line, when there are
  no decisive (win or loss) trades to compute a rate from - previously rendered "N/A" in red.
- dashboard/panels/economic.py (_build_calendar_rows): an economic indicator's actual value
  with no forecast to compare against - previously rendered green unconditionally (there's
  nothing to "beat" without a forecast baseline).
"""

from rich.console import Group
from rich.table import Table
from rich.text import Text

from dashboard.panels.economic import _build_calendar_rows
from dashboard.panels.market import panel_market_expanded
from dashboard.panels.trades import panel_trades_expanded
from dashboard.utilities import DIM, G, R


def _style_after_anchor(panel: object, line_anchor: str, value_needle: str) -> str | None:
    """Walk the panel's renderable tree (including Table.grid cells) for the Text node
    whose plain text contains `line_anchor`, then return the style covering
    `value_needle`'s position within that same node (avoids matching an unrelated
    occurrence of a generic placeholder like "--" elsewhere on the panel)."""
    stack = [panel.renderable]  # type: ignore[attr-defined]
    while stack:
        node = stack.pop()
        if isinstance(node, Text):
            if line_anchor in node.plain:
                idx = node.plain.find(value_needle, node.plain.find(line_anchor))
                if idx != -1:
                    for span in node.spans:
                        if span.start <= idx < span.end:
                            return str(span.style)
        elif isinstance(node, Table):
            for column in node.columns:
                stack.extend(column._cells)
        renderables = getattr(node, "renderables", None)
        if renderables:
            stack.extend(renderables)
        elif isinstance(node, Group):
            stack.extend(node.renderables)
    return None


def test_market_expanded_missing_spy_change_not_red():
    mkt = {
        "tier": "core",
        "pct": 50.0,
        "vix": 15.0,
        "spy": 500.0,
        "spy_chg": None,
        "dist": None,
        "stage": None,
        "halts": [],
    }
    panel = panel_market_expanded(mkt)
    style = _style_after_anchor(panel, "SPY Change:", "--")
    assert style is not None
    assert style != R
    assert style == DIM


def test_trades_expanded_no_decisive_trades_win_rate_not_red():
    trades = {
        "items": [
            {
                "symbol": "AAPL",
                "status": "closed",
                "entry_price": 140.0,
                "exit_price": 140.0,
                "profit_loss_pct": None,
                "profit_loss_dollars": None,
            }
        ]
    }
    panel = panel_trades_expanded(trades)
    style = _style_after_anchor(panel, "Win Rate:", "N/A")
    assert style is not None
    assert style != R
    assert style == DIM


def test_economic_calendar_actual_without_forecast_not_green():
    econ_cal = {
        "items": [
            {
                "event_name": "GDP Growth Rate",
                "event_date": "2026-07-27",
                "importance": "HIGH",
                "actual": 3.2,
                "forecast": None,
                "previous": 2.8,
            }
        ]
    }
    rows = _build_calendar_rows(econ_cal)
    text_rows = [r for r in rows if isinstance(r, Text)]
    row = next(r for r in text_rows if "A=" in r.plain)
    idx = row.plain.find("A=")
    style = None
    for span in row.spans:
        if span.start <= idx < span.end:
            style = str(span.style)
    assert style is not None
    assert style != G
    assert style == DIM
