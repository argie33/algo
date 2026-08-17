"""Regression test: a loader whose consecutive_failures streak is purely from
reap_stale_running_loaders() marking an abandoned (no owning process alive) run FAILED must
not be permanently skipped by run_pipeline()'s 3+-consecutive-failures circuit breaker.

Bug (live-reproduced 2026-08-16): reap_stale_running_loaders() increments
consecutive_failures and writes an "[REAPED] ..." error_message identically to a real repeated
failure. stability_metrics hit consecutive_failures=6 from one abandoned-run reap cascade
(scheduler process killed mid-run, not a code bug) - every subsequent pipeline run then hit the
"3+ consecutive failures - needs manual fix" branch and skipped it before it ever got a chance
to actually run and self-reset the counter via mark_completed(). Same underlying deadlock class
already fixed once manually for earnings_calendar (see
price_daily_20260814_missing_load_monitor memory) - this generalizes it so it self-heals instead
of requiring a manual consecutive_failures reset every time.
"""

import importlib.util
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_scheduler_module(tmp_path):
    """Load the real scheduler source from a copy under tmp_path, not its real repo location -
    see test_local_loader_scheduler_marks_failed_on_crash.py's _load_scheduler_module for why
    (these tests use "stability_metrics" with real, unmocked wall-clock timestamps, so loading
    straight from the real file leaks a real logs/load_stability_metrics_*.log on every run)."""
    fake_scripts_dir = tmp_path / "scripts"
    fake_scripts_dir.mkdir(parents=True, exist_ok=True)
    fake_module_path = fake_scripts_dir / "local_loader_scheduler.py"
    shutil.copyfile(REPO_ROOT / "scripts" / "local_loader_scheduler.py", fake_module_path)

    spec = importlib.util.spec_from_file_location("local_loader_scheduler_under_test_reaped", fake_module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stdout_mock(lines=()):
    stdout = MagicMock()
    stdout.__iter__.return_value = iter(lines)
    return stdout


def _mock_db_row(failures, error_message):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = (failures, error_message)
    # BUG FIX 2026-08-17: rowcount defaulted to a bare MagicMock attribute here, so
    # status_manager.py's `if cur.rowcount != 1: raise` (real single-row-UPDATE check) always
    # failed, masking this test's real assertion behind an unrelated "Failed to update status"
    # crash - live-reproduced via both tests in this file.
    cur.rowcount = 1
    conn.cursor.return_value = cur
    return conn


class TestReapedFailuresDoNotDeadlock:
    def test_reaped_only_failures_do_not_skip_the_loader(self, tmp_path):
        module = _load_scheduler_module(tmp_path)
        mock_proc = MagicMock()
        mock_proc.stdout = _stdout_mock([])
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        fake_conn = _mock_db_row(
            6, "[REAPED] Stuck in RUNNING since 2026-08-16 11:47:02 UTC (>0.6h ago). No owning process alive."
        )
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["stability_metrics"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", return_value=mock_proc) as mock_popen,
            patch("utils.db.connection.get_db_connection", return_value=fake_conn),
        ):
            rc = module.run_pipeline("test_pipeline")

        assert rc == 0
        mock_popen.assert_called_once()

    def test_genuine_repeated_failures_still_skip_the_loader(self, tmp_path):
        """Same 3+ threshold, but the most recent failure was a real error - must still block,
        this fix must not weaken the original protection for an actually-broken loader."""
        module = _load_scheduler_module(tmp_path)
        fake_conn = _mock_db_row(4, "ValueError: division by zero in stability calc")
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["stability_metrics"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen") as mock_popen,
            patch("utils.db.connection.get_db_connection", return_value=fake_conn),
        ):
            rc = module.run_pipeline("test_pipeline")

        assert rc == 1
        mock_popen.assert_not_called()

    def test_reaped_failures_below_threshold_are_unaffected(self, tmp_path):
        """Sanity check: this fix only changes behavior at/above the 3-failure threshold."""
        module = _load_scheduler_module(tmp_path)
        mock_proc = MagicMock()
        mock_proc.stdout = _stdout_mock([])
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        fake_conn = _mock_db_row(1, "[REAPED] Stuck in RUNNING since ... No owning process alive.")
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["stability_metrics"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", return_value=mock_proc) as mock_popen,
            patch("utils.db.connection.get_db_connection", return_value=fake_conn),
        ):
            rc = module.run_pipeline("test_pipeline")

        assert rc == 0
        mock_popen.assert_called_once()
