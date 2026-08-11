#!/usr/bin/env python3
"""Regression test for the Session 81 position_sync.py trade_ids_arr corruption fix.

sync_positions_from_trades() re-derives an existing position's trade_ids_arr via
ARRAY_AGG(trade_id) FROM algo_trades WHERE status IN (...) every time Phase 1 runs. Two
bugs combined to silently corrupt good data:

1. The status filter only listed ('filled', 'open'), so a trade sitting in a transitional
   broker status (partially_filled/paper_pending/pending/active) at the instant Phase 1
   ran fell out of the ARRAY_AGG entirely (Postgres ARRAY_AGG returns NULL on zero rows).
2. The code then unconditionally wrote that NULL/empty result into trade_ids_arr, even
   when the position already had a correct, non-empty trade_ids_arr - manufacturing the
   "orphaned trade_ids_arr" fail-closed halt in circuit_breaker.py's total-risk check.

Fixed by (1) using the canonical TradeStatus.all_open() status set, and (2) never writing
an empty ARRAY_AGG result over an existing non-empty trade_ids_arr.
"""

from unittest.mock import MagicMock, patch

from algo.orchestration.position_sync import LINKED_TRADE_STATUSES, sync_positions_from_trades
from utils.trading import TradeStatus


def _queue_side_effect(values, default):
    values = list(values)

    def _side_effect(*_args, **_kwargs):
        return values.pop(0) if values else default

    return _side_effect


class TestLinkedTradeStatusesCoversAllOpenStatuses:
    def test_matches_canonical_trade_status_all_open(self):
        assert set(LINKED_TRADE_STATUSES) == set(TradeStatus.all_open())
        for status in ("partially_filled", "paper_pending", "pending", "active"):
            assert status in LINKED_TRADE_STATUSES, (
                f"{status!r} missing from LINKED_TRADE_STATUSES - a trade in this status "
                "would fall out of the ARRAY_AGG and risk blanking trade_ids_arr"
            )


class TestSyncPreservesTradeIdsArrOnEmptyArrayAgg:
    def test_existing_trade_ids_arr_not_blanked_when_array_agg_finds_nothing(self):
        """If the ARRAY_AGG query (transiently) matches zero trades for a position that
        already has a populated trade_ids_arr, the UPDATE must preserve the existing
        array rather than overwrite it with an empty one."""
        cur = MagicMock()
        cur.rowcount = 0

        # fetchall(): only the top-level "open positions per symbol" query is hit for our
        # single-symbol scenario; every later fetchall() (post-loop reconciliation) defaults to [].
        cur.fetchall.side_effect = _queue_side_effect([[("TEST", 10)]], [])

        trade_row = (100.0, "pos-1", 95.0, None, None, None, None, None, None)
        existing_row = ("pos-1", "open")
        empty_array_agg_result = (None,)  # ARRAY_AGG found zero matching rows
        existing_trade_ids_arr_row = (["old-trade-id"],)

        cur.fetchone.side_effect = _queue_side_effect(
            [trade_row, existing_row, empty_array_agg_result, existing_trade_ids_arr_row],
            None,
        )

        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        with patch("algo.orchestration.position_sync.DatabaseContext", return_value=mock_db_context):
            sync_positions_from_trades()

        update_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_positions SET quantity" in c.args[0]]
        assert update_calls, "expected the existing-position UPDATE to run"
        # Params: (total_qty, 'open', stop_loss_price, 'closed', stop_loss_price,
        # trade_ids_text, trade_ids_arr, existing_id) - trade_ids_arr is index 6, shifted from 5
        # by the 2026-08-10 CASE-guard fix (see position_sync_preserves_raised_stop_...) which
        # added one more positional parameter ('closed', the CASE comparison value).
        written_trade_ids_arr = update_calls[0].args[1][6]  # positional param: trade_ids_arr
        assert written_trade_ids_arr == ["old-trade-id"], (
            f"existing trade_ids_arr must be preserved when ARRAY_AGG returns nothing, got {written_trade_ids_arr!r}"
        )
