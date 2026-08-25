"""Regression/verification test (2026-08-25, real-money-readiness goal session): proves,
by actually calling the real function rather than asserting from reading the code, that
PreTradeChecks.run_all() independently re-enforces max_position_size_pct at the final gate
every real entry path passes through - not just position_sizer.py's own cap upstream.

This matters because position_sizer.py's calculate_position_size() computes and caps
position size once, but execute_entry()/TradeContext ultimately trust whatever
position_value they're handed - if a future bug, a different sizing path, or a manually
constructed TradeContext ever produced an oversized position_value, this is the last real
gate standing between that value and a live order. Confirms it actually rejects, with a
real position_value/portfolio_value pair well beyond the configured cap, not a
hypothetical.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.trading.pretrade_checks import PreTradeChecks


def _config(max_position_size_pct=5.0):
    return {
        "max_position_size_pct": max_position_size_pct,
        "min_order_size_dollars": 100,
        "max_positions_per_sector": 10,
        "max_positions_per_industry": 8,
    }


class TestMaxPositionSizeIndependentlyEnforced:
    def test_oversized_position_rejected_even_if_upstream_sizing_bypassed(self):
        """A position_value that would be a completely valid output of position_sizer.py
        for a LOOSER config (e.g. if it were ever misconfigured, bypassed, or a future
        caller skipped it) must still be rejected here: $20,000 position on a $100,000
        portfolio (20%) against a configured 5% cap."""
        checks = PreTradeChecks(config=_config(max_position_size_pct=5.0))

        mock_earnings = MagicMock()
        mock_earnings.run.return_value = {"pass": True, "reason": None}

        with patch("algo.trading.pretrade_checks.EarningsBlackout", return_value=mock_earnings):
            passed, reason = checks.run_all(
                symbol="AAPL",
                position_value=20_000.0,
                portfolio_value=100_000.0,
                side="BUY",
                eval_date=date(2026, 3, 15),
            )

        assert passed is False, f"a 20% position against a 5% cap must be rejected, got passed=True reason={reason!r}"
        assert reason is not None
        assert "5.0" in reason or "5%" in reason

    def test_position_within_cap_still_passes_the_size_check(self):
        """Sanity check: the size check itself must not become overly strict - a position
        genuinely within the configured cap must clear this specific check (may still be
        rejected by a later check in run_all, but not by this one)."""
        checks = PreTradeChecks(config=_config(max_position_size_pct=5.0))

        mock_earnings = MagicMock()
        mock_earnings.run.return_value = {"pass": True, "reason": None}
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None  # no duplicate/recently-closed position
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        # $4,000 on $100,000 = 4%, under the 5% cap (plus the documented 1% rounding
        # tolerance) - if this fails specifically on the size message, the cap itself is
        # miscalibrated.
        with (
            patch("algo.trading.pretrade_checks.EarningsBlackout", return_value=mock_earnings),
            patch("algo.trading.pretrade_checks.DatabaseContext", return_value=mock_db_context),
        ):
            passed, reason = checks.run_all(
                symbol="AAPL",
                position_value=4_000.0,
                portfolio_value=100_000.0,
                side="BUY",
                eval_date=date(2026, 3, 15),
            )
        if not passed:
            assert "max" not in (reason or "").lower() or "%" not in (reason or ""), (
                f"a 4% position against a 5% cap should not be rejected by the size check, got: {reason!r}"
            )
