"""Regression test for a 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep) to load_financial_statements.py's post_run() - cash-flow sibling of
_sweep_derive_missing_q4() (income statement).

operating_cash_flow is a flow quantity, additive across a fiscal year's four quarters, so
FY_annual - (Q1+Q2+Q3) recovers a real Q4 value the same way as revenue/net_income on the
income statement. Live-confirmed 929 rows recoverable. Scoped to operating_cash_flow only -
capex is deliberately excluded (frequently NULL for one or more of Q1-Q3 even when OCF is
present, so a Q4 capex subtraction would be wrong far more often).
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "cashflow", period: str = "quarterly") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _mock_write_context(rowcount: int = 5) -> tuple[MagicMock, MagicMock]:
    mock_cur = MagicMock()
    mock_cur.rowcount = rowcount
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


class TestDeriveMissingQ4CashFlow:
    def test_quarterly_cash_flow_run_issues_derive_update(self) -> None:
        loader = _make_loader(statement_type="cashflow", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        derive_sqls = [s for s in sqls if "quarterly_cash_flow q4" in s]
        assert len(derive_sqls) == 1
        sql = derive_sqls[0]
        assert "fiscal_quarter = 4" in sql
        assert "operating_cash_flow = derived.operating_cash_flow" in sql
        assert (
            "a.operating_cash_flow - (q1.operating_cash_flow + q2.operating_cash_flow + q3.operating_cash_flow)" in sql
        )
        # capex must never appear in the SET clause - deliberately not derived this way.
        set_clause = sql.split("FROM (")[0]
        assert "capex" not in set_clause

    def test_annual_cash_flow_run_does_not_trigger_q4_derive(self) -> None:
        loader = _make_loader(statement_type="cashflow", period="annual")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "quarterly_cash_flow" not in call[0][0]

    def test_income_statement_run_does_not_trigger_cash_flow_q4_derive(self) -> None:
        loader = _make_loader(statement_type="income", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "quarterly_cash_flow" not in call[0][0]
