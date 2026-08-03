"""Regression test for the 2026-08-03 fix: OptimalLoader._update_final_status() computed
completion_pct using an UNSCOPED COUNT(DISTINCT symbol) FROM {table_name} - the table's
entire symbol population, not just the symbols this specific run requested.

Harmless for a normal full-universe run (expected_symbols == real population size, so the
ratio stays sane), but a live crash for a --symbols-scoped run (e.g. local dev/test) against
a table an earlier full run already populated broadly: requesting 10 symbols against a table
with 2,816 real distinct symbols computed completion_pct = 2816/10*100 = 28160%, overflowing
the NUMERIC(5,2) completion_pct column in mark_completed()'s later re-check and crashing the
whole run - rolling back the real data this run had just written, since both live in the same
externally-managed transaction. Live-reproduced against load_analyst_earnings_estimates.py
run with --symbols against a table a prior full run had already populated to 2,816 symbols.

Fixed by scoping the COUNT(DISTINCT symbol) subquery to `WHERE symbol = ANY(%s)` using the
symbols list this run actually requested, whenever one was provided.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from utils.optimal_loader import OptimalLoader


def _make_loader(table_name="test_table"):
    loader = OptimalLoader.__new__(OptimalLoader)
    loader.table_name = table_name
    loader.watermark_field = "date"
    loader.is_symbol_based = True
    loader._execution_start_time = None
    return loader


def _run_update_final_status(loader, expected_symbols, symbols, mocked_row):
    read_cur = MagicMock()
    read_cur.fetchone.return_value = mocked_row
    write_cur = MagicMock()

    def fake_db_context(mode, **kwargs):
        ctx = MagicMock()
        ctx.__enter__.return_value = read_cur if mode == "read" else write_cur
        ctx.__exit__.return_value = False
        return ctx

    with patch("utils.optimal_loader.DatabaseContext", side_effect=fake_db_context), \
         patch("utils.db.pooled_context_var.get_pooled_connection", return_value=None), \
         patch("utils.db.pooled_context_var.set_pooled_connection"):
        loader._update_final_status(expected_symbols, symbols)

    return read_cur, write_cur


class TestScopedSymbolsCompletionNoOverflow:
    def test_scoped_run_queries_only_requested_symbols(self):
        """A --symbols-scoped run must scope the distinct-symbol count to those symbols,
        not the table's entire population."""
        loader = _make_loader()
        symbols = ["AAPL", "MSFT", "GOOGL"]
        # Mocked row: (total_rows=2816, latest_date, actual_symbols_loaded=3) - simulating a
        # table a prior full run already populated broadly, but this run only touched 3.
        read_cur, write_cur = _run_update_final_status(
            loader, expected_symbols=3, symbols=symbols, mocked_row=(2816, date(2026, 8, 3), 3)
        )

        read_query, read_params = read_cur.execute.call_args_list[0].args
        assert "WHERE symbol = ANY(%s)" in read_query
        assert read_params == (symbols,)

    def test_scoped_run_does_not_overflow_completion_pct(self):
        """The regression itself: without scoping, a small --symbols run against a broadly
        populated table computed completion_pct in the tens of thousands, overflowing
        NUMERIC(5,2) and crashing mark_completed(). With scoping, completion_pct must stay
        a sane percentage (<=100)."""
        loader = _make_loader()
        symbols = ["AAPL", "MSFT", "GOOGL"]
        # Mocked as if the scoped subquery correctly returned 3 (all requested symbols present),
        # not 2816 (the table's full population) - proves the call site uses the scoped value.
        _, write_cur = _run_update_final_status(
            loader, expected_symbols=3, symbols=symbols, mocked_row=(2816, date(2026, 8, 3), 3)
        )

        upsert_params = next(
            call.args[1]
            for call in write_cur.execute.call_args_list
            if len(call.args) > 1 and "INSERT INTO data_loader_status " in call.args[0]
        )
        # completion_pct is the 6th positional param in the INSERT (see _update_final_status).
        completion_pct = upsert_params[5]
        assert completion_pct <= 100.0
        assert completion_pct == 100.0

    def test_unscoped_full_universe_run_keeps_single_combined_query(self):
        """When no symbols list is passed (normal full-universe run), the original
        single-query shape (one fetchone() call, no WHERE clause) must be preserved."""
        loader = _make_loader()
        read_cur, _ = _run_update_final_status(
            loader, expected_symbols=5000, symbols=None, mocked_row=(5000, date(2026, 8, 3), 4300)
        )

        assert read_cur.execute.call_count == 1
        query = read_cur.execute.call_args_list[0].args[0]
        assert "WHERE symbol = ANY" not in query
