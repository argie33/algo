#!/usr/bin/env python3
"""Regression test for the 2026-07-27 fix: reconciliation.audit_stale_estimated_prices()
mislabeled a naive DB timestamp (algo_trades.exit_time, written via SQL CURRENT_TIMESTAMP into
a `timestamp without time zone` column, so it's in the DB session's local wall-clock timezone -
confirmed live this session's actual `SHOW timezone` is America/Chicago, not UTC) as UTC via
`.replace(tzinfo=timezone.utc)`. That inflated the computed age by the session-timezone-to-UTC
offset (5+ hours), which alone exceeds the 2h stale_threshold - every unreconciled estimated
exit price would falsely alert as stale regardless of true age.

Same bug class already fixed in algo/risk/market_exposure.py's cache-age check,
algo/trading/pretrade_checks.py's re-entry cooldown (tests/unit/test_pretrade_checks_timezone.py),
and algo/monitoring/position_monitor.py's stale-order check
(tests/unit/test_position_monitor_stale_order_timezone.py).
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from algo.infrastructure.reconciliation import DailyReconciliation


class TestAuditStaleEstimatedPricesUsesRealSessionTimezone:
    def _run(self, exit_time_naive, session_tz_name="America/Chicago"):
        manager = object.__new__(DailyReconciliation)
        manager.config = {"execution_mode": "auto"}  # live mode - audit does not early-return

        mock_cur = MagicMock()
        mock_cur.execute.return_value = None
        mock_cur.fetchall.return_value = [("T1", "AAPL", 150.25, exit_time_naive)]
        mock_cur.fetchone.side_effect = [[session_tz_name]]  # SHOW timezone

        return manager.audit_stale_estimated_prices(mock_cur)

    def test_exit_reconciled_one_minute_ago_is_not_flagged_stale(self):
        """The core bug: an exit priced 1 real minute ago (naive Chicago wall-clock) must not
        be flagged stale against a 2-hour threshold - pre-fix, mislabeling it as UTC inflated
        the computed age by 5+ hours, which alone exceeds the threshold regardless of true age."""
        exit_time_naive = datetime.now(ZoneInfo("America/Chicago")).replace(tzinfo=None) - timedelta(minutes=1)

        result = self._run(exit_time_naive)

        assert result["status"] == "OK", f"a 1-minute-old estimated exit must not alert as stale, got {result}"
        assert result["stale_trade_count"] == 0

    def test_exit_genuinely_stale_past_threshold_still_flagged(self):
        """Sanity check: the fix must not silently disable the audit - an exit genuinely older
        than the 2-hour threshold must still be flagged."""
        exit_time_naive = datetime.now(ZoneInfo("America/Chicago")).replace(tzinfo=None) - timedelta(hours=3)

        result = self._run(exit_time_naive)

        assert result["status"] in ("ALERT", "CRITICAL")
        assert result["stale_trade_count"] == 1
