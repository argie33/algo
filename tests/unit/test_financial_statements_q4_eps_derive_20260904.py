"""Regression test for a 2026-09-04 fix (goal session: "missing SEC/XBRL data under 6k"
sweep) to load_financial_statements.py's post_run() - quarterly earnings_per_share
derivation (all four quarters, not Q4-only).

Unlike _sweep_derive_missing_q4()'s deliberate exclusion of EPS via subtraction (FY -
(Q1+Q2+Q3) - see that method's own AZTR evidence for why subtracting per-share values across
a changing share count is unsafe), this derives EPS the same safe way _fill_derived_eps()
already does for annual rows: net_income / THIS row's own share count, never a subtraction.
Guarded by the identical corroboration discipline: only derives when the resolved share
count agrees with company_info_sec's independently-extracted value within 20x, and an
absolute |eps| <= 100,000 ceiling (added after a live corrupted-net_income catch on INVE).
Originally scoped to fiscal_quarter=4 only (26,668 of 27,203 candidates); widened the same
day to all four quarters once proven safe in production (1,144 additional Q1-Q3 rows) - the
underlying method has no dependency on which quarter it is.
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


class TestDeriveMissingQ4Eps:
    def test_quarterly_income_statement_run_issues_eps_update(self) -> None:
        loader = _make_loader(statement_type="income", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        eps_sqls = [s for s in sqls if "earnings_per_share = derived.eps" in s]
        assert len(eps_sqls) == 1
        sql = eps_sqls[0]
        # Must divide net_income by shares, never subtract per-share values.
        assert "q4x.net_income / COALESCE(" in sql
        assert "q4x.earnings_per_share IS NULL" in sql
        # The company_info_sec corroboration guard (same 20x threshold as _fill_derived_eps).
        assert "cis.shares_outstanding" in sql
        assert "<= 20" in sql
        # The absolute EPS ceiling (live-caught via INVE's corrupted trillion-dollar
        # net_income - the share-count guard alone can't catch a bad net_income numerator).
        assert "<= 100000" in sql
        # data_source must fit the real column's VARCHAR(20) limit.
        assert "'derived_ni_shares'" in sql
        # Must NOT be restricted to Q4 only - the safe net_income/shares method applies
        # identically to every quarter, unlike the FY-minus-9mo-YTD subtraction sweeps.
        assert "fiscal_quarter = 4" not in sql
        assert "fiscal_quarter" not in sql

    def test_annual_income_statement_run_does_not_trigger_eps_sweep(self) -> None:
        loader = _make_loader(statement_type="income", period="annual")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        for call in mock_cur.execute.call_args_list:
            assert "earnings_per_share = derived.eps" not in call[0][0]
