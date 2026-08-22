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
    def test_nan_atr_raises_not_silently_produces_nan_stop(self) -> None:
        with pytest.raises(ValueError, match="atr"):
            _calculate_dynamic_stop_loss(100.0, float("nan"), 98.0)

    def test_nan_sma_raises(self) -> None:
        with pytest.raises(ValueError, match="sma_50"):
            _calculate_dynamic_stop_loss(100.0, 2.0, float("nan"))

    def test_nan_entry_price_raises(self) -> None:
        with pytest.raises(ValueError, match="entry_price"):
            _calculate_dynamic_stop_loss(float("nan"), 2.0, 98.0)

    def test_infinite_entry_price_raises(self) -> None:
        with pytest.raises(ValueError, match="entry_price"):
            _calculate_dynamic_stop_loss(float("inf"), 2.0, 98.0)

    def test_infinite_atr_still_handled_safely_by_existing_risk_cap(self) -> None:
        """Infinite ATR isn't rejected outright - the existing MAX_RISK_ALLOWED cap
        already produces a safe, finite result for it. Must stay that way."""
        stop = _calculate_dynamic_stop_loss(100.0, float("inf"), 98.0)
        assert math.isfinite(stop)
        assert 0 < stop < 100.0

    def test_result_is_always_finite_and_within_bounds_for_normal_inputs(self) -> None:
        for entry, atr, sma in [
            (100.0, 2.0, 98.0),
            (100.0, 50.0, 98.0),
            (0.5, 0.05, 0.48),
            (10000.0, 300.0, 9500.0),
        ]:
            stop = _calculate_dynamic_stop_loss(entry, atr, sma)
            assert math.isfinite(stop)
            assert 0 < stop <= entry


class TestDynamicStopLossPicksTighterOfVolatilityAndSupport:
    """Regression test for the 2026-08-21 fix: this function's docstring says to "use
    support-level stop (SMA_50 - ATR) ... if it's tighter than volatility stop", but the
    code took min(volatility_stop, support_stop) - which mathematically always selects
    whichever candidate is FARTHER from entry_price (more risk), the opposite of the
    documented intent, in every regime, not just the common one.

    Since every Phase 7 candidate is already required to have close > sma_50 (a real
    uptrend), support_stop (sma_50 - atr) is typically well below entry_price and was
    winning the old min() almost every time - live-verified this produced ~13% risk/share
    for a typical normal-volatility trade instead of the intended ~3.6%. Position sizing
    is risk-per-share-aware (position_sizer.py's risk_dollars / risk_per_share), so this
    was never a blown dollar-risk-cap bug - it was systematically wider-than-intended
    stops (and correspondingly undersized positions) on ordinary trades.
    """

    def test_typical_uptrend_uses_tight_volatility_stop_not_wide_support_stop(self) -> None:
        """entry=100, atr=3 (normal vol tier, 1.2x multiplier), sma_50=90 (typical real
        uptrend, well below entry): volatility_stop=96.4 (3.6% risk) is far tighter than
        support_stop=87 (13% risk) - the function must pick the tighter one."""
        stop = _calculate_dynamic_stop_loss(entry_price=100.0, atr=3.0, sma_50=90.0)
        assert stop == pytest.approx(96.4), (
            f"Expected the tighter volatility_stop (96.4), got {stop} - a wide support_stop "
            "was chosen instead of the tighter volatility_stop, contradicting this "
            "function's own documented 'use support only if tighter' intent."
        )

    def test_near_breakout_uses_tighter_support_stop_when_it_genuinely_is_tighter(self) -> None:
        """entry=100, atr=2, sma_50=99.8 (price just barely crossed above its 50-day SMA):
        support_stop=97.8 is genuinely tighter than volatility_stop=97.6 here - the
        function must pick the tighter support_stop in this regime too. (Live-confirmed
        the old min()-based code returned 97.6 - the wider one - even in this exact case,
        proving it picked wrong in both regimes, not just the common one.)"""
        stop = _calculate_dynamic_stop_loss(entry_price=100.0, atr=2.0, sma_50=99.8)
        assert stop == pytest.approx(97.8), (
            f"Expected the tighter support_stop (97.8), got {stop} - the wider volatility_stop was chosen instead."
        )
