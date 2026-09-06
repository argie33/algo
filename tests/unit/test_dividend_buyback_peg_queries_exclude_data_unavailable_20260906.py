"""Regression test (goal session 2026-09-06, SEC/XBRL missing-data campaign) for four
annual_cash_flow/annual_income_statement fallback queries that had no `data_unavailable` filter
at all - the same stray-value bug class fixed across the rest of this cascade (see
sec_xbrl_anchor_query_disclaimed_row_wrong_values_fixed_20260905 /
sec_xbrl_shares_outstanding_cascade_stray_value_fixed_20260906 in MEMORY.md): a row flagged
data_unavailable=TRUE can still carry a leftover non-NULL value never nulled when the row was
flagged, so an unfiltered query silently picks it up as if it were real, audited data.

vqg_value.py: dividend_yield's TIER 3 fallback, net_payout_yield's TIER 2 (dividends +
buybacks) fallback, and its TIER 3 (confirmed-buyback existence check) fallback - all three read
annual_cash_flow.dividends_paid/common_stock_repurchased with a recency window but no
data_unavailable guard.

sec_valuations_income_context.py: the "re-fetch a genuinely older year" PEG prior_year_eps
fallback (used when income_rows[1] was already consumed as the ttm_eps substitute) - reads
annual_income_statement.earnings_per_share with no data_unavailable guard, feeding directly into
the PEG ratio's growth-rate leg.

A mocked cursor can't exercise Postgres's real WHERE evaluation, so - matching this cascade's
established sibling tests - this asserts the query text itself contains the exclusion clause,
guarding against a future edit reverting it.
"""

from pathlib import Path

_VQG_VALUE_SOURCE = Path("loaders/helpers/vqg_value.py").read_text(encoding="utf-8")
_INCOME_CONTEXT_SOURCE = Path("loaders/helpers/sec_valuations_income_context.py").read_text(encoding="utf-8")


class TestDividendAndBuybackQueriesExcludeDataUnavailable:
    def test_dividend_yield_tier3_fallback_excludes_data_unavailable(self) -> None:
        anchor = "SELECT dividends_paid FROM annual_cash_flow"
        assert anchor in _VQG_VALUE_SOURCE
        idx = _VQG_VALUE_SOURCE.index(anchor)
        clause = _VQG_VALUE_SOURCE[idx : idx + 400]
        assert "data_unavailable IS NOT TRUE" in clause

    def test_net_payout_yield_tier2_fallback_excludes_data_unavailable(self) -> None:
        anchor = "SELECT dividends_paid, common_stock_repurchased FROM annual_cash_flow"
        assert anchor in _VQG_VALUE_SOURCE
        idx = _VQG_VALUE_SOURCE.index(anchor)
        clause = _VQG_VALUE_SOURCE[idx : idx + 400]
        assert "data_unavailable IS NOT TRUE" in clause

    def test_net_payout_yield_tier3_buyback_existence_check_excludes_data_unavailable(self) -> None:
        anchor = "SELECT 1 FROM annual_cash_flow"
        assert anchor in _VQG_VALUE_SOURCE
        idx = _VQG_VALUE_SOURCE.index(anchor)
        clause = _VQG_VALUE_SOURCE[idx : idx + 300]
        assert "data_unavailable IS NOT TRUE" in clause


class TestPegRatioOlderFiscalYearFallbackExcludesDataUnavailable:
    def test_re_fetched_older_eps_query_excludes_data_unavailable(self) -> None:
        anchor = "SELECT fiscal_year, earnings_per_share FROM annual_income_statement"
        assert anchor in _INCOME_CONTEXT_SOURCE
        idx = _INCOME_CONTEXT_SOURCE.index(anchor)
        clause = _INCOME_CONTEXT_SOURCE[idx : idx + 300]
        assert "data_unavailable IS NOT TRUE" in clause
