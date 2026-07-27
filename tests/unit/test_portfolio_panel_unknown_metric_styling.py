"""Regression: unavailable performance ratios (P&L, profit factor, expectancy, Sharpe,
Sortino, Calmar, win rate) must render dim, not bright_red/bright_green, matching the
fix applied to dashboard/panels/positions.py.

dashboard/panels/portfolio.py had several duplicate copies of the same style-selection
expression across its compact and expanded panel functions - some copies already
correctly used DIM for the "value unavailable" case, others (fixed here) fell through to
bright_red (or, for expectancy in one spot, bright_green - the most misleading direction:
actively signaling "good" for an unknown value).
"""

from rich.table import Table

from dashboard.panels.portfolio import panel_performance_spark, panel_portfolio_perf_expanded


def _find_tables(obj: object) -> list[Table]:
    out: list[Table] = []
    if isinstance(obj, Table):
        out.append(obj)
    if hasattr(obj, "renderables"):
        for r in obj.renderables:
            out.extend(_find_tables(r))
    return out


def _cell_text(cell: object) -> str:
    if isinstance(cell, str):
        return cell
    return getattr(cell, "plain", "")


def _style_by_label(panel: object, label: str) -> str | None:
    """Find a Table.grid row whose label cell matches `label` and return the adjacent
    value cell's style, searching all (label_col, val_col) pairs in every table."""
    group = panel.renderable if hasattr(panel, "renderable") else panel
    for table in _find_tables(group):
        cols = table.columns
        for label_ci in range(0, len(cols), 2):
            val_ci = label_ci + 1
            if val_ci >= len(cols):
                continue
            for ri, cell in enumerate(cols[label_ci]._cells):
                if _cell_text(cell) == label:
                    val_cell = cols[val_ci]._cells[ri]
                    if isinstance(val_cell, str):
                        continue
                    return val_cell.style
    return None


def _style_in_cell_containing(panel: object, needle: str, substr: str) -> str | None:
    """dashboard/panels/portfolio.py's cell() helper bakes "Label: value" into one Text
    cell (unlike the separate label/value columns used elsewhere), so find that cell by
    a substring of its content, then resolve the style span covering `substr`."""
    group = panel.renderable if hasattr(panel, "renderable") else panel
    for table in _find_tables(group):
        for col in table.columns:
            for cell in col._cells:
                text = _cell_text(cell)
                if needle in text and substr in text and not isinstance(cell, str):
                    idx = text.index(substr)
                    for span in cell.spans:
                        if span.start <= idx < span.end:
                            return span.style
    return None


def test_realized_pnl_unavailable_renders_dim_not_red():
    perf = {"pnl": None, "n": 10, "w": 5, "l": 2}
    panel = panel_performance_spark(perf, {"items": []})
    assert _style_in_cell_containing(panel, "Realized P&L:", "--") == "dim"


def test_realized_pnl_real_loss_still_renders_red():
    perf = {"pnl": -500.0, "n": 10, "w": 5, "l": 2}
    panel = panel_performance_spark(perf, {"items": []})
    assert _style_in_cell_containing(panel, "Realized P&L:", "-$500.00") == "bright_red"


def _expanded_panel(perf_anl: dict) -> object:
    port = {"total_portfolio_value": 100000.0, "total_cash": 50000.0, "position_count": 0}
    perf = {"pnl": 100.0, "n": 10, "w": 5, "l": 2}
    pos = {"items": []}
    return panel_portfolio_perf_expanded(port, {}, None, perf, perf_anl, pos)


def test_rolling_analytics_unavailable_ratios_render_dim_not_red():
    perf_anl = {"sharpe252": None, "sortino": None, "calmar": None, "wr50": None}
    panel = _expanded_panel(perf_anl)
    assert _style_by_label(panel, "Sharpe (252d):") == "dim"
    assert _style_by_label(panel, "Sortino:") == "dim"
    assert _style_by_label(panel, "Calmar:") == "dim"
    assert _style_by_label(panel, "Win Rate (50T):") == "dim"


def test_rolling_analytics_real_values_still_colored():
    perf_anl = {"sharpe252": 1.5, "sortino": 2.0, "calmar": 0.8, "wr50": 60.0}
    panel = _expanded_panel(perf_anl)
    assert _style_by_label(panel, "Sharpe (252d):") == "bright_green"
    assert _style_by_label(panel, "Sortino:") == "bright_green"
    assert _style_by_label(panel, "Calmar:") == "bright_green"
    assert _style_by_label(panel, "Win Rate (50T):") == "bright_green"
