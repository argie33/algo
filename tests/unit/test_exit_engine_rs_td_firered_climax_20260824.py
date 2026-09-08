#!/usr/bin/env python3
"""Regression tests for exit_engine.py's remaining zero-coverage exit checks:
check_rs_line_break, check_td_sequential, check_first_red_day, check_climax_exhaustion.

Continuation of test_exit_engine_target_t1_t2_t3_20260824.py's audit (see that file and
[[exit_engine_t1_t2_t3_verified_and_tested_20260824]] in memory) - these four were the
remaining names from the same "never referenced in any test file" sweep of exit_engine.py.

DESIGN NOTE surfaced while building realistic test scenarios (not a bug, but worth recording):
check_climax_exhaustion's 5R+ threshold sits ABOVE T3's default 4R target. Under default target
R-multiples, a position that took T1/T2/T3 normally would already be fully closed by 4R, so
climax_exhaustion could never fire. It only matters for a position where require_target_pullback
blocked T1/T2/T3 from ever firing (price ran straight up with no pullback) - climax_exhaustion is
the safety-net exit for exactly that runaway-parabolic-with-no-pullback scenario. Tests below use
require_target_pullback=True + a mocked-False _is_pulling_back to construct that scenario
realistically, rather than artificially inflating target prices to dodge the T1/T2/T3 gates.
"""

from datetime import date
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
        "require_target_pullback": True,
        "use_scale_out_targets": True,
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


# Position geometry: entry $100, stop $90 (1R=$10), T1=$115 (1.5R), T2=$130 (3R), T3=$140 (4R).
# require_target_pullback=True + _is_pulling_back mocked False (module-wide via autouse below)
# blocks T1/T2/T3 from ever firing regardless of price, so these lower-priority checks are
# reachable at any R-multiple without an artificial price/target mismatch.
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
    "days_held": 35,  # > 30, satisfies climax_exhaustion's days_held gate too
    "dist_days_today": 0,
}


@pytest.fixture(autouse=True)
def _block_targets_via_no_pullback():
    with patch("algo.trading.exit_engine.ExitEngine._is_pulling_back", return_value=False):
        yield


class TestRSLineBreak:
    def test_loser_exits_on_rs_break(self, mock_config):
        mock_config["exit_on_rs_line_break_50dma"] = True
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._rs_line_breaking", return_value=True):
            decision = engine._evaluate_position(
                **_BASE_KWARGS,
                cur_price=Decimal("102.00"),  # R = 0.2, a loser (<=0.5)
                prev_close=Decimal("103.00"),
                target_hits=0,
            )
        assert decision["stage"] == "stop"
        assert decision["fraction"] == 1.0

    def test_winner_not_exited_on_rs_break(self, mock_config):
        """The 2026-08-02 tuning fix this docstring documents: don't exit winners just
        because the sector/RS line weakens."""
        mock_config["exit_on_rs_line_break_50dma"] = True
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._rs_line_breaking", return_value=True):
            decision = engine._evaluate_position(
                **_BASE_KWARGS,
                cur_price=Decimal("107.00"),  # R = 0.7, a winner (>0.5)
                prev_close=Decimal("108.00"),
                target_hits=0,
            )
        assert decision is None

    def test_no_exit_when_rs_not_breaking(self, mock_config):
        mock_config["exit_on_rs_line_break_50dma"] = True
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._rs_line_breaking", return_value=False):
            decision = engine._evaluate_position(
                **_BASE_KWARGS, cur_price=Decimal("102.00"), prev_close=Decimal("103.00"), target_hits=0
            )
        assert decision is None

    def test_disabled_by_config_even_if_breaking(self, mock_config):
        mock_config["exit_on_rs_line_break_50dma"] = False
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._rs_line_breaking", return_value=True):
            decision = engine._evaluate_position(
                **_BASE_KWARGS, cur_price=Decimal("102.00"), prev_close=Decimal("103.00"), target_hits=0
            )
        assert decision is None


class TestTDSequential:
    _SELL_9 = {"combo_13_complete": False, "completed_9": True, "setup_type": "sell"}
    _SELL_13 = {"combo_13_complete": True, "completed_9": True, "setup_type": "sell"}
    _BUY_9 = {"combo_13_complete": False, "completed_9": True, "setup_type": "buy"}
    _NONE = {"combo_13_complete": False, "completed_9": False, "setup_type": None}

    def test_combo_13_full_exit(self, mock_config):
        mock_config["exit_on_td_sequential"] = True
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._get_td_state", return_value=self._SELL_13):
            decision = engine._evaluate_position(
                **_BASE_KWARGS, cur_price=Decimal("110.00"), prev_close=Decimal("109.00"), target_hits=1
            )
        assert decision["stage"] == "td_combo_13"
        assert decision["fraction"] == 1.0

    def test_completed_9_half_exit(self, mock_config):
        mock_config["exit_on_td_sequential"] = True
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._get_td_state", return_value=self._SELL_9):
            decision = engine._evaluate_position(
                **_BASE_KWARGS, cur_price=Decimal("110.00"), prev_close=Decimal("109.00"), target_hits=1
            )
        assert decision["stage"] == "td_exhaustion"
        assert decision["fraction"] == 0.50
        assert decision["new_stop"] == 100.00  # raised to breakeven

    def test_buy_setup_does_not_exit(self, mock_config):
        """A 9-count on the BUY side is not an exhaustion-of-the-uptrend signal - must not
        trigger an exit even though completed_9 is True."""
        mock_config["exit_on_td_sequential"] = True
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._get_td_state", return_value=self._BUY_9):
            decision = engine._evaluate_position(
                **_BASE_KWARGS, cur_price=Decimal("110.00"), prev_close=Decimal("109.00"), target_hits=1
            )
        # TD Sequential itself correctly did not fire; the breakeven stop-raise fallback
        # (added 2026-09-07, see BreakevenStopStrategy) surfaces since R=1.0 >= move_be_at_r.
        assert decision["stage"] == "raise_stop_breakeven"

    def test_gated_on_target_hits_zero(self, mock_config):
        """TD Sequential only applies once T1 has already been taken (target_hits>=1) -
        must not fire on a position that hasn't reached its first target yet."""
        mock_config["exit_on_td_sequential"] = True
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._get_td_state", return_value=self._SELL_13) as mocked:
            decision = engine._evaluate_position(
                **_BASE_KWARGS, cur_price=Decimal("110.00"), prev_close=Decimal("109.00"), target_hits=0
            )
        assert decision["stage"] == "raise_stop_breakeven"
        mocked.assert_not_called()

    def test_gated_on_r_multiple_below_half(self, mock_config):
        mock_config["exit_on_td_sequential"] = True
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._get_td_state", return_value=self._SELL_13) as mocked:
            decision = engine._evaluate_position(
                **_BASE_KWARGS,
                cur_price=Decimal("104.00"),  # R = 0.4, below the 0.5 gate
                prev_close=Decimal("104.00"),
                target_hits=1,
            )
        assert decision is None
        mocked.assert_not_called()

    def test_disabled_by_config(self, mock_config):
        mock_config["exit_on_td_sequential"] = False
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._get_td_state", return_value=self._SELL_13):
            decision = engine._evaluate_position(
                **_BASE_KWARGS, cur_price=Decimal("110.00"), prev_close=Decimal("109.00"), target_hits=1
            )
        # TD Sequential disabled by config; breakeven stop-raise fallback still surfaces
        # (R=1.0 >= move_be_at_r).
        assert decision["stage"] == "raise_stop_breakeven"

    def test_missing_td_state_field_fails_fast(self, mock_config):
        mock_config["exit_on_td_sequential"] = True
        engine = _engine(mock_config)
        with patch(
            "algo.trading.exit_engine.ExitEngine._get_td_state",
            return_value={"combo_13_complete": True},  # missing completed_9/setup_type
        ):
            with pytest.raises(ValueError, match="TD state missing critical fields"):
                engine._evaluate_position(
                    **_BASE_KWARGS, cur_price=Decimal("110.00"), prev_close=Decimal("109.00"), target_hits=1
                )


class TestFirstRedDay:
    def test_fires_on_down_move_with_volume_spike(self, mock_config):
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._check_volume_spike", return_value=True):
            decision = engine._evaluate_position(
                **_BASE_KWARGS,
                cur_price=Decimal("125.00"),  # R = 2.5 (exactly the gate)
                prev_close=Decimal("128.00"),  # down 2.34% from prev_close
                target_hits=0,
            )
        assert decision["stage"] == "first_red_day"
        assert decision["fraction"] == 0.50
        assert decision["new_stop"] == 100.00

    def test_no_exit_without_volume_spike(self, mock_config):
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._check_volume_spike", return_value=False):
            decision = engine._evaluate_position(
                **_BASE_KWARGS, cur_price=Decimal("123.00"), prev_close=Decimal("126.00"), target_hits=0
            )
        # First red day itself correctly did not fire; breakeven stop-raise fallback
        # surfaces (R=2.3 >= move_be_at_r=1.0).
        assert decision["stage"] == "raise_stop_breakeven"

    def test_no_exit_below_down_pct_threshold(self, mock_config):
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._check_volume_spike", return_value=True) as mocked:
            decision = engine._evaluate_position(
                **_BASE_KWARGS,
                cur_price=Decimal("125.50"),  # down only 0.4% from prev_close
                prev_close=Decimal("126.00"),
                target_hits=0,
            )
        assert decision["stage"] == "raise_stop_breakeven"
        mocked.assert_not_called()

    def test_no_exit_below_r_multiple_threshold(self, mock_config):
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._check_volume_spike", return_value=True) as mocked:
            decision = engine._evaluate_position(
                **_BASE_KWARGS,
                cur_price=Decimal("110.00"),  # R = 1.0, below the 2.5 gate
                prev_close=Decimal("113.00"),
                target_hits=0,
            )
        # Exactly at move_be_at_r=1.0 - breakeven fallback surfaces even though first-red-day
        # itself is correctly gated out.
        assert decision["stage"] == "raise_stop_breakeven"
        mocked.assert_not_called()

    def test_no_exit_when_prev_close_missing(self, mock_config):
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._check_volume_spike", return_value=True) as mocked:
            decision = engine._evaluate_position(
                **_BASE_KWARGS, cur_price=Decimal("123.00"), prev_close=None, target_hits=0
            )
        assert decision["stage"] == "raise_stop_breakeven"
        mocked.assert_not_called()


class TestClimaxExhaustion:
    def test_fires_on_parabolic_climax(self, mock_config):
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._compute_gain_last_n_days", return_value=25.0):
            decision = engine._evaluate_position(
                **_BASE_KWARGS,
                cur_price=Decimal("152.00"),  # R = 5.2
                prev_close=Decimal("150.00"),
                target_hits=0,
            )
        assert decision["stage"] == "climax_exhaustion"
        assert decision["fraction"] == 0.50
        assert decision["new_stop"] == 100.00

    def test_no_exit_below_r_multiple_threshold(self, mock_config):
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._compute_gain_last_n_days", return_value=25.0) as mocked:
            decision = engine._evaluate_position(
                **_BASE_KWARGS,
                cur_price=Decimal("145.00"),  # R = 4.5, below the 5.0 gate
                prev_close=Decimal("144.00"),
                target_hits=0,
            )
        # Climax exhaustion itself correctly did not fire; breakeven stop-raise fallback
        # surfaces (R=4.5 >= move_be_at_r=1.0).
        assert decision["stage"] == "raise_stop_breakeven"
        mocked.assert_not_called()

    def test_no_exit_below_days_held_threshold(self, mock_config):
        engine = _engine(mock_config)
        kwargs = dict(_BASE_KWARGS)
        kwargs["days_held"] = 20  # <= 30
        with patch("algo.trading.exit_engine.ExitEngine._compute_gain_last_n_days", return_value=25.0) as mocked:
            decision = engine._evaluate_position(
                **kwargs, cur_price=Decimal("152.00"), prev_close=Decimal("150.00"), target_hits=0
            )
        assert decision["stage"] == "raise_stop_breakeven"
        mocked.assert_not_called()

    def test_no_exit_below_10d_gain_threshold(self, mock_config):
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._compute_gain_last_n_days", return_value=15.0):
            decision = engine._evaluate_position(
                **_BASE_KWARGS, cur_price=Decimal("152.00"), prev_close=Decimal("150.00"), target_hits=0
            )
        assert decision["stage"] == "raise_stop_breakeven"

    def test_no_exit_when_gain_unavailable(self, mock_config):
        engine = _engine(mock_config)
        with patch("algo.trading.exit_engine.ExitEngine._compute_gain_last_n_days", return_value=None):
            decision = engine._evaluate_position(
                **_BASE_KWARGS, cur_price=Decimal("152.00"), prev_close=Decimal("150.00"), target_hits=0
            )
        assert decision["stage"] == "raise_stop_breakeven"
