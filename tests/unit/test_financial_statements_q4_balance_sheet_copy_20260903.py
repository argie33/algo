"""Regression test for a 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep) to load_financial_statements.py's post_run() - balance-sheet sibling of
_sweep_derive_missing_q4() (income statement).

US GAAP filers never file a discrete Q4 10-Q, so quarterly_balance_sheet's Q4 row has no
directly-tagged XBRL fact. Unlike the income statement, the balance sheet is a point-in-time
snapshot: a fiscal year's Q4 balance sheet IS, by definition, the same year-end snapshot the
annual 10-K reports - live-confirmed via AAL, whose real Q4 2025 total_assets already on file
is byte-identical to its annual FY2025 total_assets. Recovering it is a direct copy, not an
arithmetic derivation - no scale-mismatch/corroboration risk.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "balance", period: str = "quarterly") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _mock_write_context(rowcount: int = 5) -> tuple[MagicMock, MagicMock]:
    mock_cur = MagicMock()
    mock_cur.rowcount = rowcount
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


class TestQ4BalanceSheetCopy:
    def test_quarterly_balance_sheet_run_issues_copy_update(self) -> None:
        loader = _make_loader(statement_type="balance", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        copy_sqls = [s for s in sqls if "quarterly_balance_sheet q4" in s]
        assert len(copy_sqls) == 1
        sql = copy_sqls[0]
        assert "fiscal_quarter = 4" in sql
        assert "total_assets = a.total_assets" in sql
        assert "stockholders_equity = a.stockholders_equity" in sql
        assert "'derived_annual_q4'" in sql

    def test_annual_balance_sheet_run_does_not_trigger_q4_copy(self) -> None:
        loader = _make_loader(statement_type="balance", period="annual")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "quarterly_balance_sheet" not in call[0][0]

    def test_income_statement_run_does_not_trigger_q4_balance_copy(self) -> None:
        loader = _make_loader(statement_type="income", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "quarterly_balance_sheet" not in call[0][0]
