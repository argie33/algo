#!/usr/bin/env python3
"""Regression test: TradeExecutor._compute_exit_limit_price() gates marketable-limit exits
on urgency (exit_stage) and fails open to a plain market order (None) whenever the inputs
aren't trustworthy enough to price a limit order safely.

exit_stage="stop" is the hard capital-preservation stop-loss - it must always return None
(pure market order, certainty of exit) regardless of exit_price/config. Every other exit
reason should get a limit price a small buffer below exit_price, unless exit_price or the
exit_limit_slippage_buffer_bps config is missing/invalid, in which case this must fail open
to None rather than raise - a missing tuning value must not block the exit itself.
"""

import math
from unittest.mock import MagicMock

from algo.trading.executor import TradeExecutor


def _executor_with_config(config):
    executor = object.__new__(TradeExecutor)
    executor.config = config
    return executor


class TestComputeExitLimitPrice:
    def test_hard_stop_always_returns_none(self):
        executor = _executor_with_config({"exit_limit_slippage_buffer_bps": 50.0})
        assert executor._compute_exit_limit_price(100.0, "stop") is None

    def test_non_urgent_exit_computes_buffered_limit_price(self):
        executor = _executor_with_config({"exit_limit_slippage_buffer_bps": 50.0})
        limit_price = executor._compute_exit_limit_price(100.0, "T1")
        # 50 bps = 0.5% below exit_price
        assert limit_price == 99.5

    def test_different_exit_stages_all_get_a_limit_price(self):
        executor = _executor_with_config({"exit_limit_slippage_buffer_bps": 50.0})
        for stage in ["T1", "T2", "T3", "time", "exposure_force_exit", "exposure_partial", "early_exit", None]:
            assert executor._compute_exit_limit_price(100.0, stage) is not None

    def test_missing_exit_price_falls_back_to_none(self):
        executor = _executor_with_config({"exit_limit_slippage_buffer_bps": 50.0})
        assert executor._compute_exit_limit_price(None, "T1") is None

    def test_nan_exit_price_falls_back_to_none(self):
        executor = _executor_with_config({"exit_limit_slippage_buffer_bps": 50.0})
        assert executor._compute_exit_limit_price(math.nan, "T1") is None

    def test_non_positive_exit_price_falls_back_to_none(self):
        executor = _executor_with_config({"exit_limit_slippage_buffer_bps": 50.0})
        assert executor._compute_exit_limit_price(0.0, "T1") is None
        assert executor._compute_exit_limit_price(-5.0, "T1") is None

    def test_missing_buffer_config_fails_open_to_none(self):
        """Missing config must not crash the exit - just skip the limit-order optimization."""
        executor = _executor_with_config({})
        assert executor._compute_exit_limit_price(100.0, "T1") is None

    def test_invalid_buffer_config_fails_open_to_none(self):
        executor = _executor_with_config({"exit_limit_slippage_buffer_bps": -10.0})
        assert executor._compute_exit_limit_price(100.0, "T1") is None
        executor2 = _executor_with_config({"exit_limit_slippage_buffer_bps": math.nan})
        assert executor2._compute_exit_limit_price(100.0, "T1") is None


class TestSendAlpacaExitWiresLimitPriceThrough:
    """_send_alpaca_exit must forward the computed limit_price to order_manager.send_market_exit -
    this is what actually connects exit_engine.py's exit_price/exit_stage to the broker order."""

    def _executor(self, config):
        executor = object.__new__(TradeExecutor)
        executor.config = config
        executor.order_manager = MagicMock()
        executor.order_manager.send_market_exit.return_value = {
            "success": True,
            "order_id": "x",
            "filled_price": 1.0,
        }
        executor.execution_mode = "auto"
        cur = MagicMock()
        cur.fetchone.return_value = None
        executor._with_cursor = MagicMock(side_effect=lambda fn, acquire_locks=False: fn(cur))
        return executor

    def test_non_urgent_exit_passes_computed_limit_price(self):
        executor = self._executor({"exit_limit_slippage_buffer_bps": 50.0})

        executor._send_alpaca_exit("TEST", 10, trade_id=42, exit_price=100.0, exit_stage="T1")

        call = executor.order_manager.send_market_exit.call_args
        assert call.kwargs["limit_price"] == 99.5

    def test_hard_stop_passes_none_limit_price(self):
        executor = self._executor({"exit_limit_slippage_buffer_bps": 50.0})

        executor._send_alpaca_exit("TEST", 10, trade_id=42, exit_price=95.0, exit_stage="stop")

        call = executor.order_manager.send_market_exit.call_args
        assert call.kwargs["limit_price"] is None

    def test_omitted_exit_price_and_stage_preserves_original_market_behavior(self):
        """Callers that don't pass exit_price/exit_stage (none should exist post-wiring, but
        this locks in backward compatibility) must still get a plain market order."""
        executor = self._executor({"exit_limit_slippage_buffer_bps": 50.0})

        executor._send_alpaca_exit("TEST", 10, trade_id=42)

        call = executor.order_manager.send_market_exit.call_args
        assert call.kwargs["limit_price"] is None
