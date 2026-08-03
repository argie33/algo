"""Regression test for the 2026-07-27 fix: load_trend_analysis.py's module-level
_update_loader_status() (a standalone loader, not on the OptimalLoader/StatusManager
class hierarchy) updated data_loader_status on COMPLETED/FAILED but never archived to
data_loader_status_history - the same gap already fixed for utils/optimal_loader.py and
loaders/load_prices.py. trend_template_data is read directly by Phase 1's freshness check,
so this loader's failure history was invisible to the dashboard's failure-pattern analysis.

Fixed by adding the same SAVEPOINT-wrapped archive INSERT + 100-row retention DELETE.
"""

from unittest.mock import MagicMock, patch

from loaders.load_trend_analysis import _update_loader_status


class TestTrendAnalysisStatusHistoryArchiving:
    def test_completed_status_archives_to_history(self):
        cur = MagicMock()
        # First fetchone: safety check (symbol_count, symbols_loaded, completion_pct)
        # Second fetchone: archive query (7 columns)
        cur.fetchone.side_effect = [(10, 10, 100.0), (None, None, None, 500, 100.0, 10, 10)]
        cur.rowcount = 1  # Status manager checks rowcount

        with (
            patch("loaders.load_trend_analysis.DatabaseContext") as mock_ctx,
            patch("utils.loaders.status_manager.DatabaseContext") as mock_status_ctx,
        ):
            mock_ctx.return_value.__enter__.return_value = cur
            mock_status_ctx.return_value.__enter__.return_value = cur
            _update_loader_status("COMPLETED")

        executed = [call.args[0] for call in cur.execute.call_args_list]
        assert any("SAVEPOINT archive_trend_template_data_history" in sql for sql in executed)
        assert any("INSERT INTO data_loader_status_history" in sql for sql in executed)
        assert any("DELETE FROM data_loader_status_history" in sql for sql in executed)
        assert any("RELEASE SAVEPOINT archive_trend_template_data_history" in sql for sql in executed)
        assert any("UPDATE data_loader_status" in sql for sql in executed)

    def test_failed_status_archives_to_history(self):
        cur = MagicMock()
        # First fetchone: safety check (symbol_count, symbols_loaded, completion_pct)
        # Second fetchone: archive query (7 columns)
        cur.fetchone.side_effect = [(10, 0, 0.0), (None, None, "error", 0, 0.0, 0, 10)]
        cur.rowcount = 1  # Status manager checks rowcount

        with (
            patch("loaders.load_trend_analysis.DatabaseContext") as mock_ctx,
            patch("utils.loaders.status_manager.DatabaseContext") as mock_status_ctx,
        ):
            mock_ctx.return_value.__enter__.return_value = cur
            mock_status_ctx.return_value.__enter__.return_value = cur
            _update_loader_status("FAILED", error_message="upstream timeout")

        executed = [call.args[0] for call in cur.execute.call_args_list]
        assert any("INSERT INTO data_loader_status_history" in sql for sql in executed)

    def test_archive_failure_rolls_back_savepoint_without_raising(self):
        cur = MagicMock()
        cur.rowcount = 1  # Status manager checks rowcount
        # First fetchone: safety check (symbol_count, symbols_loaded, completion_pct)
        cur.fetchone.return_value = (10, 10, 100.0)

        def _execute(sql, *args, **kwargs):
            if "INSERT INTO data_loader_status_history" in sql:
                raise Exception("boom")

        cur.execute.side_effect = _execute

        with (
            patch("loaders.load_trend_analysis.DatabaseContext") as mock_ctx,
            patch("utils.loaders.status_manager.DatabaseContext") as mock_status_ctx,
        ):
            mock_ctx.return_value.__enter__.return_value = cur
            mock_status_ctx.return_value.__enter__.return_value = cur
            _update_loader_status("COMPLETED")  # must not raise

        executed = [call.args[0] for call in cur.execute.call_args_list]
        assert any("ROLLBACK TO SAVEPOINT archive_trend_template_data_history" in sql for sql in executed)
        assert any("UPDATE data_loader_status" in sql for sql in executed)

    def test_running_status_does_not_touch_history(self):
        cur = MagicMock()
        cur.rowcount = 1

        with (
            patch("loaders.load_trend_analysis.DatabaseContext") as mock_ctx,
            patch("utils.loaders.status_manager.DatabaseContext") as mock_status_ctx,
        ):
            mock_ctx.return_value.__enter__.return_value = cur
            mock_status_ctx.return_value.__enter__.return_value = cur
            _update_loader_status("RUNNING")

        executed = [call.args[0] for call in cur.execute.call_args_list]
        assert not any("data_loader_status_history" in sql for sql in executed)

    def test_invalid_status_raises(self):
        with (
            patch("loaders.load_trend_analysis.DatabaseContext"),
            patch("utils.loaders.status_manager.DatabaseContext"),
        ):
            try:
                _update_loader_status("BOGUS")
                raise AssertionError("expected ValueError")
            except ValueError:
                pass
