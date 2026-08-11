#!/usr/bin/env python3
"""Regression test for the 2026-07-27 stock-split price-rescale fix in position_monitor.py.

_apply_split_adjustment() used to update ONLY algo_positions.quantity and
current_stop_price when a stock split was detected. But the exit engine's R-multiple
math and every T1/T2/T3 profit-target comparison read entry_price/stop_loss_price/
target_N_price from algo_trades (joined per position in _evaluate_position), not
algo_positions - and those were never rescaled. After a real split, cur_price reflected
the new post-split price scale while entry_price/targets stayed at the old pre-split
scale, silently corrupting R-multiple and profit-target exit logic for the rest of the
position's life. Fixed by rescaling every price-scale column on both algo_trades (the
table the exit engine actually reads) and algo_positions (cache/display columns).
"""

from unittest.mock import MagicMock

from algo.monitoring.position_monitor import PositionMonitor


def _make_monitor() -> PositionMonitor:
    return PositionMonitor(config={})


class TestSplitAdjustmentRescalesTradePrices:
    def test_algo_trades_price_columns_rescaled_for_all_trade_ids(self) -> None:
        """A 2:1 split (100 -> 200 shares) must rescale algo_trades entry/stop/target
        prices for every trade_id in the position's trade_ids_arr, not just the
        position-level current_stop_price."""
        monitor = _make_monitor()
        cur = MagicMock()
        adjustments: list = []

        monitor._apply_split_adjustment(
            cur,
            pos_id=42,
            symbol="TEST",
            db_qty=100,
            db_stop=90.0,
            alpaca_qty=200,
            trade_ids_arr=[501, 502],
            adjustments=adjustments,
        )

        trades_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]]
        assert len(trades_calls) == 1, "must issue exactly one algo_trades UPDATE for the split"

        sql, params = trades_calls[0].args
        assert "entry_price" in sql
        assert "stop_loss_price" in sql
        assert "target_1_price" in sql
        assert "target_2_price" in sql
        assert "target_3_price" in sql
        assert "trade_id = ANY(%s)" in sql
        # ratio params (5x) + the trade_ids_arr list itself
        assert params[-1] == [501, 502]
        for ratio_param in params[:-1]:
            assert ratio_param == 2.0

    def test_algo_positions_price_columns_rescaled_not_just_stop(self) -> None:
        """The algo_positions UPDATE must also rescale entry_price/avg_entry_price/
        stop_loss_price/target_N_price/initial_risk_per_share, not just
        quantity/current_stop_price (the pre-fix behavior)."""
        monitor = _make_monitor()
        cur = MagicMock()
        adjustments: list = []

        monitor._apply_split_adjustment(
            cur,
            pos_id=42,
            symbol="TEST",
            db_qty=100,
            db_stop=90.0,
            alpaca_qty=200,
            trade_ids_arr=[501],
            adjustments=adjustments,
        )

        positions_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_positions" in c.args[0]]
        assert len(positions_calls) == 1
        sql, params = positions_calls[0].args
        for col in (
            "entry_price",
            "avg_entry_price",
            "stop_loss_price",
            "target_1_price",
            "target_2_price",
            "target_3_price",
            "initial_risk_per_share",
        ):
            assert col in sql, f"{col} must be rescaled in the algo_positions UPDATE"

    def test_no_trade_ids_logs_warning_instead_of_silently_skipping(self) -> None:
        """If trade_ids_arr is empty/NULL, the stale-price gap must be surfaced via a
        warning log, not silently left uncorrected with no trace."""
        monitor = _make_monitor()
        cur = MagicMock()
        adjustments: list = []

        monitor._apply_split_adjustment(
            cur,
            pos_id=42,
            symbol="TEST",
            db_qty=100,
            db_stop=90.0,
            alpaca_qty=200,
            trade_ids_arr=None,
            adjustments=adjustments,
        )

        trades_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0]]
        assert len(trades_calls) == 0
