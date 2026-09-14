"""Regression test for `_sweep_correct_cumulative_ytd_field_monotonic`
(loaders/helpers/financial_statements_q4_sweeps.py), added 2026-09-13 (goal session:
DataPatrol WARN-backlog audit, quarterly_stock_based_compensation_nonnegative).

The pre-existing `_sweep_correct_cumulative_ytd_field` only catches a cumulative-YTD-stored-
as-discrete-quarter bug when Q2 and Q3 are byte-identical (no real incremental activity after
Q2). AAPL/META/UNH (stock_based_compensation) and Mastercard/MA (common_stock_repurchased)
all have genuinely increasing cumulative facts (Q1 < Q2 < Q3, never equal), so they never
matched that fingerprint - live-confirmed via META FY2024 (stored Q1/Q2/Q3 = $3,562M/$8,178M/
$12,428M, annual = $16,690M): the existing FY-minus-9mo Q4 derivation computes annual -
stored_Q3, and since stored_Q3 already double-counts Q1+Q2's cumulative overlap the derived
Q4 goes negative whenever stored_Q1+Q2+Q3 exceeds the real annual total. Telescoping
(true_Qn = stored_Qn - stored_Q(n-1)) reconciles META/UNH/MA exactly to their real annual
totals.

Uses a temp-table snapshot (`_cum_ytd_mono_candidates`) rather than a `data_source` marker
for its idempotency/correlation, per a same-day follow-up fix (live-caught via MA FY2018
common_stock_repurchased): `data_source` is a single per-ROW column shared by every
cash-flow field, so a marker set while correcting one field falsely blocks a different
field's correction on the same symbol/year.
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


class TestSweepCorrectCumulativeYtdFieldMonotonic:
    def test_detection_fingerprint_is_conservative_for_both_fields(self) -> None:
        loader = _make_loader()
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        for field in ("stock_based_compensation", "common_stock_repurchased"):
            insert_sql = next(s for s in sqls if "INSERT INTO _cum_ytd_mono_candidates" in s and f"q1.{field}" in s)
            normalized = " ".join(insert_sql.split())
            # Unambiguous, already-proven-wrong signal: the field's own Q4 is currently
            # negative (impossible for a non-negative-by-GAAP flow field).
            assert f"q4x.{field} < 0" in normalized
            # Monotonic, not the flat exact-duplicate shape.
            assert f"q1.{field} >= 0" in normalized
            assert f"q1.{field} <= q2.{field}" in normalized
            assert f"q2.{field} <= q3x.{field}" in normalized
            # Algebraically guarantees the telescoped Q4 (annual - Q3) is non-negative too.
            assert f"a.{field} >= q3x.{field}" in normalized

    def test_q3_correction_runs_before_q2_and_before_q4_derivation(self) -> None:
        loader = _make_loader()
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        for field in ("stock_based_compensation", "common_stock_repurchased"):
            # Both this sweep's Q2 step and the flat exact-duplicate sweep's Q2 step share
            # the identical `SET {field} = c.q2_val - c.q1_val` text (only the FROM table
            # differs), so disambiguate via the FROM clause naming _cum_ytd_mono_candidates.
            q3_sql = next(
                s for s in sqls if f"SET {field} = c.q3_val - c.q2_val" in s and "_cum_ytd_mono_candidates" in s
            )
            q2_sql = next(
                s for s in sqls if f"SET {field} = c.q2_val - c.q1_val" in s and "_cum_ytd_mono_candidates" in s
            )
            q4_derivation_sql = next(s for s in sqls if f"{field} = derived.{field}" in s)
            assert sqls.index(q3_sql) < sqls.index(q2_sql) < sqls.index(q4_derivation_sql)

    def test_only_the_two_verified_fields_get_this_monotonic_sweep(self) -> None:
        loader = _make_loader()
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        for field in ("capex", "dividends_paid", "financing_cash_flow", "investing_cash_flow"):
            assert not any("INSERT INTO _cum_ytd_mono_candidates" in s and f"q1.{field}" in s for s in sqls)

    def test_annual_cash_flow_run_does_not_trigger_this_sweep(self) -> None:
        loader = _make_loader(period="annual")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "_cum_ytd_mono_candidates" not in call[0][0]

    def test_temp_table_is_dropped_after_use_per_field(self) -> None:
        loader = _make_loader()
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        create_count = sum(1 for s in sqls if "CREATE TEMP TABLE IF NOT EXISTS _cum_ytd_mono_candidates" in s)
        drop_count = sum(1 for s in sqls if s.strip() == "DROP TABLE _cum_ytd_mono_candidates")
        # Once per field this sweep covers (stock_based_compensation, common_stock_repurchased).
        assert create_count == 2
        assert drop_count == 2
