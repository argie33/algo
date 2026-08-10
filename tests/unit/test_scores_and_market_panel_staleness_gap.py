"""Regression: SCORES and MARKET-EXPANDED panels had no stale-data visual warning.

BUG FOUND 2026-08-10 (frontend/dashboard audit pass): unlike positions.py/portfolio.py and
market.py's own compact panel_market_full, panel_scores_compact/panel_scores_expanded showed
only a passive "Xh ago" age string (fmt_age does no threshold check or color-coding) and
panel_market_expanded dropped the staleness check its own compact sibling has - a trader could
be looking at genuinely stale data with zero visual indication in either case.

Also: dashboard/fetchers_signals.py's fetch_scores() stamped "timestamp" with the client's own
fetch time (datetime.now(ET)) instead of reading the API's real server-computed data_freshness
field, which was available in the response but silently dropped - the same "always looks fresh"
bug class already fixed for positions/portfolio.
"""

from datetime import datetime, timedelta, timezone

from dashboard.panels.market import panel_market_expanded, panel_market_full
from dashboard.panels.scores import _stale_warning, panel_scores_compact, panel_scores_expanded


def _base_mkt(**overrides: object) -> dict:
    row = {
        "vix": 18.5,
        "spy": 550.0,
        "tier": "confirmed_uptrend",
        "timestamp": overrides.pop("timestamp", None),
    }
    row.update(overrides)
    return row


def _stale_ts() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()


def _fresh_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_market_expanded_shows_stale_badge_when_old():
    mkt = _base_mkt(timestamp=_stale_ts())
    panel = panel_market_expanded(mkt)
    assert "STALE" in str(panel.title)


def test_market_expanded_no_stale_badge_when_fresh():
    mkt = _base_mkt(timestamp=_fresh_ts())
    panel = panel_market_expanded(mkt)
    assert "STALE" not in str(panel.title)


def test_market_full_and_expanded_agree_on_staleness():
    mkt = _base_mkt(timestamp=_stale_ts())
    full_panel = panel_market_full(mkt)
    expanded_panel = panel_market_expanded(mkt)
    assert "STALE" in str(full_panel.title)
    assert "STALE" in str(expanded_panel.title)


def test_scores_stale_warning_helper_detects_is_stale():
    scores = {"data_freshness": {"is_stale": True, "warning": "3 days old"}}
    assert "STALE" in _stale_warning(scores)


def test_scores_stale_warning_helper_silent_when_fresh():
    scores = {"data_freshness": {"is_stale": False}}
    assert _stale_warning(scores) == ""


def test_scores_stale_warning_helper_silent_when_missing():
    assert _stale_warning({}) == ""
    assert _stale_warning([]) == ""  # malformed input must not crash


def _base_score_row(**overrides: object) -> dict:
    row = {
        "symbol": "AAPL",
        "composite_score": 75.0,
        "data_completeness": 95.0,
    }
    row.update(overrides)
    return row


def test_scores_compact_panel_shows_stale_badge():
    scores = {"top": [_base_score_row()], "data_freshness": {"is_stale": True, "warning": "stale"}}
    panel = panel_scores_compact(scores)
    assert "STALE" in str(panel.title)


def test_scores_compact_panel_no_badge_when_fresh():
    scores = {"top": [_base_score_row()], "data_freshness": {"is_stale": False}}
    panel = panel_scores_compact(scores)
    assert "STALE" not in str(panel.title)


def test_scores_expanded_panel_shows_stale_badge():
    scores = {"top": [_base_score_row()], "data_freshness": {"is_stale": True, "warning": "stale"}}
    panel = panel_scores_expanded(scores)
    assert "STALE" in str(panel.title)
