"""Regression test: DataPatrol.run() must actually persist findings to data_patrol_log via
PatrolLogger, not just alert through notify().

BUG FOUND 2026-09-07 (goal: stock_scores/tie-out CI sanity audit): PatrolLogger
(algo/monitoring/data_patrol/logger.py, INSERT INTO data_patrol_log, fully implemented and
unit-tested in isolation) was never actually called from DataPatrol.run() - self.run_id sat as
a permanent "" placeholder and data_patrol_log's last row was 2026-07-05 despite this run()
executing on every scheduled ECS invocation since. The lambda API's own data-quality dashboard
endpoints (lambda/api/routes/algo_handlers/market/data_quality.py, monitoring.py) read
data_patrol_log directly and were silently showing a 2-month-stale snapshot. Same "computed but
never delivered" class as the notify() gap fixed 2026-09-01
(test_data_patrol_run_notify_wired_20260901.py).
"""

from contextlib import ExitStack
from typing import Any
from unittest.mock import MagicMock, patch

from algo.monitoring.data_patrol.base import CheckResult, DataPatrol
from algo.monitoring.data_patrol.checks import (
    AlignmentChecker,
    CoverageChecker,
    NewXbrlConceptChecker,
    PriceSanityChecker,
    QualityChecker,
    ScoreRatioOutlierChecker,
    SpecializedChecker,
    StalenessChecker,
    StatisticalAnomalyChecker,
    TieOutChecker,
)
from algo.monitoring.data_patrol.config import CRIT, PatrolConfig


def _run_patrol_with_results(results_by_checker: dict[str, list[CheckResult]]) -> dict[str, Any]:
    """STALE-MOCK-LIST BUG FIXED 2026-09-08 (goal session score-sanity/tie-out sweep):
    DataPatrol.run()'s real `checkers` list (algo/monitoring/data_patrol/base.py) grew to 10
    checkers (TieOutChecker added 2026-09-06, NewXbrlConceptChecker/StatisticalAnomalyChecker/
    ScoreRatioOutlierChecker at various points since) but this test's checker_classes dict was
    never updated past the original 6 - so every "unit" test here silently let the 4 newer
    checkers run for REAL against a MagicMock cursor instead of being mocked out.
    NewXbrlConceptChecker in particular calls utils/external/xbrl_concept_coverage.py's
    scan_cache(), a real disk scan of the entire SEC EDGAR companyfacts cache (5,373 files
    on this machine) - turning what should be a millisecond-scale mocked unit test into a
    60-120+ second real filesystem operation on every run (live-confirmed via
    faulthandler.dump_traceback_later: the hang's full stack traced to exactly this call).
    Same failure class as any other unmocked real-I/O leak in a "unit" test - CI has no
    XBRL cache at all, so there this call likely finds nothing and returns fast, but on any
    machine that DOES have one (like this local dev box, or anyone else's), the test either
    hangs for minutes or returns whatever real findings that scan produces instead of the
    controlled `results_by_checker` fixture - either way, not a real unit test anymore.
    """
    patrol = DataPatrol(PatrolConfig())

    checker_classes = {
        "StalenessChecker": StalenessChecker,
        "CoverageChecker": CoverageChecker,
        "QualityChecker": QualityChecker,
        "PriceSanityChecker": PriceSanityChecker,
        "AlignmentChecker": AlignmentChecker,
        "SpecializedChecker": SpecializedChecker,
        "TieOutChecker": TieOutChecker,
        "NewXbrlConceptChecker": NewXbrlConceptChecker,
        "StatisticalAnomalyChecker": StatisticalAnomalyChecker,
        "ScoreRatioOutlierChecker": ScoreRatioOutlierChecker,
    }

    mock_conn = MagicMock()
    with ExitStack() as stack:
        stack.enter_context(patch("utils.db.connection.get_db_connection", return_value=mock_conn))
        stack.enter_context(patch("algo.reporting.notify"))
        mock_patrol_logger_cls = stack.enter_context(patch("algo.monitoring.data_patrol.logger.PatrolLogger"))
        for name, cls in checker_classes.items():
            stack.enter_context(patch.object(cls, "run", return_value=results_by_checker.get(name, [])))
        summary = patrol.run()

    return {"summary": summary, "mock_patrol_logger_cls": mock_patrol_logger_cls, "patrol": patrol}


class TestDataPatrolLogWiring:
    def test_run_id_is_generated_not_empty_placeholder(self) -> None:
        result = _run_patrol_with_results({})
        assert result["patrol"].run_id != ""

    def test_log_results_called_with_this_runs_findings(self) -> None:
        finding = CheckResult(check_name="staleness", severity=CRIT, target_table="price_daily", message="3d stale")
        result = _run_patrol_with_results({"StalenessChecker": [finding]})
        mock_logger_instance = result["mock_patrol_logger_cls"].return_value
        mock_logger_instance.log_results.assert_called_once()
        _, logged_results = mock_logger_instance.log_results.call_args[0]
        assert finding in logged_results

    def test_log_performance_called_with_elapsed_time_and_status(self) -> None:
        result = _run_patrol_with_results({})
        mock_logger_instance = result["mock_patrol_logger_cls"].return_value
        mock_logger_instance.log_performance.assert_called_once()
        args = mock_logger_instance.log_performance.call_args[0]
        assert args[2] == "OK"

    def test_clean_run_still_logs_zero_findings(self) -> None:
        """Even a clean run (no errors/warnings) must persist to data_patrol_log - otherwise
        the dashboard can't distinguish "patrol never ran" from "patrol ran clean"."""
        result = _run_patrol_with_results({})
        mock_logger_instance = result["mock_patrol_logger_cls"].return_value
        mock_logger_instance.log_results.assert_called_once()

    def test_patrol_logger_failure_does_not_crash_patrol_run(self) -> None:
        """A data_patrol_log persistence failure must be swallowed (logged), not propagate and
        abort the patrol run or its notify() alert - same fail-safe posture as notify()."""
        patrol = DataPatrol(PatrolConfig())
        mock_conn = MagicMock()
        with (
            patch("utils.db.connection.get_db_connection", return_value=mock_conn),
            patch("algo.reporting.notify") as mock_notify,
            patch(
                "algo.monitoring.data_patrol.logger.PatrolLogger",
                side_effect=RuntimeError("db down"),
            ),
            patch.object(
                StalenessChecker,
                "run",
                return_value=[
                    CheckResult(check_name="staleness", severity=CRIT, target_table="price_daily", message="stale")
                ],
            ),
            patch.object(CoverageChecker, "run", return_value=[]),
            patch.object(QualityChecker, "run", return_value=[]),
            patch.object(PriceSanityChecker, "run", return_value=[]),
            patch.object(AlignmentChecker, "run", return_value=[]),
            patch.object(SpecializedChecker, "run", return_value=[]),
            patch.object(TieOutChecker, "run", return_value=[]),
            patch.object(NewXbrlConceptChecker, "run", return_value=[]),
            patch.object(StatisticalAnomalyChecker, "run", return_value=[]),
            patch.object(ScoreRatioOutlierChecker, "run", return_value=[]),
        ):
            summary = patrol.run()  # must not raise despite PatrolLogger failing internally

        assert summary["ready"] is False
        mock_notify.assert_called_once()  # notify() must still fire despite the logging failure
