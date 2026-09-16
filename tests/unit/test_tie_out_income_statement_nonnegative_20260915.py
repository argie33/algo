"""Tests for algo/monitoring/data_patrol/checks/tie_out_income_statement_nonnegative.py.

Added 2026-09-15 (/goal "make sure we have the right tie outs for all we should" session) -
income-statement side of the DQC_0015/US1-style nonnegative-magnitude guard, same check class
as tie_out_nonnegative_magnitudes.py's balance-sheet fields but for interest_expense/
depreciation_expense/amortization_expense/research_development_expense/
goodwill_impairment_loss, which had zero tie-out coverage before this.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.tie_out import TieOutChecker
from algo.monitoring.data_patrol.config import INFO, WARN, PatrolConfig


def _checker() -> TieOutChecker:
    return TieOutChecker(PatrolConfig())


def _mock_cursor(fetchall_results: list[list[dict]]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.side_effect = fetchall_results
    return cur


_EXPECTED_FIELDS = [
    "interest_expense",
    "depreciation_expense",
    "amortization_expense",
    "research_development_expense",
    "goodwill_impairment_loss",
]


class TestIncomeStatementNonnegativeFields:
    def test_flags_negative_row_for_each_field(self) -> None:
        for field in _EXPECTED_FIELDS:
            cur = _mock_cursor([[{"symbol": "BADCO", "fiscal_year": 2025, field: -500.0}]])
            checker = _checker()
            getattr(checker, f"check_{field}_nonnegative")(cur)
            assert len(checker.results) == 1
            result = checker.results[0]
            assert result.severity == WARN
            assert result.check_name == f"{field}_nonnegative"
            assert result.details["examples"][0]["symbol"] == "BADCO"

    def test_clean_row_logs_info_not_silence(self) -> None:
        cur = _mock_cursor([[{"symbol": "GOODCO", "fiscal_year": 2025, "interest_expense": 500.0}]])
        checker = _checker()
        checker.check_interest_expense_nonnegative(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_quarterly_variant_uses_quarterly_table_and_columns(self) -> None:
        cur = _mock_cursor(
            [[{"symbol": "BADCO", "fiscal_year": 2025, "fiscal_quarter": "Q2", "interest_expense": -500.0}]]
        )
        checker = _checker()
        checker.check_quarterly_interest_expense_nonnegative(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "quarterly_income_statement" in executed_sql
        assert "b.fiscal_quarter" in executed_sql
        assert checker.results[0].check_name == "quarterly_interest_expense_nonnegative"
        assert checker.results[0].details["examples"][0]["fiscal_quarter"] == "Q2"

    def test_annual_variant_uses_annual_income_statement_table(self) -> None:
        cur = _mock_cursor([[{"symbol": "BADCO", "fiscal_year": 2025, "goodwill_impairment_loss": -500.0}]])
        checker = _checker()
        checker.check_goodwill_impairment_loss_nonnegative(cur)
        executed_sql = cur.execute.call_args[0][0]
        assert "annual_income_statement" in executed_sql
