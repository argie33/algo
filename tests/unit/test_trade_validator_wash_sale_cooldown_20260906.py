"""Regression test for a 2026-09-06 real-money-readiness audit finding: TradeValidator's
check_reentry_rules() enforced only min_days_before_reentry_same_symbol (a pure flip-flop-
prevention reset period, default 5 days) with no tax awareness at all. Re-entering the same
symbol 6-29 days after a LOSS-driven stop-out - which the 5-day reset already permits -
systematically triggers the IRS wash-sale rule (30-day window before/after a loss sale),
disallowing that loss for tax purposes in a taxable account.

Wash sale only applies to LOSSES, not gains - a profitable stop-out (e.g. a trailing stop)
has no tax concern and should only wait the shorter base reset period. Fixed by adding a
separate wash_sale_cooldown_days config (default 31 = IRS 30-day window + 1 day buffer)
that only raises the effective required cooldown when the prior exit was a loss.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from algo.trading.trade_validator import TradeValidator
from utils.infrastructure import EASTERN_TZ


def _make_validator(min_days=5, wash_sale_cooldown_days=31, max_reentries=3):
    config = {
        "t1_target_r_multiple": 2.0,
        "t2_target_r_multiple": 3.0,
        "t3_target_r_multiple": 4.0,
        "max_reentries_per_name": max_reentries,
        "min_days_before_reentry_same_symbol": min_days,
        "wash_sale_cooldown_days": wash_sale_cooldown_days,
    }
    return TradeValidator(config)


def _cursor_with_prior_exit(days_ago: int, profit_loss_pct, exit_reason="STOP hit: hard capital preservation"):
    cur = MagicMock()
    exit_date = datetime.now(EASTERN_TZ).date() - timedelta(days=days_ago)
    cur.fetchone.return_value = ("TRD-PRIOR", exit_date, exit_reason, profit_loss_pct, 0)
    return cur


class TestWashSaleCooldown:
    def test_missing_config_raises(self):
        try:
            TradeValidator(
                {
                    "t1_target_r_multiple": 2.0,
                    "t2_target_r_multiple": 3.0,
                    "t3_target_r_multiple": 4.0,
                    "max_reentries_per_name": 3,
                    "min_days_before_reentry_same_symbol": 5,
                }
            )
            raise AssertionError("Expected ValueError for missing wash_sale_cooldown_days")
        except ValueError as e:
            assert "wash_sale_cooldown_days" in str(e)

    def test_loss_exit_15_days_ago_blocked_by_wash_sale_window(self):
        """The exact bug scenario: 15 days since a LOSS stop-out clears the base 5-day reset
        but is well inside the 30-day wash-sale window - must still be blocked."""
        validator = _make_validator(min_days=5, wash_sale_cooldown_days=31)
        cur = _cursor_with_prior_exit(days_ago=15, profit_loss_pct=-4.2)

        is_valid, message, _ = validator.check_reentry_rules(cur, "AAPL")

        assert is_valid is False
        assert message is not None
        assert "wash-sale" in message.lower()
        assert "31d" in message

    def test_loss_exit_32_days_ago_allowed_past_wash_sale_window(self):
        validator = _make_validator(min_days=5, wash_sale_cooldown_days=31)
        cur = _cursor_with_prior_exit(days_ago=32, profit_loss_pct=-4.2)

        is_valid, message, _ = validator.check_reentry_rules(cur, "AAPL")

        assert is_valid is True

    def test_profitable_stop_out_only_needs_the_shorter_base_reset(self):
        """A trailing stop that locked in a GAIN has no wash-sale concern - re-entry after
        just the base reset period (well inside 31 days) must be allowed."""
        validator = _make_validator(min_days=5, wash_sale_cooldown_days=31)
        cur = _cursor_with_prior_exit(days_ago=10, profit_loss_pct=3.7)

        is_valid, message, _ = validator.check_reentry_rules(cur, "AAPL")

        assert is_valid is True

    def test_profitable_stop_out_still_blocked_within_base_reset(self):
        validator = _make_validator(min_days=5, wash_sale_cooldown_days=31)
        cur = _cursor_with_prior_exit(days_ago=2, profit_loss_pct=3.7)

        is_valid, message, _ = validator.check_reentry_rules(cur, "AAPL")

        assert is_valid is False
        assert message is not None
        assert "reset period" in message
        assert "wash-sale" not in message.lower()

    def test_null_profit_loss_pct_treated_as_non_loss_uses_base_reset(self):
        """Missing P&L data must never be treated as a loss (which would over-apply the
        longer cooldown) - falls back to the base reset period only."""
        validator = _make_validator(min_days=5, wash_sale_cooldown_days=31)
        cur = _cursor_with_prior_exit(days_ago=10, profit_loss_pct=None)

        is_valid, _message, _ = validator.check_reentry_rules(cur, "AAPL")

        assert is_valid is True

    def test_exact_boundary_31_days_allowed(self):
        validator = _make_validator(min_days=5, wash_sale_cooldown_days=31)
        cur = _cursor_with_prior_exit(days_ago=31, profit_loss_pct=-1.0)

        is_valid, _message, _ = validator.check_reentry_rules(cur, "AAPL")

        assert is_valid is True

    def test_exact_boundary_30_days_still_blocked(self):
        validator = _make_validator(min_days=5, wash_sale_cooldown_days=31)
        cur = _cursor_with_prior_exit(days_ago=30, profit_loss_pct=-1.0)

        is_valid, _message, _ = validator.check_reentry_rules(cur, "AAPL")

        assert is_valid is False

    def test_loss_exit_with_non_stop_time_reason_still_blocked_by_wash_sale(self):
        """Round-2 gap found 2026-09-06: the wash-sale check was nested inside
        `if is_stop_out` (exit_reason containing "STOP" or "TIME"), so a loss exit labeled
        with any other reason string - RS-line breakdown, TD Combo/Sequential exhaustion,
        First Red Day, climax exhaustion, all genuine loss-exit paths in
        exit_position_context.py - bypassed the wash-sale cooldown entirely and allowed
        same-day re-entry inside the IRS 30-day window. Wash-sale exposure depends only on
        whether the prior exit was a loss, not on how it was labeled."""
        validator = _make_validator(min_days=5, wash_sale_cooldown_days=31)
        cur = _cursor_with_prior_exit(
            days_ago=15, profit_loss_pct=-4.2, exit_reason="RS line broke below 50-DMA (loser: R=0.3)"
        )

        is_valid, message, _ = validator.check_reentry_rules(cur, "AAPL")

        assert is_valid is False
        assert message is not None
        assert "wash-sale" in message.lower()

    def test_profitable_exit_with_non_stop_time_reason_not_blocked(self):
        """Symmetric check: a non-STOP/TIME-labeled exit that was profitable must not be
        blocked by either the flip-flop reset (never applied - not a stop_out) or wash-sale
        (not a loss)."""
        validator = _make_validator(min_days=5, wash_sale_cooldown_days=31)
        cur = _cursor_with_prior_exit(days_ago=1, profit_loss_pct=2.5, exit_reason="Climax run exhaustion")

        is_valid, _message, _ = validator.check_reentry_rules(cur, "AAPL")

        assert is_valid is True
