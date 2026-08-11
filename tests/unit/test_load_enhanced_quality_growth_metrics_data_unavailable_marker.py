"""Regression test for two 2026-08-09 fixes to
EnhancedQualityGrowthMetricsLoader.run():

1. fetch_incremental() returns a truthy {"data_unavailable": True, "reason": ...} marker
   dict (not an empty list) for a symbol with no annual_income_statement history - e.g. a
   REIT symbol mid-refetch. Before this fix, `if not metrics:` only caught an empty list,
   so the marker dict fell through to the growth_fields/quality_fields extraction, found no
   matching keys, executed no UPDATE, and yet still incremented symbols_succeeded - a symbol
   with zero real data written was silently counted as a success. Same bug class as
   earnings_calendar's fetch-failure placeholder rows fooling Phase 8.

2. mark_completed() was called bare (no current_run_* overrides) against the shared
   quality_metrics/growth_metrics status rows also written by
   load_value_quality_growth_metrics.py, so its internal completion safety-check re-read
   THAT OTHER loader's counts instead of this run's own. Fixed by passing this run's real
   symbols_succeeded/attempted counts explicitly.
"""

from unittest.mock import MagicMock, patch

from loaders.load_enhanced_quality_growth_metrics import EnhancedQualityGrowthMetricsLoader


def _loader() -> EnhancedQualityGrowthMetricsLoader:
    loader = EnhancedQualityGrowthMetricsLoader.__new__(EnhancedQualityGrowthMetricsLoader)
    loader._backfill_days = 0
    loader._watermark = MagicMock()
    loader._watermark.get_current_watermark.return_value = None
    return loader


def _run_with_fetch_results(fetch_results: dict, symbols: list[str]):
    loader = _loader()

    def fake_fetch_incremental(symbol, since_date=None):
        return fetch_results[symbol]

    write_cur = MagicMock()

    def fake_db_context(mode, **kwargs):
        ctx = MagicMock()
        ctx.__enter__.return_value = write_cur
        ctx.__exit__.return_value = False
        return ctx

    status_managers: dict[str, MagicMock] = {}

    def fake_status_manager(table_name):
        mgr = MagicMock()
        status_managers[table_name] = mgr
        return mgr

    with (
        patch.object(loader, "fetch_incremental", side_effect=fake_fetch_incremental),
        patch("loaders.load_enhanced_quality_growth_metrics.DatabaseContext", side_effect=fake_db_context),
        patch("loaders.load_enhanced_quality_growth_metrics.LoaderStatusManager", side_effect=fake_status_manager),
    ):
        stats = loader.run(symbols, parallelism=1)

    return stats, write_cur, status_managers


class TestDataUnavailableMarkerNotCountedAsSuccess:
    def test_data_unavailable_marker_counts_as_failure_not_success(self):
        fetch_results = {
            "GOOD": [{"symbol": "GOOD", "gross_margin_trend": 1.5, "earnings_surprise_avg": 0.02}],
            "UDR": [{"symbol": "UDR", "data_unavailable": True, "reason": "no_historical_data"}],
        }
        stats, write_cur, _ = _run_with_fetch_results(fetch_results, ["GOOD", "UDR"])

        assert stats["symbols_failed"] == 1
        # Only GOOD's fields should have produced an UPDATE; UDR's marker dict must not.
        calls = write_cur.execute.call_args_list
        assert any("UPDATE growth_metrics" in call.args[0] for call in calls)
        assert all("UDR" not in call.args[1] for call in calls)

    def test_all_symbols_unavailable_does_not_report_success(self):
        fetch_results = {
            "UDR": [{"symbol": "UDR", "data_unavailable": True, "reason": "no_historical_data"}],
            "BFS": [{"symbol": "BFS", "data_unavailable": True, "reason": "no_historical_data"}],
        }
        stats, write_cur, status_managers = _run_with_fetch_results(fetch_results, ["UDR", "BFS"])

        assert stats["symbols_failed"] == 2
        write_cur.execute.assert_not_called()
        # Both shared status rows must be marked failed, not completed.
        for table in ("quality_metrics", "growth_metrics"):
            status_managers[table].mark_completed.assert_not_called()
            status_managers[table].mark_failed.assert_called_once()


class TestMarkCompletedUsesOwnRunCounts:
    def test_mark_completed_passes_this_runs_own_counts(self):
        fetch_results = {
            "GOOD": [{"symbol": "GOOD", "gross_margin_trend": 1.5}],
        }
        _, _, status_managers = _run_with_fetch_results(fetch_results, ["GOOD"])

        for table in ("quality_metrics", "growth_metrics"):
            status_managers[table].mark_completed.assert_called_once_with(
                current_run_symbols_loaded=1,
                current_run_symbol_count=1,
            )
