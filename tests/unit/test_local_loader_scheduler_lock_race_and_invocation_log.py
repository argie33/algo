"""Regression test for two real gaps found live 2026-08-16 in
scripts/local_loader_scheduler.py's main():

1. TOCTOU race: the original lock acquisition was `if scheduler_lock.exists(): ... else:
   scheduler_lock.touch()` - two scheduler processes starting within the same window can
   both see no lock and both proceed. Live-observed symptom: overlapping `--now reference`
   and `--now metrics` invocations, where every loader in the second pipeline collided with
   per-loader/per-table locks the first pipeline already held and exited near-instantly with
   zero output - a whole "metrics" batch (including company_info_sec) left 0-byte log files
   at 16:53 and 17:06 that day while a `--now reference` run already held the lock. Fixed by
   using os.open() with O_CREAT|O_EXCL, which is atomic at the OS level.

2. This process's own top-level output (pipeline start, lock rejections) was bare
   print()/stderr with zero persistent capture - only each loader SUBPROCESS's stdout gets
   tee'd to logs/load_*.log inside run_pipeline(). A rejected invocation's "Another scheduler
   instance is already running" message went only to whatever terminal launched it, leaving
   no durable trace anywhere. Fixed by tee-ing stdout/stderr to logs/scheduler_invocations.log
   from the very first line of main(), before the lock check even runs.

Uses tmp_path + monkeypatching tempfile.gettempdir() so this test never touches the real
system temp dir's algo-scheduler.lock - that file may be actively held by a real,
in-progress local loader run on the machine running these tests, and unlinking/racing it
would be a genuinely dangerous side effect for a unit test to risk. Every test that calls
main() also redirects module.__file__ under tmp_path (main()'s Tee writes to
Path(__file__).parent.parent / "logs") and restores sys.stdout/sys.stderr afterward - main()
overwrites those module-globally, and leaving them pointed at a file handle under a
since-cleaned-up tmp_path would leak into every later test in the same pytest process.
"""

import importlib.util
import io
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_scheduler_module():
    spec = importlib.util.spec_from_file_location(
        "local_loader_scheduler_under_test_lockrace", REPO_ROOT / "scripts" / "local_loader_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def scheduler_module(tmp_path):
    """A freshly-loaded module instance with __file__ redirected under tmp_path, so main()'s
    logs_dir = Path(__file__).parent.parent / "logs" never touches the real repo's logs/
    directory. Restores the real sys.stdout/sys.stderr on teardown regardless of what
    main() did to them.
    """
    module = _load_scheduler_module()
    (tmp_path / "scripts").mkdir(exist_ok=True)
    module.__file__ = str(tmp_path / "scripts" / "local_loader_scheduler.py")
    real_stdout, real_stderr = sys.stdout, sys.stderr
    try:
        yield module
    finally:
        sys.stdout, sys.stderr = real_stdout, real_stderr


class TestSchedulerLockIsAtomicNotCheckThenAct:
    def test_pre_created_lock_file_is_detected_even_though_touch_would_have_overwritten_it(
        self, scheduler_module, tmp_path
    ):
        module = scheduler_module
        # Simulate a lock already held by another process (fresh, well under the 12h
        # staleness threshold) - the old .touch()-based acquisition would silently succeed
        # here (touch() just updates mtime, it doesn't check existence), which is exactly
        # the race that let two pipelines run concurrently.
        lock_path = tmp_path / "algo-scheduler.lock"
        lock_path.write_text("held by another process")

        with (
            patch.object(module.tempfile, "gettempdir", return_value=str(tmp_path)),
            patch.object(module.sys, "argv", ["local_loader_scheduler.py", "--now", "metrics"]),
            patch.object(module, "run_pipeline") as mock_run_pipeline,
        ):
            result = module.main()

        assert result == 1
        mock_run_pipeline.assert_not_called()

    def test_stale_lock_is_reclaimed_and_pipeline_runs(self, scheduler_module, tmp_path):
        module = scheduler_module
        lock_path = tmp_path / "algo-scheduler.lock"
        lock_path.write_text("stale")
        # Older than the 12h staleness threshold.
        old_time = module.time.time() - 43201
        os.utime(lock_path, (old_time, old_time))

        with (
            patch.object(module.tempfile, "gettempdir", return_value=str(tmp_path)),
            patch.object(module.sys, "argv", ["local_loader_scheduler.py", "--now", "metrics"]),
            patch.object(module, "run_pipeline", return_value=0) as mock_run_pipeline,
        ):
            result = module.main()

        assert result == 0
        mock_run_pipeline.assert_called_once_with("metrics")
        # Lock is released again after a successful run, not left dangling.
        assert not lock_path.exists()


class TestSchedulerInvocationIsDurablyLogged:
    def test_rejected_invocation_still_writes_to_scheduler_invocations_log(self, scheduler_module, tmp_path):
        module = scheduler_module
        lock_path = tmp_path / "algo-scheduler.lock"
        lock_path.write_text("held by another process")

        with (
            patch.object(module.tempfile, "gettempdir", return_value=str(tmp_path)),
            patch.object(module.sys, "argv", ["local_loader_scheduler.py", "--now", "metrics"]),
        ):
            result = module.main()

        assert result == 1
        invocation_log = tmp_path / "logs" / "scheduler_invocations.log"
        assert invocation_log.exists()
        content = invocation_log.read_text(encoding="utf-8")
        assert "Another scheduler instance is already running" in content
        assert "--now=metrics" in content


class TestTeeMirrorsToFileAndUnderlyingStream:
    def test_write_appends_to_file_and_forwards_to_stream(self, tmp_path):
        module = _load_scheduler_module()
        log_path = tmp_path / "tee_test.log"
        underlying = io.StringIO()

        tee = module._Tee(underlying, log_path)
        tee.write("hello\n")
        tee.write("world\n")
        tee.flush()

        assert underlying.getvalue() == "hello\nworld\n"
        assert log_path.read_text(encoding="utf-8") == "hello\nworld\n"

    def test_survives_process_kill_because_every_write_flushes(self, tmp_path):
        # Regression guard: if a future edit buffers writes instead of flushing per-line,
        # an abruptly killed process (exactly the failure mode this whole fix targets)
        # would lose its own diagnostic output just like before the fix.
        module = _load_scheduler_module()
        log_path = tmp_path / "tee_test.log"
        underlying = io.StringIO()

        tee = module._Tee(underlying, log_path)
        tee.write("not flushed by caller\n")

        # No explicit tee.flush() call - content must already be on disk regardless.
        assert log_path.read_text(encoding="utf-8") == "not flushed by caller\n"
