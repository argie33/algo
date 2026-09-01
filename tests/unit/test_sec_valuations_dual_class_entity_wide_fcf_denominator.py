"""Tests for the entity-wide-FCF-denominator fix in _compute_valuations (2026-08-25, goal:
"margin of safety results look wrong" audit).

Root cause: data.sec.gov's companyfacts API collapses every XBRL concept to ONE value per
CIK+period, so operating_cash_flow/capex for a dual-class filer is duplicated verbatim onto
every sibling ticker's annual_cash_flow rows (live-confirmed: TAP and TAP.A carry identical
OCF/CapEx across all 19 fiscal years on file) - fcf is always entity-wide. shares_out, however,
is deliberately resolved to a CLASS-SPECIFIC count for a dual-class sibling ticker (correct for
market_cap/pe_ratio/pb_ratio/ps_ratio, which must reflect that class's own price x share count -
see test_sec_valuations_dual_class_yfinance_shares_fallback.py). Dividing entity-wide fcf by a
minority class's tiny class-specific share count overstated fcf_yield/DCF intrinsic value by
orders of magnitude: live-confirmed TAP.A (Molson Coors Class A, ~2.56M shares vs TAP's ~188M
combined) computed fcf_yield=936% and margin_of_safety_pct=99.8% on a normally-priced stock.

Fix: fetch_incremental now resolves a separate `entity_shares_out_for_fcf` (the entity-wide
reported_shares_outstanding SEC tag) whenever shares_out was resolved via the dual-class
yfinance fallback, and passes it into _compute_valuations. fcf_yield and the DCF
(intrinsic_value_per_share/margin_of_safety_pct) use this entity-wide denominator;
market_cap/pe_ratio/pb_ratio/ps_ratio keep using the class-specific shares_out unchanged.

SAME-DAY FOLLOW-UP: dividend_yield (dividends_paid, also an entity-wide $ total - no per-class
breakdown exists in SEC data) and enterprise_value (total_debt/total_cash, also entity-wide
balance sheet figures) had the identical class-specific-denominator mismatch, inherited by
ev_ebitda/ev_revenue downstream. Both now use the same entity_market_cap
(current_price x entity_shares_out) computed for fcf_yield above.
"""

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestEntityWideFcfDenominator:
    def _base_kwargs(self) -> dict:
        return {
            "symbol": "TESTCO.A",
            "current_price": 5.0,
            "shares_out": 10.0,  # class-specific: tiny minority class
            "ttm_eps": 1.0,
            "ttm_revenue": 200.0,
            "book_value": 50.0,
            "ocf": 100.0,
            "capex": 0.0,  # entity-wide fcf = 100
            "prior_year_eps": 1.0,
            "dividends_paid": None,
            "total_debt": None,
            "total_cash": None,
            "ebitda": None,
        }

    def test_no_entity_shares_out_falls_back_to_shares_out_unchanged(self) -> None:
        """Default (entity_shares_out_for_fcf=None) must reproduce pre-fix behavior exactly -
        every existing non-dual-class caller/test is unaffected."""
        loader = _make_loader()
        result = loader._compute_valuations(**self._base_kwargs())
        assert result["intrinsic_value_per_share"] == 138.22
        assert result["margin_of_safety_pct"] == 96.38
        assert result["fcf_yield"] == 200.0  # 100 / (5.0 * 10.0) * 100
        assert result["pe_ratio"] == 5.0

    def test_entity_shares_out_used_for_fcf_yield_and_dcf_not_for_market_cap(self) -> None:
        """A dual-class minority ticker: shares_out=10 (this class), entity_shares_out_for_fcf
        =1000 (the real combined entity total). fcf_yield/DCF must use 1000; market_cap/pe_ratio
        must still use the class-specific 10."""
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["entity_shares_out_for_fcf"] = 1000.0
        result = loader._compute_valuations(**kwargs)

        # market_cap/pe_ratio: unaffected, still class-specific (price=5.0, shares_out=10).
        assert result["market_cap"] == 50.0
        assert result["pe_ratio"] == 5.0

        # fcf_yield: fcf=100 / entity market cap (5.0 * 1000 = 5000) * 100 = 2.0%, not the
        # class-specific-denominator 200% test_no_entity_shares_out... asserts above.
        assert result["fcf_yield"] == 2.0

        # DCF: intrinsic value computed against 1000 entity shares, not 10 class shares -
        # order of magnitude smaller/more plausible than the class-specific-denominator case.
        entity_ivps, entity_mos = loader._compute_dcf_intrinsic_value(
            "TESTCO.A", fcf=100.0, eps_growth_pct=0.0, shares_out=1000.0, current_price=5.0
        )
        assert result["intrinsic_value_per_share"] == entity_ivps
        assert result["margin_of_safety_pct"] == entity_mos
        assert result["intrinsic_value_per_share"] < 138.22  # << the shares_out=10 case above

    def test_entity_shares_out_zero_or_none_treated_as_not_supplied(self) -> None:
        """A falsy entity_shares_out_for_fcf (0.0, explicit None) must not crash and must fall
        back to shares_out, same as the parameter being omitted entirely."""
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["entity_shares_out_for_fcf"] = None
        result = loader._compute_valuations(**kwargs)
        assert result["intrinsic_value_per_share"] == 138.22
        assert result["fcf_yield"] == 200.0

    def test_entity_shares_out_used_for_dividend_yield_and_enterprise_value(self) -> None:
        """dividend_yield and enterprise_value (-> ev_ebitda/ev_revenue) must also use the
        entity-wide market cap, not the class-specific one."""
        loader = _make_loader()
        kwargs = self._base_kwargs()
        # dividends_paid=10.0 (not 20.0): the class-specific-denominator yield (10/50=20%) must
        # stay under MAX_PLAUSIBLE_DIVIDEND_YIELD_RATIO (0.30, tightened 2026-09-01) so this test
        # still exercises the real denominator-selection logic instead of tripping the
        # plausibility bound - a change to that unrelated constant shouldn't silently invalidate
        # this test's own assertions.
        kwargs["dividends_paid"] = 10.0
        kwargs["total_debt"] = 500.0
        kwargs["total_cash"] = 100.0
        kwargs["ebitda"] = 400.0

        no_entity_result = loader._compute_valuations(**kwargs)
        # Pre-fix-equivalent (no entity shares supplied): class-specific market cap = 50.
        assert no_entity_result["dividend_yield"] == round(10.0 / 50.0, 4)
        assert no_entity_result["enterprise_value"] == 50.0 + 500.0 - 100.0

        kwargs["entity_shares_out_for_fcf"] = 1000.0
        entity_result = loader._compute_valuations(**kwargs)
        entity_market_cap = 5.0 * 1000.0
        assert entity_result["dividend_yield"] == round(10.0 / entity_market_cap, 4)
        assert entity_result["enterprise_value"] == entity_market_cap + 500.0 - 100.0
        assert entity_result["enterprise_value"] > no_entity_result["enterprise_value"]
        assert entity_result["ev_ebitda"] == round(entity_result["enterprise_value"] / 400.0, 2)
