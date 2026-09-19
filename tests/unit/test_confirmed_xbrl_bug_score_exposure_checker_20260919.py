"""Regression tests for ConfirmedXbrlBugScoreExposureChecker
(algo/monitoring/data_patrol/checks/confirmed_xbrl_bug_score_exposure.py).

Added 2026-09-19 (/goal "we can only be confident in our scores if we are confident in our
data" session). Covers: clean pass (no confirmed unfixed bugs), a flagged symbol (WARN with
symbol/table/field details), and exception handling.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.confirmed_xbrl_bug_score_exposure import (
    ConfirmedXbrlBugScoreExposureChecker,
)
from algo.monitoring.data_patrol.config import ERROR, INFO, WARN, PatrolConfig


def _checker() -> ConfirmedXbrlBugScoreExposureChecker:
    return ConfirmedXbrlBugScoreExposureChecker(PatrolConfig())


def _mock_cursor(rows: list[dict]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = rows
    return cur


def _row(symbol: str, table: str, field: str, fiscal_year: int, note: str = "root-caused") -> dict:
    return {"symbol": symbol, "our_table": table, "our_field": field, "fiscal_year": fiscal_year, "review_note": note}


class TestConfirmedXbrlBugScoreExposure:
    def test_no_confirmed_bugs_logs_info(self) -> None:
        cur = _mock_cursor([])
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == INFO

    def test_confirmed_bug_flagged_warn(self) -> None:
        cur = _mock_cursor(
            [_row("COP", "annual_income_statement", "operating_income", 2025, "fallback overstates by $24.8B")]
        )
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == WARN
        assert results[0].details["symbol_count"] == 1
        assert results[0].details["row_count"] == 1
        assert results[0].details["symbols"] == ["COP"]
        assert results[0].details["examples"][0]["field"] == "operating_income"

    def test_multiple_rows_same_symbol_counted_once_in_symbol_count(self) -> None:
        cur = _mock_cursor(
            [
                _row("COP", "annual_income_statement", "operating_income", 2024),
                _row("COP", "annual_income_statement", "operating_income", 2025),
                _row("PSX", "annual_income_statement", "operating_income", 2025),
            ]
        )
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].details["symbol_count"] == 2
        assert results[0].details["row_count"] == 3
        assert results[0].details["symbols"] == ["COP", "PSX"]

    def test_exception_logged_as_error(self) -> None:
        cur = MagicMock()
        cur.fetchall.side_effect = RuntimeError("boom")
        results = _checker().run(cur)
        assert len(results) == 1
        assert results[0].severity == ERROR
