#!/usr/bin/env python3
"""Regression tests for the 2026-07-21 multi-leg exit P&L aggregation fix.

Bug: a position closed via multiple partial exits (T1/T2 profit-taking before a final
stop/target exit) had algo_trades.profit_loss_dollars/pct/exit_r_multiple set from ONLY
the final leg's remaining shares, silently discarding every dollar realized on earlier
partial exits. ExitHandler._compute_cumulative_pnl() now sums this leg's P&L with
every prior partial exit's P&L (recorded per-leg in algo_audit_log) before the trade is
marked closed.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from algo.trading.executor_exit_handler import ExitHandler


def _make_handler() -> ExitHandler:
    return object.__new__(ExitHandler)


def _cur_with_prior_partial_sum(total: float) -> MagicMock:
    cur = MagicMock()
    cur.fetchone.return_value = (Decimal(str(total)),)
    return cur


class TestComputeCumulativePnl:
    def test_no_prior_partials_returns_single_leg_values_unchanged(self):
        """The common case (single, full exit - no partial legs before it) must be a no-op."""
        handler = _make_handler()
        cur = _cur_with_prior_partial_sum(0)

        pnl_dollars, pnl_pct, r_multiple = handler._compute_cumulative_pnl(
            cur,
            trade_id=1,
            symbol="AAPL",
            pnl_dollars=150.0,
            pnl_pct=3.0,
            r_multiple=1.5,
            entry_price=50.0,
            entry_qty=100,
            risk_per_share=Decimal("2.0"),
            full_exit=True,
            is_estimated_price=False,
        )

        assert pnl_dollars == 150.0
        assert pnl_pct == 3.0
        assert r_multiple == 1.5

    def test_partial_exit_call_returns_single_leg_values_unchanged(self):
        """A partial exit (full_exit=False) has no final total to report yet - must not
        query the DB or aggregate anything."""
        handler = _make_handler()
        cur = MagicMock()

        pnl_dollars, pnl_pct, r_multiple = handler._compute_cumulative_pnl(
            cur,
            trade_id=1,
            symbol="AAPL",
            pnl_dollars=80.0,
            pnl_pct=4.0,
            r_multiple=2.0,
            entry_price=50.0,
            entry_qty=100,
            risk_per_share=Decimal("2.0"),
            full_exit=False,
            is_estimated_price=False,
        )

        assert pnl_dollars == 80.0
        assert pnl_pct == 4.0
        assert r_multiple == 2.0
        cur.execute.assert_not_called()

    def test_estimated_price_returns_single_leg_values_unchanged(self):
        """An unreconciled estimated fill must not aggregate - P&L is deferred entirely
        until reconciliation with the real broker fill (existing NULL-storage behavior)."""
        handler = _make_handler()
        cur = MagicMock()

        pnl_dollars, pnl_pct, r_multiple = handler._compute_cumulative_pnl(
            cur,
            trade_id=1,
            symbol="AAPL",
            pnl_dollars=0.0,
            pnl_pct=0.0,
            r_multiple=0.0,
            entry_price=50.0,
            entry_qty=100,
            risk_per_share=Decimal("2.0"),
            full_exit=True,
            is_estimated_price=True,
        )

        assert (pnl_dollars, pnl_pct, r_multiple) == (0.0, 0.0, 0.0)
        cur.execute.assert_not_called()

    def test_multi_leg_exit_sums_pnl_across_all_legs(self):
        """The core bug: 100-share position, T1 took 40sh profit (+$200 already realized,
        recorded in algo_audit_log), final leg closes remaining 60sh at breakeven ($0 this
        leg). Total realized must be +$200, not $0."""
        handler = _make_handler()
        cur = _cur_with_prior_partial_sum(200.0)  # prior partial leg's pnl_dollars

        pnl_dollars, pnl_pct, r_multiple = handler._compute_cumulative_pnl(
            cur,
            trade_id=42,
            symbol="AAPL",
            pnl_dollars=0.0,  # final 60sh leg exited at breakeven
            pnl_pct=0.0,
            r_multiple=0.0,
            entry_price=50.0,
            entry_qty=100,  # ORIGINAL full position size, not the remaining 60sh
            risk_per_share=Decimal("2.0"),
            full_exit=True,
            is_estimated_price=False,
        )

        assert pnl_dollars == 200.0  # not $0 - the pre-fix bug
        # pct/r_multiple computed against the ORIGINAL 100-share cost basis/risk, not
        # just the final leg's 60 shares.
        assert pnl_pct == pytest.approx(4.0)  # 200 / (50*100) * 100
        assert r_multiple == pytest.approx(1.0)  # 200 / (2.0*100)

    def test_multi_leg_exit_with_loss_on_final_leg(self):
        """T1 took profit (+$300), final leg stops out at a loss (-$100) - net must be
        the correct sum (+$200), not just the final leg's loss."""
        handler = _make_handler()
        cur = _cur_with_prior_partial_sum(300.0)

        pnl_dollars, pnl_pct, r_multiple = handler._compute_cumulative_pnl(
            cur,
            trade_id=7,
            symbol="MSFT",
            pnl_dollars=-100.0,
            pnl_pct=-2.0,
            r_multiple=-0.5,
            entry_price=100.0,
            entry_qty=50,
            risk_per_share=Decimal("4.0"),
            full_exit=True,
            is_estimated_price=False,
        )

        assert pnl_dollars == 200.0
        assert pnl_pct == pytest.approx(4.0)  # 200 / (100*50) * 100
        assert r_multiple == pytest.approx(1.0)  # 200 / (4.0*50)

    def test_query_scopes_to_this_trade_id_and_partial_legs_only(self):
        """The aggregation query must filter by this specific trade_id and exclude any
        already-recorded full-exit row (there should never be one prior to this call, but
        the filter must be explicit, not incidental)."""
        handler = _make_handler()
        cur = _cur_with_prior_partial_sum(50.0)

        handler._compute_cumulative_pnl(
            cur,
            trade_id=99,
            symbol="TSLA",
            pnl_dollars=10.0,
            pnl_pct=1.0,
            r_multiple=0.5,
            entry_price=200.0,
            entry_qty=10,
            risk_per_share=Decimal("5.0"),
            full_exit=True,
            is_estimated_price=False,
        )

        executed_sql, params = cur.execute.call_args[0]
        assert "trade_id" in executed_sql
        assert "full_exit" in executed_sql
        assert params == (99,)
