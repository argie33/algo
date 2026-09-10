"""Regression test: an unchanged share count between our DB and Alpaca does not mean "nothing
happened" for corporate-action purposes.

BUG FOUND 2026-09-09 (real-money-readiness audit, spinoff-handling gap): check_corporate_actions()
only ever detected corporate actions via a quantity mismatch. A spinoff (or special cash-in-lieu
distribution) doesn't change how many shares of THIS symbol you hold - it distributes new shares
of a different symbol - so it left zero trace anywhere in this codebase: the position kept being
monitored at its stale pre-event entry_price/stop/targets indefinitely with no alert, unless (and
only after) the resulting price gap happened to breach the stop.

Fix: when qty is unchanged, also check the current_price/lastday_price fields Alpaca already
returns in the same position lookup (no new API call or data feed) for an unexplained gap above
the same threshold exit_engine.py's `_gap_risk_note` already treats as "verify before trusting
this reflects genuine performance" - raising a critical alert for manual review, same
annotation-only philosophy (never auto-adjusts prices, since the cause can't be confirmed without
a real corporate-actions data feed).
"""

from unittest.mock import MagicMock, patch

from algo.monitoring.position_monitor import PositionMonitor


class TestCorporateActionsPriceGapAnomaly:
    def test_unchanged_qty_large_gap_raises_manual_review_alert(self):
        monitor = PositionMonitor(config={"api_request_timeout_seconds": 10})
        cur = MagicMock()
        cur.fetchall.return_value = [(1, "TEST", 100, 45.00, 50.00, ["TRD-1"])]

        alpaca_pos = {"qty": "100", "current_price": "40.00", "lastday_price": "50.00"}  # 20% gap down

        with (
            patch("algo.monitoring.position_monitor.DatabaseContext") as MockCtx,
            patch.object(monitor, "_get_alpaca_creds", return_value=("https://api", "key", "secret")),
            patch.object(monitor, "_fetch_alpaca_position", return_value=alpaca_pos),
            patch("algo.reporting.notifications.notify") as mock_notify,
        ):
            MockCtx.return_value.__enter__.return_value = cur
            adjustments = monitor.check_corporate_actions()

        assert mock_notify.called, "an unexplained large gap with unchanged qty must raise a critical alert"
        gap_adjustments = [a for a in adjustments if a["action"] == "UNEXPLAINED_PRICE_GAP|requires_manual_review"]
        assert len(gap_adjustments) == 1
        assert gap_adjustments[0]["symbol"] == "TEST"

        rescale_calls = [
            call
            for call in cur.execute.call_args_list
            if "UPDATE algo_positions" in call.args[0] and "entry_price" in call.args[0]
        ]
        assert not rescale_calls, "a price gap alone (qty unchanged) must never trigger a price rescale"

    def test_unchanged_qty_small_move_does_not_alert(self):
        monitor = PositionMonitor(config={"api_request_timeout_seconds": 10})
        cur = MagicMock()
        cur.fetchall.return_value = [(1, "TEST", 100, 45.00, 50.00, ["TRD-1"])]

        alpaca_pos = {"qty": "100", "current_price": "49.50", "lastday_price": "50.00"}  # 1% move

        with (
            patch("algo.monitoring.position_monitor.DatabaseContext") as MockCtx,
            patch.object(monitor, "_get_alpaca_creds", return_value=("https://api", "key", "secret")),
            patch.object(monitor, "_fetch_alpaca_position", return_value=alpaca_pos),
            patch("algo.reporting.notifications.notify") as mock_notify,
        ):
            MockCtx.return_value.__enter__.return_value = cur
            adjustments = monitor.check_corporate_actions()

        assert not mock_notify.called
        assert adjustments == []

    def test_missing_price_fields_does_not_crash_or_alert(self):
        monitor = PositionMonitor(config={"api_request_timeout_seconds": 10})
        cur = MagicMock()
        cur.fetchall.return_value = [(1, "TEST", 100, 45.00, 50.00, ["TRD-1"])]

        alpaca_pos = {"qty": "100"}  # older/minimal payload shape, no price fields

        with (
            patch("algo.monitoring.position_monitor.DatabaseContext") as MockCtx,
            patch.object(monitor, "_get_alpaca_creds", return_value=("https://api", "key", "secret")),
            patch.object(monitor, "_fetch_alpaca_position", return_value=alpaca_pos),
            patch("algo.reporting.notifications.notify") as mock_notify,
        ):
            MockCtx.return_value.__enter__.return_value = cur
            adjustments = monitor.check_corporate_actions()

        assert not mock_notify.called
        assert adjustments == []


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
