"""Regression test: local_loader_scheduler.py must mark a crashed/timed-out loader's own
data_loader_status row(s) FAILED, not just print a warning and abort the pipeline.

Bug (found 2026-08-10, live-reproduced): run_pipeline()'s subprocess.run() call, on a non-zero
exit code OR a subprocess.TimeoutExpired, only printed to stderr and returned 1 - it never
touched data_loader_status. Since mark_running()/mark_completed()/mark_failed() are all called
from INSIDE the loader subprocess itself, a subprocess that crashes or gets killed by the
timeout leaves its table(s) stuck at status=RUNNING indefinitely, with no error_message and no
owning process - only reap_stale_running_loaders()'s 4-hour-later check on the *next* pipeline
invocation would ever correct it. Live-confirmed: quality_metrics/growth_metrics (written by
enhanced_quality_growth) found stuck exactly this way, with data_loader_status showing a fresh
execution_started but the process long gone and rds_locks empty.

Fixed by having run_pipeline() call a small `_mark_loader_failed_after_crash()` helper - looks
up every table the crashed loader owns via loaders.loader_registry.all_tables() and calls
LoaderStatusManager.mark_failed() on each - in both the non-zero-exit and TimeoutExpired
branches.
"""

import importlib.util
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_scheduler_module():
    spec = importlib.util.spec_from_file_location(
        "local_loader_scheduler_under_test", REPO_ROOT / "scripts" / "local_loader_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMarkLoaderFailedAfterCrash:
    def test_marks_every_table_the_loader_owns(self):
        module = _load_scheduler_module()
        mock_manager = MagicMock()
        with patch.object(module, "all_tables", return_value=["table_a", "table_b"]) as mock_all_tables, \
             patch.object(module, "LoaderStatusManager", return_value=mock_manager) as mock_ctor:
            module._mark_loader_failed_after_crash("load_fake.py", "boom")

        mock_all_tables.assert_called_once_with("load_fake.py")
        assert mock_ctor.call_count == 2
        assert mock_ctor.call_args_list[0].args == ("table_a",)
        assert mock_ctor.call_args_list[1].args == ("table_b",)
        assert mock_manager.mark_failed.call_count == 2
        mock_manager.mark_failed.assert_any_call("boom")

    def test_swallows_its_own_errors_without_raising(self):
        """A failure to record the failure must never mask the original crash being reported
        by the caller - run_pipeline() must be able to call this unconditionally."""
        module = _load_scheduler_module()
        with patch.object(module, "all_tables", side_effect=ValueError("unknown loader")):
            module._mark_loader_failed_after_crash("load_unknown.py", "boom")  # must not raise


class TestRunPipelineMarksFailedOnCrash:
    def test_nonzero_exit_marks_loader_failed(self):
        module = _load_scheduler_module()
        mock_result = MagicMock(returncode=1)
        with patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis"]}), \
             patch.object(module, "reap_stale_running_loaders", return_value=[]), \
             patch.object(module.subprocess, "run", return_value=mock_result), \
             patch.object(module, "_mark_loader_failed_after_crash") as mock_mark:
            rc = module.run_pipeline("test_pipeline")

        assert rc == 1
        mock_mark.assert_called_once()
        assert mock_mark.call_args.args[0] == "load_trend_analysis.py"
        assert "exit" in mock_mark.call_args.args[1] or "1" in mock_mark.call_args.args[1]

    def test_timeout_marks_loader_failed(self):
        module = _load_scheduler_module()
        with patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis"]}), \
             patch.object(module, "reap_stale_running_loaders", return_value=[]), \
             patch.object(
                 module.subprocess, "run",
                 side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1),
             ), \
             patch.object(module, "_mark_loader_failed_after_crash") as mock_mark:
            rc = module.run_pipeline("test_pipeline")

        assert rc == 1
        mock_mark.assert_called_once()
        assert mock_mark.call_args.args[0] == "load_trend_analysis.py"
        assert "timed out" in mock_mark.call_args.args[1]

    def test_success_does_not_mark_failed(self):
        module = _load_scheduler_module()
        mock_result = MagicMock(returncode=0)
        with patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis"]}), \
             patch.object(module, "reap_stale_running_loaders", return_value=[]), \
             patch.object(module.subprocess, "run", return_value=mock_result), \
             patch.object(module, "_mark_loader_failed_after_crash") as mock_mark:
            rc = module.run_pipeline("test_pipeline")

        assert rc == 0
        mock_mark.assert_not_called()
