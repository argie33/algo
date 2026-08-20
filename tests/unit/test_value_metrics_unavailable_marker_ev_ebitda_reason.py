"""Regression test: _unavailable_marker("value_metrics", ...) must label ev_ebitda the same
way as every sibling reason field.

Bug (found 2026-08-18, "no SEC data" audit): this is the fully-unavailable fallback used when
a symbol has NO SEC valuation data at all - every sibling *_unavailable_reason in this dict
says "missing_sec_data" for exactly that case, but ev_ebitda_unavailable_reason was still
hardcoded to "depreciation_amortization_not_loaded", a specific (and usually false) claim left
over from before the real per-symbol ev_ebitda_reason logic (in fetch_incremental, around line
800) was rewritten to distinguish unprofitable_stock/ebitda_not_extracted/missing_sec_data by
actual cause. Live-confirmed 441 rows universe-wide carried this stale, misleading label.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestUnavailableMarkerEvEbitdaReason:
    def test_ev_ebitda_reason_matches_sibling_missing_sec_data_reasons(self):
        loader = _make_loader()

        marker = loader._unavailable_marker("value_metrics", "TEST")

        assert marker["ev_ebitda_unavailable_reason"] == "missing_sec_data"
        # Every other ratio reason in this fully-unavailable fallback already says this -
        # ev_ebitda must be consistent with them, not carry a stale, more-specific claim.
        assert marker["pe_ratio_unavailable_reason"] == "missing_sec_data"
        assert marker["pb_ratio_unavailable_reason"] == "missing_sec_data"
        assert marker["ev_revenue_unavailable_reason"] == "missing_sec_data"

    def test_real_reason_propagates_to_every_sibling_field(self):
        # Regression (2026-08-19, same audit): _build_value_metrics used to always call this
        # with no reason, discarding the real, specific cause load_sec_valuations.py already
        # computed and stored in sec_valuations.reason (e.g. "shares_outstanding_unavailable")
        # in favor of this generic fallback - live-confirmed 771 of 817 universe
        # "missing_sec_data" market_cap rows were actually this specific, more actionable cause.
        loader = _make_loader()

        marker = loader._unavailable_marker("value_metrics", "TEST", reason="shares_outstanding_unavailable")

        assert marker["market_cap_unavailable_reason"] == "shares_outstanding_unavailable"
        assert marker["pe_ratio_unavailable_reason"] == "shares_outstanding_unavailable"
        assert marker["pb_ratio_unavailable_reason"] == "shares_outstanding_unavailable"
        assert marker["ev_ebitda_unavailable_reason"] == "shares_outstanding_unavailable"
        assert marker["intrinsic_value_unavailable_reason"] == "shares_outstanding_unavailable"
        assert marker["margin_of_safety_unavailable_reason"] == "shares_outstanding_unavailable"
        # forward_pe's reason is about analyst data, not SEC valuation data - must stay
        # unaffected by the underlying sec_valuations cause.
        assert marker["forward_pe_unavailable_reason"] == "analyst_estimates_not_in_sec_filings"
