"""Regression: an Alpaca open (resting/unfilled) order with no matching algo_trades row must
be detected as a crash-orphan, not silently invisible forever.

REAL-MONEY-READINESS FINDING (2026-09-10, order-execution re-audit): executor.py's
_with_cursor wraps the broker POST /v2/orders call and the algo_trades INSERT in a single DB
transaction - if the process dies after Alpaca accepts the order but before that transaction
commits, the INSERT rolls back entirely. sync_alpaca_positions only catches this once the
order FILLS into a real position (orphan_symbols cross-check). A still-resting order at the
moment of the crash was invisible to every existing reconciliation check.

Fixed by AlpacaSyncManager.find_orphaned_open_orders: cross-checks each open order's
client_order_id (== the idempotency_key we insert into algo_trades) against algo_trades,
excluding anything submitted within the last ORPHANED_ORDER_GRACE_MINUTES (a genuinely
in-flight transaction, not a crash).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager


def _make_manager():
    manager = object.__new__(AlpacaSyncManager)
    manager.config = {"execution_mode": "auto", "api_request_timeout_seconds": 10}
    manager._alpaca_key = "key"
    manager._alpaca_secret = "secret"
    manager._alpaca_base_url = "https://paper-api.alpaca.markets"
    return manager


def _mock_response(payload):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


def _order(client_order_id, symbol="ORPHAN", minutes_ago=20):
    submitted_at = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")
    return {
        "id": f"alpaca-{client_order_id}",
        "client_order_id": client_order_id,
        "symbol": symbol,
        "qty": "10",
        "side": "buy",
        "submitted_at": submitted_at,
    }


class TestOrphanedOpenOrders:
    def test_order_with_no_matching_trade_row_past_grace_window_is_orphaned(self):
        manager = _make_manager()
        manager._session = MagicMock()
        manager._session.get.return_value = _mock_response([_order("no-such-key", minutes_ago=30)])

        cur = MagicMock()
        cur.fetchall.return_value = []  # nothing in algo_trades matches

        orphans = manager.find_orphaned_open_orders(cur)

        assert len(orphans) == 1
        assert orphans[0]["client_order_id"] == "no-such-key"

    def test_order_with_matching_trade_row_is_not_orphaned(self):
        manager = _make_manager()
        manager._session = MagicMock()
        manager._session.get.return_value = _mock_response([_order("known-key", minutes_ago=30)])

        cur = MagicMock()
        cur.fetchall.return_value = [("known-key",)]  # algo_trades has this idempotency_key

        orphans = manager.find_orphaned_open_orders(cur)

        assert orphans == []

    def test_order_within_grace_window_is_not_flagged_as_orphaned(self):
        """A resting order submitted seconds ago with no algo_trades row yet is very likely a
        transaction still in flight, not a crash - must not false-positive."""
        manager = _make_manager()
        manager._session = MagicMock()
        manager._session.get.return_value = _mock_response([_order("fresh-key", minutes_ago=1)])

        cur = MagicMock()
        cur.fetchall.return_value = []

        orphans = manager.find_orphaned_open_orders(cur)

        assert orphans == []

    def test_no_open_orders_returns_empty(self):
        manager = _make_manager()
        manager._session = MagicMock()
        manager._session.get.return_value = _mock_response([])

        cur = MagicMock()

        orphans = manager.find_orphaned_open_orders(cur)

        assert orphans == []
        cur.execute.assert_not_called()

    def test_missing_credentials_raises_instead_of_silently_reporting_no_orphans(self):
        manager = _make_manager()
        manager._alpaca_key = ""
        manager._alpaca_secret = ""
        manager._session = MagicMock()

        # A missing-credentials misconfiguration must fail fast, not silently read
        # as "verified clean" for a real-money reconciliation safety check.
        with pytest.raises(RuntimeError, match="no Alpaca credentials"):
            manager.find_orphaned_open_orders(MagicMock())

        manager._session.get.assert_not_called()
