"""Regression: the TRADES panel's stale-data warning could never fire.

BUG FOUND 2026-08-17: panel_completed_trades read trades.get("age_hours"), a key
fetch_completed_trades() (dashboard/fetchers_portfolio.py) never set - the API's real
freshness signal (check_data_freshness() on algo_trades.created_at, computed server-side
in lambda/api/routes/algo_handlers/dashboard.py's list_trades handler) was silently dropped
by the fetcher instead of being passed through, the same bug class the already-correct
fetch_positions()/positions.py sibling avoids. panel_trades_expanded had no staleness
handling at all. Live-confirmed the fetcher only ever set items/timestamp/trades_count/
data_available - never age_hours or data_freshness - so the compact panel's staleness
check was dead code regardless of how stale algo_trades actually was.
"""

from dashboard.fetchers_portfolio import fetch_completed_trades
from dashboard.panels.trades import _stale_warning, panel_completed_trades, panel_trades_expanded


def _closed_trade(**overrides: object) -> dict:
    row = {
        "trade_id": 1,
        "symbol": "AAPL",
        "status": "closed",
        "entry_price": 100.0,
        "exit_price": 110.0,
        "profit_loss_dollars": 100.0,
        "profit_loss_pct": 10.0,
        "exit_r_multiple": 1.5,
        "trade_duration_days": 3,
        "exit_date": "2026-08-13",
    }
    row.update(overrides)
    return row


def test_stale_warning_helper_detects_is_stale():
    trades = {"data_freshness": {"is_stale": True, "warning": "4 days old"}}
    assert "STALE" in _stale_warning(trades)


def test_stale_warning_helper_silent_when_fresh():
    trades = {"data_freshness": {"is_stale": False}}
    assert _stale_warning(trades) == ""


def test_stale_warning_helper_silent_when_missing():
    assert _stale_warning({}) == ""
    assert _stale_warning([]) == ""  # malformed input must not crash


def test_compact_panel_shows_stale_badge_with_trades():
    data = {"items": [_closed_trade()], "data_freshness": {"is_stale": True, "warning": "stale"}}
    panel = panel_completed_trades(data)
    assert panel is not None
    assert "STALE" in str(panel.title)


def test_compact_panel_no_badge_when_fresh():
    data = {"items": [_closed_trade()], "data_freshness": {"is_stale": False}}
    panel = panel_completed_trades(data)
    assert panel is not None
    assert "STALE" not in str(panel.title)


def test_compact_panel_shows_stale_badge_with_no_closed_trades():
    data = {"items": [], "data_freshness": {"is_stale": True, "warning": "stale"}}
    panel = panel_completed_trades(data)
    assert panel is not None
    assert "STALE" in str(panel.title)


def test_expanded_panel_shows_stale_badge():
    data = {"items": [_closed_trade()], "data_freshness": {"is_stale": True, "warning": "stale"}}
    panel = panel_trades_expanded(data)
    assert panel is not None
    assert "STALE" in str(panel.title)


def test_expanded_panel_no_badge_when_fresh():
    data = {"items": [_closed_trade()], "data_freshness": {"is_stale": False}}
    panel = panel_trades_expanded(data)
    assert panel is not None
    assert "STALE" not in str(panel.title)


def test_fetch_completed_trades_propagates_data_freshness(monkeypatch):
    """fetch_completed_trades() must pass through the API's data_freshness field,
    not silently drop it the way it did before this fix."""
    import dashboard.fetchers_portfolio as fp

    monkeypatch.setattr(
        fp,
        "api_call",
        lambda *a, **kw: {
            "items": [_closed_trade()],
            "data_freshness": {"is_stale": True, "warning": "4 days old"},
        },
    )
    result = fetch_completed_trades(None)
    assert result["data_freshness"] == {"is_stale": True, "warning": "4 days old"}
