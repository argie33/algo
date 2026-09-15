"""Risk-adjustment multiplier cap (added 2026-09-14, tightened same day) - the cap was
originally a hardcoded [0.5x, 2.0x] justified by a single live incident (TXNM), which is the
same "population will drift, hardcoded number won't" risk the same commit already called out
and fixed for MEDIAN_UNIVERSE_VOL_252D one paragraph above it. This locks in the fix: the cap
is now a [1st, 99th] percentile of the batch's own median_vol/vol_252d ratio distribution,
mirroring factor_normalization.py's `_winsorize_group` convention, with a static fallback only
when the batch is too thin (<5 symbols) or unpopulated (isolated unit tests).
"""

from loaders.stock_scores.momentum_scoring import (
    MAX_RISK_ADJUSTMENT_MULTIPLIER,
    MIN_RISK_ADJUSTMENT_MULTIPLIER,
    MomentumScoringMixin,
)


class _Host(MomentumScoringMixin):
    def __init__(self, stability_cache: dict[str, tuple[float]]) -> None:
        self._stability_cache = stability_cache


class TestRiskAdjustmentMultiplierBoundsDynamic:
    def test_thin_batch_falls_back_to_static_bounds(self) -> None:
        host = _Host({"AAA": (0.30,), "BBB": (0.40,)})
        bounds = host._get_risk_adjustment_multiplier_bounds()
        assert bounds == (MIN_RISK_ADJUSTMENT_MULTIPLIER, MAX_RISK_ADJUSTMENT_MULTIPLIER)

    def test_empty_batch_falls_back_to_static_bounds(self) -> None:
        host = _Host({})
        bounds = host._get_risk_adjustment_multiplier_bounds()
        assert bounds == (MIN_RISK_ADJUSTMENT_MULTIPLIER, MAX_RISK_ADJUSTMENT_MULTIPLIER)

    def test_narrow_vol_distribution_produces_tighter_bounds_than_static(self) -> None:
        # A batch where every symbol's vol_252d is close together (0.28-0.32) should produce a
        # [1st, 99th] percentile band much tighter than the generic static [0.5x, 2.0x] - a real
        # low-dispersion regime shouldn't get the same wide cap as a highly dispersed one.
        stability_cache = {f"SYM{i}": (0.28 + (i % 10) * 0.004,) for i in range(50)}
        host = _Host(stability_cache)
        min_mult, max_mult = host._get_risk_adjustment_multiplier_bounds()
        assert MIN_RISK_ADJUSTMENT_MULTIPLIER < min_mult
        assert max_mult < MAX_RISK_ADJUSTMENT_MULTIPLIER

    def test_bounds_cached_after_first_call(self) -> None:
        host = _Host({f"SYM{i}": (0.20 + i * 0.01,) for i in range(20)})
        first = host._get_risk_adjustment_multiplier_bounds()
        host._stability_cache = {}  # mutate underlying cache - should have no effect now
        second = host._get_risk_adjustment_multiplier_bounds()
        assert first == second

    def test_dynamic_bounds_actually_used_by_risk_adjust_pct(self) -> None:
        min_mult, max_mult = 0.7, 1.3
        median_vol = 0.30
        # vol far below median would hit the static MAX (2.0x) but should clip to the tighter
        # dynamic max_mult instead when passed explicitly.
        adjusted = MomentumScoringMixin._risk_adjust_pct(10.0, 0.05, median_vol, min_mult, max_mult)
        assert adjusted == 10.0 * max_mult
