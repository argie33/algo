"""Regression test for the CHTR stale-fiscal-year-stub bug found live 2026-08-31 (goal
session: "get all the data we need" full-coverage audit).

annual_income_statement.fiscal_year=2026 held a real-looking $27.123B "revenue" for CHTR
(Charter Communications, a calendar-fiscal-year filer), written 2026-08-01 by an earlier
version of this extraction pipeline that mistakenly accepted a partial-year/interim SEC fact
as a complete annual figure. That acceptance bug was since fixed elsewhere (a fresh, full-
history refetch genuinely returns no FY2026 entry at all for CHTR today), but nothing ever
retracted the row the OLD bug already wrote - the normal `fiscal_year > since_year` filter
only ever adds newer years, it never removes one no longer confirmed by SEC. This silently
poisoned every downstream "most recent fiscal year" calculation (CHTR's revenue_growth_1y
computed a nonsensical -50.48%, comparing the stub's implausibly low value against the real
FY2025 total, instead of the correct ~-0.56%).

Fixed via SecEdgarStatementLoader.fetch_incremental(): when an incremental refetch happens
(since is not None), compare the freshest full-history fetch's maximum fiscal_year against
any fiscal year the DB currently marks available (data_unavailable=FALSE) - anything beyond
that maximum is no longer backed by any data this extraction pipeline can produce and gets
retracted (data_unavailable=TRUE), the same explicit governance-marker convention every other
data-availability signal in this codebase already follows.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.helpers.sec_base import SecEdgarStatementLoader


class _FakeCursor:
    """Dispatches fetchone/fetchall/execute based on the executed query's shape, since
    fetch_incremental() issues several distinct queries (desync check, unavailable_years
    base query, per-core-field retry query, and this fix's retraction UPDATE) against the
    same symbol within one call."""

    def __init__(self, symbol_has_any_row: bool, stale_future_years: list[int]) -> None:
        self._symbol_has_any_row = symbol_has_any_row
        self._stale_future_years = stale_future_years
        self.executed_queries: list[str] = []
        self.update_calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        self.executed_queries.append(query)
        if query.strip().startswith("UPDATE"):
            self.update_calls.append((query, params))
            # Simulate one row retracted per stale year that matches the WHERE fiscal_year > %s bound.
            max_fetched = params[-1]
            self.rowcount = sum(1 for y in self._stale_future_years if y > max_fetched)

    def fetchone(self) -> tuple[Any, ...] | None:
        return (1,) if self._symbol_has_any_row else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        # Both the data_unavailable=TRUE query and the core-field-NULL retry query return
        # nothing here - this test is only exercising the NEW retraction path, not the
        # pre-existing retry-candidate mechanisms.
        return []


def _make_loader(statement_type: str = "income") -> SecEdgarStatementLoader:
    loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
    loader.table_name = "annual_income_statement"
    loader.period = "annual"
    loader.statement_type = statement_type
    loader.is_symbol_based = True
    return loader


def _run_with_fake_db(
    loader: SecEdgarStatementLoader,
    symbol: str,
    sec_rows: list[dict[str, Any]],
    symbol_has_any_row: bool,
    stale_future_years: list[int],
) -> _FakeCursor:
    fake_cursor = _FakeCursor(symbol_has_any_row, stale_future_years)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    loader._sec_client = MagicMock()
    loader._sec_client.symbol_to_cik.return_value = "0001091667"
    loader._sec_client.get_income_statement.return_value = sec_rows
    loader._STATEMENT_TYPE_TO_METHOD = {"income": "get_income_statement"}

    import datetime

    with patch("utils.db.context.DatabaseContext", return_value=fake_ctx):
        loader.fetch_incremental(symbol, datetime.date(2026, 8, 1))
    return fake_cursor


class TestStaleFutureFiscalYearRetraction:
    def test_stale_fiscal_year_beyond_fresh_refetch_max_is_retracted(self) -> None:
        # Fresh full-history refetch tops out at FY2025 (no genuine FY2026 entry) - matches
        # the live CHTR case where FY2026 has no real 10-K yet.
        sec_rows = [
            {"symbol": "CHTR", "fiscal_year": 2025, "revenues": 54_774_000_000},
            {"symbol": "CHTR", "fiscal_year": 2024, "revenues": 55_085_000_000},
        ]
        loader = _make_loader()

        cursor = _run_with_fake_db(loader, "CHTR", sec_rows, symbol_has_any_row=True, stale_future_years=[2026])

        assert cursor.update_calls, "Expected a retraction UPDATE for the stale FY2026 stub"
        update_query, params = cursor.update_calls[0]
        assert "data_unavailable = TRUE" in update_query
        assert params[0] == "CHTR"
        assert params[1] == 2025  # max fiscal_year actually reproduced by the fresh refetch
        assert cursor.rowcount == 1, "The stale FY2026 row should actually be retracted"

    def test_no_retraction_when_fresh_refetch_confirms_the_latest_year(self) -> None:
        # Normal case: the freshest fiscal year fetched IS the max, nothing to retract.
        sec_rows = [
            {"symbol": "MSFT", "fiscal_year": 2026, "revenues": 270_000_000_000},
            {"symbol": "MSFT", "fiscal_year": 2025, "revenues": 245_000_000_000},
        ]
        loader = _make_loader()

        cursor = _run_with_fake_db(loader, "MSFT", sec_rows, symbol_has_any_row=True, stale_future_years=[])

        assert cursor.rowcount == 0, "No stale year exists beyond the fresh refetch max - nothing should be retracted"
