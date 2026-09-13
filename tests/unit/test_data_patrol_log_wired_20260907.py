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
    CompositeScoreReconciliationChecker,
    CoverageChecker,
    FinancialStatementFlagDriftChecker,
    NewXbrlConceptChecker,
    PillarScoreReconciliationChecker,
    PriceSanityChecker,
    QualityChecker,
    ScoreRatioOutlierChecker,
    SpecializedChecker,
    StalenessChecker,
    StatisticalAnomalyChecker,
    TieOutChecker,
    XbrlConceptContinuityChecker,
)
from algo.monitoring.data_patrol.config import CRIT, PatrolConfig


def _run_patrol_with_results(results_by_checker: dict[str, list[CheckResult]]) -> dict[str, Any]:
    """STALE-MOCK-LIST BUG FIXED 2026-09-08, RECURRED AND FIXED AGAIN 2026-09-12 (goal
    session: "data integrity gaps galore... gaps in our approach"): DataPatrol.run()'s real
    `checkers` list (algo/monitoring/data_patrol/base.py) grew to 14 checkers
    (FinancialStatementFlagDriftChecker/XbrlConceptContinuityChecker/
    CompositeScoreReconciliationChecker/PillarScoreReconciliationChecker added since the 2026-
    09-08 fix) but this test's checker_classes dict was only ever updated to 10 - so the same
    "4 newer checkers run for REAL against a MagicMock cursor instead of being mocked out" bug
    class recurred with a different 4 checkers. Live-reproduced 2026-09-12: running this file
    in isolation with a `timeout 30` wrapper never completes at all (was previously "just"
    60-120s for the 2026-09-08 case) - one of the 4 newly-unmocked checkers here hangs
    indefinitely rather than merely running slowly, discovered because this file was one of
    358 tests in a `-k "tie_out or data_patrol"` run that itself never finished. This is
    exactly the "gap in our approach" class the goal session was hunting: a stale test
    fixture silently let real, unmocked, unbounded I/O leak into what every CI run treats as
    a millisecond-scale mocked unit test. The structural fix (keep this dict in permanent sync
    with base.py's real list) still doesn't exist - see the TODO on this dict below; this is
    the second time it's silently drifted out of sync.

    TODO: this dict must be derived from (or asserted equal to) DataPatrol.run()'s actual
    `checkers` list rather than hand-copied, or it will drift a third time the next time a
    checker is added to base.py. Not done in this pass - out of scope for the immediate hang
    fix, flagged here so the next session doesn't have to rediscover it via another hang.
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
        "FinancialStatementFlagDriftChecker": FinancialStatementFlagDriftChecker,
        "NewXbrlConceptChecker": NewXbrlConceptChecker,
        "XbrlConceptContinuityChecker": XbrlConceptContinuityChecker,
        "StatisticalAnomalyChecker": StatisticalAnomalyChecker,
        "ScoreRatioOutlierChecker": ScoreRatioOutlierChecker,
        "CompositeScoreReconciliationChecker": CompositeScoreReconciliationChecker,
        "PillarScoreReconciliationChecker": PillarScoreReconciliationChecker,
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
            patch.object(FinancialStatementFlagDriftChecker, "run", return_value=[]),
            patch.object(NewXbrlConceptChecker, "run", return_value=[]),
            patch.object(XbrlConceptContinuityChecker, "run", return_value=[]),
            patch.object(StatisticalAnomalyChecker, "run", return_value=[]),
            patch.object(ScoreRatioOutlierChecker, "run", return_value=[]),
            patch.object(CompositeScoreReconciliationChecker, "run", return_value=[]),
            patch.object(PillarScoreReconciliationChecker, "run", return_value=[]),
        ):
            summary = patrol.run()  # must not raise despite PatrolLogger failing internally

        assert summary["ready"] is False
        mock_notify.assert_called_once()  # notify() must still fire despite the logging failure
