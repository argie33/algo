"""Regression test for FinancialStatementFlagDriftChecker
(algo/monitoring/data_patrol/checks/financial_statement_flag_drift.py) - the DataPatrol
companion to scripts/fix_stuck_available_but_null_financial_statement_flags.py (2026-09-10,
goal: retroactive correction of financial_statement rows stuck
data_unavailable=FALSE/reason=NULL with every required field NULL). This checker exists so a
row that ends up stuck this way again in the future (e.g. a new force-null code path that
bypasses post_run()'s flag sync) surfaces on the next scheduled DataPatrol pass instead of
only when a human happens to re-run the one-time script by hand.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.financial_statement_flag_drift import (
    _REQUIRED_FIELDS_BY_TABLE,
    FinancialStatementFlagDriftChecker,
)
from algo.monitoring.data_patrol.config import ERROR, WARN, PatrolConfig


def _checker() -> FinancialStatementFlagDriftChecker:
    return FinancialStatementFlagDriftChecker(PatrolConfig())


class TestCheckStuckAvailableButNullRows:
    def test_all_clean_tables_produce_no_findings(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.fetchone.return_value = (0, 0)
        results = checker.run(cur)
        assert results == []

    def test_stuck_rows_log_warn_with_counts(self) -> None:
        checker = _checker()
        cur = MagicMock()
        # First table (annual_balance_sheet) has stuck rows, every other table is clean.
        responses = [(12, 5)] + [(0, 0)] * (len(_REQUIRED_FIELDS_BY_TABLE) - 1)
        cur.fetchone.side_effect = responses
        results = checker.run(cur)
        assert len(results) == 1
        finding = results[0]
        assert finding.severity == WARN
        assert finding.target_table == "annual_balance_sheet"
        assert finding.details == {"row_count": 12, "symbol_count": 5}
        assert "12 row(s)" in finding.message
        assert "5 symbol(s)" in finding.message

    def test_every_configured_table_is_checked(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.fetchone.return_value = (1, 1)
        results = checker.run(cur)
        checked_tables = {r.target_table for r in results}
        assert checked_tables == set(_REQUIRED_FIELDS_BY_TABLE.keys())

    def test_query_failure_logs_error_and_continues(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.execute.side_effect = [RuntimeError("boom")] + [None] * (len(_REQUIRED_FIELDS_BY_TABLE) - 1)
        cur.fetchone.return_value = (0, 0)
        results = checker.run(cur)
        errors = [r for r in results if r.severity == ERROR]
        assert len(errors) == 1
        assert "boom" in errors[0].message
