#!/usr/bin/env python3
"""Regression test for the 2026-07-27 fix: ExitEngine._evaluate_position() checked
min_hold_days BEFORE the hard stop-loss, so a position that gapped/crashed through its stop
before min_hold_days was satisfied (min_hold_days=1 in production - i.e. the entire entry day)
reported "hold" and never exited.

This file's own documented exit hierarchy lists the stop-loss first, specifically because it's
an unconditional "hard capital preservation rule" - unlike the other 11 exit checks (Minervini
break, targets, chandelier trail, etc.), which are legitimately gated by a min-hold buffer to
avoid same-day whipsaw exits.

In execution_mode="auto" (real Alpaca orders) the broker's own bracket stop-loss order is a
backstop, but in paper/dry/LOCAL_MODE (no real Alpaca order exists - see executor.py's
_submit_and_validate_order) this Python-side check was the ONLY stop-loss enforcement, and even
in auto mode it's a real defense-in-depth gap if the broker order is ever cancelled/modified/
missed.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from algo.trading.exit_engine import ExitEngine


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
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
    }


def _engine(mock_config):
    with patch("algo.trading.exit_engine.TradeExecutor"):
        return ExitEngine(mock_config)


class TestStopLossOverridesMinHoldDays:
    def test_stop_hit_on_entry_day_exits_despite_min_hold_days(self, mock_config):
        """The core bug: a position entered today (days_held=0) that has already crashed
        through its stop must exit immediately, not be held just because min_hold_days=1
        hasn't been satisfied yet."""
        engine = _engine(mock_config)

        decision = engine._evaluate_position(
            cur=None,
            symbol="CRASH",
            current_date=date(2026, 7, 27),
            cur_price=Decimal("85.00"),
            prev_close=Decimal("100.00"),
            entry_price=Decimal("100.00"),
            active_stop=Decimal("90.00"),
            init_stop=Decimal("90.00"),
            t1_price=Decimal("115.00"),
            t2_price=Decimal("130.00"),
            t3_price=Decimal("140.00"),
            target_hits=0,
            days_held=0,  # below min_hold_days=1
            dist_days_today=0,
        )

        assert decision["stage"] == "stop", (
            f"a position crashed through its stop on entry day must still exit, got {decision}"
        )
        assert decision["fraction"] == 1.0

    def test_price_above_stop_on_entry_day_still_holds_for_min_hold_days(self, mock_config):
        """Sanity check: the fix must not disable min_hold_days for everything - a position
        still above its stop on entry day must still be held (no other exit type should fire
        early)."""
        engine = _engine(mock_config)

        decision = engine._evaluate_position(
            cur=None,
            symbol="OK",
            current_date=date(2026, 7, 27),
            cur_price=Decimal("101.00"),
            prev_close=Decimal("100.00"),
            entry_price=Decimal("100.00"),
            active_stop=Decimal("90.00"),
            init_stop=Decimal("90.00"),
            t1_price=Decimal("115.00"),
            t2_price=Decimal("130.00"),
            t3_price=Decimal("140.00"),
            target_hits=0,
            days_held=0,
            dist_days_today=0,
        )

        # None means "no action" - see check_and_execute_exits' `if not exit_signal:`
        # guard. A truthy "hold" dict here (fraction=0.0, no new_stop) previously fell
        # through into the stop-raise-only branch downstream and crashed.
        assert decision is None

    def test_price_exactly_at_stop_on_entry_day_exits(self, mock_config):
        """Boundary check: cur_price == active_stop is a stop trigger (<=), even on entry day."""
        engine = _engine(mock_config)

        decision = engine._evaluate_position(
            cur=None,
            symbol="EDGE",
            current_date=date(2026, 7, 27),
            cur_price=Decimal("90.00"),
            prev_close=Decimal("100.00"),
            entry_price=Decimal("100.00"),
            active_stop=Decimal("90.00"),
            init_stop=Decimal("90.00"),
            t1_price=Decimal("115.00"),
            t2_price=Decimal("130.00"),
            t3_price=Decimal("140.00"),
            target_hits=0,
            days_held=0,
            dist_days_today=0,
        )

        assert decision["stage"] == "stop"
