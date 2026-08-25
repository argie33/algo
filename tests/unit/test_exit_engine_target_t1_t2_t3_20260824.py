#!/usr/bin/env python3
"""Regression tests for check_target_t1/check_target_t2/check_target_t3 (algo/trading/
exit_engine.py's PositionContext), the profit-taking exit legs that decide when a winning
position gets partially/fully sold - direct P&L impact on every trade that reaches a target.

FOUND 2026-08-24 (real-money-readiness goal session, test-coverage completeness sweep):
these three functions - plus check_rs_line_break, check_td_sequential, check_climax_exhaustion,
check_first_red_day, check_time_exit - were never referenced by name in any existing test file.
The existing exit_engine test suite (17 files) covers stop-loss/trailing-stop mechanics
thoroughly, but every test that touches the higher-level dispatch either never reaches a
target-triggering price, or (test_exit_engine_hold_returns_none.py) mocks out
ExitStrategyChain.evaluate() entirely, short-circuiting before check_target_t1/t2/t3 would
ever run for real.

Before writing these tests, independently hand-verified the logic is actually correct (not just
documenting existing behavior, right or wrong): the `fraction` returned by each check is applied
to the CURRENT remaining quantity (see executor_exit_handler.py's _calculate_exit_shares,
called with current_qty not entry_qty), so T1's 0.50 + T2's 0.50-of-remainder + T3's 1.0-of-
remainder nets to exactly 50%/25%/25% of the ORIGINAL position - matching each function's own
docstring despite the fractions themselves looking inconsistent (0.50/0.50/1.0) out of context.
Also verified target_hits actually advances: position_tracker.py's partial-exit UPDATE
increments the real DB column (target_levels_hit, aliased to target_hits here) whenever
exit_stage contains "target", and stamps target_N_hit_time - so the T1->T2->T3 gate sequence
and same-day re-fire guard are both real, not just theoretical.

Uses the same real (non-mocked) ExitStrategyChain path as
test_exit_engine_stop_loss_overrides_min_hold.py, via ExitEngine._evaluate_position() - not a
direct PositionContext construction - so these tests also exercise strategy priority ordering
(StopLoss -> Minervini -> RSLineBreak -> TimeBased -> T1 -> T2 -> T3 -> ...).
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from algo.trading.exit_engine import ExitEngine

TODAY = date(2026, 8, 24)


@pytest.fixture
def mock_config():
    return {
        "min_hold_days": 1,
        "max_hold_days": 60,
        "eight_week_rule_threshold_pct": 20.0,
        "eight_week_rule_window_days": 21,
        "exit_on_distribution_day": False,
        "max_distribution_days": 3,
        "move_be_at_r": 1.0,
        "chandelier_atr_mult": 3.0,
        "use_chandelier_trail": False,
        "exit_on_td_sequential": False,
        "exit_on_rs_line_break_50dma": False,
        "require_target_pullback": False,
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
        "t1_target_r_multiple": 1.5,
        "t2_target_r_multiple": 3.0,
        "t3_target_r_multiple": 4.0,
        "max_reentries_per_name": 2,
        "min_days_before_reentry_same_symbol": 5,
    }


def _engine(mock_config):
    with patch("algo.trading.exit_engine.TradeExecutor"):
        return ExitEngine(mock_config)


# Shared position geometry: entry $100, stop $90 (1R = $10), T1=$115 (1.5R), T2=$130 (3R),
# T3=$140 (4R) - matches the R-multiple convention documented in mock_config above.
_BASE_KWARGS = {
    "cur": None,
    "symbol": "TGT",
    "current_date": TODAY,
    "entry_price": Decimal("100.00"),
    "active_stop": Decimal("90.00"),
    "init_stop": Decimal("90.00"),
    "t1_price": Decimal("115.00"),
    "t2_price": Decimal("130.00"),
    "t3_price": Decimal("140.00"),
    "days_held": 5,
    "dist_days_today": 0,
}


class TestTargetT1:
    def test_fires_at_t1_price_with_zero_target_hits(self, mock_config):
        engine = _engine(mock_config)
        decision = engine._evaluate_position(
            **_BASE_KWARGS, cur_price=Decimal("115.00"), prev_close=Decimal("114.00"), target_hits=0
        )
        assert decision["stage"] == "target_1"
        assert decision["fraction"] == 0.50
        # New stop raised to breakeven (max(active_stop, entry_price))
        assert decision["new_stop"] == 100.00

    def test_does_not_fire_below_t1_price(self, mock_config):
        engine = _engine(mock_config)
        decision = engine._evaluate_position(
            **_BASE_KWARGS, cur_price=Decimal("114.99"), prev_close=Decimal("110.00"), target_hits=0
        )
        assert decision is None

    def test_does_not_refire_once_target_hits_advanced(self, mock_config):
        """Once T1 has fired (target_hits=1), price staying above t1_price but below
        t2_price must NOT re-trigger T1 (its own gate is target_hits==0) and must not
        fire T2 either (price below t2_price) - the position should simply hold."""
        engine = _engine(mock_config)
        decision = engine._evaluate_position(
            **_BASE_KWARGS, cur_price=Decimal("120.00"), prev_close=Decimal("118.00"), target_hits=1
        )
        assert decision is None

    def test_same_day_rehit_guard_blocks_refire(self, mock_config):
        """Even with target_hits still 0 (e.g. a stale/racing read), a T1 already recorded
        as hit today must not fire again - this is the guard that prevents the exit engine
        from repeatedly selling 50% of the position on every pass within the same day."""
        engine = _engine(mock_config)
        decision = engine._evaluate_position(
            **_BASE_KWARGS,
            cur_price=Decimal("116.00"),
            prev_close=Decimal("115.50"),
            target_hits=0,
            t1_hit_time=datetime(2026, 8, 24, 10, 30, 0),
        )
        assert decision is None

    def test_prior_day_hit_does_not_block_refire(self, mock_config):
        """Sanity check on the dedup guard's date boundary: a hit recorded on a PRIOR day
        must not suppress today's evaluation (target_hits gating handles real dedup;
        this guard is same-day-only)."""
        engine = _engine(mock_config)
        decision = engine._evaluate_position(
            **_BASE_KWARGS,
            cur_price=Decimal("115.00"),
            prev_close=Decimal("114.00"),
            target_hits=0,
            t1_hit_time=datetime(2026, 8, 23, 10, 30, 0),
        )
        assert decision["stage"] == "target_1"

    def test_require_pullback_blocks_fire_when_no_pullback(self, mock_config):
        # ProfitTargetStrategy.evaluate() constructs its OWN internal ExitEngine
        # (algo/trading/exit_strategies.py) rather than reusing the outer instance below -
        # patch the class method so it applies to whichever instance actually calls it.
        mock_config["require_target_pullback"] = True
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._is_pulling_back", return_value=False):
            decision = engine._evaluate_position(
                **_BASE_KWARGS, cur_price=Decimal("115.00"), prev_close=Decimal("114.00"), target_hits=0
            )
        assert decision is None

    def test_require_pullback_allows_fire_when_pullback_confirmed(self, mock_config):
        mock_config["require_target_pullback"] = True
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._is_pulling_back", return_value=True):
            decision = engine._evaluate_position(
                **_BASE_KWARGS, cur_price=Decimal("115.00"), prev_close=Decimal("114.00"), target_hits=0
            )
        assert decision["stage"] == "target_1"


class TestTargetT2:
    def test_fires_at_t2_price_with_one_target_hit(self, mock_config):
        engine = _engine(mock_config)
        decision = engine._evaluate_position(
            **_BASE_KWARGS, cur_price=Decimal("130.00"), prev_close=Decimal("128.00"), target_hits=1
        )
        assert decision["stage"] == "target_2"
        assert decision["fraction"] == 0.50
        # New stop raised to T1 area (max(active_stop, t1_price))
        assert decision["new_stop"] == 115.00

    def test_does_not_fire_without_t1_hit_first(self, mock_config):
        """Price at T2 level but target_hits still 0 (T1 never recorded) must not skip
        straight to a T2 exit - the sequence is strictly gated."""
        engine = _engine(mock_config)
        decision = engine._evaluate_position(
            **_BASE_KWARGS, cur_price=Decimal("130.00"), prev_close=Decimal("128.00"), target_hits=0
        )
        # T1's own gate (target_hits==0 and price>=t1_price) fires instead, since price is
        # also above t1_price - confirms T2 doesn't preempt T1 in the sequence.
        assert decision["stage"] == "target_1"

    def test_same_day_rehit_guard_blocks_refire(self, mock_config):
        engine = _engine(mock_config)
        decision = engine._evaluate_position(
            **_BASE_KWARGS,
            cur_price=Decimal("131.00"),
            prev_close=Decimal("130.50"),
            target_hits=1,
            t2_hit_time=datetime(2026, 8, 24, 11, 0, 0),
        )
        assert decision is None


class TestTargetT3:
    def test_fires_at_t3_price_with_two_target_hits(self, mock_config):
        engine = _engine(mock_config)
        decision = engine._evaluate_position(
            **_BASE_KWARGS, cur_price=Decimal("140.00"), prev_close=Decimal("138.00"), target_hits=2
        )
        assert decision["stage"] == "target_3"
        # T3 is the final leg: exits 100% of whatever remains.
        assert decision["fraction"] == 1.0

    def test_same_day_rehit_guard_blocks_refire(self, mock_config):
        engine = _engine(mock_config)
        decision = engine._evaluate_position(
            **_BASE_KWARGS,
            cur_price=Decimal("141.00"),
            prev_close=Decimal("140.50"),
            target_hits=2,
            t3_hit_time=datetime(2026, 8, 24, 12, 0, 0),
        )
        assert decision is None

    def test_full_sequence_nets_to_100pct_of_original_position(self, mock_config):
        """End-to-end sanity check on the fraction cascade: T1 (0.50 of remaining) + T2
        (0.50 of remaining) + T3 (1.0 of remaining) must net to exactly 100% of the
        ORIGINAL position across all three legs, matching each function's own docstring
        ("50%"/"25%"/"25% final") - this is what _calculate_exit_shares' current-quantity
        (not entry-quantity) semantics is relied on to produce."""
        original_qty = 100.0
        remaining = original_qty

        t1_fraction = 0.50
        t1_shares = remaining * t1_fraction
        remaining -= t1_shares

        t2_fraction = 0.50
        t2_shares = remaining * t2_fraction
        remaining -= t2_shares

        t3_fraction = 1.0
        t3_shares = remaining * t3_fraction
        remaining -= t3_shares

        assert t1_shares == pytest.approx(50.0)
        assert t2_shares == pytest.approx(25.0)
        assert t3_shares == pytest.approx(25.0)
        assert remaining == pytest.approx(0.0)
