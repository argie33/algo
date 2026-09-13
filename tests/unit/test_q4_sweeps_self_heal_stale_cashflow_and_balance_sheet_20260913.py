"""Regression test for the 2026-09-13 widening of _sweep_derive_missing_q4_cash_flow() and
_sweep_copy_missing_q4_balance_sheet() (loaders/helpers/financial_statements_q4_sweeps.py) -
same self-healing fix as _sweep_derive_missing_q4()'s income-statement sibling (see
test_financial_statements_q4_sweep_self_heals_stale_nonnull_value_20260913.py), extended to
the other two tables sharing the identical "NULL/data_unavailable-only guard never re-fires
on a stale-but-present value" shape.

Live-confirmed the income-statement version of this bug via QCOM (a stale Q4 revenue row
survived a full reload of corrected Q1-Q3 data because it was neither NULL nor
data_unavailable=TRUE); the cash-flow and balance-sheet sweeps had the exact same guard
shape, so the same staleness is possible there whenever an annual_cash_flow/
annual_balance_sheet/quarterly_cash_flow correction (e.g. this session's NCI double-count
fixes) leaves a now-inconsistent Q4 row untouched.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str, period: str = "quarterly") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _mock_write_context(rowcount: int = 1) -> tuple[MagicMock, MagicMock]:
    mock_cur = MagicMock()
    mock_cur.rowcount = rowcount
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


class TestQ4SweepsSelfHealStaleCashflowAndBalanceSheet:
    def test_cash_flow_derive_sql_refires_on_stale_but_present_ocf(self) -> None:
        loader = _make_loader(statement_type="cashflow")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        derive_sqls = [s for s in sqls if "operating_cash_flow = derived.operating_cash_flow" in s]
        assert len(derive_sqls) == 1
        sql = derive_sqls[0]
        assert "q4x.operating_cash_flow IS NULL" in sql
        assert "q4x.data_unavailable = TRUE" in sql
        assert "q4x.operating_cash_flow IS DISTINCT FROM" in sql

    def test_balance_sheet_copy_sql_refires_on_stale_but_present_total_assets(self) -> None:
        loader = _make_loader(statement_type="balance")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        copy_sqls = [s for s in sqls if "total_assets = a.total_assets" in s]
        assert len(copy_sqls) == 1
        sql = copy_sqls[0]
        assert "q4.total_assets IS NULL" in sql
        assert "q4.data_unavailable = TRUE" in sql
        assert "q4.total_assets IS DISTINCT FROM a.total_assets" in sql
