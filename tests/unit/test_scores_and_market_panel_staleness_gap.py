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

UPDATED 2026-08-17: the MARKET panels' staleness check itself was ALSO a variant of this same
bug class and has been fixed - it used to diff mkt.get("timestamp") against datetime.now(), but
that "timestamp" was always datetime.now(ET) at fetch time (see fetch_market() in
dashboard/fetchers_market.py), so the diff was always ~0 seconds regardless of actual data age -
the "shows stale badge when old" tests below only ever passed because they injected a fake old
`timestamp` directly, which real production data never did. Root-caused to
dashboard/api_data_layer.py's _unwrap_api_response() silently dropping the API's real
data_freshness field for any endpoint that passed it via json_response's separate kwarg (30+
call sites; the endpoints that "worked" - positions.py's fetcher - did so by coincidence, by
stuffing data_freshness inside the payload dict instead of using the kwarg). Now uses
_stale_warning() from data_freshness like scores.py/positions.py/signals.py/trades.py.
"""

from dashboard.panels.market import _stale_warning as _market_stale_warning
from dashboard.panels.market import panel_market_expanded, panel_market_full
from dashboard.panels.scores import _stale_warning, panel_scores_compact, panel_scores_expanded


def _base_mkt(**overrides: object) -> dict:
    row = {
        "vix": 18.5,
        "spy": 550.0,
        "tier": "confirmed_uptrend",
        "halts": [],
        "timestamp": None,
    }
    row.update(overrides)
    return row


def test_market_stale_warning_helper_detects_is_stale():
    mkt = {"data_freshness": {"is_stale": True, "warning": "2 days old"}}
    assert "STALE" in _market_stale_warning(mkt)


def test_market_stale_warning_helper_silent_when_fresh():
    mkt = {"data_freshness": {"is_stale": False}}
    assert _market_stale_warning(mkt) == ""


def test_market_stale_warning_helper_silent_when_missing():
    assert _market_stale_warning({}) == ""
    assert _market_stale_warning([]) == ""  # malformed input must not crash


def test_market_expanded_shows_stale_badge_when_old():
    mkt = _base_mkt(data_freshness={"is_stale": True, "warning": "stale"})
    panel = panel_market_expanded(mkt)
    assert "STALE" in str(panel.title)


def test_market_expanded_no_stale_badge_when_fresh():
    mkt = _base_mkt(data_freshness={"is_stale": False})
    panel = panel_market_expanded(mkt)
    assert "STALE" not in str(panel.title)


def test_market_full_and_expanded_agree_on_staleness():
    mkt = _base_mkt(data_freshness={"is_stale": True, "warning": "stale"})
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
