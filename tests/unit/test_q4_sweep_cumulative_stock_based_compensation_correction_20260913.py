"""Regression test for the 2026-09-13 fix (goal session: data-quarantine architecture audit,
RITM's negative-Q4-stock_based_compensation DataPatrol finding):
`_sweep_correct_cumulative_stock_based_compensation` in financial_statements_q4_sweeps.py.

Root cause, live-verified against RITM's real cached SEC companyfacts JSON (CIK 0001556593):
`AllocatedShareBasedCompensationExpense` is filed exclusively as year-to-date cumulative facts
(every instance's `start` is the fiscal year's January 1st) - no discrete-quarter fact is ever
filed. The extraction layer stores the raw cumulative value as if it were the discrete quarter,
so Q2/Q3 are inflated (Q1 happens to be correct since a first quarter's cumulative-to-date
equals its own discrete value) and the pre-existing Q4 = FY - (Q1+Q2+Q3) sweep then
double/triple-subtracts the cumulative overlap, producing a deeply negative Q4 "plug" -
RITM FY2018: 1,020,000 - (420,000+1,019,000+1,019,000) = -1,438,000, matching the real
corrupted value that was live in the DB before this fix.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "cashflow", period: str = "quarterly") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _mock_write_context(rowcount: int = 1) -> tuple[MagicMock, MagicMock]:
    mock_cur = MagicMock()
    mock_cur.rowcount = rowcount
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


class TestSweepCorrectCumulativeStockBasedCompensation:
    def test_quarterly_cash_flow_run_issues_q3_then_q2_correction(self) -> None:
        loader = _make_loader(statement_type="cashflow", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        q3_sqls = [s for s in sqls if "q3.stock_based_compensation - src.q2_val" in s]
        q2_sqls = [s for s in sqls if "q2.stock_based_compensation - src.q1_val" in s]
        assert len(q3_sqls) == 1
        assert len(q2_sqls) == 1
        # Q3's own correction must run before Q2's (Q2's guard depends on Q3 already being
        # flagged 'derived_ytd_split' this run).
        assert sqls.index(q3_sqls[0]) < sqls.index(q2_sqls[0])

    def test_detection_fingerprint_matches_verified_ritm_shape(self) -> None:
        loader = _make_loader(statement_type="cashflow", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        q3_sql = next(s for s in sqls if "q3.stock_based_compensation - src.q2_val" in s)
        # Exact-duplicate fingerprint: Q2 == Q3, Q1 < Q2, Q2 > 0 - verified against RITM's
        # real SEC source data (FY2018: Q1=420000, Q2=Q3=1019000).
        assert "q2.stock_based_compensation = q3x.stock_based_compensation" in q3_sql
        assert "q1.stock_based_compensation < q2.stock_based_compensation" in q3_sql
        assert "q2.stock_based_compensation > 0" in q3_sql
        # Never re-fires on its own prior output.
        assert "q2.data_source IS DISTINCT FROM 'derived_ytd_split'" in q3_sql
        assert "q3x.data_source IS DISTINCT FROM 'derived_ytd_split'" in q3_sql

    def test_q3_correction_runs_before_q4_derivation_from_remaining_fields_sweep(self) -> None:
        loader = _make_loader(statement_type="cashflow", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        q3_correction_sql = next(s for s in sqls if "q3.stock_based_compensation - src.q2_val" in s)
        q4_derivation_sql = next(s for s in sqls if "stock_based_compensation = derived.stock_based_compensation" in s)
        assert sqls.index(q3_correction_sql) < sqls.index(q4_derivation_sql)

    def test_q4_stock_based_compensation_self_heals_scoped_to_that_field_only(self) -> None:
        # 2026-09-13 widening: without this, correcting Q1-Q3 (above) would never propagate
        # to an already-populated-but-wrong Q4 stock_based_compensation, since the sibling
        # per-field Q4 derivation loop otherwise only fills a NULL cell. Scoped narrowly -
        # the other 5 fields in the same loop stay on the conservative fill-only guard until
        # each is independently source-verified.
        loader = _make_loader(statement_type="cashflow", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        sbc_sql = next(s for s in sqls if "SET stock_based_compensation = derived.stock_based_compensation" in s)
        normalized = " ".join(sbc_sql.split())
        assert "q4x.data_unavailable = TRUE" in normalized
        assert (
            "q4x.stock_based_compensation IS DISTINCT FROM ( a.stock_based_compensation - "
            "(q1.stock_based_compensation + q2.stock_based_compensation + q3.stock_based_compensation)" in normalized
        )

        for field in (
            "financing_cash_flow",
            "investing_cash_flow",
            "dividends_paid",
            "common_stock_repurchased",
            "capex",
        ):
            field_sql = " ".join(next(s for s in sqls if f"SET {field} = derived.{field}" in s).split())
            assert f"WHERE q4x.fiscal_quarter = 4 AND q4x.{field} IS NULL AND" in field_sql
            assert f"q4x.{field} IS DISTINCT FROM" not in field_sql

    def test_annual_cash_flow_run_does_not_trigger_this_sweep(self) -> None:
        loader = _make_loader(statement_type="cashflow", period="annual")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "q3.stock_based_compensation - src.q2_val" not in call[0][0]
