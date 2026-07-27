"""Regression: unavailable avg P&L for a sector's holdings must render dim, not
bright_red, matching the fix applied to dashboard/panels/positions.py and trades.py.

Both panel_sector_compact and panel_sectors_expanded colored a sector's holdings bar
and "N/A"/"avg P&L n/a" text bright_red whenever every position in that sector lacked
unrealized_pnl_pct - visually indistinguishable from a real losing sector.
"""

from rich.table import Table

from dashboard.panels.sectors import panel_sector_compact, panel_sectors_expanded


def _position(sector: str, pnl_pct: float | None, value: float = 1000.0) -> dict:
    row = {
        "symbol": "XYZ",
        "sector": sector,
        "position_value": value,
        "avg_entry_price": 10.0,
        "current_price": 10.0,
    }
    if pnl_pct is not None:
        row["unrealized_pnl_pct"] = pnl_pct
    return row


def _style_at(text, substr: str) -> str | None:
    idx = text.plain.index(substr)
    for span in text.spans:
        if span.start <= idx < span.end:
            return span.style
    return None


def test_compact_unknown_avg_pnl_renders_dim_not_red():
    pos = {"items": [_position("Technology", None)]}
    port = {"total_portfolio_value": 10000.0}
    panel = panel_sector_compact({"items": []}, pos, port)
    table = next(i for i in panel.renderable.renderables if isinstance(i, Table))
    cell = table.columns[0]._cells[0]
    assert _style_at(cell, "N/A") == "dim"


def test_compact_real_loss_still_renders_red():
    pos = {"items": [_position("Technology", -5.0)]}
    port = {"total_portfolio_value": 10000.0}
    panel = panel_sector_compact({"items": []}, pos, port)
    table = next(i for i in panel.renderable.renderables if isinstance(i, Table))
    cell = table.columns[0]._cells[0]
    assert _style_at(cell, "-5.0%") == "bright_red"


def test_expanded_unknown_avg_pnl_renders_dim_not_red():
    pos = {"items": [_position("Technology", None)]}
    port = {"total_portfolio_value": 10000.0}
    panel = panel_sectors_expanded({"items": []}, pos, port)
    group = panel.renderable if hasattr(panel, "renderable") else panel
    texts = [r for r in group.renderables if hasattr(r, "plain") and "avg P&L n/a" in r.plain]
    assert texts, "expected an 'avg P&L n/a' row"
    assert _style_at(texts[0], "avg P&L n/a") == "dim"
