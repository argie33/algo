"""Regression tests for NewXbrlConceptChecker (algo/monitoring/data_patrol/checks/xbrl_new_concepts.py).

Added 2026-09-07 (goal session: automate scripts/xbrl_concept_coverage_scan.py so a newly-
adopted XBRL taxonomy tag is caught on the next scheduled DataPatrol run instead of only when
a human remembers to run the script by hand).
"""

from pathlib import Path
from unittest.mock import patch

from algo.monitoring.data_patrol.checks.xbrl_new_concepts import NewXbrlConceptChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _checker() -> NewXbrlConceptChecker:
    return NewXbrlConceptChecker(PatrolConfig())


class TestNewXbrlConceptChecker:
    def test_no_cache_means_no_finding(self) -> None:
        checker = _checker()
        with patch(
            "algo.monitoring.data_patrol.checks.xbrl_new_concepts.iter_companyfacts_cache",
            return_value=[],
        ):
            checker.run(cur=None)
        assert checker.results == []

    def test_undismissed_gap_above_threshold_warns(self) -> None:
        checker = _checker()
        with (
            patch(
                "algo.monitoring.data_patrol.checks.xbrl_new_concepts.iter_companyfacts_cache",
                return_value=[Path("fake.json")],
            ),
            patch(
                "algo.monitoring.data_patrol.checks.xbrl_new_concepts.find_gaps",
                return_value=[(120, "us-gaap:SomeNewTag", "SOME FILER INC")],
            ),
        ):
            checker.run(cur=None)
        assert len(checker.results) == 1
        result = checker.results[0]
        assert result.check_name == "xbrl_new_concepts"
        assert result.severity == "warn"
        assert result.details["count"] == 1
        assert result.details["examples"][0]["concept"] == "us-gaap:SomeNewTag"

    def test_no_gaps_means_no_finding(self) -> None:
        checker = _checker()
        with (
            patch(
                "algo.monitoring.data_patrol.checks.xbrl_new_concepts.iter_companyfacts_cache",
                return_value=[Path("fake.json")],
            ),
            patch(
                "algo.monitoring.data_patrol.checks.xbrl_new_concepts.find_gaps",
                return_value=[],
            ),
        ):
            checker.run(cur=None)
        assert checker.results == []

    def test_scan_failure_logs_error_not_raise(self) -> None:
        checker = _checker()
        with patch(
            "algo.monitoring.data_patrol.checks.xbrl_new_concepts.iter_companyfacts_cache",
            side_effect=RuntimeError("cache read failed"),
        ):
            results = checker.run(cur=None)
        assert len(results) == 1
        assert results[0].severity == "error"
