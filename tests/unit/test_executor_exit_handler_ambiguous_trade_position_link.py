#!/usr/bin/env python3
"""Regression test: _fetch_and_lock_trade_data()'s LEFT JOIN keys off
`t.trade_id::text = ANY(p.trade_ids_arr::text[])`, which assumes a trade_id appears in at
most one position's trade_ids_arr. That assumption doesn't hold - live-reproduced 2026-08-19
via GEN/TRD-D9501EE6A4, which position_sync.py's symbol-only "existing position" lookup had
written into BOTH a stale closed position's trade_ids_arr and the real open position's.

With no ORDER BY, plain fetchone() took whichever row Postgres happened to scan first. When
that was the closed position, GUARD 3 in _execute_exit() returned "Position already closed
(idempotency guard)" for a position that was very much open and had just hit its stop -
silently skipping the exit every single orchestrator run that day, with no error surfaced in
algo_exit_check_errors (the caller only ever saw a generic "success": False and logged it,
never an exception to catch and persist).

The fix orders the join so the open position always wins when a trade_id is ambiguously
linked, and logs the ambiguity as a CRITICAL data-integrity finding rather than silently
picking a row.
"""

from unittest.mock import MagicMock

from algo.trading.executor_exit_handler import ExitHandler


def _row(position_id, status):
    # (symbol, entry_price, entry_qty, stop_loss_price, alpaca_order_id,
    #  position_id, quantity, target_levels_hit, status)
    return (
        "GEN",
        29.17,
        73.0,
        24.99,
        None,
        position_id,
        73.0,
        0,
        status,
    )


class TestAmbiguousTradePositionLink:
    def test_prefers_open_position_when_trade_id_linked_to_multiple_positions(self):
        handler = ExitHandler(MagicMock())
        cur = MagicMock()
        # Simulate Postgres returning the closed position's row first - the exact ordering
        # that silently blocked GEN's stop-loss exit before the ORDER BY fix.
        cur.fetchall.return_value = [
            _row("closed-position-uuid", "closed"),
            _row("open-position-uuid", "open"),
        ]

        result = handler._fetch_and_lock_trade_data(cur, "TRD-D9501EE6A4")

        position_id = result[5]
        position_status = result[8]
        assert position_id == "open-position-uuid"
        assert position_status == "open"

    def test_single_matching_position_still_works(self):
        handler = ExitHandler(MagicMock())
        cur = MagicMock()
        cur.fetchall.return_value = [_row("open-position-uuid", "open")]

        result = handler._fetch_and_lock_trade_data(cur, "TRD-SOME-TRADE")

        assert result[5] == "open-position-uuid"
        assert result[8] == "open"

    def test_no_match_raises_runtime_error(self):
        handler = ExitHandler(MagicMock())
        cur = MagicMock()
        cur.fetchall.return_value = []

        import pytest

        with pytest.raises(RuntimeError, match="not found in database"):
            handler._fetch_and_lock_trade_data(cur, "TRD-NONEXISTENT")
