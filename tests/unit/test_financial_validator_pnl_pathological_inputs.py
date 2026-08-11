#!/usr/bin/env python3
"""Regression test for FinancialDataValidator.validate_pnl_calculation, found via fuzzing
with pathological inputs on 2026-08-10. This function had zero real callers at the time
(dead code) but is clearly meant as a pre-recording P&L safety validator - its own module
docstring promises "Prevents NaN, Infinity, negative prices" - and its bugs directly
contradicted that guarantee:

Bug 1 (most serious): NaN and Infinity entry/exit prices silently passed validation as
valid=True, with pnl_dollars/pnl_pct set to NaN/Infinity - `float('nan') <= 0` is False in
Python (NaN compares False against everything) and NaN/Inf arithmetic doesn't raise, so
neither the precondition checks nor the try/except caught it. If this validator is ever
wired into the real exit-recording pipeline (its clear intended purpose), a NaN/Inf price
anywhere upstream would silently produce garbage P&L on a real trade record instead of
being rejected.

Bug 2: a string-typed entry/exit_price crashed with an uncaught
"TypeError: '<=' not supported between instances of 'str' and 'int'" instead of the clean
(False, None, None, msg) tuple this function's own signature promises.

Fixed by delegating to validate_price/validate_quantity - the sibling static methods in
this same class that already correctly handle type coercion, NaN, Infinity, and
negative/zero values.
"""

import math

from utils.validation.financial import FinancialDataValidator


class TestPnlCalculationRejectsNanAndInfinity:
    def test_nan_entry_price_rejected_not_silently_accepted(self):
        valid, pnl_dollars, pnl_pct, msg = FinancialDataValidator.validate_pnl_calculation(float("nan"), 110.0, 10)
        assert valid is False
        assert pnl_dollars is None
        assert pnl_pct is None
        assert msg

    def test_infinity_entry_price_rejected(self):
        valid, pnl_dollars, pnl_pct, msg = FinancialDataValidator.validate_pnl_calculation(float("inf"), 110.0, 10)
        assert valid is False
        assert pnl_dollars is None

    def test_nan_exit_price_rejected(self):
        valid, pnl_dollars, pnl_pct, msg = FinancialDataValidator.validate_pnl_calculation(100.0, float("nan"), 10)
        assert valid is False

    def test_nan_quantity_rejected(self):
        valid, pnl_dollars, pnl_pct, msg = FinancialDataValidator.validate_pnl_calculation(100.0, 110.0, float("nan"))
        assert valid is False

    def test_valid_result_never_contains_nan_or_inf(self):
        """Defense in depth: even if a future refactor reintroduces a gap, a result
        claiming valid=True must never carry a non-finite pnl value."""
        for entry, exit_price, qty in [
            (100.0, 110.0, 10),
            (50.0, 45.0, 100),
            (0.01, 0.02, 1),
        ]:
            valid, pnl_dollars, pnl_pct, _ = FinancialDataValidator.validate_pnl_calculation(entry, exit_price, qty)
            if valid:
                assert math.isfinite(pnl_dollars)
                assert math.isfinite(pnl_pct)


class TestPnlCalculationTypeCoercion:
    def test_string_prices_succeed_not_typeerror(self):
        """A valid string-typed price must be coerced and sized normally, not crash with
        "'<=' not supported between instances of 'str' and 'int'"."""
        valid, pnl_dollars, pnl_pct, msg = FinancialDataValidator.validate_pnl_calculation("100.0", "110.0", 10)
        assert valid is True
        assert pnl_dollars == 100.0
        assert pnl_pct == 10.0

    def test_negative_entry_still_rejected_after_fix(self):
        valid, _, _, msg = FinancialDataValidator.validate_pnl_calculation(-100.0, 110.0, 10)
        assert valid is False
        assert "negative" in msg.lower()
