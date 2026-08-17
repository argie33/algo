"""Regression test: invoke_loader_retry()'s subprocess-based LOCAL_MODE path never called
_mark_loader_failed_after_crash() on failure, unlike the sibling in-process retry path
(_check_and_refresh_local(), covered by test_phase1_failsafe_crash_marks_failed_not_stuck_running.py)
which already wires it into 4 branches.

Bug (found 2026-08-17): scripts/run_loader.py --force-refresh marks its output tables RUNNING
before doing any real work. invoke_loader_retry() launches it via
subprocess.run(timeout=subprocess_timeout) - on a timeout, subprocess.run() kills the child,
bypassing run_loader.py's own except-block cleanup exactly like an external hard kill would
(SIGKILL/TerminateProcess skip Python's exception handling). invoke_loader_retry()'s
`except subprocess.TimeoutExpired` and `except Exception` handlers only logged and re-raised -
neither called _mark_loader_failed_after_crash(), so the pre-marked RUNNING row was left stuck
until the coarser reap_stale_running_loaders() eventually caught it, sometimes 24h+ later.

Fixed: both branches now call _mark_loader_failed_after_crash(loader_key, ...), guarded so a
failure before loader_key is resolved (e.g. an unregistered table) can't raise UnboundLocalError
and mask the real error.
"""

from unittest.mock import MagicMock, patch

import pytest

from algo.orchestrator.phase1_failsafe_retry import invoke_loader_retry


@pytest.fixture(autouse=True)
def _local_mode(monkeypatch):
    monkeypatch.setenv("LOCAL_MODE", "true")


class TestInvokeLoaderRetrySubprocessCrashCleanup:
    def test_subprocess_timeout_marks_still_running_tables_failed(self):
        import subprocess

        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "RUNNING"}

        with (
            patch("loaders.loader_registry.table_to_loader_shorthand", return_value="prices"),
            patch("algo.orchestrator.phase1_failsafe_retry.get_loader_timeouts", return_value={"prices": 60}),
            patch(
                "algo.orchestrator.phase1_failsafe_retry.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="run_loader.py", timeout=75),
            ),
            patch("algo.orchestrator.phase1_failsafe_retry.LoaderStatusManager", return_value=mock_status_mgr),
            pytest.raises(RuntimeError, match="timeout"),
        ):
            invoke_loader_retry("price_daily", is_critical=True)

        # load_prices.py owns 6 output tables - the crash cleanup must have run for all of them
        assert mock_status_mgr.mark_failed.call_count == 6

    def test_subprocess_start_failure_marks_still_running_tables_failed(self):
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "RUNNING"}

        with (
            patch("loaders.loader_registry.table_to_loader_shorthand", return_value="prices"),
            patch("algo.orchestrator.phase1_failsafe_retry.get_loader_timeouts", return_value={"prices": 60}),
            patch(
                "algo.orchestrator.phase1_failsafe_retry.subprocess.run",
                side_effect=OSError("could not start subprocess"),
            ),
            patch("algo.orchestrator.phase1_failsafe_retry.LoaderStatusManager", return_value=mock_status_mgr),
            pytest.raises(RuntimeError, match="Failed to invoke"),
        ):
            invoke_loader_retry("price_daily", is_critical=True)

        assert mock_status_mgr.mark_failed.call_count == 6

    def test_unregistered_table_does_not_raise_unbound_local_error(self):
        # loader_key is never resolved when the table isn't registered - the cleanup call in
        # the except branch must not blow up with UnboundLocalError and mask the real error.
        with (
            patch("loaders.loader_registry.table_to_loader_shorthand", return_value=None),
            pytest.raises(RuntimeError, match="not registered"),
        ):
            invoke_loader_retry("not_a_real_table_xyz", is_critical=True)
