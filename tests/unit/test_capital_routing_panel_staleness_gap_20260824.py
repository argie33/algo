"""Regression: the CAPITAL ROUTING panel never checked server-computed staleness.

BUG FOUND 2026-08-24 (same bug class as test_exposure_panel_staleness_gap.py's 2026-08-17
finding, applied here for the first time): unlike panel_exposure_compact/panel_exposure_expanded,
panel_capital_routing never called _stale_warning() despite fetch_capital_routing() (dashboard/
fetchers_market.py) already carrying data_freshness through in its result dict. The panel only
showed fmt_age(cr["timestamp"]) - the dashboard's own fetch time, not the real
capital_routing_daily.date - so the age display always read ~fresh regardless of true data
staleness. Fixed by adding the same _stale_warning() badge the sibling exposure panels use.
"""

from dashboard.panels.exposure import _stale_warning, panel_capital_routing


def _base_cr(**overrides: object) -> dict:
    row = {
        "gld_trend_up": True,
        "gld_weight": 0.5,
        "ief_trend_up": False,
        "ief_weight": 0.0,
        "dbc_trend_up": False,
        "dbc_weight": 0.0,
        "cash_weight": 0.5,
        "uninvested_capital_pct": 50.0,
        "move_index": 90.0,
        "move_veto": False,
        "timestamp": None,
    }
    row.update(overrides)
    return row


def test_panel_shows_stale_badge_when_data_freshness_stale():
    cr = _base_cr(data_freshness={"is_stale": True, "warning": "2 days old"})
    panel = panel_capital_routing(cr)
    assert "STALE" in str(panel.title)


def test_panel_no_badge_when_data_freshness_fresh():
    cr = _base_cr(data_freshness={"is_stale": False})
    panel = panel_capital_routing(cr)
    assert "STALE" not in str(panel.title)


def test_panel_no_badge_when_data_freshness_missing():
    cr = _base_cr()
    panel = panel_capital_routing(cr)
    assert "STALE" not in str(panel.title)


def test_stale_warning_helper_reused_directly():
    assert "STALE" in _stale_warning({"data_freshness": {"is_stale": True, "warning": "stale"}})
    assert _stale_warning({"data_freshness": {"is_stale": False}}) == ""
