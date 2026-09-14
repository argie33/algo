"""Regression test: StalenessChecker must cover the 6 core financial-statement tables
(annual/quarterly income statement, balance sheet, cash flow).

Live-caught (goal session 2026-09-13): these tables - load_financial_statements.py's real
output, the tables this session's whole quarantine-backlog effort revolves around - had ZERO
staleness coverage despite being actively written to continuously. Unlike every other table in
this file, a per-symbol "days since this filer's own last update" threshold would be WRONG here
(a company's own quarterly filing being 80 days old between real filings is normal) - this is a
coarse, table-level "is the loader still running at all" signal (5-day threshold), matching
institutional_holdings_13f's role for its own irregular SEC-driven cadence.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.monitoring.data_patrol.checks.staleness import StalenessChecker
from algo.monitoring.data_patrol.config import PatrolConfig

_TABLES = [
    "annual_income_statement",
    "annual_balance_sheet",
    "annual_cash_flow",
    "quarterly_income_statement",
    "quarterly_balance_sheet",
    "quarterly_cash_flow",
]


def _cursor_with_latest_date(latest_date_str: str) -> MagicMock:
    cursor = MagicMock()

    def fake_execute(sql, *args, **kwargs):
        cursor._last_sql = sql

    def fake_fetchone():
        sql = cursor._last_sql
        if "MAX(" in sql:
            return (1, latest_date_str)
        return (0,)

    cursor.execute.side_effect = fake_execute
    cursor.fetchone.side_effect = fake_fetchone
    cursor.fetchall.return_value = []
    return cursor


class TestStalenessFinancialStatementTables:
    def test_all_six_tables_covered_and_fresh(self):
        with patch("algo.monitoring.data_patrol.checks.staleness._date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 13)
            checker = StalenessChecker(PatrolConfig())
            results = checker.run(_cursor_with_latest_date("2026-09-13"))

        for table in _TABLES:
            rows = [r for r in results if r.target_table == table and "age_days" in r.details]
            assert len(rows) == 1, f"{table} missing a staleness result with age_days"
            assert rows[0].severity == "info", f"{table} unexpectedly not info-severity: {rows[0].message}"
