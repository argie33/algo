"""Regression test (2026-09-07, same bug class/fix as executor_exit_handler.py's
_compute_cumulative_pnl - see 8e0c0ccec/4735a8bc4 - a THIRD independent copy of this logic,
found by grepping the repo for "cumulative_pnl"): _record_closed_positions_exits()'s
multi-leg cumulative_pnl_pct/cumulative_r_multiple used this row's own single-leg
entry_quantity as the cost-basis/risk denominator, understating both for a position that is
BOTH pyramided (2+ legs) AND was exited via multiple partial legs before this catch-up path
ran. Fixed to sum entry_quantity across every leg on the position
(algo_positions.trade_ids_arr) instead.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase9_reconciliation import _record_closed_positions_exits


def _run(closed_row, prior_partial_pnl, total_entry_qty):
    mock_read_cur = MagicMock()
    mock_read_cur.fetchall.return_value = [closed_row]
    mock_read_ctx = MagicMock()
    mock_read_ctx.__enter__.return_value = mock_read_cur
    mock_read_ctx.__exit__.return_value = False

    mock_write_cur = MagicMock()
    mock_write_cur.rowcount = 1
    mock_write_cur.fetchone.side_effect = [
        (150.0,),  # price_daily close price
        (Decimal(str(prior_partial_pnl)),),  # COALESCE(SUM(prior_partial), 0)
        (Decimal(str(total_entry_qty)),),  # SUM(entry_quantity) across trade_ids_arr
        (150.0,),  # verify exit_price was written
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

    return mock_write_cur


def test_multi_leg_cumulative_pct_uses_summed_position_qty_not_first_leg_qty():
    # leg's own entry_quantity=100 (columns: symbol, entry_price, position_qty,
    # stop_loss_price, entry_qty, trade_id, current_price, position_id), but the true
    # position spans 150 shares across 2 pyramid legs (avg_entry_price=11.67 already
    # correct via ap.avg_entry_price). T1 already realized +$300 on a different leg.
    # exit_price is resolved from the mocked price_daily EOD close (150.0) below, not the
    # row's own current_price field.
    closed_row = ("AAPL", 11.67, 150, 10.0, 100, 456, 20.0, "POS-321")

    write_cur = _run(closed_row, prior_partial_pnl=300.0, total_entry_qty=150.0)

    update_calls = [c for c in write_cur.execute.call_args_list if "UPDATE algo_trades" in str(c.args[0])]
    assert len(update_calls) == 1
    params = update_calls[0].args[1]
    # params: (run_date, exit_price, pnl_dollars, pnl_pct, r_multiple, exit_reason, ...)
    # pnl_dollars this leg: (150-11.67)*100 = 13833; cumulative = 300 + 13833 = 14133
    cumulative_pnl_pct = params[3]
    # Against the TRUE 150-share cost basis (11.67*150=1750.5), not 100 shares (1167.0).
    assert cumulative_pnl_pct == round(14133.0 / (11.67 * 150) * 100, 2)
    assert cumulative_pnl_pct != round(14133.0 / (11.67 * 100) * 100, 2)  # the pre-fix bug


def test_single_leg_no_prior_partial_unaffected():
    """No prior partial legs (prior_partial_pnl == 0) - must not query for a total and
    must use the simple single-leg formula unchanged."""
    closed_row = ("AAPL", 50.0, 100, 45.0, 100, 456, 55.0, "POS-1")

    write_cur = _run(closed_row, prior_partial_pnl=0.0, total_entry_qty=100.0)

    # Only 3 fetchone calls consumed (price, prior_partial=0, verify) - the qty-sum query
    # must not have run at all.
    assert write_cur.fetchone.call_count == 3
