"""Regression test for the 2026-07-27 fix: OptimalLoader._update_final_status() hardcoded a
90% completion threshold for every subclass, ignoring each subclass's own declared
max_fail_rate (already used elsewhere in this file to gate the load itself, e.g.
"max_fail_rate = getattr(self, 'max_fail_rate', 60.0)" in _run_sequential).

ConsolidatedFinancialStatementsLoader (quarterly_balance_sheet, quarterly_income_statement)
declares max_fail_rate=15.0 because ADRs/foreign private issuers file 20-F/6-K instead of
10-Q, so SEC XBRL companyfacts structurally has no quarterly data for them - confirmed live
2026-07-27, both loaders sit permanently at completion_pct~85-86%, exactly at their declared
85% floor (100 - 15). Combined with this same session's fix to write canonical FAILED
(instead of a non-canonical "INCOMPLETE") and increment consecutive_failures, a hardcoded
90% threshold would have made these two loaders show FAILED with consecutive_failures
climbing forever - a permanent false alarm for a loader doing everything it structurally can.

Fixed by using min_completion_pct = 100.0 - getattr(self, "max_fail_rate", 10.0), so the
"COMPLETED vs FAILED" call defers to the same per-loader tolerance the load itself already
respects. Default of 10.0 preserves the original 90% threshold for loaders that never
declared their own max_fail_rate.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from utils.optimal_loader import OptimalLoader


def _make_loader(table_name="test_table", max_fail_rate=None):
    loader = OptimalLoader.__new__(OptimalLoader)
    loader.table_name = table_name
    loader.watermark_field = "date"
    loader.is_symbol_based = True
    loader._execution_start_time = None
    if max_fail_rate is not None:
        loader.max_fail_rate = max_fail_rate
    return loader


def _run_update_final_status(loader, actual_symbols_loaded, expected_symbols):
    read_cur = MagicMock()
    read_cur.fetchone.return_value = (5000, date(2026, 7, 27), actual_symbols_loaded)
    write_cur = MagicMock()

    def fake_db_context(mode, **kwargs):
        ctx = MagicMock()
        ctx.__enter__.return_value = read_cur if mode == "read" else write_cur
        ctx.__exit__.return_value = False
        return ctx

    with patch("utils.optimal_loader.DatabaseContext", side_effect=fake_db_context), \
         patch("utils.db.pooled_context_var.get_pooled_connection", return_value=None), \
         patch("utils.db.pooled_context_var.set_pooled_connection"):
        loader._update_final_status(expected_symbols)

    return write_cur


class TestMaxFailRateCompletionThreshold:
    @staticmethod
    def _upsert_status(write_cur):
        for call in write_cur.execute.call_args_list:
            if len(call.args) > 1 and "INSERT INTO data_loader_status " in call.args[0]:
                return call.args[1]
        raise AssertionError("data_loader_status upsert not found in execute calls")

    def test_default_threshold_marks_86_percent_as_failed(self):
        # No max_fail_rate override -> default 10% tolerance -> 90% floor. 86% < 90%.
        loader = _make_loader()
        write_cur = _run_update_final_status(loader, actual_symbols_loaded=4300, expected_symbols=5000)

        assert "FAILED" in self._upsert_status(write_cur)

    def test_higher_max_fail_rate_marks_86_percent_as_completed(self):
        # max_fail_rate=15.0 -> 85% floor (matches ConsolidatedFinancialStatementsLoader). 86% >= 85%.
        loader = _make_loader(max_fail_rate=15.0)
        write_cur = _run_update_final_status(loader, actual_symbols_loaded=4300, expected_symbols=5000)

        assert "COMPLETED" in self._upsert_status(write_cur)

    def test_higher_max_fail_rate_still_fails_below_its_own_floor(self):
        # max_fail_rate=15.0 -> 85% floor. 70% is still below even the relaxed floor.
        loader = _make_loader(max_fail_rate=15.0)
        write_cur = _run_update_final_status(loader, actual_symbols_loaded=3500, expected_symbols=5000)

        assert "FAILED" in self._upsert_status(write_cur)
