"""Regression test for a 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep) to load_financial_statements.py's post_run().

free_cash_flow has no direct XBRL concept - sec_base.py's transform() derives it in-row as
`operating_cash_flow - capex` from THIS run's own freshly-fetched values only. But
free_cash_flow itself is not in preserve_on_missing_fields (it's synthesized, not a
field_mapping value), so bulk_insert()'s ON CONFLICT always overwrites it with whatever this
run's row computed - including NULL whenever this run's fetch came back without a fresh value
for either operating_cash_flow or capex. Those two ARE preserved (real field_mapping values),
so a transient gap in either one leaves the DB with real, COALESCE-preserved
operating_cash_flow/capex but a permanently wiped, never-recomputed free_cash_flow.

Live-confirmed 57 rows / 39 symbols (CNQ, DB, VET, BTE and others) with real operating_cash_flow
AND capex on file right now but free_cash_flow NULL.

Fix: post_run() now also calls _sweep_missing_free_cash_flow() (annual_cash_flow only), a
table-wide `UPDATE ... SET free_cash_flow = operating_cash_flow - capex WHERE free_cash_flow
IS NULL AND operating_cash_flow IS NOT NULL AND capex IS NOT NULL` - same "recompute from
already-stored real values" discipline as the existing income-statement
_sweep_stale_implausible_eps() sweep.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "cashflow", period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _mock_write_context() -> tuple[MagicMock, MagicMock]:
    mock_cur = MagicMock()
    mock_cur.rowcount = 3
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


class TestFreeCashFlowSweep:
    def test_cashflow_statement_run_issues_recompute_update(self) -> None:
        loader = _make_loader(statement_type="cashflow")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        assert mock_cur.execute.call_count == 1
        sql = mock_cur.execute.call_args[0][0]
        assert "UPDATE annual_cash_flow" in sql
        assert "free_cash_flow = operating_cash_flow - capex" in sql
        assert "free_cash_flow IS NULL" in sql
        assert "operating_cash_flow IS NOT NULL" in sql
        assert "capex IS NOT NULL" in sql

    def test_quarterly_cash_flow_is_not_swept_for_free_cash_flow(self) -> None:
        """This free_cash_flow sweep is scoped to annual_cash_flow only - quarterly filings
        routinely omit a full cash-flow statement (interim reports), so a NULL free_cash_flow
        there is far more often genuinely absent than a transient-refetch artifact; don't
        force a value onto it. A quarterly cashflow run DOES trigger its own, separate Q4
        operating_cash_flow derivation sweep (see
        test_financial_statements_q4_cash_flow_derive_20260903.py) - this test only asserts
        the free_cash_flow-specific UPDATE never fires for quarterly."""
        loader = _make_loader(statement_type="cashflow", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "UPDATE annual_cash_flow" not in call[0][0]

    def test_income_statement_run_does_not_trigger_cashflow_sweep(self) -> None:
        loader = _make_loader(statement_type="income")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "annual_cash_flow" not in call[0][0]

    def test_balance_statement_run_does_not_trigger_cashflow_sweep(self) -> None:
        loader = _make_loader(statement_type="balance")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx) as mock_dc:
            loader.post_run()

        mock_dc.assert_not_called()
