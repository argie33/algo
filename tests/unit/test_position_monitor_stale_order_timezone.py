#!/usr/bin/env python3
"""Regression test for the 2026-07-27 position_monitor.py stale-order timezone fix.

algo_trades.created_at is written via SQL CURRENT_TIMESTAMP into a `timestamp without time
zone` column, so a naive value is in the DB session's local wall-clock timezone (utils/
bulk_insert_manager.py's documented convention), not UTC - confirmed live this session's
`SHOW timezone` is America/Chicago, 5+ hours off UTC. check_stale_orders() mislabeled this
naive value as UTC via `.replace(tzinfo=timezone.utc)`, silently inflating age_minutes by the
session-timezone-to-UTC offset - a pending order submitted minutes ago would compute as hours
old, immediately tripping auto_cancel_threshold and cancelling a legitimate, still-processing
live order. Same bug class already fixed in algo/risk/market_exposure.py's cache-age check
and algo/trading/pretrade_checks.py's re-entry cooldown (see
tests/unit/test_pretrade_checks_timezone.py).
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from algo.monitoring.position_monitor import PositionMonitor


def _config():
    return {
        "stale_order_alert_minutes": 15,
        "stale_order_auto_cancel_minutes": 120,
    }


def _mock_db(created_at_naive, session_tz_name="America/Chicago"):
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [
        ("trade-1", "AAPL", 150.0, 10, created_at_naive),
    ]
    mock_cur.fetchone.return_value = (session_tz_name,)  # SHOW timezone

    mock_db_context = MagicMock()
    mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
    mock_db_context.__exit__ = MagicMock(return_value=False)
    return mock_db_context


def _mock_market_event_handler():
    mock_instance = MagicMock()
    mock_instance.check_single_stock_halt.return_value = {"halted": False}
    return MagicMock(return_value=mock_instance)


class TestStaleOrderAgeUsesRealSessionTimezone:
    def test_order_created_one_minute_ago_in_chicago_time_is_not_auto_cancelled(self):
        """The core bug: an order created 1 real minute ago (naive Chicago wall-clock, this
        session's actual DB timezone) must NOT be treated as stale enough to auto-cancel -
        pre-fix, mislabeling it as UTC inflated the computed age by ~5 hours (Chicago's UTC
        offset), pushing it past the 120-minute auto-cancel threshold and cancelling a live,
        still-processing order."""
        created_at_naive = datetime.now(ZoneInfo("America/Chicago")).replace(tzinfo=None) - timedelta(minutes=1)

        monitor = PositionMonitor(config=_config())

        with (
            patch(
                "algo.monitoring.position_monitor.DatabaseContext",
                return_value=_mock_db(created_at_naive),
            ),
            patch("algo.infrastructure.MarketEventHandler", _mock_market_event_handler()),
        ):
            result = monitor.check_stale_orders()

        assert result["status"] == "STALE_ORDERS_FOUND", (
            f"an order created 1 minute ago must not be auto-cancelled, got {result}"
        )
        assert result["count"] == 1

    def test_order_actually_stale_past_auto_cancel_threshold_is_still_cancelled(self):
        """Sanity check: the fix must not make staleness impossible to detect - an order truly
        old (past the auto-cancel threshold in real elapsed time) must still be auto-cancelled."""
        created_at_naive = datetime.now(ZoneInfo("America/Chicago")).replace(tzinfo=None) - timedelta(hours=3)

        monitor = PositionMonitor(config=_config())

        with (
            patch(
                "algo.monitoring.position_monitor.DatabaseContext",
                return_value=_mock_db(created_at_naive),
            ),
            patch("algo.infrastructure.MarketEventHandler", _mock_market_event_handler()),
            patch.object(monitor, "_cancel_on_alpaca") as mock_cancel,
        ):
            result = monitor.check_stale_orders()

        mock_cancel.assert_called_once_with("trade-1")
        assert result["status"] == "AUTO_CANCELLED"
        assert result["count"] == 1
