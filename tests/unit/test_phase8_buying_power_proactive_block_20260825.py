"""Regression test for the 2026-08-25 fix (goal session, financial-review audit):
pretrade_checks.py's own module docstring flagged that after the 2026-08-24 PDT fix, the one
remaining reactive-only gap was a hard dollar-for-dollar buying-power/margin check - distinct
from position_sizer.py's max_total_invested_pct cap, which sizes against TOTAL EQUITY (cash +
open positions' market value), not actual settled/available cash. Those two can diverge in
either direction, so a position clearing every existing check could still be rejected at the
broker for insufficient funds, caught only reactively by Alpaca's own order-time rejection.

_check_buying_power_sufficient() (algo/orchestrator/phase8_entry_execution.py) now proactively
rejects a candidate whose position value would exceed this run's remaining buying-power
balance, mirroring _check_pdt_limit_breach()'s "pure, testable helper called from the main
entry loop" shape.
"""

from decimal import Decimal

from algo.orchestrator.phase8_entry_execution import _check_buying_power_sufficient


def test_position_within_buying_power_passes():
    ok, reason = _check_buying_power_sufficient(Decimal("10000.00"), Decimal("5000.00"))
    assert ok is True
    assert reason is None


def test_position_exactly_at_buying_power_passes():
    ok, reason = _check_buying_power_sufficient(Decimal("5000.00"), Decimal("5000.00"))
    assert ok is True
    assert reason is None


def test_position_exceeding_buying_power_blocks():
    ok, reason = _check_buying_power_sufficient(Decimal("1000.00"), Decimal("1000.01"))
    assert ok is False
    assert reason is not None
    assert "1000.01" in reason
    assert "1000.00" in reason


def test_zero_remaining_buying_power_blocks_any_positive_position():
    ok, reason = _check_buying_power_sufficient(Decimal("0"), Decimal("1.00"))
    assert ok is False
    assert reason is not None
