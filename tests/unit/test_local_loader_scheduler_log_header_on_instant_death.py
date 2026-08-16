"""Regression test: a subprocess that dies before writing any output must not leave a 0-byte
per-loader log file.

Gap found 2026-08-16: live-observed price_daily/stock_scores (and other loaders) each produced
several 0-byte log files across a ~4h window during an active company_info_sec backfill -
run_pipeline()'s tee-capture thread only wrote lines as they streamed from the child, so a
subprocess killed or crashed before its first line of output left nothing in the log at all.
This defeated the entire point of the tee-capture mechanism added 2026-08-11, whose stated goal
was making failures diagnosable from the log file rather than a bare exit code - a 0-byte file
is indistinguishable from "never ran". Fixed by writing a header (command, pid, start time)
immediately when the log file is opened, before blocking on the child's output.
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = REPO_ROOT / "logs"


def _load_scheduler_module():
    spec = importlib.util.spec_from_file_location(
        "local_loader_scheduler_under_test_log_header", REPO_ROOT / "scripts" / "local_loader_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stdout_mock(lines=()):
    stdout = MagicMock()
    stdout.__iter__.return_value = iter(lines)
    return stdout


class TestLogHeaderOnInstantDeath:
    def test_zero_output_child_still_leaves_a_non_empty_diagnosable_log(self) -> None:
        module = _load_scheduler_module()
        mock_proc = MagicMock()
        mock_proc.pid = 999999
        mock_proc.stdout = _stdout_mock([])  # child produced zero lines before dying
        mock_proc.wait.return_value = 1

        # Fixed, collision-proof epoch so this test's log filename can never clash with
        # another test in the same suite run creating a load_trend_analysis_*.log in the
        # same wall-clock second (both this file and test_local_loader_scheduler_marks_
        # failed_on_crash.py use the "trend_analysis" loader for the same reason).
        fixed_epoch = 1735689600  # 2025-01-01T00:00:00Z - not a real run, safe sentinel
        expected_log_path = LOGS_DIR / f"load_trend_analysis_{fixed_epoch}.log"
        expected_log_path.unlink(missing_ok=True)

        try:
            with (
                patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis"]}),
                patch.object(module, "reap_stale_running_loaders", return_value=[]),
                patch.object(module.subprocess, "Popen", return_value=mock_proc),
                patch.object(module, "_mark_loader_failed_after_crash"),
                patch.object(module.time, "time", return_value=fixed_epoch),
            ):
                module.run_pipeline("test_pipeline")

            assert expected_log_path.exists(), "expected a log file at the fixed test epoch"
            content = expected_log_path.read_text(encoding="utf-8")
            assert content != "", "log file must not be empty even when the child wrote nothing"
            assert "cmd=" in content
            assert "pid=999999" in content
        finally:
            expected_log_path.unlink(missing_ok=True)

    def test_mock_popen_with_non_int_pid_does_not_leak_magicmock_repr_into_log(self) -> None:
        """Regression for a bug in the header fix itself, found the same day: tests/unit/
        test_local_loader_scheduler_direct_invocation.py mocks subprocess.Popen for every real
        loader name (including company_info_sec) to exercise run_pipeline()'s full shorthand
        coverage - proc.pid on that mock is a MagicMock, not an int. Live-observed: this wrote
        a confusing `pid=<MagicMock name='mock.pid' id=...>` line into a REAL-looking
        logs/load_company_info_sec_*.log file, worse than the pre-header-fix behavior (a
        harmless 0-byte file) for exactly the scenario the header fix was meant to help with.
        """
        module = _load_scheduler_module()
        mock_proc = MagicMock()  # proc.pid is a MagicMock attribute here, not patched to an int
        mock_proc.stdout = _stdout_mock([])
        mock_proc.wait.return_value = 1

        fixed_epoch = 1735689601  # distinct sentinel from the test above, same safe non-real date
        expected_log_path = LOGS_DIR / f"load_trend_analysis_{fixed_epoch}.log"
        expected_log_path.unlink(missing_ok=True)

        try:
            with (
                patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis"]}),
                patch.object(module, "reap_stale_running_loaders", return_value=[]),
                patch.object(module.subprocess, "Popen", return_value=mock_proc),
                patch.object(module, "_mark_loader_failed_after_crash"),
                patch.object(module.time, "time", return_value=fixed_epoch),
            ):
                module.run_pipeline("test_pipeline")

            content = expected_log_path.read_text(encoding="utf-8")
            assert "MagicMock" not in content, f"MagicMock repr leaked into a diagnostic log file: {content!r}"
            assert "pid=<unknown>" in content
        finally:
            expected_log_path.unlink(missing_ok=True)
