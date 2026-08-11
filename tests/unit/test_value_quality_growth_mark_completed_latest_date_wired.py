"""Regression test for the 2026-08-10 fix: ValueQualityGrowthMetricsLoader.run() computed
actual_latest_date (MAX(updated_at) per table) but never passed it to mark_completed() -
data_loader_status.latest_date silently never refreshed for value_metrics/quality_metrics/
growth_metrics on any run. The variable was also a bare loop-local (not captured per-table),
so even a naive fix would have used whichever table was queried LAST for all 3 mark_completed()
calls. Fixed by capturing each table's own MAX(updated_at) into a per-table dict, mirroring the
existing per_table_counts pattern for symbols_succeeded/symbols_failed.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    loader._watermark = MagicMock()
    return loader


def _row(symbol):
    row = {"symbol": symbol, "data_unavailable": False, "reason": None, "updated_at": "2026-08-10"}
    return (row, row, row)


class TestMarkCompletedLatestDateWired:
    def test_each_table_gets_its_own_max_updated_at_date(self):
        loader = _make_loader()
        symbols = ["AAA"]
        rows = [_row("AAA")]

        # Distinguish the MAX(updated_at) query from any other fetchone() call (e.g. the
        # today_count verification COUNT(*) query) by its distinctive SQL text, so this
        # doesn't depend on knowing the exact total call count of every fetchone() in run().
        max_updated_at_dates = iter([date(2026, 8, 8), date(2026, 8, 9), date(2026, 8, 10)])

        def fake_fetchone():
            last_call = mock_cur.execute.call_args
            query_text = last_call.args[0] if last_call and last_call.args else ""
            if "MAX(updated_at)" in query_text:
                return (next(max_updated_at_dates),)
            return (1,)

        with (
            patch.object(loader, "fetch_incremental", side_effect=lambda s, since: [rows[symbols.index(s)]]),
            patch.object(loader, "_insert_value_metrics"),
            patch.object(loader, "_insert_quality_metrics"),
            patch.object(loader, "_insert_growth_metrics"),
            patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx,
            patch("utils.loaders.config.get_default_parallelism", return_value=1),
        ):
            mock_cur = MagicMock()
            mock_cur.fetchone.side_effect = fake_fetchone
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

        value_kwargs = captured_managers["value_metrics"].mark_completed.call_args.kwargs
        quality_kwargs = captured_managers["quality_metrics"].mark_completed.call_args.kwargs
        growth_kwargs = captured_managers["growth_metrics"].mark_completed.call_args.kwargs

        assert value_kwargs["latest_date"] == date(2026, 8, 8), "must not be None (the pre-fix bug)"
        assert quality_kwargs["latest_date"] == date(2026, 8, 9)
        assert growth_kwargs["latest_date"] == date(2026, 8, 10)
        # The core bug: reusing one bare loop variable would make all 3 equal the LAST
        # queried table's date (growth_metrics, 08-10) instead of each table's own.
        assert value_kwargs["latest_date"] != growth_kwargs["latest_date"]
        assert quality_kwargs["latest_date"] != growth_kwargs["latest_date"]
