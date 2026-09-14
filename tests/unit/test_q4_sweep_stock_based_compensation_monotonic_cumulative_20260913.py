"""Regression test for `_sweep_correct_cumulative_ytd_stock_based_compensation_monotonic`
(loaders/helpers/financial_statements_q4_sweeps.py), added 2026-09-13 (goal session:
DataPatrol WARN-backlog audit, quarterly_stock_based_compensation_nonnegative).

The pre-existing `_sweep_correct_cumulative_ytd_field` only catches a cumulative-YTD-stored-
as-discrete-quarter bug when Q2 and Q3 are byte-identical (no real incremental activity after
Q2). AAPL/META/UNH all have genuinely increasing cumulative facts (Q1 < Q2 < Q3, never equal),
so they never matched that fingerprint - live-confirmed via META FY2024 (stored Q1/Q2/Q3 =
$3,562M/$8,178M/$12,428M, annual = $16,690M): the existing FY-minus-9mo Q4 derivation computes
16,690 - 12,428 = a deeply wrong Q4 of $4,262M... no wait, computes annual - stored_Q3, and
since stored_Q3 already double-counts Q1+Q2's cumulative overlap the derived Q4 goes negative
whenever stored_Q1+Q2+Q3 exceeds the real annual total. Telescoping (true_Qn = stored_Qn -
stored_Q(n-1)) reconciles META/UNH exactly to their real annual totals.
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


class TestSweepCorrectCumulativeStockBasedCompensationMonotonic:
    def test_detection_fingerprint_is_conservative(self) -> None:
        loader = _make_loader()
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        q3_sql = next(s for s in sqls if "q3.stock_based_compensation - src.q2_val" in s and "derived_ytd_mono" in s)
        normalized = " ".join(q3_sql.split())
        # Unambiguous, already-proven-wrong signal: the field's own Q4 is currently negative
        # (impossible for a non-negative-by-GAAP flow field).
        assert "q4x.stock_based_compensation < 0" in normalized
        # Monotonic, not the flat exact-duplicate shape.
        assert "q1.stock_based_compensation >= 0" in normalized
        assert "q1.stock_based_compensation <= q2.stock_based_compensation" in normalized
        assert "q2.stock_based_compensation <= q3x.stock_based_compensation" in normalized
        # Algebraically guarantees the telescoped Q4 (annual - Q3) is non-negative too.
        assert "a.stock_based_compensation >= q3x.stock_based_compensation" in normalized
        # Never re-fires on its own prior output.
        assert "q2.data_source IS DISTINCT FROM 'derived_ytd_mono'" in normalized
        assert "q3x.data_source IS DISTINCT FROM 'derived_ytd_mono'" in normalized

    def test_q3_correction_runs_before_q2_and_before_q4_derivation(self) -> None:
        loader = _make_loader()
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        q3_sql = next(s for s in sqls if "q3.stock_based_compensation - src.q2_val" in s and "derived_ytd_mono" in s)
        q2_sql = next(s for s in sqls if "q2.stock_based_compensation - src.q1_val" in s and "derived_ytd_mono" in s)
        q4_derivation_sql = next(s for s in sqls if "stock_based_compensation = derived.stock_based_compensation" in s)
        assert sqls.index(q3_sql) < sqls.index(q2_sql) < sqls.index(q4_derivation_sql)

    def test_only_stock_based_compensation_gets_this_monotonic_sweep(self) -> None:
        loader = _make_loader()
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        for field in (
            "common_stock_repurchased",
            "capex",
            "dividends_paid",
            "financing_cash_flow",
            "investing_cash_flow",
        ):
            assert not any(f"q4x.{field} < 0" in s and "derived_ytd_mono" in s for s in sqls)

    def test_annual_cash_flow_run_does_not_trigger_this_sweep(self) -> None:
        loader = _make_loader(period="annual")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "derived_ytd_mono" not in call[0][0]
