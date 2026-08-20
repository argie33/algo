#!/usr/bin/env python3
"""Tests for load_sec_valuations.py's CAPM-based DCF discount rate (2026-08-20, goal:
finance-accuracy audit).

Before this fix, _compute_dcf_intrinsic_value discounted every symbol's cash flows at a single
flat 10%/yr regardless of risk - a mega-cap utility and a small-cap biotech got the exact same
cost of capital, which is not industry-standard DCF practice (a risk-adjusted cost of equity is
the standard, per CAPM). _compute_discount_rate() replaces that with:

    discount_rate = risk_free_rate + blume_adjusted_beta x equity_risk_premium

where blume_adjusted_beta = 2/3 x raw_beta + 1/3 x 1.0 (the standard Bloomberg/Merrill Lynch
shrinkage-toward-market-average correction for noisy individual-stock betas), clamped so the
result never falls at/below the risk-free rate (equities are inherently riskier than Treasuries)
nor exceeds a 25% sanity ceiling (guards against degenerate terminal-value math on an extreme
beta outlier).

Expected values below are computed independently (plain arithmetic, not by calling the
implementation) so this test locks in the CAPM formula itself, not just mirrors the code.
"""

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class TestComputeDiscountRate:
    def test_no_beta_no_rate_uses_documented_defaults(self) -> None:
        """beta=None, risk_free_rate=None -> DCF_DEFAULT_BETA (1.0) and
        DCF_DEFAULT_RISK_FREE_RATE (4.5%): 4.5% + 1.0*5% = 9.5%."""
        loader = _make_loader()
        assert loader._compute_discount_rate(None, None) == 0.095

    def test_high_beta_raises_the_rate(self) -> None:
        """A high-risk name (beta=2.0) must get a higher discount rate than a market-average
        name - a raw flat rate would overvalue it by discounting its cash flows too gently."""
        loader = _make_loader()
        rate = loader._compute_discount_rate(2.0, 0.045)
        assert round(rate, 6) == round(0.045 + (2 / 3 * 2.0 + 1 / 3 * 1.0) * 0.05, 6)
        assert rate > loader._compute_discount_rate(1.0, 0.045)

    def test_low_beta_lowers_the_rate(self) -> None:
        """A low-risk name (beta=0.3) must get a lower discount rate than a market-average
        name - a raw flat rate would undervalue it by discounting its cash flows too harshly."""
        loader = _make_loader()
        rate = loader._compute_discount_rate(0.3, 0.045)
        assert round(rate, 6) == round(0.045 + (2 / 3 * 0.3 + 1 / 3 * 1.0) * 0.05, 6)
        assert rate < loader._compute_discount_rate(1.0, 0.045)

    def test_extreme_negative_beta_floors_at_risk_free_plus_minimum_premium(self) -> None:
        """An extreme/noisy negative beta must not push the discount rate at or below the
        risk-free rate - equities are inherently riskier than Treasuries by construction."""
        loader = _make_loader()
        rate = loader._compute_discount_rate(-5.0, 0.045)
        assert rate == 0.045 + loader.DCF_MIN_EQUITY_RISK_PREMIUM_APPLIED

    def test_extreme_positive_beta_caps_at_max_discount_rate(self) -> None:
        """An extreme positive beta outlier must not produce a degenerate/absurd discount
        rate - clamped at DCF_MAX_DISCOUNT_RATE."""
        loader = _make_loader()
        rate = loader._compute_discount_rate(9.9, 0.045)
        assert rate == loader.DCF_MAX_DISCOUNT_RATE

    def test_rate_tracks_the_live_risk_free_rate(self) -> None:
        """Same beta, higher risk-free environment -> higher discount rate (CAPM should track
        the actual macro rate environment, not be frozen at one guessed constant)."""
        loader = _make_loader()
        assert loader._compute_discount_rate(1.0, 0.06) > loader._compute_discount_rate(1.0, 0.045)

    def test_beta_none_defaults_to_market_average_not_a_guess(self) -> None:
        """A missing beta (e.g. insufficient price history) must resolve to the same rate as
        a real beta of exactly 1.0 - 'unknown risk, assume average' rather than an arbitrary
        overvaluing/undervaluing bias."""
        loader = _make_loader()
        assert loader._compute_discount_rate(None, 0.045) == loader._compute_discount_rate(1.0, 0.045)


class TestDcfUsesRiskAdjustedRate:
    """End-to-end: two symbols with identical cash flows but different beta must get
    different intrinsic values - proof the DCF is now actually risk-sensitive, not just that
    _compute_discount_rate is correct in isolation."""

    def test_higher_beta_produces_lower_intrinsic_value(self) -> None:
        loader = _make_loader()
        kwargs = {"symbol": "TESTCO", "fcf": 100.0, "eps_growth_pct": 0.0, "shares_out": 10.0, "current_price": 5.0}
        low_risk_ivps, _ = loader._compute_dcf_intrinsic_value(**kwargs, beta=0.3, risk_free_rate=0.045)
        high_risk_ivps, _ = loader._compute_dcf_intrinsic_value(**kwargs, beta=2.5, risk_free_rate=0.045)
        assert low_risk_ivps > high_risk_ivps, (
            "a riskier company's cash flows must be discounted more harshly, producing a "
            "lower intrinsic value per share, not the same value a flat-rate DCF would give both"
        )


class TestGetRiskFreeRate:
    """_get_risk_free_rate reads the live 10Y Treasury yield (economic_data.DGS10) and caches
    it per loader-run instance instead of querying it once per symbol (5,000+ times a run)."""

    def test_converts_percent_to_decimal_and_caches(self) -> None:
        loader = _make_loader()

        class _FakeCursor:
            def __init__(self) -> None:
                self.call_count = 0

            def execute(self, *_args, **_kwargs) -> None:
                self.call_count += 1

            def fetchone(self):
                return (4.71,)

        cur = _FakeCursor()
        rate = loader._get_risk_free_rate(cur)
        assert rate == 0.0471, "DGS10 is published as a percentage (4.71 = 4.71%), must convert to decimal"

        # Second call must reuse the cached value, not re-query.
        loader._get_risk_free_rate(cur)
        assert cur.call_count == 1, "risk-free rate must be cached per instance, not re-fetched per call"

    def test_falls_back_to_default_when_no_recent_reading(self) -> None:
        loader = _make_loader()

        class _FakeCursor:
            def execute(self, *_args, **_kwargs) -> None:
                pass

            def fetchone(self):
                return None

        rate = loader._get_risk_free_rate(_FakeCursor())
        assert rate == loader.DCF_DEFAULT_RISK_FREE_RATE
