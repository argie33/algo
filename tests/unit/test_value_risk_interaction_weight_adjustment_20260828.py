"""Tests for _value_risk_adjusted_weights (loaders/stock_scores/pillar_weights.py).

Goal session 2026-08-28: a full 15-pair cross-pillar interaction sweep
(algo/research/cross_pillar_interaction_sweep_20260828.py) found value_proxy x
stability_proxy(risk) is the one pair that cleared this repo's era-robustness bar at the time
(t=-4.09/-2.17/-3.61, double-sort confirmed - Value's predictive edge concentrates in
higher-risk names). See value_stability_interaction_found_robust_20260828 in memory for the
full evidence trail.

RETIRED 2026-09-11 (user directive - see pillar_weights.py's BASE_PILLAR_WEIGHTS comment for
the full rationale): that sweep is the same contaminated-FM-data family as the rest of this
repo's backtest-tuned weights, and the interaction is itself a differential/conditional
weighting device, inconsistent with the new uniform equal-weight-everything principle.
`_value_risk_adjusted_weights` now always returns BASE_PILLAR_WEIGHTS unmodified regardless of
risk_score - kept as a function (not inlined) purely for call-site compatibility. These tests
are rewritten to pin THAT invariant (no shift, ever) rather than deleted, matching this repo's
convention of keeping a documented trail instead of silently erasing history.
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

    def test_low_risk_score_no_longer_shifts_weight(self) -> None:
        # Previously the maximum shift UP for Value / DOWN for Risk - the interaction is
        # retired, so even the riskiest possible risk_score now reproduces base weights exactly.
        weights = _value_risk_adjusted_weights(0.0)
        assert weights["value"] == BASE_PILLAR_WEIGHTS["value"]
        assert weights["risk"] == BASE_PILLAR_WEIGHTS["risk"]

    def test_high_risk_score_no_longer_shifts_weight(self) -> None:
        # Previously the maximum shift DOWN for Value / UP for Risk - same retirement as above.
        weights = _value_risk_adjusted_weights(100.0)
        assert weights["value"] == BASE_PILLAR_WEIGHTS["value"]
        assert weights["risk"] == BASE_PILLAR_WEIGHTS["risk"]

    def test_weights_no_longer_vary_with_risk_score(self) -> None:
        risky = _value_risk_adjusted_weights(10.0)["value"]
        mid = _value_risk_adjusted_weights(50.0)["value"]
        safe = _value_risk_adjusted_weights(90.0)["value"]
        assert risky == mid == safe == BASE_PILLAR_WEIGHTS["value"]

    def test_weight_budget_conserved_across_risk_score_range(self) -> None:
        for risk_score in (0.0, 25.0, 50.0, 75.0, 100.0):
            weights = _value_risk_adjusted_weights(risk_score)
            assert abs(sum(weights.values()) - sum(BASE_PILLAR_WEIGHTS.values())) < 1e-9

    def test_only_value_and_risk_weights_change(self) -> None:
        # Retired: NOTHING changes now, for any pillar - this loop is kept to assert that
        # explicitly rather than narrowed, since it's a stronger guarantee than the original
        # "only Value/Risk move" invariant it replaces.
        weights = _value_risk_adjusted_weights(20.0)
        for pillar in ("quality", "growth", "value", "risk", "momentum"):
            assert weights[pillar] == BASE_PILLAR_WEIGHTS[pillar]

    def test_out_of_range_risk_score_still_returns_base_weights(self) -> None:
        below = _value_risk_adjusted_weights(-20.0)
        above = _value_risk_adjusted_weights(150.0)
        assert below == BASE_PILLAR_WEIGHTS
        assert above == BASE_PILLAR_WEIGHTS

    def test_max_shift_constant_retired_to_zero(self) -> None:
        assert VALUE_RISK_INTERACTION_MAX_SHIFT == 0.0

    def test_weights_remain_non_negative_at_extremes(self) -> None:
        for risk_score in (0.0, 100.0):
            weights = _value_risk_adjusted_weights(risk_score)
            assert weights["value"] > 0
            assert weights["risk"] > 0
