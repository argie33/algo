"""Regression: unavailable P&L/R-multiple in the trades panels must render dim, not
bright_red, matching the fix applied to dashboard/panels/positions.py.

Both panel_completed_trades (compact) and panel_trades_expanded computed `pc` (the style
applied to the P&L/R-multiple cells) as bright_red whenever the underlying value was
None - visually indistinguishable from a genuine loss for a closed trade whose P&L
wasn't available (e.g. not yet reconciled).
"""

from rich.table import Table
from rich.text import Text

from dashboard.panels.trades import panel_completed_trades, panel_trades_expanded


def _closed_trade(**overrides: object) -> dict:
    row = {
        "symbol": "AAPL",
        "status": "closed",
        "entry_price": 140.0,
        "exit_price": 150.0,
        "exit_date": "2026-07-20",
        "trade_date": "2026-07-15",
    }
    row.update(overrides)
    return row


def _pnl_pct_cell_style_compact(trades_payload: dict) -> str | None:
    panel = panel_completed_trades(trades_payload)
    table = panel.renderable
    assert isinstance(table, Table)
    # Columns: Sym, Exit, Entry$, Exit$, P&L% (index 4)
    cell = table.columns[4]._cells[0]
    assert isinstance(cell, Text)
    return cell.style


def test_compact_unknown_pnl_renders_dim_not_red():
    payload = {"items": [_closed_trade(profit_loss_dollars=None, profit_loss_pct=None)]}
    assert _pnl_pct_cell_style_compact(payload) == "dim"


def test_compact_real_loss_still_renders_red():
    payload = {"items": [_closed_trade(profit_loss_dollars=-50.0, profit_loss_pct=-3.0)]}
    assert _pnl_pct_cell_style_compact(payload) == "bright_red"


def test_compact_real_gain_still_renders_green():
    payload = {"items": [_closed_trade(profit_loss_dollars=50.0, profit_loss_pct=3.0)]}
    assert _pnl_pct_cell_style_compact(payload) == "bright_green"


def _pnl_pct_cell_style_expanded(trades_payload: dict) -> str | None:
    result = panel_trades_expanded(trades_payload)
    group = result.renderable
    table = next(item for item in group.renderables if isinstance(item, Table))
    # Columns: Sym, Entry Date, Exit Date, Entry$, Exit$, P&L$, P&L%, R, Days, Grade, ExitRsn, MFE, ...
    cell = table.columns[6]._cells[0]
    assert isinstance(cell, Text)
    return cell.style


def test_expanded_unknown_pnl_renders_dim_not_red():
    payload = {"items": [_closed_trade(profit_loss_dollars=None, profit_loss_pct=None)]}
    assert _pnl_pct_cell_style_expanded(payload) == "dim"
