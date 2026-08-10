"""Regression test for a fail-open bug in scripts/run_loader.py's --force-refresh path.

Bug (found 2026-08-10): after running a loader, main() unconditionally called
LoaderStatusManager(table_name).mark_completed() for every output table whenever
--force-refresh was passed, with zero inspection of the loader's own result. Most loaders
(OptimalLoader subclasses) already call their own mark_completed()/mark_failed() internally
based on real completion_pct - so this blindly clobbered a legitimate mark_failed() the loader
itself had just recorded, back to COMPLETED. main() also always returned exit code 0 as long
as no exception propagated, and Phase 1's failsafe retry (the only caller that passes
--force-refresh) decides "recovered" from that exit code - so a loader that correctly detected
and reported a real failure was reported as both COMPLETED in the DB and "recovered" to the
caller: a fail-open, fabricate-success bug in the safety-critical stale-data recovery path.

Fixed: only apply the fallback mark_completed() when the table is still RUNNING (the loader
doesn't self-manage status at all); otherwise respect the loader's own terminal status, and
return exit code 1 if that status isn't a success state.
"""

import sys
from unittest.mock import MagicMock, patch

import scripts.run_loader as run_loader_module


def _run_main_with_force_refresh(loader_arg="technical"):
    argv = ["run_loader.py", loader_arg, "--force-refresh"]
    with patch.object(sys, "argv", argv):
        return run_loader_module.main()


class TestForceRefreshRespectsLoaderOwnStatus:
    def test_loader_that_self_reported_failed_is_not_clobbered_to_completed(self):
        """The core bug: a loader whose own run() already called mark_failed() must not be
        overwritten back to COMPLETED, and the process must exit non-zero."""
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "FAILED"}

        with (
            patch.object(run_loader_module, "get_loader_class_for_file", return_value=MagicMock()),
            patch.object(run_loader_module, "run_loader_generic", return_value={"symbols_failed": 100}),
            patch.object(run_loader_module, "update_watermarks_to_today"),
            patch("utils.loaders.status_manager.LoaderStatusManager", return_value=mock_status_mgr),
        ):
            exit_code = _run_main_with_force_refresh("technical")

        mock_status_mgr.mark_completed.assert_not_called()
        assert exit_code == 1

    def test_loader_still_running_after_run_gets_fallback_completed(self):
        """A loader that never self-manages status (still RUNNING after run() returns) still
        gets the fallback mark_completed() - this is the safety net for legacy loaders that
        would otherwise be stuck RUNNING forever."""
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "RUNNING"}

        with (
            patch.object(run_loader_module, "get_loader_class_for_file", return_value=MagicMock()),
            patch.object(run_loader_module, "run_loader_generic", return_value={"symbols_processed": 100}),
            patch.object(run_loader_module, "update_watermarks_to_today"),
            patch("utils.loaders.status_manager.LoaderStatusManager", return_value=mock_status_mgr),
        ):
            exit_code = _run_main_with_force_refresh("technical")

        mock_status_mgr.mark_completed.assert_called_once()
        assert exit_code == 0

    def test_loader_that_self_reported_completed_is_left_alone(self):
        """A loader that already reached COMPLETED on its own must not get a second,
        redundant mark_completed() call."""
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "COMPLETED"}

        with (
            patch.object(run_loader_module, "get_loader_class_for_file", return_value=MagicMock()),
            patch.object(run_loader_module, "run_loader_generic", return_value={"symbols_processed": 100}),
            patch.object(run_loader_module, "update_watermarks_to_today"),
            patch("utils.loaders.status_manager.LoaderStatusManager", return_value=mock_status_mgr),
        ):
            exit_code = _run_main_with_force_refresh("technical")

        mock_status_mgr.mark_completed.assert_not_called()
        assert exit_code == 0
