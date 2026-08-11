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


def _stdout_mock(lines=()):
    """The reader thread does `for line in proc.stdout` then `proc.stdout.close()` - a plain
    iter() has no .close(), so use a MagicMock with __iter__ wired to the given lines."""
    stdout = MagicMock()
    stdout.__iter__.return_value = iter(lines)
    return stdout


class TestMarkLoaderFailedAfterCrash:
    def test_marks_every_table_the_loader_owns(self):
        module = _load_scheduler_module()
        mock_manager = MagicMock()
        with (
            patch.object(module, "all_tables", return_value=["table_a", "table_b"]) as mock_all_tables,
            patch.object(module, "LoaderStatusManager", return_value=mock_manager) as mock_ctor,
        ):
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
    """NOTE 2026-08-11: run_pipeline() switched from subprocess.run() to subprocess.Popen()
    (see local_loader_scheduler.py's tail-capture fix) so a crash's real output could be
    attached to the failure message instead of a bare "exit code N". These tests mock
    subprocess.Popen accordingly - the process's stdout must be an iterable (the reader
    thread does `for line in pipe`) and wait() takes the place of run()'s returncode/
    TimeoutExpired."""

    def test_nonzero_exit_marks_loader_failed(self):
        module = _load_scheduler_module()
        mock_proc = MagicMock()
        mock_proc.stdout = _stdout_mock([])
        mock_proc.wait.return_value = 1
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", return_value=mock_proc),
            patch.object(module, "_mark_loader_failed_after_crash") as mock_mark,
        ):
            rc = module.run_pipeline("test_pipeline")

        assert rc == 1
        mock_mark.assert_called_once()
        assert mock_mark.call_args.args[0] == "load_trend_analysis.py"
        assert "exit" in mock_mark.call_args.args[1] or "1" in mock_mark.call_args.args[1]

    def test_timeout_marks_loader_failed(self):
        module = _load_scheduler_module()
        mock_proc = MagicMock()
        mock_proc.stdout = _stdout_mock([])
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="x", timeout=1), 0]
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", return_value=mock_proc),
            patch.object(module, "_mark_loader_failed_after_crash") as mock_mark,
        ):
            rc = module.run_pipeline("test_pipeline")

        assert rc == 1
        mock_mark.assert_called_once()
        assert mock_mark.call_args.args[0] == "load_trend_analysis.py"
        assert "timed out" in mock_mark.call_args.args[1]
        mock_proc.kill.assert_called_once()

    def test_success_does_not_mark_failed(self):
        module = _load_scheduler_module()
        mock_proc = MagicMock()
        mock_proc.stdout = _stdout_mock([])
        mock_proc.wait.return_value = 0
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", return_value=mock_proc),
            patch.object(module, "_mark_loader_failed_after_crash") as mock_mark,
        ):
            rc = module.run_pipeline("test_pipeline")

        assert rc == 0
        mock_mark.assert_not_called()

    def test_failure_message_includes_captured_output_tail(self):
        """The whole point of the Popen switch: a crash's real stdout/stderr output must
        reach data_loader_status.error_message, not just a bare exit code."""
        module = _load_scheduler_module()
        mock_proc = MagicMock()
        mock_proc.stdout = _stdout_mock(["Traceback (most recent call last):\n", "ValueError: boom\n"])
        mock_proc.wait.return_value = 1
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", return_value=mock_proc),
            patch.object(module, "_mark_loader_failed_after_crash") as mock_mark,
        ):
            module.run_pipeline("test_pipeline")

        mock_mark.assert_called_once()
        message = mock_mark.call_args.args[1]
        assert "ValueError: boom" in message


class TestChildLoaderTimeoutMatchesScheduler:
    """FIX 2026-08-10: loaders/runner.py enforces its own process-level watchdog
    (LOADER_TIMEOUT_MINUTES env var, default 120 min) completely independent of this
    scheduler's own per-loader subprocess.run(timeout=...) budget. A same-day fix bumped
    LOADER_TIMEOUTS["enhanced_quality_growth"] to 150 min, but that never mattered - live-
    reproduced: the loader's own inner watchdog fired first at the stale 120 min default,
    silently making the outer-timeout fix a no-op. The scheduler must propagate its own
    per-loader budget into the child's LOADER_TIMEOUT_MINUTES env var so the two can never
    drift apart again."""

    def test_env_carries_matching_timeout_minutes(self):
        module = _load_scheduler_module()
        mock_proc = MagicMock()
        mock_proc.stdout = _stdout_mock([])
        mock_proc.wait.return_value = 0
        # "trend_analysis" -> 15 * 60 = 900s in LOADER_TIMEOUTS
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", return_value=mock_proc) as mock_popen,
        ):
            module.run_pipeline("test_pipeline")

        assert mock_proc.wait.call_args.kwargs["timeout"] == 900
        assert mock_popen.call_args.kwargs["env"]["LOADER_TIMEOUT_MINUTES"] == "15"

    def test_env_carries_matching_timeout_for_the_loader_that_hit_this_bug(self):
        """Direct regression for the live-reproduced case: enhanced_quality_growth's
        scheduler budget (200 min as of 2026-08-10's margin bump over the original 150 min -
        LOADER_TIMEOUTS is local to run_pipeline(), not importable, so this value must be
        kept in sync with that dict by hand) must reach its child process instead of the
        runner's stale 120 min default, because nothing used to propagate the real budget
        through."""
        module = _load_scheduler_module()
        mock_proc = MagicMock()
        mock_proc.stdout = _stdout_mock([])
        mock_proc.wait.return_value = 0
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["enhanced_quality_growth"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module, "_check_loader_dependencies", return_value=True),
            patch.object(module.subprocess, "Popen", return_value=mock_proc) as mock_popen,
        ):
            module.run_pipeline("test_pipeline")

        assert mock_proc.wait.call_args.kwargs["timeout"] == 200 * 60
        assert mock_popen.call_args.kwargs["env"]["LOADER_TIMEOUT_MINUTES"] == "200"
