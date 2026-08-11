#!/usr/bin/env python3
"""Regression test for EntryHandler._record_entry_phase, found via a systematic sweep for
the NaN-comparison-guard bug class on 2026-08-10 (after fuzzing found 9 other instances
this session).

`stop_loss_price <= 0` doesn't catch a float NaN (NaN comparisons are always False in
Python). This guard runs AFTER the order has already executed/filled - a NaN here would
write stop_loss_price=NaN into algo_positions for a real, already-open position instead
of being rejected, corrupting every downstream risk calculation, position sizing check,
and exit decision for that position.

Confirmed genuinely reachable as a float: executor.py:428 explicitly does
`stop_loss_price=float(stop_loss_price)` before passing down this exact call chain
(executor.py -> executor_entry_handler.py's execute_entry -> _record_entry_phase).

BUG FOUND 2026-08-11 (via fuzzing exposure_policy.py's tier_for_exposure, then checking for
the same isinstance(..., float)-only pattern elsewhere): the guard's isinstance check only
covered float, not Decimal - but this whole file is Decimal-only by convention
(stop_loss_price is typed `Decimal` throughout _record_entry_phase/_upsert_position_record),
so a Decimal("NaN") used to fall through to `stop_loss_price <= 0` and raise a raw
decimal.InvalidOperation instead of this guard's own clean ValueError. The enclosing
`except Exception` in _upsert_position_record caught it either way (same fail-safe outcome -
no position ever inserted), so this was never a live safety gap, just a much worse
diagnostic message. Fixed to also check Decimal.is_nan()/is_infinite().
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from algo.trading.executor_entry_handler import EntryHandler


def _make_trade_context():
    ctx = MagicMock()
    ctx.signal_date = date(2026, 7, 24)
    ctx.entry_date = date(2026, 7, 24)
    ctx.sqs = 75
    ctx.signals.trend_score = 80
    ctx.signals.base_type = "flat_base"
    ctx.signals.base_quality = "A"
    ctx.signals.stage_phase = "mid"
    ctx.signals.rs_percentile = 90
    ctx.signals.advanced_components = None
    ctx.market.sector = "Technology"
    ctx.market.industry = "Software"
    ctx.market.market_exposure_at_entry = 50.0
    ctx.market.exposure_tier_at_entry = "full"
    ctx.execution.stop_method = "atr"
    ctx.execution.stop_reasoning = "atr_based"
    return ctx


def _make_handler():
    handler_context = MagicMock()
    handler_context.execution_mode = "paper"
    handler_context._get_portfolio_value.return_value = Decimal("100000")
    return EntryHandler(handler_context)


def test_nan_float_stop_loss_price_raises_before_position_insert():
    handler = _make_handler()
    cur = MagicMock()
    cur.fetchone.return_value = None

    with pytest.raises(ValueError, match="invalid stop_loss"):
        handler._record_entry_phase(
            cur=cur,
            trade_id="TRD-CHAOSFUZZ",
            symbol="CHAOSFUZZ",
            shares=Decimal("10"),
            entry_price=Decimal("100.00"),
            executed_price=Decimal("100.00"),
            stop_loss_price=float("nan"),  # the reachable type per executor.py:428
            target_1_price=Decimal("110.00"),
            target_2_price=None,
            target_3_price=None,
            order_status="paper_pending",
            alpaca_order_id="",
            context=_make_trade_context(),
            rejection_reason="Paper mode - Alpaca unavailable: connection timeout",
            idempotency_key="idem-chaos-nan",
            order_send_time=None,
        )

    # The critical assertion: no position was ever written with the bad value.
    position_insert_calls = [c for c in cur.execute.call_args_list if "INSERT INTO algo_positions" in str(c.args[0])]
    assert not position_insert_calls, "must not insert a position before validating stop_loss_price"


def test_nan_decimal_stop_loss_price_raises_clean_value_error_not_invalid_operation():
    handler = _make_handler()
    cur = MagicMock()
    cur.fetchone.return_value = None

    with pytest.raises(ValueError, match="invalid stop_loss"):
        handler._record_entry_phase(
            cur=cur,
            trade_id="TRD-CHAOSFUZZ2",
            symbol="CHAOSFUZZ2",
            shares=Decimal("10"),
            entry_price=Decimal("100.00"),
            executed_price=Decimal("100.00"),
            stop_loss_price=Decimal("NaN"),  # this file's actual Decimal-only type in practice
            target_1_price=Decimal("110.00"),
            target_2_price=None,
            target_3_price=None,
            order_status="paper_pending",
            alpaca_order_id="",
            context=_make_trade_context(),
            rejection_reason="Paper mode - Alpaca unavailable: connection timeout",
            idempotency_key="idem-chaos-nan-decimal",
            order_send_time=None,
        )

    position_insert_calls = [c for c in cur.execute.call_args_list if "INSERT INTO algo_positions" in str(c.args[0])]
    assert not position_insert_calls, "must not insert a position before validating stop_loss_price"
