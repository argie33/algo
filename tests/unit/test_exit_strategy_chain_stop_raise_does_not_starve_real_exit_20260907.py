"""Regression test for a 2026-09-07 pre-live-trading audit fix to ExitStrategyChain.evaluate()
(algo/trading/exit_strategies.py).

Before the fix, the chain returned on the FIRST triggered strategy regardless of whether it was
a real exit (fraction > 0) or a pure stop-tightening (fraction == 0.0, e.g.
ChandelierTrailStrategy - see check_chandelier_trail's own "raise_stop_trail"/fraction=0.0
decision in exit_position_context.py). ChandelierTrailStrategy sits ahead of
TDSequentialStrategy/FirstRedDayStrategy/ClimaxExhaustionStrategy in priority order, and triggers
whenever the newly computed trail is even slightly higher than the current stop - the normal,
frequent case during a strong uptrend. That's exactly the market condition Climax Exhaustion
(30+ days held, 5R+ gain, 20%+ in 10 days) is designed to catch, so a routine stop-raise could
silently starve the real exhaustion exit for an entire evaluation cycle.

Fix: the chain now keeps scanning past a fraction==0.0 trigger for a real (fraction > 0) exit
among remaining strategies, only falling back to the stop-raise if nothing else fires.
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
        "use_chandelier_trail": True,
        "exit_on_td_sequential": False,
        "exit_on_rs_line_break_50dma": False,
        "require_target_pullback": True,
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


# Same geometry as test_exit_engine_rs_td_firered_climax_20260824.py: entry $100, stop $90 (1R=
# $10), climax-eligible at 35 days held / R=5.2 / 25% gain in last 10 days. require_target_
# pullback=True + _is_pulling_back mocked False blocks T1/T2/T3 so lower-priority checks are
# reachable without an artificial price/target mismatch.
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
    "days_held": 35,
    "dist_days_today": 0,
}


@pytest.fixture(autouse=True)
def _block_targets_via_no_pullback():
    with patch("algo.trading.exit_engine.ExitEngine._is_pulling_back", return_value=False):
        yield


class TestChandelierDoesNotStarveClimaxExhaustion:
    def test_climax_exhaustion_fires_despite_a_concurrent_chandelier_stop_raise(self, mock_config):
        """The bug scenario: chandelier trail wants to raise the stop (triggered=True,
        fraction=0.0) on the SAME evaluation as a genuine climax-exhaustion exit condition.
        Before the fix, the chain returned the chandelier stop-raise and never reached
        ClimaxExhaustionStrategy this cycle. After the fix, the real exit must win."""
        engine = _engine(mock_config)
        with (
            patch("algo.trading.exit_engine.ExitEngine._compute_gain_last_n_days", return_value=25.0),
            patch("algo.trading.exit_engine.ExitEngine._chandelier_or_ema_stop", return_value=95.00),
        ):
            decision = engine._evaluate_position(
                **_BASE_KWARGS,
                cur_price=Decimal("152.00"),  # R = 6.2, well above chandelier's 1R gate too
                prev_close=Decimal("150.00"),
                target_hits=0,
            )
        assert decision is not None
        assert decision["stage"] == "climax_exhaustion"
        assert decision["fraction"] == 0.50

    def test_pure_stop_raise_still_returned_when_no_real_exit_triggers(self, mock_config):
        """Sanity counterpart: with no climax/TD/first-red-day condition present, the
        chandelier stop-raise must still be the returned signal (not swallowed by the fix)."""
        engine = _engine(mock_config)
        with (
            patch("algo.trading.exit_engine.ExitEngine._compute_gain_last_n_days", return_value=5.0),
            patch("algo.trading.exit_engine.ExitEngine._chandelier_or_ema_stop", return_value=95.00),
        ):
            decision = engine._evaluate_position(
                **_BASE_KWARGS,
                cur_price=Decimal("110.00"),  # R = 2.0 - well above chandelier's 1R gate
                prev_close=Decimal("109.00"),
                target_hits=0,
            )
        assert decision is not None
        assert decision["stage"] == "raise_stop_trail"
        assert decision["fraction"] == 0.0
        assert decision["new_stop"] == 95.00
