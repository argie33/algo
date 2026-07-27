"""Regression: unavailable P&L%/R-multiple must render dim, not bright_red.

dashboard/panels/positions.py colored a position's P&L% and R-Mult columns bright_red
whenever the value was simply unavailable (unrealized_pnl_pct/r_multiple is None) - the
exact same color as a genuinely losing position. The displayed text ("--") does say
"no data", but coloring it identically to a real loss misleads a quick visual scan of
the table (a trader scanning for red rows to spot losers would flag unknown-P&L rows
too). Fixed to use DIM for the unknown case, reserving bright_red for real losses.
"""

from rich.table import Table
from rich.text import Text

from dashboard.panels.positions import panel_positions


def _base_position(**overrides: object) -> dict:
    row = {
        "symbol": "AAPL",
        "avg_entry_price": 140.0,
        "current_price": 150.0,
        "position_value": 1500.0,
    }
    row.update(overrides)
    return row


def _pnl_cell_style(pos_payload: dict) -> str | None:
    panel = panel_positions(pos_payload)
    table = panel.renderable
    assert isinstance(table, Table)
    # Columns: Symbol, Name, Val, Entry, Price, P&L% (index 5)
    pnl_cell = table.columns[5]._cells[0]
    assert isinstance(pnl_cell, Text)
    return pnl_cell.style


def test_unknown_pnl_renders_dim_not_red():
    payload = {"items": [_base_position(unrealized_pnl_pct=None)]}
    assert _pnl_cell_style(payload) == "dim"


def test_real_loss_still_renders_red():
    payload = {"items": [_base_position(unrealized_pnl_pct=-5.0)]}
    assert _pnl_cell_style(payload) == "bright_red"


def test_real_gain_still_renders_green():
    payload = {"items": [_base_position(unrealized_pnl_pct=5.0)]}
    assert _pnl_cell_style(payload) == "bright_green"
