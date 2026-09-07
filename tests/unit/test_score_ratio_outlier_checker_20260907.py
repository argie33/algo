"""Regression tests for ScoreRatioOutlierChecker
(algo/monitoring/data_patrol/checks/score_ratio_outliers.py).

Added 2026-09-07 (goal session: "automate the XBRL stuff for the future" - generalizing the
by-hand SOAR/LX/ROC/MSB leaderboard-outlier findings from the same session into an ongoing
DataPatrol check, same "detect and route to review" philosophy as statistical_anomaly.py's
own YoY magnitude checks).
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.score_ratio_outliers import ScoreRatioOutlierChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _checker() -> ScoreRatioOutlierChecker:
    return ScoreRatioOutlierChecker(PatrolConfig())


def _mock_cursor(rows: list[dict]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = rows
    return cur


class TestLowDirectionOutlier:
    """pe_ratio/pb_ratio/ps_ratio: cheap-is-good, outlier is far BELOW the population's own p05."""

    def test_flags_symbol_far_below_p05(self) -> None:
        # 99 normal values (2.0..100.0) + one outlier at 0.01 - well under bound (p05/5).
        rows = [{"symbol": f"SYM{i}", "val": float(i)} for i in range(2, 101)]
        rows.append({"symbol": "SOAR_SHAPED", "val": 0.01})
        cur = _mock_cursor(rows)
        checker = _checker()
        checker._check_ratio_outliers(cur, "value_metrics", "pe_ratio", "low")
        assert len(checker.results) == 1
        assert checker.results[0].severity == "warn"
        examples = checker.results[0].details["examples"]
        assert any(e["symbol"] == "SOAR_SHAPED" for e in examples)

    def test_does_not_flag_a_normal_population(self) -> None:
        rows = [{"symbol": f"SYM{i}", "val": float(i)} for i in range(1, 101)]
        cur = _mock_cursor(rows)
        checker = _checker()
        checker._check_ratio_outliers(cur, "value_metrics", "pe_ratio", "low")
        assert checker.results == []

    def test_negative_values_never_flagged_as_cheap(self) -> None:
        # Negative pe_ratio means something else entirely (e.g. negative book value context) -
        # must not be treated as "extremely cheap".
        rows = [{"symbol": f"SYM{i}", "val": float(i)} for i in range(2, 101)]
        rows.append({"symbol": "NEGATIVE", "val": -50.0})
        cur = _mock_cursor(rows)
        checker = _checker()
        checker._check_ratio_outliers(cur, "value_metrics", "pe_ratio", "low")
        assert all(
            e["symbol"] != "NEGATIVE" for r in checker.results for e in r.details["examples"]
        )


class TestHighDirectionOutlier:
    """fcf_yield/roe/roce_pct: higher-is-good, outlier is far ABOVE the population's own p95."""

    def test_flags_symbol_far_above_p95(self) -> None:
        # 99 normal values (1.0..99.0) + one outlier at 1000.0 - well over bound (p95*5).
        rows = [{"symbol": f"SYM{i}", "val": float(i)} for i in range(1, 100)]
        rows.append({"symbol": "ROC_SHAPED", "val": 1000.0})
        cur = _mock_cursor(rows)
        checker = _checker()
        checker._check_ratio_outliers(cur, "quality_metrics", "roe", "high")
        assert len(checker.results) == 1
        examples = checker.results[0].details["examples"]
        assert any(e["symbol"] == "ROC_SHAPED" for e in examples)

    def test_does_not_flag_a_normal_population(self) -> None:
        rows = [{"symbol": f"SYM{i}", "val": float(i)} for i in range(1, 101)]
        cur = _mock_cursor(rows)
        checker = _checker()
        checker._check_ratio_outliers(cur, "quality_metrics", "roe", "high")
        assert checker.results == []


class TestSmallPopulationGuard:
    def test_population_under_100_skipped_entirely(self) -> None:
        rows = [{"symbol": f"SYM{i}", "val": float(i)} for i in range(1, 50)]
        rows.append({"symbol": "OUTLIER", "val": 100000.0})
        cur = _mock_cursor(rows)
        checker = _checker()
        checker._check_ratio_outliers(cur, "quality_metrics", "roe", "high")
        assert checker.results == []


class TestErrorHandling:
    def test_query_failure_logs_error_not_raise(self) -> None:
        cur = MagicMock()
        cur.execute.side_effect = RuntimeError("db down")
        checker = _checker()
        checker._check_ratio_outliers(cur, "value_metrics", "pe_ratio", "low")
        assert len(checker.results) == 1
        assert checker.results[0].severity == "error"


class TestRunExecutesAllFields:
    def test_run_covers_all_six_ratio_fields_without_crashing(self) -> None:
        rows = [{"symbol": f"SYM{i}", "val": float(i + 1)} for i in range(150)]
        cur = _mock_cursor(rows)
        checker = _checker()
        results = checker.run(cur)
        assert isinstance(results, list)
        # 6 fields queried, none should error given well-formed mock data.
        assert cur.execute.call_count == 6
        assert all(r.severity != "error" for r in results)
