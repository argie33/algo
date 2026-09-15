"""Regression tests for FinancialStatementPeriodSanityChecker
(algo/monitoring/data_patrol/checks/financial_statement_period_sanity.py) - a new checker added
2026-09-15 (live-caught via SMMT, CIK 0001599298 fiscal-year-labeling corruption) with zero
pytest coverage of its own despite being wired into DataPatrol.run() from day one - same gap
shape this repo has fixed for other checkers before (see
test_data_patrol_quality_and_price_sanity_checks_20260908.py's own docstring).
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.financial_statement_period_sanity import (
    FinancialStatementPeriodSanityChecker,
)
from algo.monitoring.data_patrol.config import ERROR, INFO, WARN, PatrolConfig


def _checker() -> FinancialStatementPeriodSanityChecker:
    return FinancialStatementPeriodSanityChecker(PatrolConfig())


class TestCheckFuturePeriodEnd:
    def test_no_future_period_end_logs_info(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.return_value = []
        checker.check_future_period_end(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO
        assert checker.results[0].target_table == "quarterly_income_statement"

    def test_future_period_end_logs_warn_with_samples(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.return_value = [
            ("AAL", 2027, 2, "2027-07-17"),
            ("MCAH", 2026, 3, "2026-09-30"),
        ]
        checker.check_future_period_end(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == WARN
        assert checker.results[0].details["count"] == 2
        symbols = {s["symbol"] for s in checker.results[0].details["samples"]}
        assert symbols == {"AAL", "MCAH"}

    def test_db_error_logged_not_raised(self) -> None:
        import psycopg2

        checker = _checker()
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("connection lost")
        checker.check_future_period_end(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == ERROR


class TestCheckFutureFiscalYearQuarter:
    def test_no_implausible_rows_logs_info_for_every_table(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.return_value = []
        checker.check_future_fiscal_year_quarter(cur)
        # 5 fiscal-bound-only tables, one INFO result each, since fetchall always returns []
        assert len(checker.results) == 5
        assert all(r.severity == INFO for r in checker.results)

    def test_implausible_quarterly_row_logs_warn(self) -> None:
        checker = _checker()
        cur = MagicMock()
        # quarterly_balance_sheet is checked first among _FISCAL_BOUND_ONLY_TABLES; return a hit
        # only for the first call, empty for the rest.
        cur.fetchall.side_effect = [
            [("XYZ", 2028, 3)],
            [],
            [],
            [],
            [],
        ]
        checker.check_future_fiscal_year_quarter(cur)
        assert len(checker.results) == 5
        assert checker.results[0].severity == WARN
        assert checker.results[0].target_table == "quarterly_balance_sheet"
        assert checker.results[0].details["count"] == 1

    def test_db_error_on_one_table_does_not_block_others(self) -> None:
        import psycopg2

        checker = _checker()
        cur = MagicMock()
        cur.execute.side_effect = [
            psycopg2.OperationalError("connection lost"),
            None,
            None,
            None,
            None,
        ]
        cur.fetchall.return_value = []
        checker.check_future_fiscal_year_quarter(cur)
        assert len(checker.results) == 5
        assert checker.results[0].severity == ERROR
        assert all(r.severity == INFO for r in checker.results[1:])


class TestRun:
    def test_run_invokes_both_subchecks(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.return_value = []
        results = checker.run(cur)
        # 1 (future_period_end) + 5 (one per fiscal-bound-only table)
        assert len(results) == 6


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
