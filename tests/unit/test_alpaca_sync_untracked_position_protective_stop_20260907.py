"""Regression tests for a real-money-readiness audit finding: an orphaned broker position
(found at Alpaca, no matching algo_trades/algo_positions row) previously got a critical
alert but ZERO stop-loss protection - the code's own prior comment said "no stop-loss, no
exit management, no risk-limit accounting will ever apply to it... a real orphaned position
could sit silently for days."

Fix: AlpacaSyncManager._attach_protective_stop_if_missing submits a standalone (non-bracket)
protective sell-stop directly at the broker for any untracked position that doesn't already
have one live. It deliberately does NOT enroll the position in algo_positions/algo_trades
(migration 1118 keeps algo_untracked_positions separate "to avoid circuit breaker conflicts"
- an untracked position may be a deliberate manual/external holding the operator does not
want the algo's signal-driven exit logic touching) - only downside protection is attached.
"""

from unittest.mock import MagicMock, patch

from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager


def _make_manager(config_overrides=None):
    manager = object.__new__(AlpacaSyncManager)
    config = {
        "untracked_position_auto_protective_stop_enabled": True,
        "imported_position_default_stop_loss_pct": 5.0,
    }
    if config_overrides:
        config.update(config_overrides)
    manager.config = MagicMock()
    manager.config.get = lambda key, default=None: config.get(key, default)
    manager._alpaca_key = "key"
    manager._alpaca_secret = "secret"
    manager._alpaca_base_url = "https://paper-api.alpaca.markets"
    return manager


class TestProtectiveStopAttachedForNewUntrackedPosition:
    def test_new_untracked_position_gets_a_protective_stop_submitted(self):
        manager = _make_manager()
        cur = MagicMock()
        cur.fetchone.return_value = None  # no existing row -> INSERT branch, no existing stop
        cur.rowcount = 1

        mock_order_mgr = MagicMock()
        mock_order_mgr.submit_standalone_protective_stop.return_value = {
            "success": True,
            "order_id": "order-123",
            "message": "submitted",
        }

        with (
            patch("algo.reporting.notifications.notify"),
            patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        ):
            manager._sync_untracked_positions(
                cur,
                orphan_symbols=["AAPL"],
                alpaca_positions=[{"symbol": "AAPL", "qty": "10", "current_price": "200.00"}],
            )

        assert mock_order_mgr.submit_standalone_protective_stop.called, (
            "an orphaned broker position with no existing protective stop must have one "
            "submitted - this is the literal 'no stop-loss will ever apply to it' gap the "
            "audit found."
        )
        _, kwargs = mock_order_mgr.submit_standalone_protective_stop.call_args
        assert kwargs["symbol"] == "AAPL"
        assert kwargs["qty"] == 10.0
        # imported_position_default_stop_loss_pct=5.0 -> 200 * 0.95 = 190.0
        assert abs(kwargs["stop_price"] - 190.0) < 0.01

        # Successful submission must persist the order id so future cycles don't resubmit.
        update_calls = [c for c in cur.execute.call_args_list if "protective_stop_order_id" in str(c)]
        assert update_calls, "successful stop submission must be persisted to algo_untracked_positions"

    def test_already_live_protective_stop_is_not_resubmitted(self):
        manager = _make_manager()
        cur = MagicMock()
        cur.fetchone.return_value = (1, "order-existing")  # existing row WITH a stop order id
        cur.rowcount = 1

        mock_order_mgr = MagicMock()
        mock_order_mgr.is_order_still_live.return_value = True

        with patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr):
            manager._sync_untracked_positions(
                cur,
                orphan_symbols=["AAPL"],
                alpaca_positions=[{"symbol": "AAPL", "qty": "10", "current_price": "200.00"}],
            )

        mock_order_mgr.is_order_still_live.assert_called_once_with("order-existing")
        mock_order_mgr.submit_standalone_protective_stop.assert_not_called()

    def test_no_longer_live_protective_stop_is_resubmitted(self):
        """A previously-submitted stop that was cancelled/filled must not leave the
        position silently unprotected forever - a fresh one must be attempted."""
        manager = _make_manager()
        cur = MagicMock()
        cur.fetchone.return_value = (1, "order-stale")
        cur.rowcount = 1

        mock_order_mgr = MagicMock()
        mock_order_mgr.is_order_still_live.return_value = False
        mock_order_mgr.submit_standalone_protective_stop.return_value = {
            "success": True,
            "order_id": "order-new",
            "message": "submitted",
        }

        with patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr):
            manager._sync_untracked_positions(
                cur,
                orphan_symbols=["AAPL"],
                alpaca_positions=[{"symbol": "AAPL", "qty": "10", "current_price": "200.00"}],
            )

        assert mock_order_mgr.submit_standalone_protective_stop.called

    def test_disabled_via_config_does_not_submit(self):
        manager = _make_manager({"untracked_position_auto_protective_stop_enabled": False})
        cur = MagicMock()
        cur.fetchone.return_value = None
        cur.rowcount = 1

        mock_order_mgr = MagicMock()

        with (
            patch("algo.reporting.notifications.notify"),
            patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        ):
            manager._sync_untracked_positions(
                cur,
                orphan_symbols=["AAPL"],
                alpaca_positions=[{"symbol": "AAPL", "qty": "10", "current_price": "200.00"}],
            )

        mock_order_mgr.submit_standalone_protective_stop.assert_not_called()

    def test_submission_failure_does_not_raise_or_abort_sync(self):
        """A protective-stop submission failure must not blow up the whole reconciliation
        cycle - it's best-effort, backstopped by the existing critical alert."""
        manager = _make_manager()
        cur = MagicMock()
        cur.fetchone.return_value = None
        cur.rowcount = 1

        mock_order_mgr = MagicMock()
        mock_order_mgr.submit_standalone_protective_stop.side_effect = RuntimeError("broker down")

        with (
            patch("algo.reporting.notifications.notify"),
            patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        ):
            # Must not raise.
            untracked_count, _ = manager._sync_untracked_positions(
                cur,
                orphan_symbols=["AAPL"],
                alpaca_positions=[{"symbol": "AAPL", "qty": "10", "current_price": "200.00"}],
            )

        assert untracked_count == 1, "the DB sync itself must still succeed even if stop submission fails"

    def test_does_not_enroll_position_into_algo_positions_or_algo_trades(self):
        """The whole point of keeping algo_untracked_positions separate (migration 1118) is
        that this position must NEVER be written to algo_positions/algo_trades by this path -
        only a protective stop is attached, not full algo-managed exit enrollment."""
        manager = _make_manager()
        cur = MagicMock()
        cur.fetchone.return_value = None
        cur.rowcount = 1

        mock_order_mgr = MagicMock()
        mock_order_mgr.submit_standalone_protective_stop.return_value = {
            "success": True,
            "order_id": "order-123",
            "message": "submitted",
        }

        with (
            patch("algo.reporting.notifications.notify"),
            patch("algo.trading.order_manager.OrderManager", return_value=mock_order_mgr),
        ):
            manager._sync_untracked_positions(
                cur,
                orphan_symbols=["AAPL"],
                alpaca_positions=[{"symbol": "AAPL", "qty": "10", "current_price": "200.00"}],
            )

        for c in cur.execute.call_args_list:
            sql = str(c)
            assert "INSERT INTO algo_positions" not in sql
            assert "INSERT INTO algo_trades" not in sql
