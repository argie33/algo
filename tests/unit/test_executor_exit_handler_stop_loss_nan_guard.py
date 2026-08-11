#!/usr/bin/env python3
"""Regression test: ExitHandler._execute_exit()'s NaN/Infinity price guards checked
final_exit_price and entry_price, but not stop_loss_price - despite this exact block's own
comment claiming it was "the last gate before Decimal(str(entry_price)) -
Decimal(str(stop_loss_price))". A NaN stop_loss_price (e.g. legacy pre-validation bad data)
reached the Decimal subtraction unguarded: Decimal arithmetic silently propagates NaN
(unlike ordering comparisons, which raise), so risk_per_share became a NaN Decimal, and the
very next `if risk_per_share <= 0:` then raised a raw decimal.InvalidOperation instead of
this function's own clean, diagnostic ValueError pattern used for every other invalid price.
"""

from unittest.mock import MagicMock

import pytest

from algo.trading.executor_exit_handler import ExitHandler


def _make_handler(execution_mode="paper"):
    context = MagicMock()
    context.execution_mode = execution_mode
    handler = ExitHandler(context)
    handler._check_trade_not_already_closed = MagicMock(return_value=None)
    handler._fetch_and_lock_trade_data = MagicMock(return_value=())
    return handler, context


def _patch_trade_data(handler, entry_price, stop_loss_price, current_qty=10.0):
    handler._validate_and_convert_trade_data = MagicMock(
        return_value=(
            "TESTSYM",  # symbol
            entry_price,  # entry_price
            10.0,  # entry_qty
            stop_loss_price,  # stop_loss_price
            None,  # alpaca_order_id
            1,  # position_id
            current_qty,  # current_qty
            0,  # target_hits
            "open",  # position_status
        )
    )


class TestStopLossNanGuard:
    def test_nan_stop_loss_price_raises_clean_value_error_not_invalid_operation(self):
        handler, _context = _make_handler()
        _patch_trade_data(handler, entry_price=100.0, stop_loss_price=float("nan"))

        with pytest.raises(ValueError, match="INVALID_STOP_LOSS_PRICE"):
            handler._execute_exit(
                cur=MagicMock(),
                trade_id=1,
                exit_price=110.0,
                exit_reason="test",
                exit_fraction=1.0,
                exit_stage=None,
                new_stop_price=None,
            )

    def test_infinite_stop_loss_price_raises_clean_value_error(self):
        handler, _context = _make_handler()
        _patch_trade_data(handler, entry_price=100.0, stop_loss_price=float("inf"))

        with pytest.raises(ValueError, match="INVALID_STOP_LOSS_PRICE"):
            handler._execute_exit(
                cur=MagicMock(),
                trade_id=1,
                exit_price=110.0,
                exit_reason="test",
                exit_fraction=1.0,
                exit_stage=None,
                new_stop_price=None,
            )

    def test_zero_stop_loss_price_raises_clean_value_error(self):
        handler, _context = _make_handler()
        _patch_trade_data(handler, entry_price=100.0, stop_loss_price=0.0)

        with pytest.raises(ValueError, match="INVALID_STOP_LOSS_PRICE"):
            handler._execute_exit(
                cur=MagicMock(),
                trade_id=1,
                exit_price=110.0,
                exit_reason="test",
                exit_fraction=1.0,
                exit_stage=None,
                new_stop_price=None,
            )
