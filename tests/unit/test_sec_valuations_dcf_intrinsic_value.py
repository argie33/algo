"""Tests for the DCF intrinsic value / margin of safety computation added to
load_sec_valuations.py (Value factor goal, 2026-08-17, migration 1208).

_score_value() in load_stock_scores.py had never included any discounted-cash-flow signal -
purely relative valuation (P/E, P/B, P/S, PEG, FCF yield, dividend yield, forward P/E,
EV/EBITDA, EV/Revenue). A field literally named `intrinsic_value_per_share` existed on the
API (lambda/api/routes/stocks.py deep-value endpoint) but was current_price / pb_ratio - a
book-value proxy, not a DCF. This adds a real two-stage FCFE-style DCF:
(OCF - CapEx) grown for 5 explicit years at the same EPS growth rate already used for
peg_ratio (clamped to [-10%, +15%]/yr), discounted at a CAPM cost of equity, plus a Gordon
Growth terminal value at 2.5% terminal growth, divided by shares outstanding.

FIXED 2026-08-20 (goal: finance-accuracy audit): the discount rate used to be a single flat
10%/yr for every company regardless of risk profile - not industry-standard DCF practice (a
risk-adjusted cost of equity, not one guessed constant, is what CAPM/DCF theory calls for).
Replaced with risk_free_rate + Blume-adjusted-beta x equity_risk_premium (see
_compute_discount_rate). These tests exercise the no-beta/no-rate-supplied default path
(DCF_DEFAULT_BETA=1.0, DCF_DEFAULT_RISK_FREE_RATE=4.5%), which resolves to a 9.5% discount
rate; test_sec_valuations_capm_discount_rate.py covers the beta-varies-the-rate behavior.

FIXED 2026-08-25 (goal: DCF audit follow-up - growth-rate fade): the 5-year explicit forecast
used to hold eps_growth_pct flat for all 5 years, then drop straight to the 2.5% terminal
growth rate for the Gordon Growth terminal value - an abrupt one-year cliff, not how a real
company's growth decays. Replaced with a Damodaran-style linear fade from eps_growth_pct
(year 1, in full) down to DCF_TERMINAL_GROWTH_RATE (year 5, exactly) - see
_compute_dcf_intrinsic_value's docstring. Every expected value below (including the "flat
growth" 0%/yr baseline, which now fades *up* to 2.5% by year 5) was recomputed under the new
fade methodology.

margin_of_safety_pct = (intrinsic_value_per_share - current_price) / intrinsic_value_per_share
* 100 is the "discount to intrinsic value" figure - positive means undervalued.

Expected values below are computed independently (see the module docstring's formula) with a
tolerance, not copied from the implementation, so this test actually locks in the methodology
(discount rate, terminal growth, forecast horizon, growth fade) rather than just mirroring the
code.
"""

import math

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestDcfIntrinsicValueCore:
    def test_flat_growth_positive_fcf(self) -> None:
        loader = _make_loader()
        ivps, mos = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=0.0, shares_out=10.0, current_price=5.0
        )
        assert ivps == 138.22
        assert mos == 96.38

    def test_growth_increases_intrinsic_value(self) -> None:
        loader = _make_loader()
        flat_ivps, _ = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=0.0, shares_out=10.0, current_price=5.0
        )
        grown_ivps, _ = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=10.0, shares_out=10.0, current_price=5.0
        )
        assert grown_ivps == 173.11
        assert grown_ivps > flat_ivps

    def test_extreme_growth_rate_clamped_not_extrapolated(self) -> None:
        """500% single-year EPS growth must clamp to DCF_GROWTH_CEILING (15%/yr), not be
        extrapolated verbatim across all 5 forecast years."""
        loader = _make_loader()
        ivps, mos = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=500.0, shares_out=10.0, current_price=5.0
        )
        assert ivps == 192.69
        assert mos == 97.41

    def test_negative_growth_rate_floored(self) -> None:
        """A -90% growth rate must floor at DCF_GROWTH_FLOOR (-10%/yr), not compound to
        near-zero cash flows by year 5."""
        loader = _make_loader()
        floored_ivps, _ = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=-10.0, shares_out=10.0, current_price=5.0
        )
        extreme_ivps, _ = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=-90.0, shares_out=10.0, current_price=5.0
        )
        assert extreme_ivps == floored_ivps

    def test_undervalued_vs_overvalued_sign(self) -> None:
        """Price well below intrinsic value -> positive margin of safety (undervalued);
        price well above -> negative (overvalued)."""
        loader = _make_loader()
        _, mos_cheap = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=0.0, shares_out=10.0, current_price=5.0
        )
        _, mos_expensive = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=0.0, shares_out=10.0, current_price=200.0
        )
        assert mos_cheap == 96.38
        assert mos_expensive == -44.7
        assert mos_cheap > 0
        assert mos_expensive < 0


class TestDcfIntrinsicValueGuards:
    def test_negative_fcf_returns_none(self) -> None:
        loader = _make_loader()
        ivps, mos = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=-50.0, eps_growth_pct=10.0, shares_out=10.0, current_price=5.0
        )
        assert ivps is None
        assert mos is None

    def test_zero_fcf_returns_none(self) -> None:
        loader = _make_loader()
        ivps, mos = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=0.0, eps_growth_pct=10.0, shares_out=10.0, current_price=5.0
        )
        assert ivps is None
        assert mos is None

    def test_missing_growth_rate_defaults_to_flat_not_skipped(self) -> None:
        """eps_growth_pct=None must still produce a DCF (0% growth default), not a None -
        FCF/shares/price are the primary drivers and are independently available."""
        loader = _make_loader()
        ivps, mos = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=None, shares_out=10.0, current_price=5.0
        )
        assert ivps == 138.22
        assert mos == 96.38

    def test_zero_shares_returns_none(self) -> None:
        loader = _make_loader()
        ivps, mos = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=0.0, shares_out=0.0, current_price=5.0
        )
        assert ivps is None
        assert mos is None

    def test_zero_price_returns_none(self) -> None:
        loader = _make_loader()
        ivps, mos = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=0.0, shares_out=10.0, current_price=0.0
        )
        assert ivps is None
        assert mos is None

    def test_implausibly_high_result_rejected(self) -> None:
        """A tiny share count blowing the per-share result past MAX_INTRINSIC_VALUE_PER_SHARE
        must be rejected (None), not stored as a nonsensical multi-million-dollar-per-share
        figure."""
        loader = _make_loader()
        ivps, mos = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=1_000_000.0, eps_growth_pct=0.0, shares_out=1.0, current_price=5.0
        )
        assert ivps is None
        assert mos is None

    def test_result_always_finite(self) -> None:
        loader = _make_loader()
        for fcf, g, shares, price in [
            (100.0, 0.0, 10.0, 5.0),
            (1e12, 0.15, 1.0, 1.0),
            (0.01, -0.10, 1e9, 1000.0),
        ]:
            ivps, mos = loader._compute_dcf_intrinsic_value(
                "TESTCO", fcf=fcf, eps_growth_pct=g * 100, shares_out=shares, current_price=price
            )
            if ivps is not None:
                assert math.isfinite(ivps)
            if mos is not None:
                assert math.isfinite(mos)


class TestComputeValuationsWiring:
    """Confirm _compute_valuations actually calls the DCF and stores its result, and that a
    non-positive FCF (ocf <= capex) correctly leaves both fields None instead of crashing the
    rest of the valuation computation (pe_ratio/pb_ratio/etc. must still compute)."""

    def _base_kwargs(self) -> dict:
        return {
            "symbol": "TESTCO",
            "current_price": 5.0,
            "shares_out": 10.0,
            "ttm_eps": 1.0,
            "ttm_revenue": 200.0,
            "book_value": 50.0,
            "ocf": 100.0,
            "capex": 0.0,
            "prior_year_eps": 1.0,
            "dividends_paid": None,
            "total_debt": None,
            "total_cash": None,
            "ebitda": None,
        }

    def test_positive_fcf_populates_intrinsic_value(self) -> None:
        loader = _make_loader()
        result = loader._compute_valuations(**self._base_kwargs())
        assert result["intrinsic_value_per_share"] == 138.22
        assert result["margin_of_safety_pct"] == 96.38
        # Other ratios must still compute normally alongside the new DCF fields.
        assert result["pe_ratio"] == 5.0

    def test_negative_fcf_leaves_intrinsic_value_none_without_crashing(self) -> None:
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["ocf"] = 10.0
        kwargs["capex"] = 50.0  # FCF = 10 - 50 = -40
        result = loader._compute_valuations(**kwargs)
        assert result["intrinsic_value_per_share"] is None
        assert result["margin_of_safety_pct"] is None
        assert result["pe_ratio"] == 5.0
        assert result["data_unavailable"] is False

    def test_stock_based_compensation_deducted_from_fcf_yield_and_dcf(self) -> None:
        """FIXED 2026-08-25 (finance best practices audit): OCF already adds SBC back as a
        non-cash expense - a real economic cost via dilution ("Owner Earnings" convention) -
        so it must be deducted from both fcf_yield and the DCF's fcf_base, not left in."""
        loader = _make_loader()
        no_sbc_result = loader._compute_valuations(**self._base_kwargs())

        kwargs = self._base_kwargs()
        kwargs["stock_based_compensation"] = 30.0  # fcf: 100 - 0 - 30 = 70, not 100
        sbc_result = loader._compute_valuations(**kwargs)

        assert sbc_result["fcf_yield"] < no_sbc_result["fcf_yield"]
        assert sbc_result["fcf_yield"] == 140.0  # 70 / (5.0*10.0) * 100
        assert sbc_result["intrinsic_value_per_share"] < no_sbc_result["intrinsic_value_per_share"]

        expected_ivps, expected_mos = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=70.0, eps_growth_pct=0.0, shares_out=10.0, current_price=5.0
        )
        assert sbc_result["intrinsic_value_per_share"] == expected_ivps
        assert sbc_result["margin_of_safety_pct"] == expected_mos

    def test_stock_based_compensation_none_treated_as_zero_matches_pre_fix_behavior(self) -> None:
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["stock_based_compensation"] = None
        result = loader._compute_valuations(**kwargs)
        assert result["intrinsic_value_per_share"] == 138.22
        assert result["margin_of_safety_pct"] == 96.38


class TestAvgFcfFallback:
    """A single negative-FCF year (capex-heavy/cyclical) shouldn't unconditionally kill the
    DCF when the company is normally FCF-positive - see load_sec_valuations.py's 2026-08-18
    'coverage' fix. avg_fcf_fallback (the 3yr-average FCF) only kicks in when the latest
    year's own FCF is unusable, and only if the average itself is positive."""

    def _base_kwargs(self) -> dict:
        return {
            "symbol": "TESTCO",
            "current_price": 5.0,
            "shares_out": 10.0,
            "ttm_eps": 1.0,
            "ttm_revenue": 200.0,
            "book_value": 50.0,
            "ocf": 10.0,
            "capex": 50.0,  # latest-year FCF = 10 - 50 = -40 (unusable alone)
            "prior_year_eps": 1.0,
            "dividends_paid": None,
            "total_debt": None,
            "total_cash": None,
            "ebitda": None,
        }

    def test_positive_average_recovers_intrinsic_value(self) -> None:
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["avg_fcf_fallback"] = 100.0
        result = loader._compute_valuations(**kwargs)
        # Same fcf=100.0 case as test_positive_fcf_populates_intrinsic_value above.
        assert result["intrinsic_value_per_share"] == 138.22
        assert result["margin_of_safety_pct"] == 96.38

    def test_negative_average_still_leaves_intrinsic_value_none(self) -> None:
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["avg_fcf_fallback"] = -10.0
        result = loader._compute_valuations(**kwargs)
        assert result["intrinsic_value_per_share"] is None
        assert result["margin_of_safety_pct"] is None

    def test_fallback_not_used_when_latest_year_already_positive(self) -> None:
        """A positive latest-year FCF must win over the average, not be overridden by it."""
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["ocf"] = 100.0
        kwargs["capex"] = 0.0  # latest-year FCF = 100.0, already usable
        kwargs["avg_fcf_fallback"] = 1.0  # would produce a very different (tiny) result
        result = loader._compute_valuations(**kwargs)
        assert result["intrinsic_value_per_share"] == 138.22
        assert result["margin_of_safety_pct"] == 96.38

    def test_fcf_yield_unaffected_by_fallback(self) -> None:
        """fcf_yield must stay based on the latest year only, never the smoothed average."""
        loader = _make_loader()
        kwargs = self._base_kwargs()
        kwargs["avg_fcf_fallback"] = 100.0
        result = loader._compute_valuations(**kwargs)
        # latest-year fcf = -40, market_cap = 5.0 * 10.0 = 50 -> fcf_yield = -80%, within bounds.
        assert result["fcf_yield"] == -80.0


class TestComputeAvgFcfFallback:
    """Regression tests for the 2026-08-24 fix (see _compute_avg_fcf_fallback's docstring):
    a single usable (ocf, capex) year must produce a fallback value, not require 2+ to
    average - live-confirmed via VLO, whose 2 most-recently-fetched fiscal years both lack
    a tagged capex figure while the 3rd-most-recent has a real, correct one."""

    def test_single_usable_year_no_longer_requires_a_second(self) -> None:
        loader = _make_loader()
        # Most recent 2 years unusable (capex not yet tagged), 3rd year usable.
        cash_rows = [(100.0, None, None, None), (90.0, None, None, None), (80.0, 20.0, None, None)]
        assert loader._compute_avg_fcf_fallback(cash_rows, is_capex_exempt=False) == 60.0

    def test_two_usable_years_still_averages(self) -> None:
        loader = _make_loader()
        cash_rows = [(100.0, 40.0, None, None), (80.0, 20.0, None, None)]
        # (60 + 60) / 2 = 60.0
        assert loader._compute_avg_fcf_fallback(cash_rows, is_capex_exempt=False) == 60.0

    def test_no_usable_years_returns_none(self) -> None:
        loader = _make_loader()
        cash_rows = [(None, None, None, None), (100.0, None, None, None)]
        assert loader._compute_avg_fcf_fallback(cash_rows, is_capex_exempt=False) is None

    def test_capex_exempt_treats_missing_capex_as_zero(self) -> None:
        loader = _make_loader()
        cash_rows = [(100.0, None, None, None)]
        assert loader._compute_avg_fcf_fallback(cash_rows, is_capex_exempt=True) == 100.0

    def test_stock_based_compensation_deducted_from_average(self) -> None:
        """FIXED 2026-08-25 (finance best practices audit): SBC must be deducted per year,
        same as capex - OCF already added it back as a non-cash expense."""
        loader = _make_loader()
        cash_rows = [(100.0, 20.0, None, 10.0), (80.0, 10.0, None, None)]
        # Year 1: 100 - 20 - 10 = 70. Year 2: 80 - 10 - 0 (None SBC treated as 0) = 70.
        assert loader._compute_avg_fcf_fallback(cash_rows, is_capex_exempt=False) == 70.0
