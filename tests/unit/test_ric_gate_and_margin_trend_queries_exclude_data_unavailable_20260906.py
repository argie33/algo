"""Regression test (goal session 2026-09-06, SEC/XBRL missing-data campaign) for two more
queries in the same stray-value bug class as the rest of this cascade (see
sec_xbrl_anchor_query_disclaimed_row_wrong_values_fixed_20260905 /
sec_xbrl_shares_outstanding_cascade_stray_value_fixed_20260906 in MEMORY.md): a row flagged
data_unavailable=TRUE can still carry a leftover non-NULL value never nulled when the row was
flagged, so an unfiltered query silently picks it up as if it were real, audited data.

load_sec_valuations.py: _recategorize_ric_dcf_fcf_reason's `NOT EXISTS` gate on
annual_cash_flow.free_cash_flow had no data_unavailable filter - a disclaimed row's stray
free_cash_flow value would make NOT EXISTS false, suppressing the specific
"registered_investment_company_no_xbrl" recategorization in favor of the generic
"missing_cash_flow_data" reason.

load_enhanced_quality_growth_metrics.py: the gross/operating/net margin trend computation's
cost_of_revenue/gross_profit lookup against annual_income_statement had no data_unavailable
filter at all, letting a disclaimed row's stray value corrupt gross_margin_trend/
operating_margin_trend/net_margin_trend.

A mocked cursor can't exercise Postgres's real WHERE evaluation, so - matching this cascade's
established sibling tests - this asserts the query text itself contains the exclusion clause,
guarding against a future edit reverting it.
"""

from pathlib import Path

_SEC_VALUATIONS_SOURCE = Path("loaders/load_sec_valuations.py").read_text(encoding="utf-8")
_ENHANCED_QUALITY_GROWTH_SOURCE = Path("loaders/load_enhanced_quality_growth_metrics.py").read_text(encoding="utf-8")


class TestRicRecategorizationGateExcludesDataUnavailable:
    def test_free_cash_flow_not_exists_check_excludes_data_unavailable(self) -> None:
        anchor = "SELECT 1 FROM annual_cash_flow"
        assert anchor in _SEC_VALUATIONS_SOURCE
        idx = _SEC_VALUATIONS_SOURCE.index(anchor)
        clause = _SEC_VALUATIONS_SOURCE[idx : idx + 250]
        assert "data_unavailable IS NOT TRUE" in clause


class TestMarginTrendQueryExcludesDataUnavailable:
    def test_cost_of_revenue_gross_profit_lookup_excludes_data_unavailable(self) -> None:
        anchor = "SELECT fiscal_year, cost_of_revenue, gross_profit"
        assert anchor in _ENHANCED_QUALITY_GROWTH_SOURCE
        idx = _ENHANCED_QUALITY_GROWTH_SOURCE.index(anchor)
        clause = _ENHANCED_QUALITY_GROWTH_SOURCE[idx : idx + 250]
        assert "data_unavailable IS NOT TRUE" in clause
