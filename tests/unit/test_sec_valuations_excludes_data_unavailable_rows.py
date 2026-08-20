"""Regression test for a 2026-08-20 bug in load_sec_valuations.py's "latest fiscal year"
queries (goal: finance-accuracy audit) that read annual_income_statement/annual_balance_sheet/
annual_cash_flow with no `data_unavailable` filter at all.

A prior fix (commit 32e2f8555, "Remove premature data_unavailable checks that block loader
execution") removed the original `data_unavailable = FALSE` filters so that rows where the flag
was simply unset (NULL) wouldn't be wrongly excluded - the stated fix was "check the actual data
values (not the flag)". That premise only holds when data_unavailable=TRUE rows have NULL
financial columns; it breaks for `reason='incomplete_sec_filing_income'` /
'incomplete_sec_filing_balance' / 'incomplete_sec_filing_cashflow' rows, which can carry a
non-NULL but known-unreliable value (e.g. a raw, un-translated foreign-currency magnitude, or a
partial/estimate-stage figure) - there's no NULL for the "check the actual value" logic to catch.

Live-confirmed via the real DB (2026-08-20): 113 symbols picking up a flagged income-statement
row were computing pe_ratio/ps_ratio in the hundreds (e.g. ASBP pe_ratio=1649.85, AVLN=1535.70,
BOBS=922.50); 253 symbols picking up a flagged balance-sheet row were doing the same for
cash_and_equivalents/total_debt/stockholders_equity; 13 symbols (e.g. BAP, DLB, PHG) were
computing fcf_yield in the hundreds-to-thousands-of-percent range (BAP=40.81 i.e. 4081%) from a
flagged cash-flow row - KT (Korea Telecom) FY2025 operating_cash_flow=4.94e12, still-untranslated
KRW, was the clearest case.

Fix: `data_unavailable IS NOT TRUE` (not `= FALSE`) on all four "latest fiscal year" queries -
still admits NULL-flag rows exactly as before (preserving the original 32e2f8555 fix's intent)
while excluding only the confirmed-bad TRUE rows, falling back to the next real fiscal year (or
the existing unavailable-marker paths) instead of a fabricated ratio.

A mocked cursor can't exercise Postgres's real WHERE evaluation, so this test asserts the query
text itself still contains the exclusion clause - a regression guard against someone reverting
it in a future edit.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _RecordingCursor:
    """Sequential fetchone/fetchall stand-in (same shape as the sibling query tests'
    _RecordingCursor) that records every executed query's SQL text for inspection."""

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


class TestExcludesDataUnavailableRows:
    def test_all_four_latest_fiscal_year_queries_exclude_data_unavailable_true(self) -> None:
        fetchone_results = [
            (50.0,),  # price_daily.close
            (5_157_000_000.0,),  # annual_balance_sheet.stockholders_equity
            (68_111_000.0,),  # annual_balance_sheet.cash_and_equivalents
            (80_000_000.0, 10_000_000.0, None),  # annual_cash_flow: ocf, capex, dividends_paid
            (20_000_000.0, 5_000_000.0, None, None),  # debt_row
            (1.0,),  # beta (stability_metrics)
            (4.5,),  # risk_free_rate (economic_data DGS10)
            (None, None),  # yfinance_snapshot market_cap/pe_ratio sanity check (2026-08-20)
        ]
        _, cursor = _run_fetch_incremental("KT", fetchone_results)

        income_queries = [sql for sql in cursor.executed_sql if "FROM annual_income_statement ais" in sql]
        assert len(income_queries) == 1
        assert "ais.data_unavailable IS NOT TRUE" in income_queries[0]

        cash_bs_queries = [
            sql for sql in cursor.executed_sql if "cash_and_equivalents" in sql and "long_term_debt" not in sql
        ]
        assert len(cash_bs_queries) == 1
        assert "data_unavailable IS NOT TRUE" in cash_bs_queries[0]

        debt_queries = [sql for sql in cursor.executed_sql if "long_term_debt" in sql]
        assert len(debt_queries) == 1
        assert "data_unavailable IS NOT TRUE" in debt_queries[0]

        equity_queries = [sql for sql in cursor.executed_sql if "stockholders_equity" in sql]
        assert len(equity_queries) == 1
        assert "data_unavailable IS NOT TRUE" in equity_queries[0]

        cash_flow_queries = [sql for sql in cursor.executed_sql if "FROM annual_cash_flow" in sql]
        assert len(cash_flow_queries) == 1
        assert "data_unavailable IS NOT TRUE" in cash_flow_queries[0]

        # Regression guard: none of these queries should ever go back to the old bare
        # `= FALSE` filter either - that would silently re-exclude legitimate NULL-flag rows
        # (the exact regression 32e2f8555 fixed).
        for sql in income_queries + cash_bs_queries + debt_queries + equity_queries + cash_flow_queries:
            assert "= FALSE" not in sql
