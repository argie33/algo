"""Tests for the 2026-09-07 exit-strategy validation backtest finding: T1/T2/T3 partial-exit
scale-out is now gated by `use_scale_out_targets` (see algo/trading/exit_position_context.py's
check_target_t1 docstring for the full backtest results -
scripts/backtest_exit_strategy_comparison_20260907.py, 471,972 paired trades - that motivated
disabling scale-out by default). Schema default stays True (existing tests are unaffected
unless they read algo_config for real); the LIVE algo_config value is False via migration 1272.

This file covers the gate itself: disabled means T1 never fires (and T2/T3 cascade-disable
since target_hits never advances past 0), while explicitly re-enabling restores the original
T1/T2/T3 behavior unchanged - the machinery itself is untouched, just gated.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from algo.trading.exit_engine import ExitEngine

TODAY = date(2026, 9, 7)


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
        "use_scale_out_targets": False,  # the new live default
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
        "t1_target_r_multiple": 1.5,
        "t2_target_r_multiple": 3.0,
        "t3_target_r_multiple": 4.0,
        "max_reentries_per_name": 2,
        "min_days_before_reentry_same_symbol": 5,
        "wash_sale_cooldown_days": 31,
    }


def _engine(mock_config):
    with patch("algo.trading.exit_engine.TradeExecutor"):
        return ExitEngine(mock_config)


# entry $100, stop $90 (1R=$10), T1=$115 (1.5R), T2=$130 (3R), T3=$140 (4R)
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


class TestScaleOutGatedOffByDefault:
    def test_t1_does_not_fire_when_gated_off_even_at_target_price(self, mock_config):
        engine = _engine(mock_config)
        decision = engine._evaluate_position(
            **_BASE_KWARGS, cur_price=Decimal("115.00"), prev_close=Decimal("114.00"), target_hits=0
        )
        assert decision is None or decision["stage"] != "target_1"

    def test_t1_never_advances_target_hits_so_t2_is_naturally_unreachable_for_new_trades(self, mock_config):
        """check_target_t2 itself is deliberately NOT gated on use_scale_out_targets (only T1
        is - see check_target_t1's docstring): target_hits==1 only ever gets set by a real T1
        fire, so for any BRAND NEW trade opened while the gate is off, T1 never fires, target_
        hits never leaves 0, and T2/T3 are naturally inert without needing their own gate.
        This also means a position that already sold its T1 leg BEFORE this gate was deployed
        (target_hits=1 already recorded) correctly still completes T2/T3 rather than being
        stranded half-exited - confirmed deliberately, not a gap: feeding target_hits=1
        directly (simulating that legacy in-flight state) still lets T2 fire normally."""
        engine = _engine(mock_config)
        # Fresh trade, target_hits=0: T1 must not fire, so target_hits has no path to 1.
        fresh_decision = engine._evaluate_position(
            **_BASE_KWARGS, cur_price=Decimal("115.00"), prev_close=Decimal("114.00"), target_hits=0
        )
        assert fresh_decision is None or fresh_decision["stage"] != "target_1"

        # A pre-existing position that already recorded target_hits=1 under the old default
        # must still be able to complete T2 - not stranded by the gate change.
        legacy_decision = engine._evaluate_position(
            **_BASE_KWARGS, cur_price=Decimal("130.00"), prev_close=Decimal("128.00"), target_hits=1
        )
        assert legacy_decision is not None
        assert legacy_decision["stage"] == "target_2"

    def test_missing_config_key_fails_fast(self, mock_config):
        from algo.trading.exit_engine import PositionContext

        config = dict(mock_config)
        del config["use_scale_out_targets"]
        ctx = PositionContext(
            symbol="TGT",
            current_date=TODAY,
            cur_price=Decimal("115.00"),
            prev_close=Decimal("114.00"),
            entry_price=Decimal("100.00"),
            active_stop=Decimal("90.00"),
            init_stop=Decimal("90.00"),
            t1_price=Decimal("115.00"),
            t2_price=Decimal("130.00"),
            t3_price=Decimal("140.00"),
            target_hits=0,
            days_held=5,
            dist_days_today=0,
            config=config,
        )
        with pytest.raises(ValueError, match="use_scale_out_targets"):
            ctx.check_target_t1(engine=None)


class TestScaleOutStillWorksWhenExplicitlyReenabled:
    def test_t1_fires_normally_when_flag_set_true(self, mock_config):
        mock_config["use_scale_out_targets"] = True
        engine = _engine(mock_config)
        decision = engine._evaluate_position(
            **_BASE_KWARGS, cur_price=Decimal("115.00"), prev_close=Decimal("114.00"), target_hits=0
        )
        assert decision is not None
        assert decision["stage"] == "target_1"
        assert decision["fraction"] == 0.50
