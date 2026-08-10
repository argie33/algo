"""Regression test for the 2026-08-10 fix: OptimalLoader._update_final_status()'s
is_symbol_based=False branch used the table's entire ALL-TIME row count as
`symbols_loaded`, compared against expected_symbols (the single "market" pseudo-symbol,
always 1 for market-wide loaders like MarketStatusDailyLoader).

Live-confirmed on market_health_daily: total_rows=1314 (one row per day across years of
history), expected_symbols=1 -> completion_pct = min(1314/1*100, 100.0) = 100.0%,
symbols_loaded=1314 written to data_loader_status. Logged by the orchestrator's proactive
critical-loader wait as "Critical loader 'market_health_daily' stalled at 100.0% complete
(1314/1 symbols)" - a nonsensical ratio, not an honest per-run signal, on every single run
regardless of whether that run's own fetch actually succeeded.

Fixed by scoping the count to rows matching the latest watermark value (this run's data),
matching the is_symbol_based=True branch's existing pattern of scoping to what THIS run
actually touched rather than the table's unscoped historical population.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from utils.optimal_loader import OptimalLoader


def _make_loader(table_name="market_health_daily"):
    loader = OptimalLoader.__new__(OptimalLoader)
    loader.table_name = table_name
    loader.watermark_field = "date"
    loader.is_symbol_based = False
    loader._execution_start_time = None
    return loader


def _run_update_final_status(loader, expected_symbols, count_and_max_row, scoped_count_row):
    read_cur = MagicMock()
    read_cur.fetchone.side_effect = [count_and_max_row, scoped_count_row]
    write_cur = MagicMock()

    def fake_db_context(mode, **kwargs):
        ctx = MagicMock()
        ctx.__enter__.return_value = read_cur if mode == "read" else write_cur
        ctx.__exit__.return_value = False
        return ctx

    with patch("utils.optimal_loader.DatabaseContext", side_effect=fake_db_context), \
         patch("utils.db.pooled_context_var.get_pooled_connection", return_value=None), \
         patch("utils.db.pooled_context_var.set_pooled_connection"):
        loader._update_final_status(expected_symbols, ["market"])

    return read_cur, write_cur


class TestNonSymbolBasedCompletionScoped:
    def test_scoped_query_filters_to_latest_watermark(self):
        """The second read query must scope to the latest watermark value, not recount
        the whole table."""
        loader = _make_loader()
        latest = date(2026, 8, 10)
        read_cur, _ = _run_update_final_status(
            loader,
            expected_symbols=1,
            count_and_max_row=(1314, latest),
            scoped_count_row=(1,),
        )

        assert read_cur.execute.call_count == 2
        scoped_query, scoped_params = read_cur.execute.call_args_list[1].args
        assert "WHERE date = %s" in scoped_query
        assert scoped_params == (latest,)

    def test_symbols_loaded_reflects_this_run_not_all_time_history(self):
        """The regression itself: symbols_loaded must reflect today's row (1), not the
        table's entire 1314-row history."""
        loader = _make_loader()
        latest = date(2026, 8, 10)
        _, write_cur = _run_update_final_status(
            loader,
            expected_symbols=1,
            count_and_max_row=(1314, latest),
            scoped_count_row=(1,),
        )

        upsert_params = next(
            call.args[1]
            for call in write_cur.execute.call_args_list
            if len(call.args) > 1 and "INSERT INTO data_loader_status " in call.args[0]
        )
        # row_count (2nd param) still reflects the true all-time table size.
        assert upsert_params[1] == 1314
        # completion_pct (6th param) and symbols_loaded (8th param) reflect this run's
        # scoped result (1/1 = 100%), not the unscoped 1314/1 = 131400%-capped-to-100%
        # that happened to look identical on completion_pct alone but wrote a garbage
        # symbols_loaded=1314 into the same row.
        completion_pct = upsert_params[5]
        symbols_loaded = upsert_params[7]
        assert completion_pct == 100.0
        assert symbols_loaded == 1

    def test_missing_todays_row_marks_failed_not_stale_success(self):
        """If no row exists yet for the latest watermark (e.g. fetch wrote to a
        different date than MAX() found), the safety check must see 0/1 = 0% and mark
        FAILED - not silently report a stale all-time row count as if it were a
        successful current run (the pre-fix behavior: 1314/1 always read as 100% no
        matter what actually happened this run)."""
        loader = _make_loader()
        latest = date(2026, 8, 10)
        _, write_cur = _run_update_final_status(
            loader,
            expected_symbols=1,
            count_and_max_row=(1314, latest),
            scoped_count_row=(0,),
        )

        upsert_params = next(
            call.args[1]
            for call in write_cur.execute.call_args_list
            if len(call.args) > 1 and "INSERT INTO data_loader_status " in call.args[0]
        )
        status, completion_pct, symbols_loaded = upsert_params[3], upsert_params[5], upsert_params[7]
        assert status == "FAILED"
        assert completion_pct == 0.0
        assert symbols_loaded == 0
