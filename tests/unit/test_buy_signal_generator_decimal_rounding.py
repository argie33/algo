#!/usr/bin/env python3
"""Regression test for a 2026-08-10 fix in algo/signals/buy_signal_generator.py::
_generate_signal().

buylevel/stoplevel (BUY branch) and buylevel (SELL branch) used bare Python round() on a
float - the classic binary-representation trap (round(2.675, 2) == 2.67, not 2.68, because
2.675 isn't exactly representable in binary float). This file's own SELL-branch `stoplevel`
was already fixed for exactly this reason (explicitly citing "already fixed 2026-07-21 in
order_manager.py, exposure_policy.py, and position_monitor.py"), but the fix was never applied
to the BUY branch's buylevel/stoplevel - the values that actually feed real trades, since
SELL signals aren't consumed by real entry execution (phase7_signal_generation.py filters
`signal = 'BUY'` only) - nor to the SELL branch's own buylevel.

buylevel/stoplevel become _calculate_entry_exit_levels()'s Decimal(str(buylevel)) input, so
any float-rounding drift here is baked in permanently downstream.
"""

from decimal import ROUND_HALF_UP, Decimal

from algo.signals.buy_signal_generator import BuySignalGenerator


def _decimal_round(value):
    return float(Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


class TestBuySignalGeneratorDecimalRounding:
    def test_buy_branch_buylevel_matches_decimal_rounding_not_bare_round(self):
        gen = BuySignalGenerator()
        # Confirmed to diverge: round(352.58135, 4) == 352.5813 (bare float round) vs
        # Decimal("352.58135").quantize(4dp, ROUND_HALF_UP) == 352.5814 - the classic
        # round(2.675, 2) == 2.67 binary-representation trap, scaled to 4 decimal places.
        swing_high = 352.58135
        signal_type, strength, reason, buylevel, stoplevel, raw_buy, raw_sell = gen._generate_signal(
            symbol="TEST",
            close=360.0,
            high=360.0,
            low=345.0,
            sma_50=300.0,
            confirmed_swing_high=swing_high,
            confirmed_swing_low=300.0,
            stop_ref_swing_low=300.0,
            in_position=False,
        )
        assert signal_type == "BUY"
        assert buylevel == _decimal_round(swing_high)

    def test_buy_branch_stoplevel_matches_decimal_rounding_not_bare_round(self):
        gen = BuySignalGenerator()
        # Confirmed to diverge: round(86.51905, 4) == 86.519 vs Decimal ROUND_HALF_UP == 86.5191
        swing_low = 86.51905
        signal_type, strength, reason, buylevel, stoplevel, raw_buy, raw_sell = gen._generate_signal(
            symbol="TEST",
            close=101.0,
            high=101.0,
            low=95.0,
            sma_50=90.0,
            confirmed_swing_high=100.0,
            confirmed_swing_low=swing_low,
            stop_ref_swing_low=swing_low,
            in_position=False,
        )
        assert signal_type == "BUY"
        assert stoplevel == _decimal_round(swing_low)

    def test_sell_branch_buylevel_matches_decimal_rounding_not_bare_round(self):
        gen = BuySignalGenerator()
        # Confirmed to diverge: round(130.96445, 4) == 130.9644 vs Decimal ROUND_HALF_UP == 130.9645
        close = 130.96445
        signal_type, strength, reason, buylevel, stoplevel, raw_buy, raw_sell = gen._generate_signal(
            symbol="TEST",
            close=close,
            high=101.0,
            low=85.0,
            sma_50=None,
            confirmed_swing_high=None,
            confirmed_swing_low=90.0,
            stop_ref_swing_low=90.0,
            in_position=True,  # SELL only fires while in a position (see edge-trigger tests)
        )
        assert signal_type == "SELL"
        assert buylevel == _decimal_round(close)
