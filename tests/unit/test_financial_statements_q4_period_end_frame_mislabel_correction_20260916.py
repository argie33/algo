"""Regression test for a 2026-09-16 fix (goal session: data-patrol/XBRL findings sweep) to
loaders/helpers/financial_statements_q4_sweeps.py.

ROOT CAUSE: for a non-December-FYE filer, SEC's `frame` tag (e.g. 'CY2017Q4') names the
CALENDAR quarter, not the filer's fiscal quarter - utils/external/sec_statements_entry_
resolution.py's _aggregate_concepts_resolve_entry_period previously trusted it directly,
mislabeling a real fiscal-Q3 fact (Oct-Dec) into a synthetic fiscal_quarter=4 bucket with the
wrong (Oct-Dec-shaped) period_end. That entry-resolution bug is fixed separately (commit
709f63165), but a Q4 row it already seeded before the fix never gets its period_end touched
by anything else: _sweep_derive_missing_q4() only UPDATEs revenue/net_income, never
period_end - so an already-wrong date stays wrong forever even after the value self-heals via
the FY-minus-9mo identity. Live-confirmed on AGYS (real FYE March 31): FY2021-2027 Q4 rows
kept period_end='<year>-12-31' (matching that year's own Q3) even after a fresh reload
recomputed revenue correctly.

Fix: _sweep_correct_q4_period_end_frame_mislabel(), called from post_run() for
quarterly_income_statement only (right after _sweep_derive_missing_q4()), corrects a Q4 row's
period_end to Q3's period_end + 3 months whenever the stored Q4 period_end falls in the same
month as that fiscal year's own Q3 period_end, one calendar year later - the specific
frame-mislabeling signature, live-verified to resolve exactly the 881-row DB-wide backlog
this fix shipped with (re-running the detection query afterward returned zero matches).
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


class TestCorrectQ4PeriodEndFrameMislabel:
    def test_quarterly_income_statement_run_issues_period_end_correction_update(self) -> None:
        loader = _make_loader(statement_type="income", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        correction_sqls = [s for s in sqls if "period_end = (q3.period_end + INTERVAL '3 months')" in s]
        assert len(correction_sqls) == 1
        sql = correction_sqls[0]
        assert "fiscal_quarter = 3" in sql
        assert "fiscal_quarter = 4" in sql
        # Narrow signature: same month, one calendar year later - never a blanket "any
        # mismatched Q4 date" rewrite, to avoid corrupting genuinely irregular (52/53-week)
        # fiscal calendars.
        assert "EXTRACT(MONTH FROM q4.period_end) = EXTRACT(MONTH FROM q3.period_end)" in sql
        assert "EXTRACT(YEAR FROM q4.period_end) = EXTRACT(YEAR FROM q3.period_end) + 1" in sql
        # data_source value must fit the column's varchar(20) limit (StringDataRightTruncation
        # live-hit during this fix's own testing with a longer value).
        assert "data_source = 'derived_fy_minus_9m'" in sql

    def test_period_end_correction_runs_after_revenue_derivation(self) -> None:
        loader = _make_loader(statement_type="income", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        revenue_idx = next(i for i, s in enumerate(sqls) if "revenue = derived.revenue" in s)
        period_end_idx = next(i for i, s in enumerate(sqls) if "period_end = (q3.period_end" in s)
        assert period_end_idx > revenue_idx

    def test_annual_income_statement_run_does_not_trigger_period_end_correction(self) -> None:
        loader = _make_loader(statement_type="income", period="annual")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "period_end = (q3.period_end + INTERVAL" not in call[0][0]
