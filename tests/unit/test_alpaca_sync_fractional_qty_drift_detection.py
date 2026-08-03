"""Regression: _sync_alpaca_positions_impl's quantity-drift check compared
int(prior_qty) != int(qty_float), truncating both to integers before comparing. This
system actively trades fractional shares (order_manager.py), so a genuine sub-1-share
drift (e.g. DB=10.9, Alpaca=10.1 - a real correction from a partial fill or manual
adjustment) truncated to int(10.9)=10 == int(10.1)=10 and was silently treated as "no
drift" - no warning logged, no notify() alert, even though the DB quantity was still
correctly overwritten to match the broker. The exact condition this check exists to
catch (sub-1-share drift) was the one case it couldn't detect.
"""

from unittest.mock import MagicMock, patch

from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager


def _make_manager():
    manager = object.__new__(AlpacaSyncManager)
    manager.config = {"execution_mode": "auto", "api_request_timeout_seconds": 10}
    manager._alpaca_key = "key"
    manager._alpaca_secret = "secret"
    manager._alpaca_base_url = "https://paper-api.alpaca.markets"
    manager.fetch_alpaca_account = MagicMock()
    return manager


def _mock_positions_response(positions):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = positions
    return resp


def test_sub_one_share_drift_is_detected_not_truncated_away():
    """DB has 10.9 shares, Alpaca reports 10.1 - int() truncation would hide this."""
    manager = _make_manager()
    manager._session = MagicMock()
    manager._session.get.return_value = _mock_positions_response(
        [{"symbol": "AAPL", "qty": "10.1", "avg_entry_price": "150.00", "current_price": "155.00"}]
    )

    cur = MagicMock()
    cur.fetchone.return_value = (10.9,)  # prior DB quantity
    cur.rowcount = 1

    with patch("algo.reporting.notify") as mock_notify:
        manager._sync_alpaca_positions_impl(cur)

    mock_notify.assert_called_once()
    call_str = str(mock_notify.call_args)
    assert "AAPL" in call_str
    assert "10.9" in call_str


def test_matching_fractional_quantity_does_not_falsely_alert():
    manager = _make_manager()
    manager._session = MagicMock()
    manager._session.get.return_value = _mock_positions_response(
        [{"symbol": "AAPL", "qty": "10.9", "avg_entry_price": "150.00", "current_price": "155.00"}]
    )

    cur = MagicMock()
    cur.fetchone.return_value = (10.9,)
    cur.rowcount = 1

    with patch("algo.reporting.notify") as mock_notify:
        manager._sync_alpaca_positions_impl(cur)

    mock_notify.assert_not_called()
