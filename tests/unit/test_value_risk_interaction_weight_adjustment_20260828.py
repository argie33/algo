"""Tests for _value_risk_adjusted_weights (loaders/load_stock_scores.py).

Goal session 2026-08-28: a full 15-pair cross-pillar interaction sweep
(algo/research/cross_pillar_interaction_sweep_20260828.py) found value_proxy x
stability_proxy(risk) is the one pair that clears this repo's era-robustness bar
(t=-4.09/-2.17/-3.61, double-sort confirmed - Value's predictive edge concentrates in
higher-risk names). See value_stability_interaction_found_robust_20260828 in memory for the
full evidence trail. These tests pin the implementation's key invariants: weight conservation
(never changes the total budget), fallback to unmodified base weights when risk_score is
unavailable, and the direction of the shift (more Value weight for risky/low risk_score names,
less for safe/high risk_score names).
"""

from loaders.load_stock_scores import (
    BASE_PILLAR_WEIGHTS,
    VALUE_RISK_INTERACTION_MAX_SHIFT,
    _value_risk_adjusted_weights,
)


class TestValueRiskAdjustedWeights:
    def test_risk_score_none_returns_unmodified_base_weights(self) -> None:
        assert _value_risk_adjusted_weights(None) == BASE_PILLAR_WEIGHTS

    def test_risk_score_midpoint_reproduces_base_weights(self) -> None:
        weights = _value_risk_adjusted_weights(50.0)
        assert weights["value"] == BASE_PILLAR_WEIGHTS["value"]
        assert weights["risk"] == BASE_PILLAR_WEIGHTS["risk"]

    def test_low_risk_score_risky_stock_gets_more_value_weight(self) -> None:
        # risk_score=0 = riskiest possible (Risk pillar is higher-is-safer) - Value should get
        # the maximum shift UP, Risk the maximum shift DOWN.
        weights = _value_risk_adjusted_weights(0.0)
        assert weights["value"] == BASE_PILLAR_WEIGHTS["value"] + VALUE_RISK_INTERACTION_MAX_SHIFT
        assert weights["risk"] == BASE_PILLAR_WEIGHTS["risk"] - VALUE_RISK_INTERACTION_MAX_SHIFT

    def test_high_risk_score_safe_stock_gets_less_value_weight(self) -> None:
        # risk_score=100 = safest possible - Value should get the maximum shift DOWN, Risk UP.
        weights = _value_risk_adjusted_weights(100.0)
        assert weights["value"] == BASE_PILLAR_WEIGHTS["value"] - VALUE_RISK_INTERACTION_MAX_SHIFT
        assert weights["risk"] == BASE_PILLAR_WEIGHTS["risk"] + VALUE_RISK_INTERACTION_MAX_SHIFT

    def test_shift_is_monotonic_in_risk_score(self) -> None:
        risky = _value_risk_adjusted_weights(10.0)["value"]
        mid = _value_risk_adjusted_weights(50.0)["value"]
        safe = _value_risk_adjusted_weights(90.0)["value"]
        assert risky > mid > safe

    def test_weight_budget_conserved_across_risk_score_range(self) -> None:
        for risk_score in (0.0, 25.0, 50.0, 75.0, 100.0):
            weights = _value_risk_adjusted_weights(risk_score)
            # Floating-point sums of 5 non-power-of-2 fractions (e.g. 0.27, 0.1225) can differ
            # by ~1e-16 depending on accumulation order even when mathematically identical -
            # exact `==` is too strict here (surfaced once BASE_PILLAR_WEIGHTS's Value weight
            # changed from 0.23 to 0.27 on Size's retirement, see BASE_PILLAR_WEIGHTS's own
            # comment for the full trail).
            assert abs(sum(weights.values()) - sum(BASE_PILLAR_WEIGHTS.values())) < 1e-9

    def test_only_value_and_risk_weights_change(self) -> None:
        weights = _value_risk_adjusted_weights(20.0)
        # "size" REMOVED 2026-08-28 - Size retired as a composite pillar entirely, no longer a
        # key in BASE_PILLAR_WEIGHTS at all (see that constant's own comment for the full trail).
        for pillar in ("quality", "growth", "momentum"):
            assert weights[pillar] == BASE_PILLAR_WEIGHTS[pillar]

    def test_out_of_range_risk_score_clamped_not_extrapolated(self) -> None:
        # risk_score is always clamped 0-100 upstream, but the function itself should be
        # defensive rather than produce a weight outside the intended +/-MAX_SHIFT band.
        below = _value_risk_adjusted_weights(-20.0)
        above = _value_risk_adjusted_weights(150.0)
        assert below["value"] == _value_risk_adjusted_weights(0.0)["value"]
        assert above["value"] == _value_risk_adjusted_weights(100.0)["value"]

    def test_max_shift_is_half_of_base_value_weight(self) -> None:
        assert VALUE_RISK_INTERACTION_MAX_SHIFT == BASE_PILLAR_WEIGHTS["value"] * 0.5

    def test_weights_remain_non_negative_at_extremes(self) -> None:
        for risk_score in (0.0, 100.0):
            weights = _value_risk_adjusted_weights(risk_score)
            assert weights["value"] > 0
            assert weights["risk"] > 0
