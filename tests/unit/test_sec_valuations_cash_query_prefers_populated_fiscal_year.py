"""Regression test for a 2026-08-19 "latest fiscal year is empty" bug in
load_sec_valuations.py's cash (cash_and_equivalents) query (goal: "no SEC data"/loader audit,
pb_ratio/total_debt follow-up).

The cash query was still a plain `ORDER BY fiscal_year DESC LIMIT 1` with no regard for whether
that year's cash_and_equivalents was actually populated - the exact "latest year is empty" bug
class already fixed in this file for the debt/book-value/ebitda/revenue/eps queries (see
test_sec_valuations_book_value_query_prefers_populated_fiscal_year.py and siblings) but never
applied here. Live-confirmed via the real DB: JACK (Jack in the Box) has real
cash_and_equivalents=$68.1M for FY2025 but NULL for FY2026 (in-progress/unfiled year) - the old
query picked the NULL FY2026 row and total_cash/cash_per_share silently went "missing_sec_data"
for 91 universe symbols as a result.

Fixed with the same CASE-based prioritization as the sibling queries: prefer a fiscal year with
a real reported value, only falling back to the bare latest year (still correctly NULL) for
companies with no balance sheet history at all.

FURTHER FIXED 2026-09-03 (goal session: "missing SEC/XBRL data under 6k" sweep): the original
2-tier CASE only distinguished NULL from non-NULL, treating an explicit 0 the same as a real
positive balance - live-confirmed via AM (Antero Midstream) and AR (Antero Resources): each has
a real cash_and_equivalents=$180.4M/$210M for its most recent COMPLETED fiscal year, but a NEWER
(partial/interim-derived) fiscal_year row exists with cash_and_equivalents=0 (not NULL, and not
a stub row either - that row's other balance-sheet fields are real) - the 2-tier CASE picked
that $0 row over the real one. Extended to a 3-tier CASE: prefer a real NONZERO balance, then
any non-NULL value (including a genuine zero-cash company), then NULL last.

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
        self._fetchall_results = [
            [
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
            ],
            [(80_000_000.0, 10_000_000.0, None, None, None)],  # cash_rows: ocf, capex, dividends_paid
        ]
        self._fetchall_idx = 0

    def execute(self, query: str, *args: object, **kwargs: object) -> None:
        self.executed_sql.append(query)

    def fetchall(self) -> list[tuple[Any, ...]]:
        result = self._fetchall_results[self._fetchall_idx]
        self._fetchall_idx += 1
        return result

    def fetchone(self) -> tuple[Any, ...] | None:
        # 2026-09-06: _sanity_check_shares_outstanding_vs_volume added one more fetchone() call
        # to the pipeline (see that method's own docstring) - same graceful-degradation
        # precedent as this class's own fetchall() (added 2026-09-05 for an identical reason):
        # return None (a real "no matching row") rather than IndexError once the scripted
        # sequence is exhausted, since these fixtures don't script that query's result.
        if self._fetchone_idx >= len(self._fetchone_results):
            return None
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


class TestCashQueryPrefersPopulatedFiscalYear:
    def test_cash_query_orders_by_cash_populated_before_fiscal_year(self) -> None:
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (50.0,),  # price_daily.close
            (5_157_000_000.0,),  # annual_balance_sheet.stockholders_equity
            (68_111_000.0,),  # annual_balance_sheet.cash_and_equivalents
            (80_000_000.0, 10_000_000.0, None, None, None),  # annual_cash_flow: ocf, capex, dividends_paid
            (20_000_000.0, 5_000_000.0, None, None),  # debt_row
            None,  # has_dual_class_sibling check (2026-08-21) - no matching row
            (1.0,),  # beta (stability_metrics)
            (4.5,),  # risk_free_rate (economic_data DGS10) - added 2026-08-20, CAPM discount rate
            (None, None),  # yfinance_snapshot market_cap/pe_ratio sanity check (2026-08-20)
        ]
        _, cursor = _run_fetch_incremental("JACK", fetchone_results)

        cash_queries = [
            sql for sql in cursor.executed_sql if "cash_and_equivalents" in sql and "long_term_debt" not in sql
        ]
        assert len(cash_queries) == 1
        cash_sql = cash_queries[0]
        # 3-tier: real nonzero balance first, then any non-NULL (including a genuine
        # zero), NULL last - see this file's module docstring for the 2026-09-03 fix this
        # asserts (AM/AR's real-prior-value-vs-newer-zero-row evidence).
        assert "WHEN cash_and_equivalents IS NOT NULL AND cash_and_equivalents != 0" in cash_sql
        assert "THEN 0" in cash_sql
        assert "WHEN cash_and_equivalents IS NOT NULL" in cash_sql
        assert "fiscal_year DESC" in cash_sql
