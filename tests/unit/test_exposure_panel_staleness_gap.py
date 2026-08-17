"""Regression: the EXPOSURE panel had no stale-data visual warning at all.

BUG FOUND 2026-08-17: unlike MARKET/POSITIONS/TRADES/SIGNALS/SCORES, panel_exposure_compact/
panel_exposure_expanded never checked staleness - only a passive "Xh ago" age string (fmt_age
does no threshold check). Same root cause as the MARKET panel gap: fetch_exp_factors()
(dashboard/fetchers_market.py) never propagated data_freshness from the shared
/api/algo/markets response, and stamped "timestamp" with the client's own fetch time instead
of a real data date. The 12-factor exposure breakdown feeds position-sizing gating.
"""

from dashboard.panels.exposure import _stale_warning, panel_exposure_compact, panel_exposure_expanded


def _base_exp_f(**overrides: object) -> dict:
    row = {
        "raw_score": 62.0,
        "exposure_pct": 55.0,
        "regime": "confirmed_uptrend",
        "factors": {},
        "timestamp": None,
    }
    row.update(overrides)
    return row


def test_stale_warning_helper_detects_is_stale():
    exp_f = {"data_freshness": {"is_stale": True, "warning": "2 days old"}}
    assert "STALE" in _stale_warning(exp_f)


def test_stale_warning_helper_silent_when_fresh():
    exp_f = {"data_freshness": {"is_stale": False}}
    assert _stale_warning(exp_f) == ""


def test_stale_warning_helper_silent_when_missing():
    assert _stale_warning({}) == ""
    assert _stale_warning([]) == ""  # malformed input must not crash


def test_compact_panel_shows_stale_badge():
    exp_f = _base_exp_f(data_freshness={"is_stale": True, "warning": "stale"})
    result = panel_exposure_compact(exp_f)
    assert result is not None
    assert "STALE" in str(result.title)


def test_compact_panel_no_badge_when_fresh():
    exp_f = _base_exp_f(data_freshness={"is_stale": False})
    result = panel_exposure_compact(exp_f)
    assert result is not None
    assert "STALE" not in str(result.title)


def test_expanded_panel_shows_stale_badge():
    exp_f = _base_exp_f(data_freshness={"is_stale": True, "warning": "stale"})
    panel = panel_exposure_expanded(exp_f)
    assert "STALE" in str(panel.title)


def test_expanded_panel_no_badge_when_fresh():
    exp_f = _base_exp_f(data_freshness={"is_stale": False})
    panel = panel_exposure_expanded(exp_f)
    assert "STALE" not in str(panel.title)
