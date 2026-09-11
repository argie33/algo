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

# UNIFORM EQUAL-WEIGHT 2026-09-11 (see loaders/stock_scores/pillar_weights.py's
# BASE_PILLAR_WEIGHTS comment): volatility_60d alone is now only 20% of nominal weight, below
# RISK_MIN_WEIGHT_AVAILABLE (0.40) - a single-field filler can no longer clear the floor on its
# own. Filler now supplies two components; since both use the identical curve on the identical
# input value, their weighted average equals that same single-value score regardless of weight
# (same convention test_stock_scores_risk_negative_beta_not_clipped_20260828.py already uses),
# so every original 83.33-based assertion below stays exactly true.
_VOL_FILLER = {"volatility_60d": 0.20, "volatility_252d": 0.20}


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
        """20% weight alone is below RISK_MIN_WEIGHT_AVAILABLE (0.40) - same thin-sample
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
        """avg_dollar_volume_20d=0 must not reach log10(0) - guarded by the `> 0` check, same
        as any other Risk field's None check, not a crash.

        UPDATED 2026-09-01 (same goal session, later pass - see NEAR_ZERO_LIQUIDITY_THRESHOLD's
        own docstring): a KNOWN avg_dollar_volume_20d of 0 no longer scores identically to a
        MISSING one. Live-confirmed this session: a stock with genuinely zero trading over its
        avg_dollar_volume_20d window cannot also have a trustworthy volatility_60d=0.20 "real"
        reading - the two are computed from the same price series, and live-swept symbols with
        near-zero liquidity show near-zero (often exactly 0.0) volatility too, not an unrelated
        real value (e.g. EFTY: flat $15.02, volume=0 for its entire lookback, volatility_60d
        read as exactly 0.0 - a measurement-validity failure the old code scored as "extremely
        safe"). This test's old `_VOL_FILLER` combination (0 liquidity + a real-looking 0.20
        vol) was a synthetic case that doesn't occur in production; the gate correctly treats
        a KNOWN zero as evidence price stats are unreliable, not just evidence Liquidity itself
        can't be scored - so it now withholds the whole risk_score (falls through to the
        existing no_risk_scores_computed marker) rather than fabricating 83.33 from a vol
        reading that a genuine zero-liquidity window couldn't have actually produced. A MISSING
        (None) avg_dollar_volume_20d is unaffected - unknown liquidity doesn't imply thin
        trading, so it still scores off whatever other inputs are present."""
        loader = StockScoresLoader()
        with_zero = loader._score_risk({"avg_dollar_volume_20d": 0, **_VOL_FILLER}, "ZERO_VOL")
        without_field = loader._score_risk(dict(_VOL_FILLER), "NO_FIELD")
        assert isinstance(with_zero, dict)
        assert with_zero.get("data_unavailable") is True
        assert isinstance(without_field, float)
        assert without_field == pytest.approx(83.33, abs=0.1)

    def test_missing_liquidity_field_falls_back_to_other_inputs(self):
        """A symbol with no avg_dollar_volume_20d (e.g. cache miss) must still score off
        whatever other Risk inputs are available - self-normalizing partial-availability
        blend, same as every other field in this pillar."""
        loader = StockScoresLoader()
        result = loader._score_risk({"volatility_60d": 0.20, "beta": 1.0}, "NO_LIQ")
        assert isinstance(result, float)


class TestNearZeroLiquidityPriceStatGate:
    """NEAR_ZERO_LIQUIDITY_THRESHOLD (added 2026-09-01, later same session): live-verified
    that QNBC - the exact symbol that motivated the Liquidity component above - barely moved
    (composite rank ~1-5 -> #33/5045) from Liquidity's 15% weight alone, because
    volatility_60d/beta computed from a near-frozen price series read as mechanically low
    (not genuinely low) risk, and those two inputs alone are 60% of Risk's weight. This gate
    treats volatility_60d/volatility_252d/beta as unreliable - not scored - when
    avg_dollar_volume_20d is known and below $2,000/day (see the constant's own module-level
    docstring for the live evidence: EFTY/UCFI/PC/etc. all show volatility_60d==0.0 exactly
    with sub-$1,000 ADV and a literally frozen price_daily history)."""

    def test_near_zero_liquidity_disqualifies_volatility_and_beta(self):
        """volatility_60d/beta are gated out by the near-zero-liquidity check, but Liquidity
        itself is scored off the raw (near-zero) ADV regardless of that gate - under equal
        weighting (2026-09-11), Liquidity (20%) + max_drawdown_1y (20%) = 40%, exactly clearing
        RISK_MIN_WEIGHT_AVAILABLE (0.40) (previously 15%+10%=25%, below the floor, under the old
        45/15/15/10/15 split) - a real (low) score is returned now instead of a thin-sample
        marker."""
        loader = StockScoresLoader()
        result = loader._score_risk(
            {"avg_dollar_volume_20d": 500, "volatility_60d": 0.0, "beta": 0.05, "max_drawdown_1y": -1.0}, "GHOST"
        )
        assert isinstance(result, float)

    def test_liquidity_just_above_threshold_is_not_gated(self):
        """$2,000+ (e.g. QNBC's real $454,701/day) scores volatility/beta normally - this
        gate targets only the unambiguous near-zero-trading end, not Liquidity's own 15%
        weighted policy question (already handled by _score_risk's Liquidity component)."""
        loader = StockScoresLoader()
        result = loader._score_risk({"avg_dollar_volume_20d": 454_701, **_VOL_FILLER}, "QNBC_LIKE")
        assert isinstance(result, float)
        assert result > 0

    def test_unknown_liquidity_does_not_gate(self):
        """avg_dollar_volume_20d=None (cache miss, not a known-zero reading) must not imply
        thin trading - scores off volatility/beta normally, same as
        test_missing_liquidity_field_falls_back_to_other_inputs above."""
        loader = StockScoresLoader()
        result = loader._score_risk(dict(_VOL_FILLER), "UNKNOWN_LIQ")
        assert isinstance(result, float), f"expected a real score, got {result!r}"
        assert result == pytest.approx(83.33, abs=0.1)
