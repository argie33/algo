"""Regression test for the 2026-08-16 fix: OptimalLoader._update_final_status() only ever
wrote data_loader_status for self.table_name, never for self.output_tables (secondary tables
written by the same loader run, e.g. load_risk_metrics_daily.py's
output_tables = ["momentum_metrics", "stability_metrics"]).

Live-confirmed impact: stability_metrics stuck at consecutive_failures=5,
last_success_at=2026-08-12 while its sibling momentum_metrics (same loader, same run)
correctly showed consecutive_failures=0, last_success_at=2026-08-13 - a false-positive
"unhealthy" flag on the dashboard for a loader that was actually fine.

Fixed by looping the same UPSERT (reusing this run's own already-computed loader_status/
completion_pct/symbols_loaded) over [self.table_name] + self.output_tables.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from utils.optimal_loader import OptimalLoader


def _make_loader(table_name="momentum_metrics", output_tables=None):
    loader = OptimalLoader.__new__(OptimalLoader)
    loader.table_name = table_name
    loader.watermark_field = "date"
    loader.is_symbol_based = True
    loader._execution_start_time = None
    if output_tables is not None:
        loader.output_tables = output_tables
    return loader


def _run_update_final_status(loader, actual_symbols_loaded, expected_symbols):
    read_cur = MagicMock()
    read_cur.fetchone.return_value = (5000, date(2026, 8, 16), actual_symbols_loaded)
    write_cur = MagicMock()

    def fake_db_context(mode, **kwargs):
        ctx = MagicMock()
        ctx.__enter__.return_value = read_cur if mode == "read" else write_cur
        ctx.__exit__.return_value = False
        return ctx

    with (
        patch("utils.optimal_loader.DatabaseContext", side_effect=fake_db_context),
        patch("utils.db.pooled_context_var.get_pooled_connection", return_value=None),
        patch("utils.db.pooled_context_var.set_pooled_connection"),
    ):
        loader._update_final_status(expected_symbols)

    return write_cur


def _upsert_calls(write_cur):
    return [
        call.args
        for call in write_cur.execute.call_args_list
        if len(call.args) > 1 and "INSERT INTO data_loader_status " in call.args[0]
    ]


class TestOutputTablesStatusPropagation:
    def test_no_output_tables_writes_only_primary(self):
        loader = _make_loader(table_name="price_daily")
        write_cur = _run_update_final_status(loader, actual_symbols_loaded=4900, expected_symbols=5000)

        calls = _upsert_calls(write_cur)
        assert len(calls) == 1
        assert calls[0][1][0] == "price_daily"

    def test_output_tables_each_get_their_own_upsert(self):
        loader = _make_loader(table_name="momentum_metrics", output_tables=["momentum_metrics", "stability_metrics"])
        write_cur = _run_update_final_status(loader, actual_symbols_loaded=4900, expected_symbols=5000)

        calls = _upsert_calls(write_cur)
        table_names = [args[1][0] for args in calls]
        assert table_names == ["momentum_metrics", "stability_metrics"]

    def test_output_tables_share_primary_verdict_on_success(self):
        loader = _make_loader(table_name="momentum_metrics", output_tables=["momentum_metrics", "stability_metrics"])
        write_cur = _run_update_final_status(loader, actual_symbols_loaded=4900, expected_symbols=5000)

        for args in _upsert_calls(write_cur):
            assert "COMPLETED" in args[1][3]  # loader_status param

    def test_output_tables_share_primary_verdict_on_failure(self):
        loader = _make_loader(table_name="momentum_metrics", output_tables=["momentum_metrics", "stability_metrics"])
        write_cur = _run_update_final_status(loader, actual_symbols_loaded=1000, expected_symbols=5000)

        for args in _upsert_calls(write_cur):
            assert "FAILED" in args[1][3]  # loader_status param

    def test_table_name_never_duplicated_when_included_in_output_tables(self):
        # Some loaders may (redundantly) list their own table_name inside output_tables -
        # must not produce two UPSERTs for the primary table.
        loader = _make_loader(
            table_name="momentum_metrics",
            output_tables=["momentum_metrics", "stability_metrics"],
        )
        write_cur = _run_update_final_status(loader, actual_symbols_loaded=4900, expected_symbols=5000)

        table_names = [args[1][0] for args in _upsert_calls(write_cur)]
        assert table_names.count("momentum_metrics") == 1
