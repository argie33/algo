"""Regression test: DataPatrol.run() must actually alert a human via notify() when checks
find errors or warnings, not just return a summary dict nobody looks at.

BUG FOUND 2026-09-01 (/goal session): DataPatrol is the codebase's central data-integrity
monitor (staleness/coverage/quality/price-sanity/alignment/specialized checks across 6
checkers), but run() - the only place results get aggregated - never called notify() anywhere.
Findings only ever reached a human via the CLI entrypoint's (algo_data_patrol.py) process exit
code and log output - if nobody is watching the ECS task's exit status/CloudWatch logs, a
genuine data-integrity failure goes completely unnoticed. Same "computed but never delivered"
alert gap already found and fixed today in load_market_constituents.py, Phase 9's risk-alert
path, and AlgoConfig's partial-DB-load-failure warning.
"""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from algo.monitoring.data_patrol.base import CheckResult, DataPatrol
from algo.monitoring.data_patrol.checks import (
    AlignmentChecker,
    CikSharedIssuerFinancialsLeakChecker,
    CompositeScoreReconciliationChecker,
    ConfirmedXbrlBugScoreExposureChecker,
    CoverageChecker,
    FinancialStatementFlagDriftChecker,
    FinancialStatementPeriodSanityChecker,
    GrowthShareCountGapSplitRiskChecker,
    MetricBoundsChecker,
    NewXbrlConceptChecker,
    PillarScoreReconciliationChecker,
    PriceSanityChecker,
    QualityChecker,
    ReverseMergerShellChecker,
    ScoreRatioOutlierChecker,
    SpecializedChecker,
    StalenessChecker,
    StatisticalAnomalyChecker,
    TieOutChecker,
    XbrlConceptContinuityChecker,
)
from algo.monitoring.data_patrol.config import CRIT, ERROR, WARN, PatrolConfig


def _run_patrol_with_results(results_by_checker: dict) -> dict:
    """Run DataPatrol.run() with DB connection mocked out and each checker's .run()
    patched to return a fixed CheckResult list (default: empty for unlisted checkers).

    Must mock every checker DataPatrol.run() registers (base.py), not just a subset -
    an unmocked checker runs for real against the MagicMock() DB connection and, for
    checkers that read outside the DB (e.g. NewXbrlConceptChecker/
    XbrlConceptContinuityChecker read the on-disk SEC EDGAR cache), can produce real
    findings that leak into "clean run" assertions below. FIXED 2026-09-08 (goal
    session, live-caught): XbrlConceptContinuityChecker's addition to base.py's checker
    list wasn't mirrored here, so test_clean_run_does_not_notify started failing on 9
    real, live continuity gaps the checker legitimately found in the on-disk cache -
    same trap this docstring already warns about, just not kept in sync when
    ScoreRatioOutlierChecker/CompositeScoreReconciliationChecker were added earlier
    either (added here too, alongside the fix, since both were also missing).

    FIXED AGAIN 2026-09-15 (/goal "missing data patrols/tie-outs" session, live-caught):
    MetricBoundsChecker, ReverseMergerShellChecker, CikSharedIssuerFinancialsLeakChecker, and
    the newly-added FinancialStatementPeriodSanityChecker were never added here either -
    same trap, still not kept in sync. Unmocked, each ran for real against the MagicMock()
    cursor; MagicMock().fetchall() is truthy (default __bool__) but len() == 0 (default
    __len__), which is exactly the shape FinancialStatementPeriodSanityChecker's own `if rows:`
    branches treat as "found violations" - producing bogus "0 row(s) with a fiscal_year/quarter
    that cannot exist yet" WARN findings that broke test_clean_run_does_not_notify below.
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
        "FinancialStatementPeriodSanityChecker": FinancialStatementPeriodSanityChecker,
        "GrowthShareCountGapSplitRiskChecker": GrowthShareCountGapSplitRiskChecker,
        "MetricBoundsChecker": MetricBoundsChecker,
        "NewXbrlConceptChecker": NewXbrlConceptChecker,
        "XbrlConceptContinuityChecker": XbrlConceptContinuityChecker,
        "StatisticalAnomalyChecker": StatisticalAnomalyChecker,
        "ScoreRatioOutlierChecker": ScoreRatioOutlierChecker,
        "ReverseMergerShellChecker": ReverseMergerShellChecker,
        "CompositeScoreReconciliationChecker": CompositeScoreReconciliationChecker,
        "PillarScoreReconciliationChecker": PillarScoreReconciliationChecker,
        "ConfirmedXbrlBugScoreExposureChecker": ConfirmedXbrlBugScoreExposureChecker,
        "CikSharedIssuerFinancialsLeakChecker": CikSharedIssuerFinancialsLeakChecker,
    }
    # ADDED 2026-09-08 (goal session): this dict has already drifted out of sync with
    # checks/__init__.py's __all__ twice (see this function's own docstring) - assert it
    # explicitly instead of relying on an unmocked checker happening to produce live findings.
    from algo.monitoring.data_patrol import checks as _checks_module

    assert set(checker_classes) == set(_checks_module.__all__), (
        "checker_classes here is out of sync with checks/__init__.py's __all__ - "
        f"missing: {set(_checks_module.__all__) - set(checker_classes)}, "
        f"extra: {set(checker_classes) - set(_checks_module.__all__)}"
    )

    mock_conn = MagicMock()
    with ExitStack() as stack:
        stack.enter_context(patch("utils.db.connection.get_db_connection", return_value=mock_conn))
        mock_notify = stack.enter_context(patch("algo.reporting.notify"))
        for name, cls in checker_classes.items():
            stack.enter_context(patch.object(cls, "run", return_value=results_by_checker.get(name, [])))
        summary = patrol.run()

    return {"summary": summary, "mock_notify": mock_notify}


class TestDataPatrolNotifyWiring:
    def test_errors_trigger_critical_notify(self) -> None:
        result = _run_patrol_with_results(
            {
                "StalenessChecker": [
                    CheckResult(
                        check_name="staleness",
                        severity=CRIT,
                        target_table="aaii_sentiment",
                        message="12 days stale, exceeds 7-day threshold",
                    )
                ]
            }
        )
        mock_notify = result["mock_notify"]
        mock_notify.assert_called_once()
        _, kwargs = mock_notify.call_args
        assert kwargs["severity"] == "critical"
        assert kwargs["title"] == "Data Patrol Findings"
        assert "aaii_sentiment" in kwargs["message"]
        assert kwargs["details"]["errors"] == 1
        assert result["summary"]["ready"] is False

    def test_warnings_only_trigger_warning_notify(self) -> None:
        result = _run_patrol_with_results(
            {
                "CoverageChecker": [
                    CheckResult(
                        check_name="coverage",
                        severity=WARN,
                        target_table="insider_transactions",
                        message="Coverage below expected threshold",
                    )
                ]
            }
        )
        mock_notify = result["mock_notify"]
        mock_notify.assert_called_once()
        _, kwargs = mock_notify.call_args
        assert kwargs["severity"] == "warning"
        assert kwargs["title"] == "Data Patrol Warnings"
        assert result["summary"]["ready"] is True

    def test_clean_run_does_not_notify(self) -> None:
        result = _run_patrol_with_results({})
        result["mock_notify"].assert_not_called()
        assert result["summary"]["ready"] is True

    def test_error_severity_also_triggers_critical_notify(self) -> None:
        """ERROR (not just CRIT) severity findings also count toward errors and must alert."""
        result = _run_patrol_with_results(
            {
                "QualityChecker": [
                    CheckResult(
                        check_name="quality",
                        severity=ERROR,
                        target_table="financial_statements",
                        message="Data quality violation",
                    )
                ]
            }
        )
        mock_notify = result["mock_notify"]
        mock_notify.assert_called_once()
        assert mock_notify.call_args.kwargs["severity"] == "critical"

    def test_notify_failure_does_not_crash_patrol_run(self) -> None:
        """A notification-delivery failure must be swallowed (logged), not propagate and
        abort the patrol run - alerting is best-effort here, not a governance gate."""
        patrol = DataPatrol(PatrolConfig())
        mock_conn = MagicMock()
        with (
            patch("utils.db.connection.get_db_connection", return_value=mock_conn),
            patch("algo.reporting.notify", side_effect=RuntimeError("smtp down")),
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
            patch.object(FinancialStatementPeriodSanityChecker, "run", return_value=[]),
            patch.object(MetricBoundsChecker, "run", return_value=[]),
            patch.object(NewXbrlConceptChecker, "run", return_value=[]),
            patch.object(XbrlConceptContinuityChecker, "run", return_value=[]),
            patch.object(StatisticalAnomalyChecker, "run", return_value=[]),
            patch.object(ScoreRatioOutlierChecker, "run", return_value=[]),
            patch.object(ReverseMergerShellChecker, "run", return_value=[]),
            patch.object(CompositeScoreReconciliationChecker, "run", return_value=[]),
            patch.object(PillarScoreReconciliationChecker, "run", return_value=[]),
            patch.object(CikSharedIssuerFinancialsLeakChecker, "run", return_value=[]),
        ):
            # Must not raise despite notify() failing internally.
            summary = patrol.run()

        assert summary["ready"] is False
