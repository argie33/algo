"""Regression test for a 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep) to load_financial_statements.py's post_run().

US GAAP filers never file a discrete "three months ended" Q4 10-Q - Q4 results are only ever
disclosed as part of the full-year 10-K, so quarterly_income_statement's Q4 row has no
directly-tagged XBRL fact to extract, ever, for any domestic filer. Live-confirmed 3,816
symbols / 36,812 rows sit at data_unavailable/'incomplete_sec_filing_income' purely because of
this - the single largest class found this session.

Fix: _sweep_derive_missing_q4(), called from post_run() for quarterly_income_statement only,
derives Q4 revenue/net_income = FY_annual - (Q1+Q2+Q3) - a real accounting identity for these
two flow quantities, not a heuristic. EPS is deliberately excluded (see AZTR evidence in the
method's own docstring - subtracting quarterly EPS values is not safely additive across a
changing share count).
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


class TestDeriveMissingQ4:
    def test_quarterly_income_statement_run_issues_derive_update(self) -> None:
        loader = _make_loader(statement_type="income", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        derive_sqls = [s for s in sqls if "revenue = derived.revenue" in s]
        assert len(derive_sqls) == 1
        sql = derive_sqls[0]
        assert "fiscal_quarter = 4" in sql
        assert "fiscal_quarter = 1" in sql
        assert "fiscal_quarter = 2" in sql
        assert "fiscal_quarter = 3" in sql
        assert "a.revenue - (q1.revenue + q2.revenue + q3.revenue)" in sql
        assert "a.net_income - (q1.net_income + q2.net_income + q3.net_income)" in sql
        # Non-negative-revenue guard must be present - a negative derived revenue signals an
        # inter-filing restatement, not a real Q4 result, and must never be written.
        assert "(a.revenue - (q1.revenue + q2.revenue + q3.revenue)) >= 0" in sql
        # EPS must never appear in the SET clause - deliberately not derived this way.
        set_clause = sql.split("FROM (")[0]
        assert "earnings_per_share" not in set_clause

    def test_annual_income_statement_run_does_not_trigger_q4_sweep(self) -> None:
        loader = _make_loader(statement_type="income", period="annual")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "quarterly_income_statement" not in call[0][0]

    def test_cashflow_statement_run_does_not_trigger_q4_sweep(self) -> None:
        loader = _make_loader(statement_type="cashflow", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "quarterly_income_statement" not in call[0][0]

    def test_balance_statement_run_does_not_trigger_income_q4_sweep(self) -> None:
        """A quarterly balance-sheet run triggers its OWN Q4 sweep (the balance-sheet Q4
        copy, see test_financial_statements_q4_balance_sheet_copy_20260903.py) - it must not
        also trigger this income-statement-specific derivation."""
        loader = _make_loader(statement_type="balance", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "fiscal_quarter = 1" not in call[0][0]
