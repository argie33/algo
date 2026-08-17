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
            patch.object(module, "LOCK_WAIT_TIMEOUT_SECONDS", 0.3),
            patch.object(module, "LOCK_POLL_INTERVAL_SECONDS", 0.1),
            patch.object(module.tempfile, "gettempdir", return_value=str(tmp_path)),
            patch.object(module.sys, "argv", ["local_loader_scheduler.py", "--now", "metrics"]),
            patch.object(module, "run_pipeline") as mock_run_pipeline,
        ):
            result = module.main()

        assert result == 1
        mock_run_pipeline.assert_not_called()

    def test_dead_owner_pid_is_reclaimed_immediately_even_though_lock_is_fresh(self, scheduler_module, tmp_path):
        # LIVE-INCIDENT REGRESSION 2026-08-17: a concurrent session force-killed the scheduler
        # process holding this lock, orphaning it well before the 12h age fallback would have
        # kicked in. Before this fix, nothing could tell the difference between that orphaned
        # lock and a legitimately slow-but-alive run - a lock recording a PID that's actually
        # dead must be reclaimed on liveness alone, not left to sit for up to 12h.
        module = scheduler_module
        lock_path = tmp_path / "algo-scheduler.lock"
        # A PID astronomically unlikely to be a real running process on the test machine.
        lock_path.write_text("pid=999999999 pipeline=metrics started=2026-08-17T05:32:23+00:00")
        # Fresh mtime - well under the 12h staleness threshold, so only the liveness check
        # (not the age fallback) can be responsible for reclaiming this lock.
        recent_time = module.time.time() - 5
        os.utime(lock_path, (recent_time, recent_time))

        with (
            patch.object(module.tempfile, "gettempdir", return_value=str(tmp_path)),
            patch.object(module.sys, "argv", ["local_loader_scheduler.py", "--now", "metrics"]),
            patch.object(module, "run_pipeline", return_value=0) as mock_run_pipeline,
        ):
            result = module.main()

        assert result == 0
        mock_run_pipeline.assert_called_once_with("metrics")

    def test_live_owner_pid_is_respected_but_eventually_times_out(self, scheduler_module, tmp_path):
        # Mirror case: a genuinely alive owner (this test process's own PID, guaranteed alive)
        # must NOT be reclaimed just because something about the lock looks inspectable now -
        # the liveness check must only ever shorten the wait for dead owners, never shorten it
        # for live ones. ADDED 2026-08-17: a live owner is now retried (not failed instantly)
        # for up to LOCK_WAIT_TIMEOUT_SECONDS - patched tiny here so the test doesn't really
        # wait 30 real minutes - but must still eventually give up and return 1 if the owner
        # never releases it.
        module = scheduler_module
        lock_path = tmp_path / "algo-scheduler.lock"
        lock_path.write_text(f"pid={os.getpid()} pipeline=signals started=2026-08-17T05:32:23+00:00")
        recent_time = module.time.time() - 5
        os.utime(lock_path, (recent_time, recent_time))

        with (
            patch.object(module, "LOCK_WAIT_TIMEOUT_SECONDS", 0.3),
            patch.object(module, "LOCK_POLL_INTERVAL_SECONDS", 0.1),
            patch.object(module.tempfile, "gettempdir", return_value=str(tmp_path)),
            patch.object(module.sys, "argv", ["local_loader_scheduler.py", "--now", "metrics"]),
            patch.object(module, "run_pipeline") as mock_run_pipeline,
        ):
            result = module.main()

        assert result == 1
        mock_run_pipeline.assert_not_called()

    def test_waits_for_live_owner_lock_and_succeeds_once_it_is_released(self, scheduler_module, tmp_path):
        # The actual point of the 2026-08-17 fix: a scheduled task firing while a prior
        # pipeline is still finishing should self-heal once the lock frees up, instead of
        # failing on the very first attempt and relying on Task Scheduler's own
        # -RestartCount/-RestartInterval (or a human) to notice and retry.
        module = scheduler_module
        lock_path = tmp_path / "algo-scheduler.lock"
        lock_path.write_text(f"pid={os.getpid()} pipeline=metrics started=2026-08-17T05:32:23+00:00")
        recent_time = module.time.time() - 5
        os.utime(lock_path, (recent_time, recent_time))

        original_try_acquire = module._try_acquire_lock
        call_count = {"n": 0}

        def _try_acquire_then_release_on_second_attempt(lock, name):
            call_count["n"] += 1
            if call_count["n"] == 2:
                # Simulate the other process finishing and releasing the lock right before
                # this poll.
                lock_path.unlink()
            return original_try_acquire(lock, name)

        with (
            patch.object(module, "LOCK_WAIT_TIMEOUT_SECONDS", 5),
            patch.object(module, "LOCK_POLL_INTERVAL_SECONDS", 0.05),
            patch.object(module.tempfile, "gettempdir", return_value=str(tmp_path)),
            patch.object(module.sys, "argv", ["local_loader_scheduler.py", "--now", "metrics"]),
            patch.object(module, "_try_acquire_lock", side_effect=_try_acquire_then_release_on_second_attempt),
            patch.object(module, "run_pipeline", return_value=0) as mock_run_pipeline,
        ):
            result = module.main()

        assert result == 0
        mock_run_pipeline.assert_called_once_with("metrics")
        assert call_count["n"] >= 2

    def test_successful_acquire_records_pid_and_pipeline_for_future_liveness_checks(self, scheduler_module, tmp_path):
        # The lock used to be written empty (os.O_WRONLY, no content) - nothing could verify
        # who held it without cross-referencing OS process lists by hand. Assert the content
        # a concurrent invocation (or a human debugging a "stuck" run) would actually rely on.
        module = scheduler_module
        recorded_content = {}

        def _capture_lock_content_while_held(pipeline_name):
            recorded_content["text"] = (tmp_path / "algo-scheduler.lock").read_text()
            return 0

        with (
            patch.object(module.tempfile, "gettempdir", return_value=str(tmp_path)),
            patch.object(module.sys, "argv", ["local_loader_scheduler.py", "--now", "metrics"]),
            patch.object(module, "run_pipeline", side_effect=_capture_lock_content_while_held),
        ):
            result = module.main()

        assert result == 0
        assert f"pid={os.getpid()}" in recorded_content["text"]
        assert "pipeline=metrics" in recorded_content["text"]
        assert "started=" in recorded_content["text"]

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
            patch.object(module, "LOCK_WAIT_TIMEOUT_SECONDS", 0.3),
            patch.object(module, "LOCK_POLL_INTERVAL_SECONDS", 0.1),
            patch.object(module.tempfile, "gettempdir", return_value=str(tmp_path)),
            patch.object(module.sys, "argv", ["local_loader_scheduler.py", "--now", "metrics"]),
        ):
            result = module.main()

        assert result == 1
        invocation_log = tmp_path / "logs" / "scheduler_invocations.log"
        assert invocation_log.exists()
        content = invocation_log.read_text(encoding="utf-8")
        assert "Another scheduler instance is still running" in content
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
