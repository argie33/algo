"""Regression test for the 2026-08-22 fix (goal session - coverage-bucket root-cause audit):
fcf_yield only ever looked at the SINGLE latest fiscal_year row's ocf/capex - for the current,
still-open fiscal year (e.g. 2026 while that year is in progress), a full-year capex figure
genuinely hasn't been filed yet, so capex is None and fcf_yield stayed permanently NULL even
when the immediately preceding COMPLETE fiscal year had perfectly good ocf/capex on file.

Live-confirmed via the real DB: BAX, VTR, STM, CWT, FAF, UMH, ESE, MWA (and ~1574 symbols
universe-wide, ~30% of the tracked universe) - all real, established companies with a real,
complete prior-year FCF figure already in annual_cash_flow - permanently NULL purely because
the current interim year's capex isn't tagged yet.

Fixed by wiring fcf_yield into the SAME `avg_fcf_fallback` (multi-year average FCF) that
margin_of_safety/intrinsic_value_per_share already used - fetch_incremental has always computed
and passed this in, it just was never consulted for fcf_yield itself.
"""

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestFcfYieldPriorYearFallback:
    def _base_kwargs(self) -> dict:
        return {
            "symbol": "BAX",
            "current_price": 28.0,
            "shares_out": 490_000_000.0,
            "ttm_eps": 1.0,
            "ttm_revenue": 10_500_000_000.0,
            "book_value": None,
            "ocf": 498_000_000.0,  # current (2026) interim-year OCF - real
            "capex": None,  # current (2026) interim-year capex - genuinely not yet filed
            "prior_year_eps": 1.0,
            "dividends_paid": None,
            "total_debt": None,
            "total_cash": None,
            "ebitda": None,
        }

    def test_current_year_capex_none_falls_back_to_avg_fcf(self) -> None:
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["avg_fcf_fallback"] = 350_000_000.0  # e.g. avg of FY2024/FY2025 real ocf-capex

        result = loader._compute_valuations(**kwargs)

        assert result["fcf_yield"] is not None
        expected_pct = round((350_000_000.0 / result["market_cap"]) * 100, 2)
        assert result["fcf_yield"] == expected_pct

    def test_no_fallback_available_still_leaves_fcf_yield_none(self) -> None:
        """Without a real avg_fcf_fallback (e.g. a genuinely new filer with no complete prior
        year either), fcf_yield must still stay honestly unavailable - this fix recovers real
        data, it doesn't fabricate values when none exist."""
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["avg_fcf_fallback"] = None

        result = loader._compute_valuations(**kwargs)

        assert result["fcf_yield"] is None

    def test_current_year_capex_present_does_not_need_fallback(self) -> None:
        """A symbol whose current fiscal year DOES have real capex must keep using that
        directly, not silently prefer the multi-year average."""
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["capex"] = 200_000_000.0
        kwargs["avg_fcf_fallback"] = 999_000_000.0  # deliberately different, must NOT be used

        result = loader._compute_valuations(**kwargs)

        assert result["fcf_yield"] is not None
        expected_fcf = kwargs["ocf"] - kwargs["capex"]
        expected_pct = round((expected_fcf / result["market_cap"]) * 100, 2)
        assert result["fcf_yield"] == expected_pct
