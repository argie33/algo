"""Regression test for a 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep) to load_financial_statements.py's post_run() - interest_expense sibling of
_sweep_derive_missing_q4() (revenue/net_income).

interest_expense is a flow quantity, additive across a fiscal year's four quarters, so
FY_annual - (Q1+Q2+Q3) recovers a real Q4 value the same way. Live-confirmed 27,037 rows
recoverable - a separate, independently-gated UPDATE from the revenue/net_income sweep since
interest_expense is very often the ONLY field still missing on a Q4 row whose revenue/
net_income were already recovered (or never missing).
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "income", period: str = "quarterly") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _mock_write_context(rowcount: int = 5) -> tuple[MagicMock, MagicMock]:
    mock_cur = MagicMock()
    mock_cur.rowcount = rowcount
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


class TestDeriveMissingQ4InterestExpense:
    def test_quarterly_income_statement_run_issues_interest_expense_update(self) -> None:
        loader = _make_loader(statement_type="income", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        ie_sqls = [s for s in sqls if "interest_expense = derived.interest_expense" in s]
        assert len(ie_sqls) == 1
        sql = ie_sqls[0]
        assert "q4x.interest_expense IS NULL" in sql
        assert "q1.interest_expense + q2.interest_expense + q3.interest_expense)) >= 0" in sql
        # This UPDATE must be independent of the revenue/net_income gate - it never checks
        # revenue at all, so it can fire on a row whose revenue was already recovered.
        assert "q4x.revenue" not in sql

    def test_annual_income_statement_run_does_not_trigger_interest_expense_sweep(self) -> None:
        loader = _make_loader(statement_type="income", period="annual")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "interest_expense = derived.interest_expense" not in call[0][0]
