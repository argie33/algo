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

UPDATED 2026-08-27 (goal: pre-live-money audit): the original version additionally required
pattern_day_trader == True before even looking at daytrade_count. That's backwards - Alpaca
sets pattern_day_trader only *after* the 4th day trade has already happened, while
daytrade_count climbs independently and continuously beforehand. Gating on the flag meant
the check could never fire in the exact pre-breach scenario (daytrade_count==3, flag still
False) it exists to catch. The check now looks at daytrade_count directly regardless of the
flag's value - see the function's own updated docstring for the full explanation.
"""

import pytest

from algo.orchestrator.phase8_pdt_check import _check_pdt_limit_breach


def test_not_yet_flagged_but_at_threshold_blocks():
    """The scenario the check exists for: daytrade_count==3, Alpaca hasn't flagged the
    account yet (it only does so once the 4th trade actually happens) - must still block."""
    breach, reason = _check_pdt_limit_breach({"pattern_day_trader": False, "daytrade_count": 3})
    assert breach is True
    assert "PDT" in reason
    assert "3" in reason


def test_not_yet_flagged_below_threshold_does_not_block():
    breach, reason = _check_pdt_limit_breach({"pattern_day_trader": False, "daytrade_count": 2})
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


def test_missing_daytrade_count_fails_closed():
    """FIX (real-money-readiness audit): a missing count on a sub-$25k account is an
    unknown, not a known-safe state - given the real 90-day-lockout consequence of guessing
    wrong, this must block, consistent with this file's fail-fast stance on every other
    missing PDT-relevant field."""
    breach, reason = _check_pdt_limit_breach({"pattern_day_trader": True, "daytrade_count": None})
    assert breach is True
    assert reason is not None
    breach, reason = _check_pdt_limit_breach({"pattern_day_trader": False, "daytrade_count": None})
    assert breach is True
    assert reason is not None


def test_missing_daytrade_count_does_not_block_when_equity_exempt():
    """Equity >=$25k exempts before daytrade_count is ever inspected, so a missing count
    on an already-exempt account correctly still does not block."""
    breach, reason = _check_pdt_limit_breach({"pattern_day_trader": False, "daytrade_count": None, "equity": 100_000.0})
    assert breach is False
    assert reason is None


def test_missing_pattern_day_trader_field_raises():
    with pytest.raises(KeyError):
        _check_pdt_limit_breach({"daytrade_count": 4})


class TestEquityAwarePdtCheck:
    """2026-09-06 real-money-readiness fix: FINRA Rule 4210's PDT restriction applies ONLY
    to accounts under $25,000 equity - an account at or above that threshold cannot be
    PDT-restricted at all, regardless of daytrade_count. The check previously blocked purely
    on daytrade_count>=3 with no equity awareness, needlessly halting a well-capitalized
    account's real trading on a restriction that genuinely cannot apply to it.
    """

    def test_well_capitalized_account_at_threshold_does_not_block(self):
        breach, reason = _check_pdt_limit_breach({"pattern_day_trader": False, "daytrade_count": 4, "equity": 25_000.0})
        assert breach is False
        assert reason is None

    def test_well_capitalized_account_above_threshold_does_not_block(self):
        breach, reason = _check_pdt_limit_breach(
            {"pattern_day_trader": True, "daytrade_count": 10, "equity": 100_000.0}
        )
        assert breach is False
        assert reason is None

    def test_sub_25k_account_still_blocks(self):
        breach, reason = _check_pdt_limit_breach(
            {"pattern_day_trader": False, "daytrade_count": 3, "equity": 24_999.99}
        )
        assert breach is True
        assert "PDT" in reason

    def test_missing_equity_falls_back_to_daytrade_count_only(self):
        """Can't verify equity - not treated as automatically exempt; falls back to the
        original daytrade_count-only check rather than silently skipping the safety gate."""
        breach, reason = _check_pdt_limit_breach({"pattern_day_trader": False, "daytrade_count": 3})
        assert breach is True
        assert "PDT" in reason
