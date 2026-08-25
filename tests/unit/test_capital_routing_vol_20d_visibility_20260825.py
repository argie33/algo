"""Regression: gld_vol_20d/ief_vol_20d/dbc_vol_20d (the annualized 20-day realized vol that
actually determines each leg's inverse-vol sizing weight - see algo/risk/capital_routing.py's
module docstring, "SIZING: inverse-volatility... weighting") were computed and persisted to
capital_routing_daily, and already flowed through the API (lambda/api/routes/algo_handlers/
market.py) and the TUI/web fetchers unfiltered, but were never actually rendered on either
dashboard - an operator could see GLD at 60% and DBC at 15% with no way to see why (GLD's
lower realized vol). Same "computed but invisible" bug class as
vol_managed_multiplier_dashboard_invisibility_gap_fixed_20260824 and
exposure_policy_tier_dashboard_gap_fixed_20260824.

Fixed 2026-08-25 (money-% goal session) on both dashboard.panels.exposure.panel_capital_routing
(TUI) and webapp/frontend/src/pages/MarketsHealth.jsx's CapitalRoutingCard (web - JS side not
directly testable from this Python suite, verified via eslint + manual review instead).
"""

from rich.console import Console

from dashboard.panels.exposure import panel_capital_routing


def _render(panel) -> str:
    console = Console(width=140, record=True)
    console.print(panel)
    return console.export_text()


def _valid_cr(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "data_unavailable": False,
        "uninvested_capital_pct": 35.0,
        "gld_trend_up": True,
        "gld_vol_20d": 0.148,
        "gld_weight": 0.6,
        "ief_trend_up": False,
        "ief_vol_20d": 0.082,
        "ief_weight": 0.0,
        "dbc_trend_up": True,
        "dbc_vol_20d": 0.213,
        "dbc_weight": 0.4,
        "cash_weight": 0.0,
        "move_index": 95.0,
        "move_veto": False,
        "timestamp": None,
    }
    row.update(overrides)
    return row


def test_vol_20d_shown_for_each_leg() -> None:
    text = _render(panel_capital_routing(_valid_cr()))
    assert "14.8%" in text  # GLD vol
    assert "8.2%" in text  # IEF vol
    assert "21.3%" in text  # DBC vol


def test_missing_vol_20d_renders_dashes_not_crash() -> None:
    cr = _valid_cr(gld_vol_20d=None, ief_vol_20d=None, dbc_vol_20d=None)
    text = _render(panel_capital_routing(cr))
    assert text is not None
