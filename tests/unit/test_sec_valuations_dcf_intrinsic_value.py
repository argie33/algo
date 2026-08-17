"""Tests for the DCF intrinsic value / margin of safety computation added to
load_sec_valuations.py (Value factor goal, 2026-08-17, migration 1208).

_score_value() in load_stock_scores.py had never included any discounted-cash-flow signal -
purely relative valuation (P/E, P/B, P/S, PEG, FCF yield, dividend yield, forward P/E,
EV/EBITDA, EV/Revenue). A field literally named `intrinsic_value_per_share` existed on the
API (lambda/api/routes/stocks.py deep-value endpoint) but was current_price / pb_ratio - a
book-value proxy, not a DCF. This adds a real two-stage FCFE-style DCF:
(OCF - CapEx) grown for 5 explicit years at the same EPS growth rate already used for
peg_ratio (clamped to [-10%, +15%]/yr), discounted at a fixed 10% rate, plus a Gordon Growth
terminal value at 2.5% terminal growth, divided by shares outstanding.

margin_of_safety_pct = (intrinsic_value_per_share - current_price) / intrinsic_value_per_share
* 100 is the "discount to intrinsic value" figure - positive means undervalued.

Expected values below are computed independently (see the module docstring's formula) with a
tolerance, not copied from the implementation, so this test actually locks in the methodology
(discount rate, terminal growth, forecast horizon) rather than just mirroring the code.
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
        assert ivps == 122.77
        assert mos == 95.93

    def test_growth_increases_intrinsic_value(self) -> None:
        loader = _make_loader()
        flat_ivps, _ = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=0.0, shares_out=10.0, current_price=5.0
        )
        grown_ivps, _ = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=10.0, shares_out=10.0, current_price=5.0
        )
        assert grown_ivps == 186.67
        assert grown_ivps > flat_ivps

    def test_extreme_growth_rate_clamped_not_extrapolated(self) -> None:
        """500% single-year EPS growth must clamp to DCF_GROWTH_CEILING (15%/yr), not be
        extrapolated verbatim across all 5 forecast years."""
        loader = _make_loader()
        ivps, mos = loader._compute_dcf_intrinsic_value(
            "TESTCO", fcf=100.0, eps_growth_pct=500.0, shares_out=10.0, current_price=5.0
        )
        assert ivps == 227.93
        assert mos == 97.81

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
        assert mos_cheap == 95.93
        assert mos_expensive == -62.91
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
        assert ivps == 122.77
        assert mos == 95.93

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
        assert result["intrinsic_value_per_share"] == 122.77
        assert result["margin_of_safety_pct"] == 95.93
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
