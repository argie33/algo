"""Regression test for a 2026-09-04 fix (goal session: "missing SEC/XBRL data under 6k"
sweep continuation) to load_financial_statements.py's post_run() - operating_income/
gross_profit/cost_of_revenue/depreciation_expense/amortization_expense/
research_development_expense siblings of _sweep_derive_missing_q4() (revenue/net_income).

Same accounting identity (FY_annual - (Q1+Q2+Q3)), each field gated independently on its own
null-check. cost_of_revenue/depreciation_expense/amortization_expense/
research_development_expense get a >= 0 floor (reported as non-negative cost/expense figures);
operating_income/gross_profit get no floor (can legitimately go negative for a real quarter).
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


class TestDeriveMissingQ4IncomeRemainingFields:
    def test_quarterly_income_statement_run_issues_all_six_updates(self) -> None:
        loader = _make_loader(statement_type="income", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        for field in (
            "operating_income",
            "gross_profit",
            "cost_of_revenue",
            "depreciation_expense",
            "amortization_expense",
            "research_development_expense",
        ):
            field_sqls = [s for s in sqls if f"{field} = derived.{field}" in s]
            assert len(field_sqls) == 1, f"expected exactly one UPDATE for {field}"
            assert f"q4x.{field} IS NULL" in field_sqls[0]

    def test_floored_fields_reject_negative_derived_value(self) -> None:
        loader = _make_loader(statement_type="income", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        for field in (
            "cost_of_revenue",
            "depreciation_expense",
            "amortization_expense",
            "research_development_expense",
        ):
            field_sql = next(s for s in sqls if f"{field} = derived.{field}" in s)
            assert ">= 0" in field_sql

    def test_unfloored_fields_allow_negative_derived_value(self) -> None:
        loader = _make_loader(statement_type="income", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        for field in ("operating_income", "gross_profit"):
            field_sql = next(s for s in sqls if f"{field} = derived.{field}" in s)
            assert ">= 0" not in field_sql

    def test_annual_income_statement_run_does_not_trigger_remaining_fields_sweep(self) -> None:
        loader = _make_loader(statement_type="income", period="annual")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "operating_income = derived.operating_income" not in call[0][0]
