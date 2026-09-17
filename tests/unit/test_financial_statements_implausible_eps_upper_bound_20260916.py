"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep):
_sweep_stale_implausible_eps() was missing the SYMMETRIC upper-bound check - it only
caught implied shares implausibly SMALL (abs(net_income/eps) < 10,000), not implausibly
LARGE (abs(net_income/eps) > 50,000,000,000).

Live-confirmed via ELVA (CIK 1844450, an IFRS filer): FY2022/FY2023 both tag
"WeightedAverageShares" ~1000x too large (33,832,784,000 vs. the filer's own correctly-
scaled FY2024 fact of 34,012,383 for the same concept) - a filer-side XBRL tagging error
that produced earnings_per_share off by 1000x (-0.0000437 instead of the real -0.0437).
No company on Earth has 33+ billion implied shares for ~$44M revenue - this is exactly
the kind of confidently-wrong value _sweep_stale_implausible_eps() already exists to
catch, just missing this direction.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "income", period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _mock_write_context() -> tuple[MagicMock, MagicMock]:
    mock_cur = MagicMock()
    mock_cur.rowcount = 1
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


class TestImplausibleEpsUpperBound:
    def test_sweep_sql_includes_upper_bound_check(self) -> None:
        loader = _make_loader()
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sql_calls = [c[0][0] for c in mock_cur.execute.call_args_list]
        implausible_eps_sql = next(sql for sql in sql_calls if "earnings_per_share = CASE" in sql)
        assert "50000000000" in implausible_eps_sql
        assert "10000" in implausible_eps_sql

    def test_lower_bound_still_present(self) -> None:
        """Don't regress the original 2026-08-24 lower-bound (implied shares < 10,000)."""
        loader = _make_loader()
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sql_calls = [c[0][0] for c in mock_cur.execute.call_args_list]
        implausible_eps_sql = next(sql for sql in sql_calls if "earnings_per_share = CASE" in sql)
        assert "< 10000" in implausible_eps_sql
        assert "> 50000000000" in implausible_eps_sql
