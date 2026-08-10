"""Regression test for the 2026-08-10 fix: ValueQualityGrowthMetricsLoader.run() used to
write symbols_loaded=len(symbols) / completion_pct=100.0 to data_loader_status unconditionally,
completely discarding the symbols_succeeded/symbols_failed counters it had just computed. Every
run - a full-universe run with a real partial failure rate, or a tiny scoped --symbols
diagnostic run that failed every symbol it touched - reported perfect 100% completion. Since
mark_completed() re-reads exactly those two columns to decide COMPLETED vs FAILED, this made
that safety check a permanent no-op for value_metrics/quality_metrics/growth_metrics.

Fixed to report the real success ratio and pass the loader's own declared max_fail_rate (20%)
as mark_completed()'s threshold, instead of silently faking a perfect run.

FOLLOW-UP FIX (same day): the first fix used ONE shared symbols_succeeded/symbols_failed
counter - derived solely from value_row's data_unavailable flag - for all 3 tables'
completion_pct. quality_row/growth_row come from independent source queries and fail
independently in real data (live-confirmed 216 symbols: value_metrics succeeds, growth_metrics
unavailable). Reusing value's counter for quality/growth meant a symbol where only value failed
still silently forced growth_metrics's own completion_pct down even though growth genuinely
succeeded for that symbol - and the reverse: a symbol where only growth failed wouldn't be
reflected in growth_metrics's completion_pct at all if value happened to succeed. Fixed with
per-table counters (quality_succeeded/quality_failed, growth_succeeded/growth_failed) so each
table's own mark_completed() reflects that table's own real outcome.
"""

from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    loader._watermark = MagicMock()
    return loader


def _row(symbol, available, quality_available=True, growth_available=True):
    value_row = {"symbol": symbol, "data_unavailable": not available, "reason": None if available else "no_data"}
    quality_row = {
        "symbol": symbol,
        "data_unavailable": not quality_available,
        "reason": None if quality_available else "no_data",
        "updated_at": "2026-08-10",
    }
    growth_row = {
        "symbol": symbol,
        "data_unavailable": not growth_available,
        "reason": None if growth_available else "no_data",
        "updated_at": "2026-08-10",
    }
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

        # value_metrics: real 3/4 (DDD's value_row failed).
        value_mgr = captured_managers["value_metrics"]
        value_kwargs = value_mgr.update_progress.call_args.kwargs
        assert value_kwargs["symbols_loaded"] == 3, "must report the real succeeded count, not len(symbols)"
        assert value_kwargs["symbol_count"] == 4
        assert value_kwargs["completion_pct"] == 75.0, "must be the real 3/4 ratio, not a hardcoded 100.0"

        value_mgr.mark_completed.assert_called_once()
        value_completed_kwargs = value_mgr.mark_completed.call_args.kwargs
        assert value_completed_kwargs["symbols_failed"] == 1
        # max_fail_rate = 20.0 on this loader -> min_completion_pct must be 80.0, not the
        # generic 98.0 default that would wrongly reject this loader's normal operating range.
        assert value_completed_kwargs["min_completion_pct"] == 80.0

        # quality_metrics: DDD's quality_row itself succeeded (only its value_row failed) - must
        # report 4/4, NOT value's 3/4. Reusing value's counter here is exactly the bug this
        # follow-up fix closes: it would silently misreport quality_metrics's own real outcome.
        quality_mgr = captured_managers["quality_metrics"]
        quality_mgr.update_progress.assert_called_once()
        quality_kwargs = quality_mgr.update_progress.call_args.kwargs
        assert quality_kwargs["symbols_loaded"] == 4, "quality succeeded for all 4 - must not inherit value's failure"
        assert quality_kwargs["completion_pct"] == 100.0
        quality_completed_kwargs = quality_mgr.mark_completed.call_args.kwargs
        assert quality_completed_kwargs["symbols_failed"] == 0
        assert quality_completed_kwargs["min_completion_pct"] == 80.0

    def test_quality_and_growth_track_independently_from_value_and_each_other(self):
        loader = _make_loader()
        symbols = ["AAA", "BBB"]
        # AAA: value ok, quality ok, growth FAILS. BBB: value FAILS, quality FAILS, growth ok.
        # No single shared counter can represent both rows correctly - this is the real-world
        # pattern (216 symbols value-ok/growth-unavailable; 275 value-bad/quality-ok) that the
        # old shared-counter design silently misreported.
        rows = [
            _row("AAA", available=True, quality_available=True, growth_available=False),
            _row("BBB", available=False, quality_available=False, growth_available=True),
        ]

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

        # value: AAA ok, BBB fails -> 1/2 = 50%
        assert captured_managers["value_metrics"].update_progress.call_args.kwargs["completion_pct"] == 50.0
        # quality: AAA ok, BBB fails -> 1/2 = 50% (matches value here, but computed independently)
        assert captured_managers["quality_metrics"].update_progress.call_args.kwargs["completion_pct"] == 50.0
        # growth: AAA fails, BBB ok -> the OPPOSITE symbol failed vs value/quality (which both
        # failed BBB). Same 1/2=50% ratio by coincidence in this fixture, but symbols_failed
        # tracks growth's own failing symbol (AAA), not value/quality's (BBB) - see the first
        # test above for a case where the ratios themselves diverge (4/4 vs 3/4).
        growth_kwargs = captured_managers["growth_metrics"].update_progress.call_args.kwargs
        assert growth_kwargs["completion_pct"] == 50.0
        assert captured_managers["growth_metrics"].mark_completed.call_args.kwargs["symbols_failed"] == 1

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
