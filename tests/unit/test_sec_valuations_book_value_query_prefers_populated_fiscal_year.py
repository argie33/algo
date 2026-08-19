"""Regression test for a 2026-08-18 "latest fiscal year is empty" bug in
load_sec_valuations.py's book-value (stockholders_equity) query (goal: "no SEC data"/loader
audit, triggered by a Loews dashboard screenshot investigation).

The book-value query was still a plain `ORDER BY fiscal_year DESC LIMIT 1` with no regard for
whether that year's stockholders_equity was actually populated - the exact "latest year is
empty" bug class already fixed in this same file for the debt query (see
test_sec_valuations_debt_query_prefers_populated_fiscal_year.py) but never applied here.
Live-confirmed via the real DB: AA (Alcoa) has real stockholders_equity=$5.157B for FY2024 but
NULL for FY2025/FY2026 (in-progress/unfiled years) - the old query picked the NULL FY2026 row
and pb_ratio silently went "missing_sec_data" for 1,225 symbols universe-wide as a result.

Fixed with the same CASE-based prioritization as the debt query: prefer a fiscal year with a
real reported value, only falling back to the bare latest year (still correctly NULL) for
companies with no balance sheet history at all.

A mocked cursor can't exercise Postgres's real ORDER BY evaluation, so this test asserts the
query text itself still contains the prioritization clause - a regression guard against someone
reverting to a plain `ORDER BY fiscal_year DESC` in a future edit.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _RecordingCursor:
    """Sequential fetchone/fetchall stand-in (same shape as the sibling debt-query test's
    _RecordingCursor) that also records every executed query's SQL text for inspection."""

    def __init__(self, fetchone_results: list[tuple[Any, ...]]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self.executed_sql: list[str] = []

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        self.executed_sql.append(query)

    def fetchall(self) -> list[tuple[Any, ...]]:
        return [
            (
                2026,  # fiscal_year
                1_000_000_000.0,  # revenue
                100_000_000.0,  # net_income
                2.0,  # earnings_per_share
                150_000_000.0,  # operating_income
                120_000_000.0,  # pretax_income
                10_000_000.0,  # depreciation_expense
                5_000_000.0,  # amortization_expense
                1_000_000_000.0,  # shares_outstanding_basic
                20_000_000.0,  # income_tax_expense
            )
        ]

    def fetchone(self) -> tuple[Any, ...] | None:
        result = self._fetchone_results[self._fetchone_idx]
        self._fetchone_idx += 1
        return result


def _run_fetch_incremental(
    symbol: str, fetchone_results: list[tuple[Any, ...]]
) -> tuple[list[dict[str, Any]], _RecordingCursor]:
    loader = _make_loader()
    fake_cursor = _RecordingCursor(fetchone_results)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    with patch("loaders.load_sec_valuations.DatabaseContext", return_value=fake_ctx):
        result = loader.fetch_incremental(symbol, None)
    return result, fake_cursor


class TestBookValueQueryPrefersPopulatedFiscalYear:
    def test_book_value_query_orders_by_stockholders_equity_populated_before_fiscal_year(self) -> None:
        fetchone_results = [
            (50.0,),  # price_daily.close
            (5_157_000_000.0,),  # annual_balance_sheet.stockholders_equity
            (80_000_000.0, 10_000_000.0, None),  # annual_cash_flow: ocf, capex, dividends_paid
            (30_000_000.0,),  # cash_and_equivalents
            (20_000_000.0, 5_000_000.0, None, None),  # debt_row
        ]
        _, cursor = _run_fetch_incremental("AA", fetchone_results)

        equity_queries = [sql for sql in cursor.executed_sql if "stockholders_equity" in sql and "SELECT" in sql]
        assert len(equity_queries) == 1
        equity_sql = equity_queries[0]
        assert "CASE WHEN stockholders_equity IS NOT NULL THEN 0 ELSE 1 END" in equity_sql
        assert "fiscal_year DESC" in equity_sql
