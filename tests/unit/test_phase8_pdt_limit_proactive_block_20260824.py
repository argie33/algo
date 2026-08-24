"""Regression test for the 2026-08-24 fix (goal session, real-money-readiness audit):
Phase 8 previously only logged a warning when Alpaca flagged an account
pattern_day_trader=True - nothing proactively stopped it from submitting an entry that
could become the trade crossing the rolling 5-business-day PDT day-trade limit, which
triggers a real, severe consequence (a 90-day day-trading lockout on accounts under $25k
equity). This system intentionally generates same-day stop-loss exits, so this isn't a
hypothetical edge case.

_check_pdt_limit_breach() (algo/orchestrator/phase8_entry_execution.py) now proactively
blocks new entries once daytrade_count >= 3 (one more round-trip would be the 4th, crossing
the limit) - see pdt_day_trade_limit_reactive_only_not_proactively_enforced_20260824 in
memory for the full investigation.
"""

import pytest

from algo.orchestrator.phase8_entry_execution import _check_pdt_limit_breach


def test_not_pattern_day_trader_never_blocks():
    breach, reason = _check_pdt_limit_breach({"pattern_day_trader": False, "daytrade_count": 4})
    assert breach is False
    assert reason is None


def test_pattern_day_trader_below_threshold_does_not_block():
    breach, reason = _check_pdt_limit_breach({"pattern_day_trader": True, "daytrade_count": 2})
    assert breach is False
    assert reason is None


def test_pattern_day_trader_at_threshold_blocks():
    breach, reason = _check_pdt_limit_breach({"pattern_day_trader": True, "daytrade_count": 3})
    assert breach is True
    assert "PDT" in reason
    assert "3" in reason


def test_pattern_day_trader_above_threshold_blocks():
    breach, reason = _check_pdt_limit_breach({"pattern_day_trader": True, "daytrade_count": 4})
    assert breach is True


def test_pattern_day_trader_missing_daytrade_count_does_not_block():
    """Can't verify the count - not treated as a breach here (Phase 2's own missing-count
    warning already surfaces this; blocking on unknown-but-possibly-fine data would halt
    entries in cases where the account is nowhere near the limit)."""
    breach, reason = _check_pdt_limit_breach({"pattern_day_trader": True, "daytrade_count": None})
    assert breach is False
    assert reason is None


def test_missing_pattern_day_trader_field_raises():
    with pytest.raises(KeyError):
        _check_pdt_limit_breach({"daytrade_count": 4})
