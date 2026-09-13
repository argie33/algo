"""FIXED 2026-09-13 (systematic seeded-vs-enforced algo_config sweep,
scripts/audit_unenforced_config.py): put_call_bullish_threshold/put_call_fearful_threshold/
upvol_good_threshold/upvol_caution_threshold/breadth_good_threshold/breadth_caution_threshold/
yield_curve_good_threshold/beta_warning_threshold/beta_caution_threshold were seeded, schema-
validated algo_config values only ever referenced via trading_config.py's dead
get_stock_filter_config() - dashboard/panels/market.py, portfolio.py, health_orch.py and
health_status_panel.py all had these exact breakpoints hardcoded as magic-number literals.
Same shape as the market_exposure veto-cluster fix (commit 6c9f26864) - a pure configurability
fix, zero behavior change on default config, but an operator editing e.g.
upvol_good_threshold now actually changes where the dashboard's traffic light flips.

These tests verify get_market_condition_thresholds() actually reads from AlgoConfig
(not hardcoded) and that the module-level cache works.
"""

import dashboard.utilities as dashboard_utilities


class TestGetMarketConditionThresholds:
    def setup_method(self) -> None:
        # Clear the module-level cache before each test so overrides take effect.
        dashboard_utilities._market_condition_thresholds = None

    def teardown_method(self) -> None:
        dashboard_utilities._market_condition_thresholds = None

    def test_reads_real_defaults_when_config_returns_defaults(self) -> None:
        fake_config = type(
            "FakeConfig",
            (),
            {
                "get": lambda self, key, default=None: {
                    "put_call_bullish_threshold": 0.8,
                    "put_call_fearful_threshold": 1.0,
                    "upvol_good_threshold": 60.0,
                    "upvol_caution_threshold": 50.0,
                    "breadth_good_threshold": 50,
                    "breadth_caution_threshold": 0,
                    "yield_curve_good_threshold": 0.5,
                    "beta_warning_threshold": 1.2,
                    "beta_caution_threshold": 0.8,
                }.get(key)
            },
        )()
        import unittest.mock as mock

        with mock.patch("algo.infrastructure.config.main.AlgoConfig", return_value=fake_config):
            thresholds = dashboard_utilities.get_market_condition_thresholds()

        assert thresholds["upvol_good_threshold"] == 60.0
        assert thresholds["beta_warning_threshold"] == 1.2

    def test_overridden_config_value_is_actually_used_not_hardcoded(self) -> None:
        """Regression test: fails if the thresholds are ever hardcoded again."""
        fake_config = type(
            "FakeConfig",
            (),
            {
                "get": lambda self, key, default=None: {
                    "put_call_bullish_threshold": 0.8,
                    "put_call_fearful_threshold": 1.0,
                    "upvol_good_threshold": 15.0,  # overridden from real default 60.0
                    "upvol_caution_threshold": 50.0,
                    "breadth_good_threshold": 50,
                    "breadth_caution_threshold": 0,
                    "yield_curve_good_threshold": 0.5,
                    "beta_warning_threshold": 1.2,
                    "beta_caution_threshold": 0.8,
                }.get(key)
            },
        )()
        import unittest.mock as mock

        with mock.patch("algo.infrastructure.config.main.AlgoConfig", return_value=fake_config):
            thresholds = dashboard_utilities.get_market_condition_thresholds()

        assert thresholds["upvol_good_threshold"] == 15.0

    def test_raises_when_a_required_key_is_missing(self) -> None:
        fake_config = type("FakeConfig", (), {"get": lambda self, key, default=None: None})()
        import unittest.mock as mock

        import pytest

        with (
            mock.patch("algo.infrastructure.config.main.AlgoConfig", return_value=fake_config),
            pytest.raises(ValueError, match="MARKET_CONDITION_THRESHOLDS"),
        ):
            dashboard_utilities.get_market_condition_thresholds()

    def test_result_is_cached_across_calls(self) -> None:
        call_count = {"n": 0}

        def _get(self: object, key: str, default: object = None) -> float:
            call_count["n"] += 1
            return {
                "put_call_bullish_threshold": 0.8,
                "put_call_fearful_threshold": 1.0,
                "upvol_good_threshold": 60.0,
                "upvol_caution_threshold": 50.0,
                "breadth_good_threshold": 50,
                "breadth_caution_threshold": 0,
                "yield_curve_good_threshold": 0.5,
                "beta_warning_threshold": 1.2,
                "beta_caution_threshold": 0.8,
            }[key]

        fake_config = type("FakeConfig", (), {"get": _get})()
        import unittest.mock as mock

        with mock.patch("algo.infrastructure.config.main.AlgoConfig", return_value=fake_config):
            dashboard_utilities.get_market_condition_thresholds()
            first_call_count = call_count["n"]
            dashboard_utilities.get_market_condition_thresholds()

        assert call_count["n"] == first_call_count
