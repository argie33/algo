"""Regression test for a 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep) to load_financial_statements.py's post_run() - pretax_income/income_tax_expense
siblings of _sweep_derive_missing_q4_interest_expense().

Both are flow quantities, additive across a fiscal year's four quarters, so
FY_annual - (Q1+Q2+Q3) recovers a real Q4 value. Live-confirmed 27,992 pretax_income /
27,836 income_tax_expense rows recoverable. Neither gets a non-negative floor - unlike
revenue/interest_expense, a real Q4 can legitimately post a pretax loss or a tax benefit
(negative income_tax_expense), same "no floor" treatment as net_income.
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


class TestDeriveMissingQ4PretaxAndTax:
    def test_quarterly_income_statement_run_issues_both_updates(self) -> None:
        loader = _make_loader(statement_type="income", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        pretax_sqls = [s for s in sqls if "pretax_income = derived.pretax_income" in s]
        tax_sqls = [s for s in sqls if "income_tax_expense = derived.income_tax_expense" in s]
        assert len(pretax_sqls) == 1
        assert len(tax_sqls) == 1

        # Neither gets a non-negative floor - both can legitimately be negative.
        assert ">= 0" not in pretax_sqls[0]
        assert ">= 0" not in tax_sqls[0]

        # Each is gated independently on its own field, not on revenue/net_income/each other.
        assert "q4x.pretax_income IS NULL" in pretax_sqls[0]
        assert "q4x.income_tax_expense IS NULL" in tax_sqls[0]

    def test_annual_income_statement_run_does_not_trigger_pretax_tax_sweep(self) -> None:
        loader = _make_loader(statement_type="income", period="annual")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "pretax_income = derived.pretax_income" not in call[0][0]
            assert "income_tax_expense = derived.income_tax_expense" not in call[0][0]
