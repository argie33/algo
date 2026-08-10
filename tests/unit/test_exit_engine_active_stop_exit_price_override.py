#!/usr/bin/env python3
"""Regression test for a 2026-08-10 fix in algo/trading/exit_engine.py::_evaluate_position()'s
hard-stop check (the `active_stop`-based branch, not the sibling `init_stop`-based one earlier
in the same file).

Live-reproduced via real trade data: ECPG (entry 2026-08-07 @ $100.20, active_stop raised to
$100.52 by a target-hit breakeven raise, exited 2026-08-08) recorded exit_price=$100.20 -
matching the entry/current price, not the $100.52 stop that actually triggered the exit. Traced
to this branch's return dict missing `exit_price_override`, unlike its sibling ~250 lines above
(the init_stop-based check, fixed for exactly this reason: "Paper mode was using stale prices...
creating 4-5% slippage. In reality, stops execute AT the stop price"). Downstream,
`exit_signal.get("exit_price_override")` falls back to the live/current price when this key is
absent - so this branch reintroduced the same paper-mode slippage bug the sibling check already
fixed, just for the trailing/raised-stop case instead of the original entry-time stop.

Fixed by adding `"exit_price_override": float(active_stop_dec)`, matching
position_monitor.py's own convention for the same scenario.
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


class TestActiveStopExitPriceOverride:
    def test_active_stop_hit_sets_exit_price_override_to_stop_not_current_price(self, mock_config):
        """The core bug, reproduced with ECPG's real numbers: current price ($100.20) is below
        the raised active_stop ($100.52, above the original init_stop of $83.79) - the exit
        must fill at the stop level, not the current/live price."""
        engine = _engine(mock_config)

        decision = engine._evaluate_position(
            cur=None,
            symbol="ECPG",
            current_date=date(2026, 8, 8),
            cur_price=Decimal("100.20"),
            prev_close=Decimal("100.20"),
            entry_price=Decimal("100.20"),
            active_stop=Decimal("100.52"),
            init_stop=Decimal("83.7925"),
            t1_price=Decimal("115.00"),
            t2_price=Decimal("130.00"),
            t3_price=Decimal("140.00"),
            target_hits=1,
            days_held=1,
            dist_days_today=0,
        )

        assert decision["stage"] == "stop"
        assert decision.get("exit_price_override") == pytest.approx(100.52), (
            f"expected the fill to use the active_stop level (100.52), not the current price "
            f"(100.20) - got exit_price_override={decision.get('exit_price_override')!r}"
        )

    def test_active_stop_not_hit_produces_no_override(self, mock_config):
        """Sanity check: this fix must not fabricate an override when the stop isn't hit."""
        engine = _engine(mock_config)

        decision = engine._evaluate_position(
            cur=None,
            symbol="OK",
            current_date=date(2026, 8, 8),
            cur_price=Decimal("101.00"),
            prev_close=Decimal("100.20"),
            entry_price=Decimal("100.20"),
            active_stop=Decimal("95.00"),
            init_stop=Decimal("83.79"),
            t1_price=Decimal("115.00"),
            t2_price=Decimal("130.00"),
            t3_price=Decimal("140.00"),
            target_hits=0,
            days_held=1,
            dist_days_today=0,
        )

        assert decision is None
