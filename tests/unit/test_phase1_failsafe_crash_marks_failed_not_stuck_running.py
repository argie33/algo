"""Regression test for a stuck-RUNNING bug in phase1_failsafe_retry.py's subprocess handling.

Bug (found 2026-08-10): run_loader.py --force-refresh marks its output tables RUNNING before
doing any real work. If the subprocess it's called in is then killed by
subprocess.run(timeout=300) or crashes, _check_and_refresh_local()'s exception handlers
(TimeoutExpired, OSError/IOError/RuntimeError, generic Exception) only recorded the failure
in an in-memory `still_failing` list - data_loader_status stayed RUNNING forever, with no
owning process. Live-confirmed 2026-08-10: price_daily/etf_price_daily/price_monthly/
price_weekly/etf_price_monthly/etf_price_weekly (load_prices.py's full output set) all stuck
RUNNING from exactly this path after their subprocess died mid-refresh.

Fixed: _mark_loader_failed_after_crash() now runs from every failure branch, correcting any
table still showing RUNNING to FAILED (never touching a table whose own run() already
recorded a real terminal status).
"""

from unittest.mock import MagicMock, patch

from algo.orchestrator.phase1_failsafe_retry import _mark_loader_failed_after_crash


class TestMarkLoaderFailedAfterCrash:
    def test_marks_all_output_tables_still_running_as_failed(self):
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "RUNNING"}

        with patch(
            "algo.orchestrator.phase1_failsafe_retry.LoaderStatusManager", return_value=mock_status_mgr
        ):
            _mark_loader_failed_after_crash("prices", "subprocess timed out")

        # load_prices.py owns 6 output tables - all must be checked and marked
        assert mock_status_mgr.mark_failed.call_count == 6
        for call in mock_status_mgr.mark_failed.call_args_list:
            assert "subprocess timed out" in call.args[0]

    def test_does_not_clobber_a_table_with_a_real_terminal_status(self):
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "FAILED"}

        with patch(
            "algo.orchestrator.phase1_failsafe_retry.LoaderStatusManager", return_value=mock_status_mgr
        ):
            _mark_loader_failed_after_crash("prices", "subprocess timed out")

        mock_status_mgr.mark_failed.assert_not_called()

    def test_unknown_loader_key_does_not_raise(self):
        # normalize_loader_name() raises ValueError for garbage input - must be swallowed,
        # not propagate and mask the original timeout/crash being reported by the caller.
        _mark_loader_failed_after_crash("not_a_real_loader_xyz", "subprocess timed out")
