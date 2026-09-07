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


class TestDebtQueryPrefersPopulatedFiscalYear:
    def test_debt_query_orders_by_long_term_debt_populated_before_fiscal_year(self) -> None:
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (30_000_000.0,),  # cash_and_equivalents
            (20_000_000.0, 5_000_000.0, None, None),  # debt_row
            None,  # has_dual_class_sibling check (2026-08-21) - no matching row
            (None,),  # company_info_sec shares_outstanding cross-check (2026-08-20)
            (50.0,),  # price_daily.close
            (500_000_000.0,),  # annual_balance_sheet.stockholders_equity
            (1.0,),  # beta (stability_metrics)
            (4.5,),  # risk_free_rate (economic_data DGS10) - added 2026-08-20, CAPM discount rate
            (20.0,),  # current VIX (economic_data VIXCLS)
            (20.0,),  # long-run avg VIX - equal to current so dynamic ERP == static 5% (not under test here)
            None,  # net borrowing check (2026-08-25) - no adjacent-year debt data, DCF falls back to OCF-CapEx-SBC unchanged
            (None, None),  # yfinance_snapshot market_cap/pe_ratio sanity check (2026-08-20)
        ]
        _, cursor = _run_fetch_incremental("GOOGL", fetchone_results)

        # "COALESCE(long_term_debt" (not just "long_term_debt") uniquely identifies this
        # tiered debt_row query - _get_net_borrowing_for_dcf (2026-08-25) also queries
        # long_term_debt, but via a plain WHERE clause with no COALESCE-based ORDER BY tier.
        debt_queries = [sql for sql in cursor.executed_sql if "COALESCE(long_term_debt" in sql and "SELECT" in sql]
        assert len(debt_queries) == 1
        debt_sql = debt_queries[0]
        assert "long_term_debt IS NOT NULL" in debt_sql
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
            None,  # entity_type exemption gate check (138006446) - not exempt
            (30_000_000.0,),
            (None, 0.0, 59_642_000.0, None),  # debt_row
            None,  # has_dual_class_sibling check (2026-08-21) - no matching row
            (None,),  # company_info_sec shares_outstanding cross-check (2026-08-20)
            (50.0,),
            (500_000_000.0,),
            (1.0,),  # beta (stability_metrics)
            (4.5,),  # risk_free_rate (economic_data DGS10) - added 2026-08-20, CAPM discount rate
            (20.0,),  # current VIX (economic_data VIXCLS)
            (20.0,),  # long-run avg VIX - equal to current so dynamic ERP == static 5% (not under test here)
            None,  # net borrowing check (2026-08-25) - no adjacent-year debt data, DCF falls back to OCF-CapEx-SBC unchanged
            (None, None),  # yfinance_snapshot market_cap/pe_ratio sanity check (2026-08-20)
        ]
        _, cursor = _run_fetch_incremental("ANET", fetchone_results)

        # "COALESCE(long_term_debt" (not just "long_term_debt") uniquely identifies this
        # tiered debt_row query - _get_net_borrowing_for_dcf (2026-08-25) also queries
        # long_term_debt, but via a plain WHERE clause with no COALESCE-based ORDER BY tier.
        debt_queries = [sql for sql in cursor.executed_sql if "COALESCE(long_term_debt" in sql and "SELECT" in sql]
        assert len(debt_queries) == 1
        debt_sql = debt_queries[0]
        assert "short_term_debt IS NOT NULL" in debt_sql
        assert "operating_lease_liability IS NOT NULL" in debt_sql
        assert "finance_lease_liability IS NOT NULL" in debt_sql

    def test_debt_query_prefers_nonzero_sum_over_a_lone_real_zero(self) -> None:
        # FIXED 2026-08-18 (AA live-confirmed): the prior fix above (long_term_debt/short_term_
        # debt/lease-liability "IS NOT NULL" tier) still let a lone real `0` value count as
        # "this fiscal year has debt data" - AA's FY2026 row is (long_term_debt=NULL,
        # short_term_debt=0, leases=NULL), which ties that same tier-0 bucket as FY2025's real
        # (long_term_debt=$2.439B, short_term_debt=$9M, operating_lease=$308M) and then wins on
        # `fiscal_year DESC`, producing a summed total_debt of exactly 0 for a company with
        # $2.76B of real, reported debt one fiscal year back. A mocked cursor only returns the
        # single row Postgres's ORDER BY would have already picked, so this asserts the query
        # text contains a nonzero-sum tier ranked ahead of the plain "any non-NULL component"
        # tier - the regression guard against reverting to the looser IS NOT NULL-only check.
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (30_000_000.0,),
            (2_439_000_000.0, 9_000_000.0, 308_000_000.0, None),  # debt_row: FY2025's real figures
            None,  # has_dual_class_sibling check (2026-08-21) - no matching row
            (None,),  # company_info_sec shares_outstanding cross-check (2026-08-20)
            (50.0,),
            (500_000_000.0,),
            (1.0,),  # beta (stability_metrics)
            (4.5,),  # risk_free_rate (economic_data DGS10) - added 2026-08-20, CAPM discount rate
            (20.0,),  # current VIX (economic_data VIXCLS)
            (20.0,),  # long-run avg VIX - equal to current so dynamic ERP == static 5% (not under test here)
            None,  # net borrowing check (2026-08-25) - no adjacent-year debt data, DCF falls back to OCF-CapEx-SBC unchanged
            (None, None),  # yfinance_snapshot market_cap/pe_ratio sanity check (2026-08-20)
        ]
        _, cursor = _run_fetch_incremental("AA", fetchone_results)

        # "COALESCE(long_term_debt" (not just "long_term_debt") uniquely identifies this
        # tiered debt_row query - _get_net_borrowing_for_dcf (2026-08-25) also queries
        # long_term_debt, but via a plain WHERE clause with no COALESCE-based ORDER BY tier.
        debt_queries = [sql for sql in cursor.executed_sql if "COALESCE(long_term_debt" in sql and "SELECT" in sql]
        assert len(debt_queries) == 1
        debt_sql = debt_queries[0]
        assert "COALESCE(long_term_debt, 0)" in debt_sql
        assert "!= 0" in debt_sql
        # FIXED 2026-09-01 (see TestDebtQueryPrefersRealLongTermDebtOverIncompleteRecentYear
        # below): the nonzero-sum tier moved from THEN 0 to THEN 1 - a bare "long_term_debt IS
        # NOT NULL" tier now ranks above it. Assert the nonzero-sum clause specifically maps to
        # its own THEN value by anchoring on the text immediately preceding it, rather than a
        # bare "THEN 0" substring search that would now match the wrong tier.
        nonzero_sum_clause_idx = debt_sql.index("!= 0")
        next_then_idx = debt_sql.index("THEN", nonzero_sum_clause_idx)
        then_after_nonzero_sum = debt_sql[next_then_idx : next_then_idx + 6]
        assert then_after_nonzero_sum.strip() == "THEN 1"


class TestDebtQueryPrefersRealLongTermDebtOverIncompleteRecentYear:
    def test_long_term_debt_present_outranks_a_more_recent_partial_nonzero_year(self) -> None:
        # FIXED 2026-09-01 (goal-mode factor-usage review, category-leaders spot check):
        # live-confirmed via COF (Capital One) - FY2026 has short_term_debt=$1.626B alone
        # (long_term_debt NULL, an in-progress fiscal year whose 10-Q hasn't re-disclosed the
        # full debt schedule yet) while FY2025 has the real, complete long_term_debt=$49.913B.
        # The nonzero-sum tier (THEN 1 as of this fix, THEN 0 before it) treated BOTH years as
        # equally "has debt data" and picked the more recent one on the `fiscal_year DESC`
        # tiebreak - producing total_debt=$1.626B for one of the most leveraged banks in the
        # market. Same root cause independently found for JCAP (a $3.891M operating-lease-only
        # figure beating a real $1.754B long_term_debt). A year where long_term_debt ITSELF is
        # populated must now win outright, regardless of any other year's component sum.
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (30_000_000.0,),
            (49_913_000_000.0, 1_087_000_000.0, 1_259_000_000.0, None),  # debt_row: FY2025's real figures
            None,  # has_dual_class_sibling check (2026-08-21) - no matching row
            (None,),  # company_info_sec shares_outstanding cross-check (2026-08-20)
            (50.0,),
            (500_000_000.0,),
            (1.0,),  # beta (stability_metrics)
            (4.5,),  # risk_free_rate (economic_data DGS10) - CAPM discount rate
            (20.0,),  # current VIX (economic_data VIXCLS)
            (20.0,),  # long-run avg VIX - equal to current so dynamic ERP == static 5% (not under test here)
            None,  # net borrowing check (2026-08-25) - no adjacent-year debt data
            (None, None),  # yfinance_snapshot market_cap/pe_ratio sanity check (2026-08-20)
        ]
        _, cursor = _run_fetch_incremental("COF", fetchone_results)

        debt_queries = [sql for sql in cursor.executed_sql if "COALESCE(long_term_debt" in sql and "SELECT" in sql]
        assert len(debt_queries) == 1
        debt_sql = debt_queries[0]
        # The bare "long_term_debt IS NOT NULL" tier must appear BEFORE (rank ahead of, i.e. at
        # a lower CASE position in the SQL text) the nonzero-sum tier - a mocked cursor can't
        # exercise real Postgres ORDER BY evaluation, so this pins the tier ordering textually,
        # the same convention every other test in this file already uses.
        long_term_debt_tier_idx = debt_sql.index("WHEN long_term_debt IS NOT NULL\n")
        nonzero_sum_tier_idx = debt_sql.index("!= 0")
        assert long_term_debt_tier_idx < nonzero_sum_tier_idx

    def test_cash_is_queried_separately_from_debt(self) -> None:
        # The cash query must not be coupled to the debt-prioritization ORDER BY (it uses its
        # own independent "prefer a populated fiscal year" CASE - see
        # test_sec_valuations_cash_query_prefers_populated_fiscal_year.py - not debt's
        # component-sum CASE), so a fresh cash figure isn't held back just because that year's
        # debt tags aren't filed yet.
        fetchone_results = [
            None,  # entity_type exemption gate check (138006446) - not exempt
            (55_911_000_000.0,),  # cash_and_equivalents - real, current-year figure
            (None, 0.0, None, None),  # debt_row - GOOGL-FY2026-shaped: long_term_debt NULL
            None,  # has_dual_class_sibling check (2026-08-21) - no matching row
            (None, None),  # freshest shares_outstanding_basic check (2026-08-31) - no fresher row
            (None,),  # company_info_sec shares_outstanding cross-check (2026-08-20)
            (50.0,),
            (500_000_000.0,),
            (1.0,),  # beta (stability_metrics)
            (4.5,),  # risk_free_rate (economic_data DGS10) - added 2026-08-20, CAPM discount rate
            (20.0,),  # current VIX (economic_data VIXCLS)
            (20.0,),  # long-run avg VIX - equal to current so dynamic ERP == static 5% (not under test here)
            None,  # net borrowing check (2026-08-25) - no adjacent-year debt data, DCF falls back to OCF-CapEx-SBC unchanged
            (None, None),  # yfinance_snapshot market_cap/pe_ratio sanity check (2026-08-20)
        ]
        result, cursor = _run_fetch_incremental("GOOGL", fetchone_results)

        cash_queries = [
            sql for sql in cursor.executed_sql if "cash_and_equivalents" in sql and "long_term_debt" not in sql
        ]
        assert len(cash_queries) == 1
        assert "COALESCE(long_term_debt, 0)" not in cash_queries[0]

        row = result[0]
        assert row["total_cash"] == 55_911_000_000.0
