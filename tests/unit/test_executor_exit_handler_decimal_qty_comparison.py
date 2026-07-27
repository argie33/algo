#!/usr/bin/env python3
"""Regression test for a 2026-07-27 live bug in ExitHandler._execute_exit()'s post-update
consistency check: it compared the DB's Decimal quantity directly against the Python
float `new_qty` computed via `float(current_qty_dec - shares_exited_dec)`. A binary float
cannot represent values like 4.87 exactly, so `Decimal('4.8700') != 4.87` evaluates True
even though they are the same number - this false-positived on exact matches.

Live-reproduced 2026-07-27: 3 correct partial exits raised "Position consistency error:
partial exit expected 4.87 shares... got 4.8700 shares" and were counted as failures, even
though the UPDATE had succeeded exactly as intended.

Fixed by routing both sides through Decimal(str(...)) before comparing, so the comparison
is decimal-value-based rather than binary-float-based.
"""

from decimal import Decimal


def test_float_vs_db_decimal_can_mismatch_on_exact_values():
    """Demonstrates the root cause: a value that round-trips through float() can fail a
    direct == against the DB's native Decimal, even when mathematically identical."""
    current_qty_dec = Decimal("10.00")
    shares_exited_dec = Decimal("5.13")
    new_qty_dec = current_qty_dec - shares_exited_dec
    new_qty = float(new_qty_dec)  # what _execute_exit computes and passes to the UPDATE

    final_qty_from_db = Decimal("4.8700")  # what the DB reports back after the UPDATE

    assert final_qty_from_db != new_qty, (
        "sanity check: this is the exact false-positive condition the pre-fix code hit - "
        "if this assertion fails, the float/Decimal representations no longer collide and "
        "this regression test needs a different reproducing pair"
    )


def test_decimal_str_roundtrip_comparison_matches():
    """The fix: comparing Decimal(str(final_qty)) != Decimal(str(new_qty)) must treat the
    same case above as equal, since both stringify to the same decimal value."""
    current_qty_dec = Decimal("10.00")
    shares_exited_dec = Decimal("5.13")
    new_qty_dec = current_qty_dec - shares_exited_dec
    new_qty = float(new_qty_dec)

    final_qty_from_db = Decimal("4.8700")

    assert Decimal(str(final_qty_from_db)) == Decimal(str(new_qty)), (
        "post-fix comparison must recognize these as the same quantity"
    )


def test_decimal_str_roundtrip_still_catches_genuine_mismatch():
    """The fix must not become a tautology that always passes - a genuinely different
    quantity (real optimistic-lock failure / concurrent modification) must still fail."""
    new_qty = 4.87
    final_qty_from_db = Decimal("3.00")  # genuinely wrong - some other process changed it

    assert Decimal(str(final_qty_from_db)) != Decimal(str(new_qty)), (
        "a real quantity mismatch must still be detected after the fix"
    )
