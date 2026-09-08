"""Regression tests for XbrlConceptContinuityChecker
(algo/monitoring/data_patrol/checks/xbrl_concept_continuity.py).

Added 2026-09-07 (goal session continuation: "what about when companies change things - is
that covered?"). Mirrors test_xbrl_new_concept_checker_20260907.py's structure for the sibling
checker - same mock points, same shape of assertions.
"""

from pathlib import Path
from unittest.mock import patch

from algo.monitoring.data_patrol.checks.xbrl_concept_continuity import XbrlConceptContinuityChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _checker() -> XbrlConceptContinuityChecker:
    return XbrlConceptContinuityChecker(PatrolConfig())


_MOD = "algo.monitoring.data_patrol.checks.xbrl_concept_continuity"


class TestXbrlConceptContinuityChecker:
    def test_no_cache_means_no_finding(self) -> None:
        checker = _checker()
        with patch(f"{_MOD}.iter_companyfacts_cache", return_value=[]):
            checker.run(cur=None)
        assert checker.results == []

    def test_undismissed_gap_warns(self) -> None:
        checker = _checker()
        gap = {
            "cik": "0000012345",
            "entity_name": "SOME FILER INC",
            "concept": "us-gaap:NetIncomeLoss",
            "latest_expected_end": "2025-12-31",
            "prior_years_present": ["2024-12-31", "2023-12-31", "2022-12-31"],
        }
        with (
            patch(f"{_MOD}.iter_companyfacts_cache", return_value=[Path("fake.json")]),
            patch(f"{_MOD}.find_continuity_gaps", return_value=[gap]),
        ):
            checker.run(cur=None)
        assert len(checker.results) == 1
        result = checker.results[0]
        assert result.check_name == "xbrl_concept_continuity"
        assert result.severity == "warn"
        assert result.details["count"] == 1
        assert result.details["examples"][0]["concept"] == "us-gaap:NetIncomeLoss"

    def test_no_gaps_means_no_finding(self) -> None:
        checker = _checker()
        with (
            patch(f"{_MOD}.iter_companyfacts_cache", return_value=[Path("fake.json")]),
            patch(f"{_MOD}.find_continuity_gaps", return_value=[]),
        ):
            checker.run(cur=None)
        assert checker.results == []

    def test_scan_failure_logs_error_not_raise(self) -> None:
        checker = _checker()
        with patch(f"{_MOD}.iter_companyfacts_cache", side_effect=RuntimeError("cache read failed")):
            results = checker.run(cur=None)
        assert len(results) == 1
        assert results[0].severity == "error"
