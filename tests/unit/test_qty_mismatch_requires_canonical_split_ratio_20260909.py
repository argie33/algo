"""Regression test: a >20% qty mismatch between our DB and Alpaca must only be treated as a
stock split (and rescale entry/stop/target prices) when the observed ratio actually matches a
canonical split ratio - not on any large mismatch.

BUG FOUND 2026-09-09 (real-money-readiness audit): _handle_qty_variance() previously treated
ANY qty mismatch >20% as "likely a stock split" with zero corroboration against a real split
ratio. A mistaken manual broker-side share adjustment, a reconciliation bug, or a partial-fill
accounting error producing e.g. a 30% qty divergence (ratio 0.7, not a canonical split ratio)
would get "corrected" by dividing the real stop-loss/entry/target prices by 0.7 - actively
corrupting risk-protection prices on a real position instead of just failing to fix them.
"""

from unittest.mock import MagicMock, patch

from algo.monitoring.position_monitor import PositionMonitor


class TestQtyMismatchRequiresCanonicalSplitRatio:
    def test_non_split_ratio_mismatch_does_not_rescale_prices(self):
        monitor = PositionMonitor(config={"api_request_timeout_seconds": 10})
        cur = MagicMock()
        # DB shows 100 shares; Alpaca shows 70 (30% reduction) - a real qty divergence, but
        # 0.7 does not match any canonical split ratio (2, 3, 4, 5, 10, 1/2, 1/3, ...).
        cur.fetchall.return_value = [(1, "TEST", 100, 45.00, 50.00, ["TRD-1"])]

        with (
            patch("algo.monitoring.position_monitor.DatabaseContext") as MockCtx,
            patch.object(monitor, "_get_alpaca_creds", return_value=("https://api", "key", "secret")),
            patch.object(monitor, "_fetch_alpaca_qty", return_value=70),
            patch("algo.reporting.notifications.notify") as mock_notify,
        ):
            MockCtx.return_value.__enter__.return_value = cur
            monitor.check_corporate_actions()

        rescale_calls = [
            call
            for call in cur.execute.call_args_list
            if "UPDATE algo_positions" in call.args[0] and "entry_price" in call.args[0]
        ]
        assert not rescale_calls, (
            "a non-canonical-ratio qty mismatch must NOT rescale entry/stop/target prices - "
            "doing so on a non-split cause corrupts real risk-protection prices"
        )
        assert mock_notify.called, "an unexplained qty mismatch must still raise a critical alert"

    def test_canonical_2for1_split_ratio_still_rescales_prices(self):
        monitor = PositionMonitor(config={"api_request_timeout_seconds": 10})
        cur = MagicMock()
        # DB shows 50 shares; Alpaca shows 100 (exact 2:1 split ratio).
        cur.fetchall.return_value = [(1, "TEST", 50, 45.00, 50.00, ["TRD-1"])]

        with (
            patch("algo.monitoring.position_monitor.DatabaseContext") as MockCtx,
            patch.object(monitor, "_get_alpaca_creds", return_value=("https://api", "key", "secret")),
            patch.object(monitor, "_fetch_alpaca_qty", return_value=100),
        ):
            MockCtx.return_value.__enter__.return_value = cur
            monitor.check_corporate_actions()

        rescale_calls = [
            call
            for call in cur.execute.call_args_list
            if "UPDATE algo_positions" in call.args[0] and "entry_price" in call.args[0]
        ]
        assert len(rescale_calls) == 1, "a genuine 2:1 split ratio must still trigger the price rescale"
