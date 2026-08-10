"""Regression test for the 2026-08-10 fix: ValueQualityGrowthMetricsLoader.run() used to
write symbols_loaded=len(symbols) / completion_pct=100.0 to data_loader_status unconditionally,
completely discarding the symbols_succeeded/symbols_failed counters it had just computed. Every
run - a full-universe run with a real partial failure rate, or a tiny scoped --symbols
diagnostic run that failed every symbol it touched - reported perfect 100% completion. Since
mark_completed() re-reads exactly those two columns to decide COMPLETED vs FAILED, this made
that safety check a permanent no-op for value_metrics/quality_metrics/growth_metrics.

Fixed to report the real success ratio and pass the loader's own declared max_fail_rate (20%)
as mark_completed()'s threshold, instead of silently faking a perfect run.
"""

from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    loader._watermark = MagicMock()
    return loader


def _row(symbol, available):
    value_row = {"symbol": symbol, "data_unavailable": not available, "reason": None if available else "no_data"}
    quality_row = {"symbol": symbol, "data_unavailable": False, "reason": None, "updated_at": "2026-08-10"}
    growth_row = {"symbol": symbol, "data_unavailable": False, "reason": None, "updated_at": "2026-08-10"}
    return (value_row, quality_row, growth_row)


class TestCompletionReflectsRealOutcome:
    def test_partial_failure_reports_real_completion_pct_not_100(self):
        loader = _make_loader()
        symbols = ["AAA", "BBB", "CCC", "DDD"]
        # 1 of 4 fails (25% failure) - within max_fail_rate (20%)? No - deliberately exceeds it
        # so the test also proves min_completion_pct is wired from max_fail_rate, not defaulted.
        rows = [_row("AAA", True), _row("BBB", True), _row("CCC", True), _row("DDD", False)]

        with (
            patch.object(loader, "fetch_incremental", side_effect=lambda s, since: [rows[symbols.index(s)]]),
            patch.object(loader, "_insert_value_metrics"),
            patch.object(loader, "_insert_quality_metrics"),
            patch.object(loader, "_insert_growth_metrics"),
            patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx,
            patch("utils.loaders.config.get_default_parallelism", return_value=1),
        ):
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = (1,)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            captured_managers = {}

            def fake_status_manager(table_name):
                mgr = MagicMock()
                captured_managers[table_name] = mgr
                return mgr

            with patch(
                "loaders.load_value_quality_growth_metrics.LoaderStatusManager",
                side_effect=fake_status_manager,
            ):
                result = loader.run(symbols)

        assert result["symbols_succeeded"] == 3
        assert result["symbols_failed"] == 1

        quality_mgr = captured_managers["quality_metrics"]
        quality_mgr.update_progress.assert_called_once()
        kwargs = quality_mgr.update_progress.call_args.kwargs
        assert kwargs["symbols_loaded"] == 3, "must report the real succeeded count, not len(symbols)"
        assert kwargs["symbol_count"] == 4
        assert kwargs["completion_pct"] == 75.0, "must be the real 3/4 ratio, not a hardcoded 100.0"

        quality_mgr.mark_completed.assert_called_once()
        completed_kwargs = quality_mgr.mark_completed.call_args.kwargs
        assert completed_kwargs["symbols_failed"] == 1
        # max_fail_rate = 20.0 on this loader -> min_completion_pct must be 80.0, not the
        # generic 98.0 default that would wrongly reject this loader's normal operating range.
        assert completed_kwargs["min_completion_pct"] == 80.0

    def test_full_success_still_reports_100_pct(self):
        loader = _make_loader()
        symbols = ["AAA", "BBB"]
        rows = [_row("AAA", True), _row("BBB", True)]

        with (
            patch.object(loader, "fetch_incremental", side_effect=lambda s, since: [rows[symbols.index(s)]]),
            patch.object(loader, "_insert_value_metrics"),
            patch.object(loader, "_insert_quality_metrics"),
            patch.object(loader, "_insert_growth_metrics"),
            patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx,
            patch("utils.loaders.config.get_default_parallelism", return_value=1),
        ):
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = (1,)
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            captured_managers = {}

            def fake_status_manager(table_name):
                mgr = MagicMock()
                captured_managers[table_name] = mgr
                return mgr

            with patch(
                "loaders.load_value_quality_growth_metrics.LoaderStatusManager",
                side_effect=fake_status_manager,
            ):
                loader.run(symbols)

        kwargs = captured_managers["value_metrics"].update_progress.call_args.kwargs
        assert kwargs["symbols_loaded"] == 2
        assert kwargs["completion_pct"] == 100.0
