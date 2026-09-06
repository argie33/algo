"""Regression test: check_corporate_actions() must fetch and thread the position's real
trade_ids_arr through _handle_qty_variance() to _apply_split_adjustment(), not a hardcoded
None.

BUG FOUND 2026-09-05 (real-money-readiness audit, stops/exits review): check_corporate_actions()'s
own SELECT never fetched trade_ids_arr, and unconditionally passed None down to
_handle_qty_variance(), which itself unconditionally passed None down again to
_apply_split_adjustment(). _apply_split_adjustment() has always correctly rescaled
algo_trades.entry_price/stop_loss_price/target_N_price WHEN given a real trade_ids_arr (see
test_position_split_price_rescale.py) - but every real call path always supplied None, so a
real stock split NEVER rescaled algo_trades, only algo_positions, silently corrupting
R-multiple and profit-target exit logic for the rest of the position's life exactly as
described in _apply_split_adjustment's own docstring/warning, which nothing upstream ever
supplied real data to avoid triggering.
"""

from unittest.mock import MagicMock, patch

from algo.monitoring.position_monitor import PositionMonitor


class TestCheckCorporateActionsThreadsTradeIdsArr:
    def test_split_detected_rescales_algo_trades_with_real_trade_ids(self):
        monitor = PositionMonitor(config={"api_request_timeout_seconds": 10})
        cur = MagicMock()
        # One open position, 100 shares at Alpaca now (a real 2:1 split from a DB-recorded 50).
        cur.fetchall.return_value = [(1, "TEST", 50, 45.00, 50.00, ["TRD-1", "TRD-2"])]

        with (
            patch("algo.monitoring.position_monitor.DatabaseContext") as MockCtx,
            patch.object(monitor, "_get_alpaca_creds", return_value=("https://api", "key", "secret")),
            patch.object(monitor, "_fetch_alpaca_qty", return_value=100),
        ):
            MockCtx.return_value.__enter__.return_value = cur
            monitor.check_corporate_actions()

        # Find the UPDATE algo_trades call and confirm it targeted the real trade ids, not
        # an empty/skipped rescale.
        trades_update_calls = [call for call in cur.execute.call_args_list if "UPDATE algo_trades" in call.args[0]]
        assert len(trades_update_calls) == 1, (
            "expected exactly one algo_trades rescale UPDATE - trade_ids_arr must have been "
            "threaded through as a real, non-empty list for the split-adjustment branch to "
            "take the rescale path instead of the 'trade_ids_arr is empty/NULL' warning path"
        )
        rescale_params = trades_update_calls[0].args[1]
        assert rescale_params[-1] == ["TRD-1", "TRD-2"]
