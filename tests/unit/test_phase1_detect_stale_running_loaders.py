"""Regression coverage for phase1_data_freshness._detect_and_fail_stale_running_loaders().

This function has a long history of mistuning (Session 82 -> 89 -> 94 -> 108 -> 109, per its
own docstring) but had ZERO real test coverage: the only files referencing it
(tests/integration/test_monday_brittleness_scenario.py, tests/validation/
test_loader_brittleness_fixes.py) used `return True/False` instead of `assert`, so pytest only
warned (PytestReturnNotNoneWarning) and always reported them as PASSED regardless of the actual
result - they could never catch a regression here. Those files also mutated the real
`company_info_sec` row and were retired as part of this fix (see
tests/integration/test_session_88_fixes.py's removal in the same change). This file replaces
them with deterministic, mocked coverage of the two behaviors those scripts were actually meant
to guard: per-loader mark_failed isolation, and non-fatal top-level failure.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase1_data_freshness import _detect_and_fail_stale_running_loaders


def _run_with_rows(rows: list[tuple[Any, ...]]) -> tuple[list[str], MagicMock, MagicMock]:
    mock_status_mgr = MagicMock()
    with (
        patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as MockDB,
        patch(
            "algo.orchestrator.phase1_data_freshness.LoaderStatusManager", return_value=mock_status_mgr
        ) as MockStatusMgr,
    ):
        MockDB.return_value.__enter__.return_value.fetchall.return_value = rows
        recovered = _detect_and_fail_stale_running_loaders()
    return recovered, MockStatusMgr, mock_status_mgr


class TestDetectStaleRunningLoaders:
    def test_no_stale_loaders_marks_nothing(self) -> None:
        recovered, MockStatusMgr, _ = _run_with_rows([])
        assert recovered == []
        MockStatusMgr.assert_not_called()

    def test_stale_running_loader_is_marked_failed_and_returned(self) -> None:
        rows: list[tuple[Any, ...]] = [("price_daily", "2026-08-17 05:32:00", "RUNNING", 0.0)]
        recovered, MockStatusMgr, mock_status_mgr = _run_with_rows(rows)

        assert recovered == ["price_daily"]
        MockStatusMgr.assert_called_once_with("price_daily")
        mock_status_mgr.mark_failed.assert_called_once()

    def test_stuck_not_started_loader_is_also_recovered(self) -> None:
        # SESSION 106: NOT_STARTED (subprocess crashed before mark_running()) must be detected
        # too, not just RUNNING - failsafe retry only retries FAILED/INCOMPLETE, so a stuck
        # NOT_STARTED loader would otherwise never be picked up again.
        rows: list[tuple[Any, ...]] = [("earnings_calendar", "2026-08-17 05:00:00", "NOT_STARTED", None)]
        recovered, _, mock_status_mgr = _run_with_rows(rows)

        assert recovered == ["earnings_calendar"]
        mock_status_mgr.mark_failed.assert_called_once()

    def test_one_loader_failing_to_mark_does_not_block_the_others(self) -> None:
        rows = [
            ("company_info_sec", "2026-08-17 05:00:00", "RUNNING", 0.0),
            ("price_daily", "2026-08-17 05:00:00", "RUNNING", 0.0),
        ]
        mock_status_mgr_broken = MagicMock()
        mock_status_mgr_broken.mark_failed.side_effect = RuntimeError("db write failed")
        mock_status_mgr_ok = MagicMock()

        with (
            patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as MockDB,
            patch(
                "algo.orchestrator.phase1_data_freshness.LoaderStatusManager",
                side_effect=[mock_status_mgr_broken, mock_status_mgr_ok],
            ),
        ):
            MockDB.return_value.__enter__.return_value.fetchall.return_value = rows
            recovered = _detect_and_fail_stale_running_loaders()

        # company_info_sec's mark_failed() raised - it must not appear as recovered, and the
        # exception must not stop price_daily (the next row) from being processed.
        assert recovered == ["price_daily"]
        mock_status_mgr_ok.mark_failed.assert_called_once()

    def test_query_failure_is_non_fatal_and_returns_empty_list(self) -> None:
        # Phase 1 startup must proceed even if this diagnostic query itself breaks (e.g. schema
        # drift, connection pool exhaustion) - it must never raise out of this function.
        with patch("algo.orchestrator.phase1_data_freshness.DatabaseContext", side_effect=RuntimeError("no pool")):
            recovered = _detect_and_fail_stale_running_loaders()

        assert recovered == []
