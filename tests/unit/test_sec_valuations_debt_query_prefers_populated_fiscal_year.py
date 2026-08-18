"""Regression test for a 2026-08-17 "latest fiscal year is empty" bug in
load_sec_valuations.py's debt query (loader-review goal, continuation).

The debt query used to be a plain `ORDER BY fiscal_year DESC LIMIT 1` - live-confirmed via the
real DB that GOOGL's FY2026 annual_balance_sheet row has real stockholders_equity/
total_liabilities/cash (a genuine, non-placeholder row for an in-progress fiscal year) but
long_term_debt is NULL, while FY2025 has a real reported long_term_debt=$49.085B. Because
short_term_debt on the FY2026 row is 0 (not NULL), the existing "all four components NULL"
guard never caught this - GOOGL's sec_valuations.total_debt silently went NULL despite 10 years
of real debt history, the same "latest year is empty" bug class already fixed in this file for
the income-statement and shares_outstanding queries.

Fixed by prioritizing fiscal years where long_term_debt is populated before falling back to
fiscal_year DESC alone - mirrors the existing shares_outstanding fallback chain's "prefer a real
reported value over the most recent (possibly still-filing) year" convention. Cash is now
queried separately from debt so its freshness isn't held back by debt-field completeness.

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
    """Sequential fetchone/fetchall stand-in (same shape as the sibling total_debt test's
    _FakeCursor) that also records every executed query's SQL text for inspection.

    FIXED 2026-08-18 (missing factor inputs audit, continued): see the sibling total_debt
    test's _FakeCursor docstring - fetchall() must be sequential (income_rows first, then
    the DCF 3-year-average-FCF fallback's cash_rows) since load_sec_valuations.py added a
    second fetchall() call on 2026-08-18. The single static response this class used to
    return crashed `ocf, capex, dividends_paid = cash_rows[0]` on the second call with
    "too many values to unpack (expected 3)" for every real symbol.
    """

    def __init__(self, fetchone_results: list[tuple[Any, ...]]) -> None:
        self._fetchone_results = list(fetchone_results)
        self._fetchone_idx = 0
        self.executed_sql: list[str] = []
        self._fetchall_results = [
            [
                (
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
            ],
            [(80_000_000.0, 10_000_000.0, None)],  # cash_rows: ocf, capex, dividends_paid
        ]
        self._fetchall_idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        self.executed_sql.append(query)

    def fetchall(self) -> list[tuple[Any, ...]]:
        result = self._fetchall_results[self._fetchall_idx]
        self._fetchall_idx += 1
        return result

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


class TestDebtQueryPrefersPopulatedFiscalYear:
    def test_debt_query_orders_by_long_term_debt_populated_before_fiscal_year(self) -> None:
        fetchone_results = [
            (50.0,),  # price_daily.close
            (500_000_000.0,),  # annual_balance_sheet.stockholders_equity
            (30_000_000.0,),  # cash_and_equivalents
            (20_000_000.0, 5_000_000.0, None, None),  # debt_row
        ]
        _, cursor = _run_fetch_incremental("GOOGL", fetchone_results)

        debt_queries = [sql for sql in cursor.executed_sql if "long_term_debt" in sql and "SELECT" in sql]
        assert len(debt_queries) == 1
        debt_sql = debt_queries[0]
        assert "CASE WHEN long_term_debt IS NOT NULL" in debt_sql
        assert "fiscal_year DESC" in debt_sql

    def test_debt_query_prefers_any_debt_component_not_just_long_term_debt(self) -> None:
        # FIXED 2026-08-18 (goal: "no SEC data" audit, roic_pct/total_debt follow-up):
        # live-confirmed via ANET (Arista Networks) - long_term_debt is NULL in every fiscal
        # year on file, but FY2024 reports a real operating_lease_liability ($59.6M). The old
        # CASE tier only checked long_term_debt specifically, so a filer that never tags it at
        # all (regardless of what other debt components it does report) fell through to plain
        # `fiscal_year DESC`, picking a more recent year with ALL FOUR components NULL over an
        # older year with a real, usable component. 522 of the universe's 1,060 NULL total_debt
        # symbols have this shape.
        fetchone_results = [
            (50.0,),
            (500_000_000.0,),
            (30_000_000.0,),
            (None, 0.0, 59_642_000.0, None),  # debt_row
        ]
        _, cursor = _run_fetch_incremental("ANET", fetchone_results)

        debt_queries = [sql for sql in cursor.executed_sql if "long_term_debt" in sql and "SELECT" in sql]
        assert len(debt_queries) == 1
        debt_sql = debt_queries[0]
        assert "short_term_debt IS NOT NULL" in debt_sql
        assert "operating_lease_liability IS NOT NULL" in debt_sql
        assert "finance_lease_liability IS NOT NULL" in debt_sql

    def test_cash_is_queried_separately_from_debt(self) -> None:
        # The cash query must not be coupled to the debt-prioritization ORDER BY - it should
        # stay a plain latest-fiscal-year lookup so a fresh cash figure isn't held back just
        # because that year's debt tags aren't filed yet.
        fetchone_results = [
            (50.0,),
            (500_000_000.0,),
            (55_911_000_000.0,),  # cash_and_equivalents - real, current-year figure
            (None, 0.0, None, None),  # debt_row - GOOGL-FY2026-shaped: long_term_debt NULL
        ]
        result, cursor = _run_fetch_incremental("GOOGL", fetchone_results)

        cash_queries = [
            sql for sql in cursor.executed_sql if "cash_and_equivalents" in sql and "long_term_debt" not in sql
        ]
        assert len(cash_queries) == 1
        assert "ORDER BY fiscal_year DESC" in cash_queries[0]
        assert "CASE WHEN" not in cash_queries[0]

        row = result[0]
        assert row["total_cash"] == 55_911_000_000.0
