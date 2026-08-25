"""Regression test for a 2026-08-25 fix: ValueQualityGrowthMetricsLoader.run()'s returned
dict never included a "duration_sec" key. loaders/runner.py ALWAYS re-marks the loader's
primary table (loader.table_name = "value_metrics") after run() returns, via its own
generic LoaderStatusManager(loader.table_name).mark_completed(execution_duration_sec=...)
call (~line 449-454), reading the duration from stats.get("duration_sec"). Missing that key
made runner.py's execution_duration resolve to None, clobbering the correct, real duration
this loader's own internal per-table loop had already written for value_metrics moments
earlier - live-confirmed via data_loader_status: value_metrics.execution_duration_sec was
NULL while quality_metrics/growth_metrics (secondary tables - this loader deliberately never
sets output_tables, so runner.py's secondary-table re-mark block never fires for them)
correctly showed a real duration from the same run.

Fixed by adding "duration_sec": execution_duration to the returned dict, matching the key
convention every other runner.py-driven loader's stats dict uses.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    loader._watermark = MagicMock()
    return loader


def _row(symbol: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    row = {"symbol": symbol, "data_unavailable": False, "reason": None, "updated_at": "2026-08-25"}
    return (row, row, row)


class TestDurationSecWiredIntoReturnDict:
    def test_run_returns_duration_sec_key_matching_stats_convention(self) -> None:
        loader = _make_loader()
        symbols = ["AAA"]

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1,)

        with (
            patch.object(loader, "fetch_incremental", side_effect=lambda s, since: [_row(s)]),
            patch.object(loader, "_insert_value_metrics"),
            patch.object(loader, "_insert_quality_metrics"),
            patch.object(loader, "_insert_growth_metrics"),
            patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_db_ctx,
            patch("loaders.load_value_quality_growth_metrics.LoaderStatusManager"),
            patch("utils.loaders.config.get_default_parallelism", return_value=1),
        ):
            mock_db_ctx.return_value.__enter__.return_value = mock_cur
            result = loader.run(symbols)

        # The exact key runner.py's stats.get("duration_sec") reads (loaders/runner.py ~line
        # 358-364) - runner.py re-marks loader.table_name ("value_metrics") unconditionally
        # after run() returns, so this key's absence silently clobbers the correct duration
        # this run() already wrote internally moments earlier.
        assert "duration_sec" in result, "missing this key lets runner.py re-clobber execution_duration_sec to NULL"
        assert isinstance(result["duration_sec"], float)
        assert result["duration_sec"] >= 0.0
