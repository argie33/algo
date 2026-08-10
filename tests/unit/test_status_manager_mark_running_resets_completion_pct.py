"""Regression test: mark_running() must reset completion_pct/symbols_loaded to 0.

Bug (found 2026-08-10, live DB evidence): mark_running()'s no-symbol_count UPDATE branch
left completion_pct/symbols_loaded entirely untouched, and the symbol_count branch reset
symbols_loaded but not completion_pct. A loader that calls mark_running() and then
crashes/hangs before its first update_progress() call (technical_data_daily, live-
reproduced) leaves a self-contradictory row: status=RUNNING with completion_pct/
symbols_loaded still showing 100%/full-count carried over from the PRIOR successful run.
orchestrator.py's proactive-wait keys off completion_pct, so this read as "critical loader
stalled at 100% complete ... appears hung" - a false, misleading alarm - instead of an
honest "0% - just started" signal for a run that hasn't done any real work yet.
"""

from unittest.mock import MagicMock, patch

from utils.loaders.status_manager import LoaderStatusManager


def _make_manager() -> LoaderStatusManager:
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__.return_value = MagicMock()
        mock_db_ctx.return_value.__exit__.return_value = False
        return LoaderStatusManager(table_name="technical_data_daily")


def test_mark_running_without_symbol_count_resets_completion_pct():
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.fetchone.return_value = ("COMPLETED",)
        mock_cur.rowcount = 1

        manager.mark_running()

        update_call = mock_cur.execute.call_args_list[-1]
        sql_text = update_call[0][0]
        assert "completion_pct = 0" in sql_text
        assert "symbols_loaded = 0" in sql_text


def test_mark_running_with_symbol_count_resets_completion_pct():
    manager = _make_manager()
    with patch("utils.loaders.status_manager.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_db_ctx.return_value.__enter__.return_value = mock_cur
        mock_db_ctx.return_value.__exit__.return_value = False
        mock_cur.fetchone.return_value = ("COMPLETED",)
        mock_cur.rowcount = 1

        manager.mark_running(symbol_count=10549)

        update_call = mock_cur.execute.call_args_list[-1]
        sql_text = update_call[0][0]
        assert "completion_pct = 0" in sql_text
        assert "symbols_loaded = 0" in sql_text
