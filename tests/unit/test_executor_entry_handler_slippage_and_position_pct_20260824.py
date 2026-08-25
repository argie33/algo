#!/usr/bin/env python3
"""Regression tests for two previously-zero-coverage EntryHandler helpers (continuing the
2026-08-24 test-coverage-completeness sweep - see [[exit_engine_t1_t2_t3_verified_and_tested_20260824]]
and [[exit_strategies_new_stop_silently_dropped_fixed_20260824]] in memory, which found a real
bug via this same technique on exit_engine.py):

- _recalculate_targets_for_slippage: recomputes T1/T2/T3 target prices from the ACTUAL fill
  price (not the planned entry price) after slippage, using the same R-multiple convention as
  exit_engine.py (target = executed_price + risk_per_share * R). Direct P&L impact - wrong
  targets here mean the position's profit-taking legs (see the T1/T2/T3 tests) fire at the
  wrong prices for the entire life of the trade.
- _calculate_position_size_pct: shares * price / portfolio_value * 100, with fail-fast guards
  on missing/invalid portfolio value.

Neither was referenced by name in any existing test file.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from algo.trading.executor_entry_handler import EntryHandler


def _handler():
    ctx = MagicMock()
    ctx.t1_target_r_multiple = 1.5
    ctx.t2_target_r_multiple = 3.0
    ctx.t3_target_r_multiple = 4.0
    return EntryHandler(ctx)


class TestRecalculateTargetsForSlippage:
    def test_targets_recalculated_from_executed_price_on_slippage(self):
        """Filled $0.50 higher than planned - targets must be based on the actual fill and
        actual risk (executed_price - stop), not the originally planned entry_price."""
        handler = _handler()
        t1, t2, t3 = handler._recalculate_targets_for_slippage(
            executed_price=Decimal("100.50"),
            entry_price=Decimal("100.00"),
            stop_loss_price=Decimal("90.00"),
        )
        # actual_risk_per_share = 100.50 - 90.00 = 10.50
        assert t1 == Decimal("116.25")  # 100.50 + 10.50*1.5
        assert t2 == Decimal("132.00")  # 100.50 + 10.50*3
        assert t3 == Decimal("142.50")  # 100.50 + 10.50*4

    def test_no_slippage_matches_planned_entry_geometry(self):
        handler = _handler()
        t1, t2, t3 = handler._recalculate_targets_for_slippage(
            executed_price=Decimal("100.00"),
            entry_price=Decimal("100.00"),
            stop_loss_price=Decimal("90.00"),
        )
        assert t1 == Decimal("115.00")
        assert t2 == Decimal("130.00")
        assert t3 == Decimal("140.00")

    def test_negative_slippage_still_computes_from_actual_fill(self):
        """Filled LOWER than planned (better fill) - risk_per_share shrinks, so targets
        should be tighter (closer to the fill) than the originally planned geometry."""
        handler = _handler()
        t1, t2, t3 = handler._recalculate_targets_for_slippage(
            executed_price=Decimal("99.00"),
            entry_price=Decimal("100.00"),
            stop_loss_price=Decimal("90.00"),
        )
        # actual_risk_per_share = 99.00 - 90.00 = 9.00
        assert t1 == Decimal("112.50")  # 99.00 + 9.00*1.5
        assert t2 == Decimal("126.00")  # 99.00 + 9.00*3
        assert t3 == Decimal("135.00")  # 99.00 + 9.00*4

    def test_degenerate_stop_at_or_above_fill_falls_back_to_entry_price(self):
        """If the fill price ends up AT or BELOW the stop-loss (actual_risk_per_share <= 0 -
        a bad/invalid fill), there's no valid R-multiple geometry to compute - all three
        targets fall back to entry_price rather than dividing by a non-positive risk."""
        handler = _handler()
        t1, t2, t3 = handler._recalculate_targets_for_slippage(
            executed_price=Decimal("89.00"),  # filled BELOW the stop
            entry_price=Decimal("100.00"),
            stop_loss_price=Decimal("90.00"),
        )
        assert t1 == t2 == t3 == Decimal("100.00")

    def test_zero_risk_fallback_also_uses_entry_price(self):
        handler = _handler()
        t1, t2, t3 = handler._recalculate_targets_for_slippage(
            executed_price=Decimal("90.00"),  # filled exactly AT the stop
            entry_price=Decimal("100.00"),
            stop_loss_price=Decimal("90.00"),
        )
        assert t1 == t2 == t3 == Decimal("100.00")


class TestCalculatePositionSizePct:
    def test_basic_calculation(self):
        handler = _handler()
        pct = handler._calculate_position_size_pct(
            shares=Decimal("100"), price=Decimal("50.00"), portfolio_value=Decimal("100000")
        )
        assert pct == Decimal("5.00")

    def test_rounds_to_two_decimal_places(self):
        handler = _handler()
        pct = handler._calculate_position_size_pct(
            shares=Decimal("1000"), price=Decimal("5.7321"), portfolio_value=Decimal("10000")
        )
        # 1000 * 5.7321 / 10000 * 100 = 57.321 -> 57.32
        assert pct == Decimal("57.32")

    def test_none_portfolio_value_raises(self):
        handler = _handler()
        with pytest.raises(ValueError, match="Portfolio value is None"):
            handler._calculate_position_size_pct(shares=Decimal("100"), price=Decimal("50"), portfolio_value=None)

    def test_zero_portfolio_value_raises(self):
        handler = _handler()
        with pytest.raises(ValueError, match="Cannot calculate position size"):
            handler._calculate_position_size_pct(
                shares=Decimal("100"), price=Decimal("50"), portfolio_value=Decimal("0")
            )

    def test_negative_portfolio_value_raises(self):
        handler = _handler()
        with pytest.raises(ValueError, match="Cannot calculate position size"):
            handler._calculate_position_size_pct(
                shares=Decimal("100"), price=Decimal("50"), portfolio_value=Decimal("-500")
            )
