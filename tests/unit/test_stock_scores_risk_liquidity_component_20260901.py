"""Regression test: StockScoresLoader._score_risk's Liquidity component (20-trading-day
average dollar volume).

Added 2026-09-01 (/goal session): user live-observed untradeable micro-cap banks (HYNE,
PROV, QNBC - all below algo_config's own min_adv_dollars=$500K trade-eligibility floor)
topping Risk's "safest" ranking, then explicitly delegated "figure out what is best" after
clarifying "we dont want to exclude". _score_risk had no concept of tradability at all before
this - only a disconnected pass/fail liquidity gate applied much later in Phase 7/8, well
after ranking already happened.

Deliberately scores HIGHER dollar volume as BETTER (a tradability-RISK penalty for thin
volume), the OPPOSITE sign from the academic illiquidity-return-PREMIUM direction this
codebase's own algo/research/fama_macbeth_liquidity_factor.py already found real (t=3.34) -
that premium compensates a buy-and-hold investor for years of hard-to-exit risk, which
doesn't apply to this pillar's swing-trading framing (see _score_risk's own REWEIGHTED
2026-09-01 docstring and Beta's non-alpha precedent above it for the full reasoning).
"""

import pytest

from loaders.load_stock_scores import StockScoresLoader

# Fixed filler: volatility_60d=0.20 is 45% of nominal weight, clearing RISK_MIN_WEIGHT_AVAILABLE
# on its own so each test below isolates liquidity's contribution without also exercising the
# floor - same convention as test_stock_scores_risk_negative_beta_not_clipped_20260828.py.
_VOL_FILLER = {"volatility_60d": 0.20}


class TestLiquidityCurveScore:
    def test_below_100k_scores_zero(self):
        assert StockScoresLoader._liquidity_curve_score(50_000) == 0.0

    def test_at_100k_floor_scores_zero(self):
        assert StockScoresLoader._liquidity_curve_score(100_000) == 0.0

    def test_at_500k_trade_eligibility_floor_scores_35(self):
        """$500K is algo_config.min_adv_dollars - the exact existing trade-eligibility
        threshold Phase 7/8's LiquidityChecks already enforces. A stock right at that line
        should score marginal, not high."""
        assert StockScoresLoader._liquidity_curve_score(500_000) == pytest.approx(35.0, abs=0.1)

    def test_at_2m_scores_65(self):
        assert StockScoresLoader._liquidity_curve_score(2_000_000) == pytest.approx(65.0, abs=0.1)

    def test_at_10m_scores_90(self):
        assert StockScoresLoader._liquidity_curve_score(10_000_000) == pytest.approx(90.0, abs=0.1)

    def test_at_or_above_50m_saturates_to_100(self):
        # log10(50_000_000) = 7.69897, just under the 7.7 saturation breakpoint - approx,
        # not exact equality, for this one.
        assert StockScoresLoader._liquidity_curve_score(50_000_000) == pytest.approx(100.0, abs=0.1)
        assert StockScoresLoader._liquidity_curve_score(500_000_000) == 100.0

    def test_monotonically_increasing_with_dollar_volume(self):
        """More liquid must always score >= less liquid - confirms this rewards liquidity,
        not the opposite-signed illiquidity premium."""
        values = [100_000, 300_000, 500_000, 1_000_000, 2_000_000, 5_000_000, 10_000_000, 50_000_000]
        scores = [StockScoresLoader._liquidity_curve_score(v) for v in values]
        assert scores == sorted(scores)


class TestLiquidityScoredIntoRiskScore:
    def test_liquidity_alone_below_floor_withholds_score(self):
        """15% weight alone is below RISK_MIN_WEIGHT_AVAILABLE (0.40) - same thin-sample
        floor every other individual Risk input is already held to."""
        loader = StockScoresLoader()
        result = loader._score_risk({"avg_dollar_volume_20d": 50_000_000}, "LIQ_ONLY")
        assert isinstance(result, dict)
        assert result.get("data_unavailable") is True

    def test_thin_liquidity_scores_lower_than_deep_liquidity_otherwise_identical(self):
        loader = StockScoresLoader()
        thin = loader._score_risk({"avg_dollar_volume_20d": 100_000, **_VOL_FILLER}, "THIN")
        deep = loader._score_risk({"avg_dollar_volume_20d": 50_000_000, **_VOL_FILLER}, "DEEP")
        assert isinstance(thin, float)
        assert isinstance(deep, float)
        assert deep > thin

    def test_zero_dollar_volume_guarded_not_scored(self):
        """avg_dollar_volume_20d=0 (e.g. a symbol with a zero-volume trading halt in its
        recent window) must not reach log10(0) - guarded by the `> 0` check, same as any
        other Risk field's None check, not a crash."""
        loader = StockScoresLoader()
        with_zero = loader._score_risk({"avg_dollar_volume_20d": 0, **_VOL_FILLER}, "ZERO_VOL")
        without_field = loader._score_risk(dict(_VOL_FILLER), "NO_FIELD")
        assert with_zero == without_field

    def test_missing_liquidity_field_falls_back_to_other_inputs(self):
        """A symbol with no avg_dollar_volume_20d (e.g. cache miss) must still score off
        whatever other Risk inputs are available - self-normalizing partial-availability
        blend, same as every other field in this pillar."""
        loader = StockScoresLoader()
        result = loader._score_risk({"volatility_60d": 0.20, "beta": 1.0}, "NO_LIQ")
        assert isinstance(result, float)
