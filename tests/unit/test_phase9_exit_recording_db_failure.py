#!/usr/bin/env python3
"""Regression test for phase9_reconciliation._record_closed_positions_exits's handling of
a transient DB failure while recording a closed position's exit.

The SELECT that finds candidates is scoped to `closed_at::date = run_date` (today only).
Previously, a psycopg2 error on the per-symbol UPDATE was caught, rolled back to a
savepoint, and just logged - execution moved on to the next symbol. That silently drops
the position: algo_positions already shows status='closed' (set by an earlier reconciliation
step), but algo_trades.exit_date never gets set, and because the outer SELECT only looks at
today's closures, this symbol will never be re-selected by this function again on any future
run. The trade stays "open" in algo_trades forever while contributing stale valuation to the
local-equity calculation that feeds Phase 9's broker-vs-local P&L variance check - a
permanent, invisible audit-trail gap.

This must instead alert and halt (raise), consistent with this same function's other two
fail-fast checks (missing exit_price, invalid entry_price).
"""

from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from algo.orchestrator.phase9_reconciliation import _record_closed_positions_exits


def _make_read_cursor(rows):
    cur = MagicMock()
    cur.execute.return_value = None
    cur.fetchall.return_value = rows
    return cur


def test_db_error_recording_exit_raises_instead_of_silently_continuing():
    """A transient DB error on the exit-recording UPDATE must halt Phase 9, not be
    swallowed - swallowing it creates a permanent, un-retryable audit-trail gap."""
    # Query returns: symbol, avg_entry_price, quantity, stop_loss_price, entry_quantity, trade_id
    closed_row = ("AAPL", 150.0, 10, 145.0, 10, 123)  # symbol, avg_entry_price, quantity, stop_loss_price, entry_quantity, trade_id
    read_cur = _make_read_cursor([closed_row])

    write_cur = MagicMock()

    def execute_side_effect(sql, params=None):
        if "UPDATE algo_trades" in sql and "exit_date" in sql:
            raise psycopg2.OperationalError("simulated connection drop")
        return None

    write_cur.execute.side_effect = execute_side_effect
    # Mock fetchone() to return proper values for price_daily and audit_log queries
    write_cur.fetchone.side_effect = [
        (150.50,),  # price_daily close (first fetchone call on line 1068)
        (0,),       # prior_partial audit_log sum (second fetchone call on line 1120)
    ]

    def fake_log(*args, **kwargs):
        pass

    with (
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext") as mock_ctx,
        patch("algo.orchestrator.phase9_reconciliation.acquire_advisory_lock"),
        patch("algo.orchestrator.phase9_reconciliation.release_advisory_lock"),
        patch("algo.reporting.notify") as mock_notify,
    ):
        mock_ctx.return_value.__enter__.side_effect = [read_cur, write_cur]
        mock_ctx.return_value.__exit__.return_value = False

        with pytest.raises(RuntimeError, match="AAPL"):
            _record_closed_positions_exits({}, run_date=None, log_phase_result_fn=fake_log)

    # A human must be alerted - this can't just vanish into the logs, since the symbol
    # will never be re-selected by this function again after today.
    assert mock_notify.called, "notify() must be called so a human can fix the audit gap manually"


def test_algo_trades_zero_rowcount_gracefully_continues():
    """After using direct trade_id (not subquery), if algo_trades UPDATE gets rowcount=0,
    it means another process already finalized the trade between our SELECT and UPDATE.
    This is a legitimate race condition, not an error - trade is already closed,
    so we just log and continue with position update. The trade/position is correctly
    finalized; we're just a second process attempting to finalize again."""
    # Query returns: symbol, avg_entry_price, quantity, stop_loss_price, entry_quantity, trade_id
    closed_row = ("AAPL", 150.0, 10, 145.0, 10, 123)  # symbol, avg_entry_price, quantity, stop_loss_price, entry_quantity, trade_id
    read_cur = _make_read_cursor([closed_row])

    write_cur = MagicMock()
    positions_update_reached = []

    def execute_side_effect(sql, params=None):
        if "UPDATE algo_trades" in sql and "exit_date" in sql:
            write_cur.rowcount = 0  # another process already closed the trade
        elif "UPDATE algo_positions" in sql:
            positions_update_reached.append(True)
            write_cur.rowcount = 1
        return None

    write_cur.execute.side_effect = execute_side_effect
    # Mock fetchone() to return proper values for price_daily and audit_log queries
    write_cur.fetchone.side_effect = [
        (150.50,),  # price_daily close (first fetchone call on line 1068)
        (0,),       # prior_partial audit_log sum (second fetchone call on line 1120)
    ]

    def fake_log(*args, **kwargs):
        pass

    with (
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext") as mock_ctx,
        patch("algo.orchestrator.phase9_reconciliation.acquire_advisory_lock"),
        patch("algo.orchestrator.phase9_reconciliation.release_advisory_lock"),
    ):
        mock_ctx.return_value.__enter__.side_effect = [read_cur, write_cur]
        mock_ctx.return_value.__exit__.return_value = False

        # Should NOT raise - should continue gracefully
        _record_closed_positions_exits({}, run_date=None, log_phase_result_fn=fake_log)

    assert positions_update_reached, (
        "algo_positions update should still proceed even if trade was already closed "
        "by another process - both are attempting to finalize the same exit"
    )
