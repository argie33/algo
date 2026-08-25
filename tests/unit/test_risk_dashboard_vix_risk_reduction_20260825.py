"""Regression test for the 2026-08-25 fix to
lambda/api/routes/risk_dashboard.py::_compute_vix_risk_reduction (see
[[risk_dashboard_vix_risk_reduction_hardcoded_and_shape_mismatch_fixed_20260825]] in memory).

_compute_vix_risk_reduction used to hardcode 25/35/0.75/0.0 directly instead of reading
vix_caution_threshold/vix_max_threshold/vix_caution_risk_reduction from AlgoConfig (all
admin-editable, hot-reloadable per GOVERNANCE.md) - same "hardcoded duplicate of a config
value" bug class as several other fixes this session. It also used a 3-tier shape
(1.0/0.75/0.0) that didn't match algo/trading/position_sizer.py's real 2-branch
get_vix_risk_multiplier() logic (`vix > caution_threshold and vix <= max_threshold` ->
vix_caution_risk_reduction, else -> 1.0) - inventing a "risk_reduction=0.0 at vix>=35" sizing
behavior that doesn't exist in the real code (the VIX-spike circuit breaker halts new entries
entirely at that point, it doesn't scale sizing to zero).

'lambda' is a Python keyword, so the module under test is loaded via importlib.
"""

import importlib
from unittest.mock import MagicMock, patch

risk_dashboard_module = importlib.import_module("lambda.api.routes.risk_dashboard")

_CONFIG_VALUES = {
    "vix_caution_threshold": 25.0,
    "vix_max_threshold": 35.0,
    "vix_caution_risk_reduction": 0.75,
}


def _mock_algo_config():
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key, default=None: _CONFIG_VALUES.get(key, default)
    return mock_config


class TestComputeVixRiskReduction:
    def test_below_caution_threshold_no_reduction(self):
        with patch("algo.infrastructure.AlgoConfig", return_value=_mock_algo_config()):
            result = risk_dashboard_module._compute_vix_risk_reduction(20.0)
        assert result["risk_reduction_multiplier"] == 1.0
        assert result["vix_spike_halt_active"] is False

    def test_in_caution_zone_applies_configured_reduction(self):
        with patch("algo.infrastructure.AlgoConfig", return_value=_mock_algo_config()):
            result = risk_dashboard_module._compute_vix_risk_reduction(30.0)
        assert result["risk_reduction_multiplier"] == 0.75
        assert result["vix_spike_halt_active"] is False

    def test_at_or_above_max_threshold_is_not_a_zero_sizing_multiplier(self):
        """The core fix: the real position_sizer.py never reduces its own multiplier to 0.0
        at extreme VIX - trading halts entirely via the circuit breaker instead. The old code
        fabricated a risk_reduction=0.0 state here that doesn't reflect real sizing logic."""
        with patch("algo.infrastructure.AlgoConfig", return_value=_mock_algo_config()):
            result = risk_dashboard_module._compute_vix_risk_reduction(40.0)
        assert result["risk_reduction_multiplier"] == 1.0
        assert result["vix_spike_halt_active"] is True

    def test_exactly_at_max_threshold_still_in_caution_zone(self):
        """position_sizer.py's real boundary is inclusive of max_threshold (`vix <=
        max_threshold` stays in the caution branch) - vix_spike_halt_active is also true here
        (>= max_threshold), matching the circuit breaker's own '>= threshold' convention."""
        with patch("algo.infrastructure.AlgoConfig", return_value=_mock_algo_config()):
            result = risk_dashboard_module._compute_vix_risk_reduction(35.0)
        assert result["risk_reduction_multiplier"] == 0.75
        assert result["vix_spike_halt_active"] is True

    def test_thresholds_read_from_config_not_hardcoded(self):
        """A hot-reloaded config value must be reflected immediately, not silently ignored -
        the core bug being fixed."""
        custom_config = MagicMock()
        custom_values = {
            "vix_caution_threshold": 20.0,
            "vix_max_threshold": 30.0,
            "vix_caution_risk_reduction": 0.5,
        }
        custom_config.get.side_effect = lambda key, default=None: custom_values.get(key, default)
        with patch("algo.infrastructure.AlgoConfig", return_value=custom_config):
            result = risk_dashboard_module._compute_vix_risk_reduction(25.0)
        assert result["caution_threshold"] == 20.0
        assert result["halt_threshold"] == 30.0
        assert result["risk_reduction_multiplier"] == 0.5
