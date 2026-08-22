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

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader() -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type="income", period="annual")


def _mock_db_context(existing_rows: list[tuple[Any, ...]]) -> MagicMock:
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = existing_rows
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx


class TestTransientRefetchGapNotDowngraded:
    def test_existing_available_row_not_downgraded_on_empty_refetch(self) -> None:
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

    def test_new_row_with_no_prior_data_still_marked_unavailable(self) -> None:
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

    def test_existing_row_already_stuck_true_with_real_data_self_heals(self) -> None:
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

    def test_existing_row_as_real_dictrow_shape_not_downgraded(self) -> None:
        """FIXED 2026-08-22 (goal session: CNK/Cinemark balance-sheet puzzle): every other test
        in this file mocks the existing-row lookup with plain Python tuples, e.g.
        `("GDS", 2025, ...)` - but the REAL `DatabaseContext("read")` cursor returns rows as
        `psycopg2.extras.DictRow`, a LIST subclass. Slicing a list (`existing_row[:n]`) returns
        a plain `list`, not a tuple - `already_available.add(key)` then raised `TypeError:
        unhashable type: 'list'` on EVERY call, silently swallowed by the broad `except
        Exception` a few lines below and logged only at DEBUG (invisible in this loader's
        normal WARNING/ERROR output). This made the entire already_available rescue - the exact
        mechanism the other 3 tests in this file exist to lock in - silently inert since it was
        introduced: `already_available` was always an empty set, for every symbol, every run.
        Live-confirmed via CNK (Cinemark): FY2022's real total_assets/stockholders_equity sit in
        the DB, but a fresh run kept re-marking it data_unavailable=TRUE anyway. None of the
        tuple-mocked tests above could have caught this - they don't reproduce the real cursor's
        return type. Fixed via `tuple(existing_row[:n_key_fields])` at the call site."""
        loader = ConsolidatedFinancialStatementsLoader(statement_type="balance", period="annual")
        rows = [
            {
                "symbol": "CNK",
                "fiscal_year": 2022,
                "total_assets": None,
                "stockholders_equity": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        # Real cursor rows are list subclasses (psycopg2.extras.DictRow) - plain `list`, not
        # `tuple`, is the point of this test. required_cols is sorted alphabetically
        # ("stockholders_equity" < "total_assets"), so that's the column order here.
        existing = [["CNK", 2022, 194_800_000, 4_850_500_000]]

        with (
            patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r),
            patch("loaders.load_financial_statements.DatabaseContext", return_value=_mock_db_context(existing)),
        ):
            result = loader.transform(rows)

        assert result[0]["data_unavailable"] is False
        assert result[0]["reason"] is None

    def test_no_downgrade_guard_lookup_when_all_rows_already_have_required_data(self) -> None:
        """The common, healthy case (real data every run) must not trigger the downgrade-guard
        DB round-trip this test module is about.

        UPDATED 2026-08-21: this used to assert DatabaseContext was never called at all, but a
        later, unrelated fix (commit a3a0339af, same session) added an unconditional
        company_info_sec.shares_outstanding cross-check to transform() that always issues one
        query per batch regardless of downgrade status - a real, intentional DB call this test
        predates. Narrowed to assert the specific *downgrade-guard* query (the one this file's
        other 3 tests exercise, selecting required_cols from self.table_name) is skipped, since
        that's this test's actual, still-valid intent - not "zero DB calls of any kind"."""
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

        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur
        mock_ctx.__exit__.return_value = False

        with (
            patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r),
            patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx),
        ):
            result = loader.transform(rows)

        downgrade_guard_queries = [
            call.args[0] for call in mock_cur.execute.call_args_list if f"FROM {loader.table_name}" in call.args[0]
        ]
        assert not downgrade_guard_queries, (
            "The downgrade-guard existing-row lookup must be skipped entirely when every row "
            f"in the batch already has real required-metric data: {downgrade_guard_queries}"
        )
        assert result[0]["data_unavailable"] is False
