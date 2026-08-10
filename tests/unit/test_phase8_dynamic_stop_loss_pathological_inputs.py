#!/usr/bin/env python3
"""Regression test for phase8_entry_execution._calculate_dynamic_stop_loss, found via
fuzzing with pathological inputs on 2026-08-10.

NaN silently passed both the `entry_price <= 0` and `atr < 0` precondition checks - NaN
comparisons are always False in Python (`float('nan') < 0` is False, `float('nan') <= 0`
is False) - then propagated through arithmetic (NaN doesn't raise) to produce
`stop_loss = nan`, violating this function's own documented postcondition ("Returns:
Calculated stop loss price (always > 0 and < entry_price)") with no error. Same bug class
already found and fixed this session in position_sizer.py
(entry_dec/stop_dec comparison) and utils/validation/financial.py
(validate_pnl_calculation).

A NaN stop_loss reaching downstream code (position sizing, order submission) would be a
real safety hazard - PositionSizer's own entry_dec/stop_dec validation (already fixed to
reject NaN via decimal.InvalidOperation, see test_position_sizer_pathological_input_types.py)
would catch it there, but this function should never produce it in the first place.
"""

import math

import pytest

from algo.orchestrator.phase8_entry_execution import _calculate_dynamic_stop_loss


class TestDynamicStopLossRejectsNanAndInfinity:
    def test_nan_atr_raises_not_silently_produces_nan_stop(self):
        with pytest.raises(ValueError, match="atr"):
            _calculate_dynamic_stop_loss(100.0, float("nan"), 98.0)

    def test_nan_sma_raises(self):
        with pytest.raises(ValueError, match="sma_50"):
            _calculate_dynamic_stop_loss(100.0, 2.0, float("nan"))

    def test_nan_entry_price_raises(self):
        with pytest.raises(ValueError, match="entry_price"):
            _calculate_dynamic_stop_loss(float("nan"), 2.0, 98.0)

    def test_infinite_entry_price_raises(self):
        with pytest.raises(ValueError, match="entry_price"):
            _calculate_dynamic_stop_loss(float("inf"), 2.0, 98.0)

    def test_infinite_atr_still_handled_safely_by_existing_risk_cap(self):
        """Infinite ATR isn't rejected outright - the existing MAX_RISK_ALLOWED cap
        already produces a safe, finite result for it. Must stay that way."""
        stop = _calculate_dynamic_stop_loss(100.0, float("inf"), 98.0)
        assert math.isfinite(stop)
        assert 0 < stop < 100.0

    def test_result_is_always_finite_and_within_bounds_for_normal_inputs(self):
        for entry, atr, sma in [
            (100.0, 2.0, 98.0),
            (100.0, 50.0, 98.0),
            (0.5, 0.05, 0.48),
            (10000.0, 300.0, 9500.0),
        ]:
            stop = _calculate_dynamic_stop_loss(entry, atr, sma)
            assert math.isfinite(stop)
            assert 0 < stop <= entry
