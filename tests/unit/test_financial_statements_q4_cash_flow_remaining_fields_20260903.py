"""Regression test for a 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep) to load_financial_statements.py's post_run() - financing_cash_flow/
investing_cash_flow/dividends_paid/stock_based_compensation/common_stock_repurchased
siblings of _sweep_derive_missing_q4_cash_flow() (operating_cash_flow).

Same accounting identity (FY_annual - (Q1+Q2+Q3)), each field gated independently on its
own null-check. No non-negative floor on any of them - financing/investing cash flow
legitimately go either sign, and this file has no independently-verified sign convention to
floor the other three against.
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


class TestDeriveMissingQ4CashFlowRemainingFields:
    def test_quarterly_cash_flow_run_issues_all_six_updates(self) -> None:
        loader = _make_loader(statement_type="cashflow", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        for field in (
            "financing_cash_flow",
            "investing_cash_flow",
            "dividends_paid",
            "stock_based_compensation",
            "common_stock_repurchased",
            "capex",
        ):
            field_sqls = [s for s in sqls if f"{field} = derived.{field}" in s]
            assert len(field_sqls) == 1, f"expected exactly one UPDATE for {field}"
            assert f"q4x.{field} IS NULL" in field_sqls[0]
            assert ">= 0" not in field_sqls[0]

    def test_quarterly_cash_flow_run_derives_free_cash_flow_from_ocf_minus_capex(self) -> None:
        loader = _make_loader(statement_type="cashflow", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        fcf_sqls = [s for s in sqls if "free_cash_flow = operating_cash_flow - capex" in s]
        assert len(fcf_sqls) == 1
        assert "fiscal_quarter = 4" in fcf_sqls[0]
        assert "free_cash_flow IS NULL" in fcf_sqls[0]
        assert "operating_cash_flow IS NOT NULL" in fcf_sqls[0]
        assert "capex IS NOT NULL" in fcf_sqls[0]

    def test_annual_cash_flow_run_does_not_trigger_remaining_fields_sweep(self) -> None:
        loader = _make_loader(statement_type="cashflow", period="annual")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "financing_cash_flow = derived.financing_cash_flow" not in call[0][0]
