"""Regression test for a real-money-readiness gap in
AlpacaSyncManager._attach_protective_stop_if_missing: unlike its sibling call site
(phase9_reconciliation.py's _verify_open_position_stop_loss_protection_step, fixed
2026-09-07), this untracked-position protective-stop path had no explicit execution_mode
guard - it relied entirely on self.alpaca_base_url already having been resolved to the paper
endpoint for non-"auto" modes by AlpacaSyncManager.__init__'s implicit URL-resolution
coupling. A future refactor of that shared resolution logic could silently start submitting
real protective-stop orders here with nothing catching it.

Fixed: this method now aborts explicitly, before ever constructing an OrderManager or hitting
the broker, if execution_mode != "auto" and the resolved base_url doesn't look like paper.
"""

from unittest.mock import MagicMock, patch

from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager


def _make_manager(execution_mode, base_url):
    manager = object.__new__(AlpacaSyncManager)
    config = {
        "untracked_position_auto_protective_stop_enabled": True,
        "imported_position_default_stop_loss_pct": 5.0,
        "execution_mode": execution_mode,
    }
    manager.config = MagicMock()
    manager.config.get = lambda key, default=None: config.get(key, default)
    manager._alpaca_key = "key"
    manager._alpaca_secret = "secret"
    manager._alpaca_base_url = base_url
    return manager


class TestAttachProtectiveStopExecutionModeGuard:
    def test_non_auto_mode_with_live_looking_base_url_aborts_without_submitting(self):
        manager = _make_manager(execution_mode="review", base_url="https://api.alpaca.markets")
        cur = MagicMock()
        mock_order_mgr = MagicMock()

        with patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr):
            manager._attach_protective_stop_if_missing(
                cur, "AAPL", qty=10.0, current_price=200.0, existing_stop_order_id=None
            )

        mock_order_mgr.submit_standalone_protective_stop.assert_not_called()

    def test_non_auto_mode_with_paper_base_url_still_submits(self):
        manager = _make_manager(execution_mode="paper", base_url="https://paper-api.alpaca.markets")
        cur = MagicMock()
        mock_order_mgr = MagicMock()
        mock_order_mgr.submit_standalone_protective_stop.return_value = {
            "success": True,
            "order_id": "order-123",
            "message": "submitted",
        }

        with patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr):
            manager._attach_protective_stop_if_missing(
                cur, "AAPL", qty=10.0, current_price=200.0, existing_stop_order_id=None
            )

        mock_order_mgr.submit_standalone_protective_stop.assert_called_once()

    def test_auto_mode_submits_regardless_of_base_url_shape(self):
        manager = _make_manager(execution_mode="auto", base_url="https://api.alpaca.markets")
        cur = MagicMock()
        mock_order_mgr = MagicMock()
        mock_order_mgr.submit_standalone_protective_stop.return_value = {
            "success": True,
            "order_id": "order-123",
            "message": "submitted",
        }

        with patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr):
            manager._attach_protective_stop_if_missing(
                cur, "AAPL", qty=10.0, current_price=200.0, existing_stop_order_id=None
            )

        mock_order_mgr.submit_standalone_protective_stop.assert_called_once()
