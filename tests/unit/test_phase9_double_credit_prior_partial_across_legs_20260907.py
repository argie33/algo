"""Regression test (2026-09-07, real-money-readiness audit): _record_closed_positions_exits()
processes one row per still-open leg of a pyramided position in a single batch (the
CROSS JOIN LATERAL UNNEST(ap.trade_ids_arr) query yields N rows for an N-leg position). The
prior_partial_pnl lookup is scoped only by symbol+action_date, not by trade_id/position, so
without dedup every leg of the SAME position in the same batch re-queries and re-adds the
identical prior partial P&L into that leg's own profit_loss_dollars - double/triple-counting
the prior partial exactly N times when profit_loss_dollars is later summed across the
position's algo_trades rows. Fixed via `positions_credited_partial_pnl`: only the first leg
of a given position_id in the batch gets the prior partial; every subsequent leg gets 0.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase9_reconciliation import _record_closed_positions_exits


def test_prior_partial_pnl_credited_only_once_per_position_in_batch():
    # Two legs of the SAME pyramided position (position_id="POS-321") both untouched,
    # both appear in this batch.
    row_leg1 = ("AAPL", 11.67, 150, 10.0, 100, 456, 20.0, "POS-321")
    row_leg2 = ("AAPL", 11.67, 150, 10.0, 50, 457, 20.0, "POS-321")

    mock_read_cur = MagicMock()
    mock_read_cur.fetchall.return_value = [row_leg1, row_leg2]
    mock_read_ctx = MagicMock()
    mock_read_ctx.__enter__.return_value = mock_read_cur
    mock_read_ctx.__exit__.return_value = False

    mock_write_cur = MagicMock()
    mock_write_cur.rowcount = 1
    mock_write_cur.fetchone.side_effect = [
        (150.0,),  # leg1: price_daily close
        (Decimal("300.0"),),  # leg1: prior partial P&L (credited once)
        (Decimal("150.0"),),  # leg1: SUM(entry_quantity) across trade_ids_arr
        (150.0,),  # leg1: verify exit_price was written
        (150.0,),  # leg2: price_daily close
        # leg2 must NOT query prior_partial or qty-sum again - it's already credited,
        # so prior_partial_pnl=0 short-circuits both.
        (150.0,),  # leg2: verify exit_price was written
    ]
    mock_write_ctx = MagicMock()
    mock_write_ctx.__enter__.return_value = mock_write_cur
    mock_write_ctx.__exit__.return_value = False

    ctx_instances = [mock_read_ctx, mock_write_ctx]

    def fake_database_context(role):
        return ctx_instances.pop(0)

    with (
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=fake_database_context),
        patch("algo.orchestrator.phase9_reconciliation.acquire_advisory_lock"),
        patch("algo.orchestrator.phase9_reconciliation.release_advisory_lock"),
    ):
        _record_closed_positions_exits({}, date(2026, 7, 24), MagicMock())

    update_calls = [c for c in mock_write_cur.execute.call_args_list if "UPDATE algo_trades" in str(c.args[0])]
    assert len(update_calls) == 2

    leg1_pnl_dollars = update_calls[0].args[1][2]
    leg2_pnl_dollars = update_calls[1].args[1][2]
    # leg1: (150-11.67)*100 = 13833; + prior partial 300 = 14133
    assert leg1_pnl_dollars == 14133.0
    # leg2: (150-11.67)*50 = 6916.5; prior partial must be 0 here (already credited to leg1),
    # not another +300 - that's the double-count bug this test guards against.
    assert leg2_pnl_dollars == 6916.5

    audit_log_queries = [c for c in mock_write_cur.execute.call_args_list if "algo_audit_log" in str(c.args[0])]
    assert len(audit_log_queries) == 1, "prior-partial audit_log lookup must run at most once per position in a batch"
