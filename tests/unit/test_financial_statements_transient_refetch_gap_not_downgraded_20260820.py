"""Regression test for the 2026-08-20 fix: ConsolidatedFinancialStatementsLoader.transform()'s
required-metrics check evaluated only THIS run's freshly-fetched row - but revenue/net_income/
etc. are in preserve_on_missing_fields (see __init__), so a transient concept-extraction gap
(rate limiting, a currency-conversion miss) on a fiscal year a PRIOR run already populated with
real data caused data_unavailable/reason to get overwritten to True/"incomplete_sec_filing_income"
(those 2 columns are deliberately excluded from preserve_on_missing_fields) even though the SQL-
level COALESCE preserves the real revenue/net_income value, leaving a row with real, usable data
but a false "unavailable" flag. Live-confirmed: 437 rows across 232 symbols (GDS - 12 straight
years of real revenue/net_income - AIB, AKTS) stuck exactly this way, which then excludes them
from load_value_quality_growth_metrics.py's growth-rate computation (WHERE data_unavailable =
FALSE), inflating "insufficient_history" for otherwise-complete symbols.

Fix: before downgrading a row, check whether the existing DB row for that (symbol, fiscal_year)
already has real required-metric data with data_unavailable = FALSE - if so, keep the prior
available state instead of re-judging on this run's possibly-incomplete fetch alone.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader() -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type="income", period="annual")


def _mock_db_context(existing_rows):
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = existing_rows
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx


class TestTransientRefetchGapNotDowngraded:
    def test_existing_available_row_not_downgraded_on_empty_refetch(self):
        """GDS-style case: this run's fetch has no revenue/net_income for FY2025, but the DB
        already has a real, available row for it - must not be marked unavailable."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "GDS",
                "fiscal_year": 2025,
                "revenue": None,
                "net_income": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        # Existing DB row: (symbol, fiscal_year, net_income, revenue) - required_cols sorted
        # alphabetically is ["net_income", "revenue"]
        existing = [("GDS", 2025, 949_643_000, 11_432_274_000)]

        with (
            patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r),
            patch("loaders.load_financial_statements.DatabaseContext", return_value=_mock_db_context(existing)),
        ):
            result = loader.transform(rows)

        assert result[0]["data_unavailable"] is False
        assert result[0]["reason"] is None

    def test_new_row_with_no_prior_data_still_marked_unavailable(self):
        """A genuinely new/incomplete filer (no prior DB row at all) must still be marked
        unavailable - this fix must not silently paper over real gaps."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "NEWCO",
                "fiscal_year": 2026,
                "revenue": None,
                "net_income": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]

        with (
            patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r),
            patch("loaders.load_financial_statements.DatabaseContext", return_value=_mock_db_context([])),
        ):
            result = loader.transform(rows)

        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "incomplete_sec_filing_income"

    def test_existing_row_already_stuck_true_with_real_data_self_heals(self):
        """FIXED 2026-08-21 (same bug class, one run later): the existing-row lookup used to
        also filter `data_unavailable = FALSE`, so a row that was ALREADY stuck at
        data_unavailable=True with real required data underneath it (the exact
        self-perpetuating state this whole mechanism can itself produce, before this fix
        existed) was invisible to the safety net - every future run re-derived the same
        downgrade from its own possibly-sparse refetch and wrote data_unavailable=True right
        back, forever. Live-confirmed: XP FY2017 stuck this way (real revenue=$1.28B) across
        multiple runs after the 2026-08-20 fix landed. The row's own current flag must not
        gate whether its real values are trusted - only whether the values are non-NULL."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "XP",
                "fiscal_year": 2017,
                "revenue": None,
                "net_income": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        # Existing DB row is ITSELF marked data_unavailable=True, despite carrying real values.
        existing = [("XP", 2017, 423_541_000, 1_283_616_000)]

        with (
            patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r),
            patch("loaders.load_financial_statements.DatabaseContext", return_value=_mock_db_context(existing)),
        ):
            result = loader.transform(rows)

        assert result[0]["data_unavailable"] is False
        assert result[0]["reason"] is None

    def test_no_db_lookup_when_all_rows_already_have_required_data(self):
        """The common, healthy case (real data every run) must not trigger a DB round-trip."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "AAPL",
                "fiscal_year": 2026,
                "revenue": 100_000_000,
                "net_income": 20_000_000,
                "data_unavailable": False,
                "reason": None,
            }
        ]

        with (
            patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r),
            patch("loaders.load_financial_statements.DatabaseContext") as mock_db_context,
        ):
            result = loader.transform(rows)

        mock_db_context.assert_not_called()
        assert result[0]["data_unavailable"] is False
