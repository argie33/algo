#!/usr/bin/env python3
"""Regression test for a 2026-07-27 live bug: check_distribution() raised the stop to
breakeven (max(active_stop, entry_price)) with NO check that the position was actually
profitable - unlike every other breakeven-raise trigger in this file (T1/T2 target hit,
first_red_day, climax_exhaustion), which only fire once cur_price is already above entry_price.

Live consequence, confirmed via direct DB query: on a single distribution-day trigger
("7 dist days > 4"), 9 fresh open positions - all still slightly below their entry price -
had their stop raised to entry_price (above the current price), which guaranteed a full
stop-out on the very next exit-engine pass at essentially the same price. A 50%
risk-reduction step turned into 9 simultaneous full losses, tripping the "consecutive
losses >= 3" circuit breaker and halting the algo for the day.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from algo.trading.exit_engine import ExitEngine


@pytest.fixture
def mock_config():
    return {
        "min_hold_days": 1,
        "max_hold_days": 60,
        "eight_week_rule_threshold_pct": 20.0,
        "eight_week_rule_window_days": 21,
        "exit_on_distribution_day": True,
        "max_distribution_days": 4,
        "move_be_at_r": 1.0,
        "chandelier_atr_mult": 3.0,
        "use_chandelier_trail": False,
        "exit_on_td_sequential": False,
        "exit_on_rs_line_break_50dma": False,
        "require_target_pullback": True,
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
    }


def _evaluate(mock_config, cur_price, entry_price, last_partial_exit_date=None, partial_exits_log=None):
    # Patch stays active through _evaluate_position(): the ExitStrategyChain constructs a
    # fresh ExitEngine(self.config) internally for several strategies (MinerviniBreak, etc.)
    # before reaching the distribution check, and that construction needs TradeExecutor mocked too.
    # MinerviniBreakStrategy runs before the distribution check and queries technical_data_daily
    # directly - mock a "no break" row (price comfortably above both SMA-50 and EMA-21) so the
    # chain falls through to the distribution check under test.
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (
        float(cur_price) - 5,  # sma_50, well below cur_price -> no clean break
        float(cur_price) - 5,  # ema_21, well below cur_price -> no EMA break
        1000,  # vol
        1000,  # avg_vol_50
    )
    with patch("algo.trading.exit_engine.TradeExecutor"):
        engine = ExitEngine(mock_config)
        return engine._evaluate_position(
            cur=mock_cur,
            symbol="LPG",
            current_date=date(2026, 7, 27),
            cur_price=cur_price,
            prev_close=cur_price,
            entry_price=entry_price,
            active_stop=Decimal("39.34"),  # real risk-defined stop, far below entry
            init_stop=Decimal("39.34"),
            t1_price=Decimal("55.02"),
            t2_price=Decimal("60.00"),
            t3_price=Decimal("65.00"),
            target_hits=0,
            days_held=3,
            dist_days_today=7,  # > max_distribution_days=4
            last_partial_exit_date=last_partial_exit_date,
            partial_exits_log=partial_exits_log,
        )


class TestDistributionDayBreakevenGate:
    def test_distribution_day_below_breakeven_does_not_raise_stop_above_current_price(self, mock_config):
        """The core bug: a position still below entry_price must NOT have its stop raised to
        entry_price on a distribution-day trigger - that would put the stop above the current
        price and guarantee an immediate full stop-out on the next pass."""
        decision = _evaluate(mock_config, cur_price=Decimal("45.32"), entry_price=Decimal("45.61"))

        assert decision["stage"] == "distribution"
        assert decision["fraction"] == 0.5
        assert decision["new_stop"] == Decimal("39.34"), (
            f"stop must stay at the real risk-defined stop when the position hasn't reached "
            f"breakeven yet, got {decision['new_stop']}"
        )

    def test_distribution_day_at_or_above_breakeven_still_raises_stop(self, mock_config):
        """Sanity check: the fix must not disable the breakeven raise entirely - a position
        already at or above entry_price should still get its stop raised to lock in the gain."""
        decision = _evaluate(mock_config, cur_price=Decimal("46.00"), entry_price=Decimal("45.61"))

        assert decision["stage"] == "distribution"
        assert decision["fraction"] == 0.5
        assert decision["new_stop"] == Decimal("45.61"), "stop should raise to breakeven when already profitable"

    def test_distribution_day_does_not_refire_same_day_already_reduced(self, mock_config):
        """A second, third, etc. exit-engine pass on the SAME day must not re-trigger the
        distribution reduction again - confirmed live 2026-07-27: 7 positions were each cut by
        50% three separate times in one day (all logged under the same last_partial_exit_date),
        compounding down to ~12.5% of their original size from what should have been a single
        one-time de-risking action."""
        decision = _evaluate(
            mock_config,
            cur_price=Decimal("45.32"),
            entry_price=Decimal("45.61"),
            last_partial_exit_date=date(2026, 7, 27),  # same as current_date in _evaluate
            partial_exits_log="14.5sh @ $45.32 (Market distribution: 7 dist days > 4  - reducing 50%, stop raised to breakeven, -0.05R)",
        )

        # None means "no action" (nothing else should trigger in this scenario either) -
        # see check_and_execute_exits' `if not exit_signal:` guard.
        assert decision is None, (
            f"distribution must not fire again the same day it already reduced this position, got {decision}"
        )

    def test_distribution_day_refires_on_a_new_day(self, mock_config):
        """Sanity check: the guard is per-day, not permanent - a later day should still be able
        to trigger a fresh distribution-day reduction if the condition persists."""
        decision = _evaluate(
            mock_config,
            cur_price=Decimal("45.32"),
            entry_price=Decimal("45.61"),
            last_partial_exit_date=date(2026, 7, 24),  # an earlier day, not the current_date
            partial_exits_log="14.5sh @ $45.32 (Market distribution: 7 dist days > 4  - reducing 50%, stop raised to breakeven, -0.05R)",
        )

        assert decision["stage"] == "distribution"
