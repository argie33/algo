"""Regression test for the 2026-09-13 fix (goal session: data-quarantine architecture audit,
RITM's negative-Q4-stock_based_compensation DataPatrol finding):
`_sweep_correct_cumulative_ytd_field` in financial_statements_q4_sweeps.py.

Root cause, live-verified against RITM's real cached SEC companyfacts JSON (CIK 0001556593):
`AllocatedShareBasedCompensationExpense` is filed exclusively as year-to-date cumulative facts
(every instance's `start` is the fiscal year's January 1st) - no discrete-quarter fact is ever
filed. The extraction layer stores the raw cumulative value as if it were the discrete quarter,
so Q2/Q3 are inflated (Q1 happens to be correct since a first quarter's cumulative-to-date
equals its own discrete value) and the pre-existing Q4 = FY - (Q1+Q2+Q3) sweep then
double/triple-subtracts the cumulative overlap, producing a deeply negative Q4 "plug" -
RITM FY2018: 1,020,000 - (420,000+1,019,000+1,019,000) = -1,438,000, matching the real
corrupted value that was live in the DB before this fix.

WIDENED same day to common_stock_repurchased/capex/dividends_paid/financing_cash_flow/
investing_cash_flow - see the method's own docstring for the individual per-field
real-SEC-source verification (RITM/Agilent/AAT/ABAT/ACN/ABEO).

FIXED again same day (temp-table + annual-overshoot guard): `data_source` is a single
per-ROW column shared by every cash-flow field, so correcting one field falsely blocked a
different field's correction on the same symbol/year - fixed via a per-call temp table
instead of relying on the shared column. Also added an annual-reconciliation check
(quarters must actually overshoot the annual total) after live-confirming 8 real symbol/
years (MA/APTV/ZTS/AGNC/AMC/DTM/RICK) have Q2==Q3 by genuine flat-accrual coincidence with
data that's already correct - the bare Q2==Q3 fingerprint alone would have wrongly
"corrected" (corrupted) them.
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
    def test_quarterly_cash_flow_run_issues_q3_then_q2_correction_per_field(self) -> None:
        loader = _make_loader(statement_type="cashflow", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        for field in (
            "stock_based_compensation",
            "common_stock_repurchased",
            "capex",
            "dividends_paid",
            "financing_cash_flow",
            "investing_cash_flow",
        ):
            # Q3's own text (`q3.{field} - c.q2_val`) is unique to this sweep, but its Q2 text
            # (`c.q2_val - c.q1_val`) is byte-identical to the monotonic sweep's own Q2 SQL for
            # stock_based_compensation/common_stock_repurchased - disambiguate via the FROM
            # clause table name (_cum_ytd_split_candidates is this sweep's own temp table).
            q3_sqls = [s for s in sqls if f"SET {field} = q3.{field} - c.q2_val" in s]
            q2_sqls = [
                s for s in sqls if f"SET {field} = c.q2_val - c.q1_val" in s and "_cum_ytd_split_candidates" in s
            ]
            assert len(q3_sqls) == 1
            assert len(q2_sqls) == 1
            # Q3's own correction must run before Q2's.
            assert sqls.index(q3_sqls[0]) < sqls.index(q2_sqls[0])

        # stock_based_compensation/common_stock_repurchased ALSO get the monotonic sweep's
        # own independent Q3/Q2 pass (see _sweep_correct_cumulative_ytd_field_monotonic).
        for field in ("stock_based_compensation", "common_stock_repurchased"):
            mono_q3_sqls = [
                s for s in sqls if f"SET {field} = c.q3_val - c.q2_val" in s and "_cum_ytd_mono_candidates" in s
            ]
            mono_q2_sqls = [
                s for s in sqls if f"SET {field} = c.q2_val - c.q1_val" in s and "_cum_ytd_mono_candidates" in s
            ]
            assert len(mono_q3_sqls) == 1
            assert len(mono_q2_sqls) == 1

    def test_detection_fingerprint_matches_verified_shapes(self) -> None:
        loader = _make_loader(statement_type="cashflow", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        # Exact-duplicate fingerprint: Q2 == Q3, Q1 < Q2, Q2 > 0, AND quarters overshoot the
        # annual total (the 2026-09-13 false-positive fix) - verified against RITM's real SEC
        # source data (FY2018: Q1=420000, Q2=Q3=1019000), Agilent's (FY2017: Q1=111000000,
        # Q2=Q3=194000000), and AAT/ABAT's (capex).
        for field in ("stock_based_compensation", "common_stock_repurchased", "capex", "dividends_paid"):
            insert_sql = next(s for s in sqls if "INSERT INTO _cum_ytd_split_candidates" in s and f"q1.{field}" in s)
            normalized = " ".join(insert_sql.split())
            assert f"q2.{field} = q3x.{field}" in normalized
            assert f"q1.{field} < q2.{field}" in normalized
            assert f"q2.{field} > 0" in normalized
            # Quarters must actually overshoot the annual total.
            assert f"(q1.{field} + q2.{field} + q3x.{field}) > a.{field}" in normalized

        # financing_cash_flow/investing_cash_flow are net flows that can legitimately be
        # negative, so they use sign_scoped=False: Q1 != Q2 == Q3, no sign requirement -
        # verified against ABEO's real SEC source data (FY2020 financing_cash_flow,
        # FY2012 investing_cash_flow), same distinction tie_out_cashflow_cumulative_
        # quarters.py already makes for these two fields.
        for field in ("financing_cash_flow", "investing_cash_flow"):
            insert_sql = next(s for s in sqls if "INSERT INTO _cum_ytd_split_candidates" in s and f"q1.{field}" in s)
            normalized = " ".join(insert_sql.split())
            assert f"q2.{field} = q3x.{field}" in normalized
            assert f"q1.{field} != q2.{field}" in normalized
            assert f"(q1.{field} + q2.{field} + q3x.{field}) > a.{field}" in normalized

    def test_q3_correction_runs_before_q4_derivation_from_remaining_fields_sweep(self) -> None:
        loader = _make_loader(statement_type="cashflow", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        q3_correction_sql = next(
            s for s in sqls if "SET stock_based_compensation = q3.stock_based_compensation - c.q2_val" in s
        )
        q4_derivation_sql = next(s for s in sqls if "stock_based_compensation = derived.stock_based_compensation" in s)
        assert sqls.index(q3_correction_sql) < sqls.index(q4_derivation_sql)

    def test_q4_self_heals_scoped_to_verified_fields_only(self) -> None:
        # 2026-09-13 widening: without this, correcting Q1-Q3 (above) would never propagate
        # to an already-populated-but-wrong Q4 stock_based_compensation/common_stock_repurchased
        # /capex, since the sibling per-field Q4 derivation loop otherwise only fills a NULL
        # cell. Scoped narrowly - the other 3 fields in the same loop stay on the conservative
        # fill-only guard until each is independently source-verified.
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

        csr_sql = " ".join(
            next(s for s in sqls if "SET common_stock_repurchased = derived.common_stock_repurchased" in s).split()
        )
        assert "q4x.data_unavailable = TRUE" in csr_sql
        assert (
            "q4x.common_stock_repurchased IS DISTINCT FROM ( a.common_stock_repurchased - "
            "(q1.common_stock_repurchased + q2.common_stock_repurchased + q3.common_stock_repurchased)" in csr_sql
        )

        capex_sql = " ".join(next(s for s in sqls if "SET capex = derived.capex" in s).split())
        assert "q4x.data_unavailable = TRUE" in capex_sql
        assert "q4x.capex IS DISTINCT FROM ( a.capex - (q1.capex + q2.capex + q3.capex)" in capex_sql

        # 2026-09-13 widening (dividends_paid/financing_cash_flow/investing_cash_flow):
        # once _sweep_correct_cumulative_ytd_field() itself covers all 6 fields (verified
        # against ACN/ABEO real SEC source data), the self-heal guard widens to match -
        # these 3 are no longer left on the conservative fill-only guard.
        for field in (
            "dividends_paid",
            "financing_cash_flow",
            "investing_cash_flow",
        ):
            field_sql = " ".join(next(s for s in sqls if f"SET {field} = derived.{field}" in s).split())
            assert "q4x.data_unavailable = TRUE" in field_sql
            assert f"q4x.{field} IS DISTINCT FROM ( a.{field} - (q1.{field} + q2.{field} + q3.{field})" in field_sql

    def test_annual_cash_flow_run_does_not_trigger_this_sweep(self) -> None:
        loader = _make_loader(statement_type="cashflow", period="annual")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "_cum_ytd_split_candidates" not in call[0][0]
            assert "_cum_ytd_mono_candidates" not in call[0][0]
