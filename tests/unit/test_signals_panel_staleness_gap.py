"""Regression: the SIGNALS panel had no stale-data visual warning at all.

BUG FOUND 2026-08-17: unlike scores.py (which had this exact gap found and fixed
2026-08-10, see test_scores_and_market_panel_staleness_gap.py), panel_signals_compact/
panel_signals_expanded never rendered any staleness indicator, even though the backend
(_get_dashboard_signals in lambda/api/routes/algo_handlers/dashboard.py) has always computed
and returned "data_freshness" via check_data_freshness(cur, "algo_signals", "signal_date",
warning_days=1) - the field was simply never read by either panel. Live-confirmed 2026-08-17:
algo_signals.signal_date maxed at 2026-08-13, 4 calendar days stale, with zero warning shown.
"""

from dashboard.panels.signals import _stale_warning, panel_signals_compact, panel_signals_expanded


def _base_sig(**overrides: object) -> dict:
    row = {
        "n": 0,
        "total": 100,
        "date": "2026-08-13",
        "grades": {"a": 0, "b": 0, "c": 0, "d": 0},
        "top_a": [],
        "near": [],
        "trend": [],
        "buy_sigs": [],
        "timestamp": None,
    }
    row.update(overrides)
    return row


def test_signals_stale_warning_helper_detects_is_stale():
    sig = {"data_freshness": {"is_stale": True, "warning": "4 days old"}}
    assert "STALE" in _stale_warning(sig)


def test_signals_stale_warning_helper_silent_when_fresh():
    sig = {"data_freshness": {"is_stale": False}}
    assert _stale_warning(sig) == ""


def test_signals_stale_warning_helper_silent_when_missing():
    assert _stale_warning({}) == ""
    assert _stale_warning([]) == ""  # malformed input must not crash


def test_signals_compact_panel_shows_stale_badge():
    sig = _base_sig(data_freshness={"is_stale": True, "warning": "stale"})
    panel = panel_signals_compact(sig)
    assert panel is not None
    assert "STALE" in str(panel.title)


def test_signals_compact_panel_no_badge_when_fresh():
    sig = _base_sig(data_freshness={"is_stale": False})
    panel = panel_signals_compact(sig)
    assert panel is not None
    assert "STALE" not in str(panel.title)


def test_signals_expanded_panel_shows_stale_badge():
    sig = _base_sig(data_freshness={"is_stale": True, "warning": "stale"})
    panel = panel_signals_expanded(sig)
    assert panel is not None
    assert "STALE" in str(panel.title)


def test_signals_expanded_panel_no_badge_when_fresh():
    sig = _base_sig(data_freshness={"is_stale": False})
    panel = panel_signals_expanded(sig)
    assert panel is not None
    assert "STALE" not in str(panel.title)
