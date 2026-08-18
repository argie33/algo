#!/usr/bin/env python3
"""Regression test (2026-08-18, live-reproduced on PDEX): algo/trading/exit_engine.py's
active_stop hard-stop branch (_evaluate_position) always worded its exit reason as
"STOP hit... hard capital preservation" regardless of whether active_stop was above or
below entry_price.

active_stop is the RUNNING stop and gets raised as profit targets are hit, so it can end
up ABOVE entry_price after real gains - triggering this same unconditional code path as a
legitimate trailing-stop exit that locks in profit, not a loss-cutting stop. Live case:
PDEX entered at $67.15, active_stop raised to $103.99 near target_3, exited with
exit_r_multiple=+4.01 (+54.86% P&L) - but algo_trades.exit_reason read "STOP hit: $67.15
<= $103.99 (hard capital preservation - not subject to min_hold_days)", which reads as a
loss-cutting event to anyone reading it directly (SQL, dashboard, or the trade-exit
notification in algo/reporting/notifications.py, which surfaces this exact string as
"Reason:"). Fixed to word the reason based on which side of entry_price the triggering
stop actually sits on - the stage/mechanism/exit_price_override are unchanged, only the
text differs.
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
        "t1_target_r_multiple": 1.5,
        "t2_target_r_multiple": 3.0,
        "t3_target_r_multiple": 4.0,
        "max_reentries_per_name": 2,
        "min_days_before_reentry_same_symbol": 5,
    }


def _engine(mock_config):
    with patch("algo.trading.exit_engine.TradeExecutor"):
        return ExitEngine(mock_config)


class TestActiveStopReasonDistinguishesProfitLock:
    def test_stop_raised_above_entry_is_worded_as_locked_in_gain(self, mock_config):
        """PDEX's real numbers: active_stop ($103.99) raised well above entry ($67.15) by
        target-hit raises - the exit is a big win, not a loss, and must be worded that way."""
        engine = _engine(mock_config)

        decision = engine._evaluate_position(
            cur=None,
            symbol="PDEX",
            current_date=date(2026, 8, 17),
            cur_price=Decimal("103.99"),
            prev_close=Decimal("103.99"),
            entry_price=Decimal("67.15"),
            active_stop=Decimal("103.99"),
            init_stop=Decimal("57.9559"),
            t1_price=Decimal("90.14"),
            t2_price=Decimal("94.73"),
            t3_price=Decimal("103.93"),
            target_hits=3,
            days_held=3,
            dist_days_today=0,
        )

        assert decision["stage"] == "stop"
        assert "trailing stop" in decision["reason"].lower()
        assert "locked-in gain" in decision["reason"].lower()
        assert "hard capital preservation" not in decision["reason"].lower()

    def test_stop_below_entry_still_worded_as_hard_capital_preservation(self, mock_config):
        """Sanity check: a genuine loss-cutting stop (active_stop below entry_price) must
        keep the original, accurate "hard capital preservation" wording - this fix only
        changes wording for the profit-lock case, not real stop-losses."""
        engine = _engine(mock_config)

        decision = engine._evaluate_position(
            cur=None,
            symbol="LOSSCO",
            current_date=date(2026, 8, 17),
            cur_price=Decimal("90.00"),
            prev_close=Decimal("95.00"),
            entry_price=Decimal("100.00"),
            active_stop=Decimal("95.00"),
            init_stop=Decimal("95.00"),
            t1_price=Decimal("115.00"),
            t2_price=Decimal("130.00"),
            t3_price=Decimal("140.00"),
            target_hits=0,
            days_held=1,
            dist_days_today=0,
        )

        assert decision["stage"] == "stop"
        assert "hard capital preservation" in decision["reason"].lower()
        assert "trailing stop" not in decision["reason"].lower()
        assert "locked-in gain" not in decision["reason"].lower()
