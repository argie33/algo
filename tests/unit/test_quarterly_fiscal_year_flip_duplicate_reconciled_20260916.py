"""Regression test for the 2026-09-16 fix: quarterly_income_statement/quarterly_balance_sheet/
quarterly_cash_flow are keyed on (symbol, fiscal_year, fiscal_quarter), not (symbol,
period_end). _aggregate_concepts_resolve_entry_period's fiscal_year derivation for a
non-December-FYE filer depends on fye_month, which is re-derived from a symbol's evolving SEC
evidence on every run (not cached) - when a symbol's fye_month confidence flips between two
runs, the same underlying fact (same period_end) can get assigned a different fiscal_year on a
later run. Since that's a different primary key, ON CONFLICT never fires and bulk_insert() adds
a second row instead of correcting the first - live-confirmed DB-wide sweep found 1,000+
symbol/period groups with this exact signature (e.g. AGYS, ACI, MCK, FLEX).

Fix: fetch_incremental() now reconciles this before insert - for each row it's about to write,
if the DB already has a different (fiscal_year, fiscal_quarter) row for the same symbol sharing
that row's period_end, the old one is deleted (this run's fresh resolution is authoritative).
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(
    statement_type: str = "income", table_name: str = "quarterly_income_statement"
) -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period="quarterly")
    loader.table_name = table_name
    return loader


def _mock_write_context() -> tuple[MagicMock, MagicMock]:
    mock_cur = MagicMock()
    mock_cur.rowcount = 1
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


def _mock_read_context(fetchall_result: list[tuple[Any, ...]]) -> MagicMock:
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = fetchall_result
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx


class TestStaleFiscalYearDuplicateReconciled:
    def test_stale_row_under_old_fiscal_year_is_deleted(self) -> None:
        """AGYS-shaped case: this run resolved fiscal_year=2023 for period_end 2022-12-31,
        but the DB still has a stale fiscal_year=2022 row for that same period_end (from
        before a fye_month confidence flip) - the stale row must be deleted."""
        loader = _make_loader()
        fresh_row = {
            "symbol": "AGYS",
            "fiscal_year": 2023,
            "fiscal_quarter": 3,
            "period_end": "2022-12-31",
            "revenue": 49_920_000,
        }
        read_ctx = _mock_read_context([(2022, 3, "2022-12-31")])
        write_ctx, mock_cur = _mock_write_context()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[fresh_row],
            ),
            patch(
                "loaders.load_financial_statements.DatabaseContext",
                side_effect=[read_ctx, write_ctx],
            ),
        ):
            result = loader.fetch_incremental("AGYS", None)
        assert result == [fresh_row]
        delete_sql, delete_params = mock_cur.execute.call_args_list[0][0]
        assert "DELETE FROM quarterly_income_statement" in delete_sql
        assert delete_params == ("AGYS", 2022, 3)

    def test_matching_existing_row_is_left_alone(self) -> None:
        """The common case - this run's (fiscal_year, fiscal_quarter) for a period_end
        matches what's already in the DB - must not delete anything."""
        loader = _make_loader()
        fresh_row = {
            "symbol": "AAPL",
            "fiscal_year": 2024,
            "fiscal_quarter": 4,
            "period_end": "2024-09-28",
            "revenue": 391_035_000_000,
        }
        read_ctx = _mock_read_context([(2024, 4, "2024-09-28")])
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[fresh_row],
            ),
            patch("loaders.load_financial_statements.DatabaseContext", return_value=read_ctx),
        ):
            result = loader.fetch_incremental("AAPL", None)
        assert result == [fresh_row]

    def test_annual_period_never_triggers_this_guard(self) -> None:
        """annual_* tables are keyed on (symbol, fiscal_year) alone - period_end collisions
        there are a different (already-handled) code path, not this one."""
        loader = _make_loader(table_name="annual_income_statement")
        loader.period = "annual"
        fresh_row = {"symbol": "AGYS", "fiscal_year": 2023, "period_end": "2023-03-31", "revenue": 198_065_000}
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[fresh_row],
        ):
            result = loader.fetch_incremental("AGYS", None)
        assert result == [fresh_row]

    def test_row_missing_period_end_is_skipped(self) -> None:
        """A row without a resolved period_end can't safely be reconciled - must not crash
        or issue a query keyed on nothing."""
        loader = _make_loader()
        fresh_row = {"symbol": "AGYS", "fiscal_year": 2023, "fiscal_quarter": 3, "period_end": None, "revenue": None}
        with patch.object(
            ConsolidatedFinancialStatementsLoader.__mro__[1],
            "fetch_incremental",
            return_value=[fresh_row],
        ):
            result = loader.fetch_incremental("AGYS", None)
        assert result == [fresh_row]
