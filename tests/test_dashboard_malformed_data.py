"""Test dashboard panels with MALFORMED DATA to catch type errors.

This test suite intentionally passes wrong types to dashboard functions
to verify they don't crash. This catches bugs that clean-data unit tests miss.
"""

from datetime import datetime

import pytest

from dashboard.panels.health import (
    _build_results_panel,
    panel_algo_health,
    panel_orch,
    panel_status,
)


class TestPanelWithMalformedRiskData:
    """Dashboard should handle corrupted risk metrics gracefully."""

    def test_var95_as_dict_instead_of_float(self):
        """If var95 is a dict (corrupt data), should not crash."""
        malformed_risk = {
            "var95": {"nested": "dict"},  # WRONG TYPE
            "beta": 1.1,
            "cvar95": 3.2,
            "conc5": 28,
        }
        run = {"success": True, "halted": False, "errored": False, "run_id": "test"}

        # Should not raise TypeError
        panel = panel_algo_health(run=run, act=None, hlth=None, notifs=[], risk=malformed_risk)
        assert panel is not None

    def test_beta_as_list_instead_of_float(self):
        """If beta is a list, should handle gracefully."""
        malformed_risk = {
            "var95": 2.5,
            "beta": [1.1, 1.2],  # WRONG TYPE
            "cvar95": 3.2,
            "conc5": 28,
        }
        run = {"success": True, "halted": False, "errored": False, "run_id": "test"}

        panel = panel_algo_health(run=run, act=None, hlth=None, notifs=[], risk=malformed_risk)
        assert panel is not None

    def test_conc5_as_string_instead_of_float(self):
        """If conc5 is a string, should handle gracefully."""
        malformed_risk = {
            "var95": 2.5,
            "beta": 1.1,
            "cvar95": 3.2,
            "conc5": "28%",  # WRONG TYPE
        }
        run = {"success": True, "halted": False, "errored": False, "run_id": "test"}

        panel = panel_algo_health(run=run, act=None, hlth=None, notifs=[], risk=malformed_risk)
        assert panel is not None

    def test_svar_as_dict_instead_of_float(self):
        """If svar is a dict, should handle gracefully."""
        malformed_risk = {
            "var95": 2.5,
            "beta": 1.1,
            "cvar95": 3.2,
            "conc5": 28,
            "svar": {"value": 1.5},  # WRONG TYPE
        }
        run = {"success": True, "halted": False, "errored": False, "run_id": "test"}

        panel = panel_algo_health(run=run, act=None, hlth=None, notifs=[], risk=malformed_risk)
        assert panel is not None


class TestBuildResultsPanelWithMalformedData:
    """_build_results_panel should handle corrupted data."""

    def test_all_risk_metrics_as_dicts(self):
        """Complete risk metric corruption."""
        corrupted_risk = {
            "var95": {"error": "value"},
            "beta": {"error": "value"},
            "cvar95": {"error": "value"},
            "conc5": {"error": "value"},
            "svar": {"error": "value"},
        }
        run = {"success": True, "halted": False, "errored": False, "run_id": "test"}

        panel = _build_results_panel(
            run=run, act=None, algo_metrics=[], exec_hist=[], risk=corrupted_risk, notifs=[], audit=[]
        )
        assert panel is not None


class TestPanelWithMalformedHealthData:
    """Dashboard should handle corrupted health data."""

    def test_age_hours_as_dict(self):
        """If age_hours is a dict instead of float."""
        from dashboard.panels.health import _format_data_health_summary

        malformed_items = [
            {
                "tbl": "prices",
                "age_hours": {"hours": 24},  # WRONG TYPE
                "st": "stale",
            }
        ]

        result = _format_data_health_summary(malformed_items)
        # Should not crash, should return something
        assert result is not None

    def test_row_count_as_string(self):
        """If row_count is a string instead of int."""
        from dashboard.panels.health import _build_freshness_panel

        malformed_items = [
            {
                "tbl": "trades",
                "st": "ok",
                "role": "CRIT",
                "row_count": "1000",  # WRONG TYPE
                "age_hours": 2,
            }
        ]

        panel = _build_freshness_panel(malformed_items, ready_to_trade=True)
        assert panel is not None


class TestSignalQualityScoreWithMalformedData:
    """Signal filtering should handle wrong score types."""

    def test_signal_quality_score_as_dict(self):
        """If signal_quality_score is a dict."""
        from dashboard.data_validation import safe_float

        malformed_score = {"signal_quality_score": {"value": 75}}
        score = safe_float(malformed_score.get("signal_quality_score"))

        # Should return None, not crash
        assert score is None

    def test_signal_quality_score_as_list(self):
        """If signal_quality_score is a list."""
        from dashboard.data_validation import safe_float

        malformed_score = [75, 80]
        score = safe_float(malformed_score)

        # Should return None, not crash
        assert score is None


class TestMarketDataWithMalformedPercentages:
    """Market movers should handle corrupted percentage data."""

    def test_pct_change_as_dict(self):
        """If pct_change is a dict instead of float."""
        from dashboard.data_validation import safe_float

        malformed_data = {"pct_change": {"change": 2.5}}
        pct = safe_float(malformed_data.get("pct_change"))

        # Should return None, not crash
        assert pct is None

    def test_avg_return_as_string(self):
        """If avg_return is a string instead of float."""
        from dashboard.data_validation import safe_float

        malformed_data = {"avg_return": "2.5%"}
        ret = safe_float(malformed_data.get("avg_return"))

        # Should return None, not crash
        assert ret is None


class TestComparisonSafetyPatterns:
    """Verify that all numeric comparisons are type-safe."""

    def test_safe_float_before_comparison(self):
        """Comparison should only happen after safe_float."""
        from dashboard.data_validation import safe_float

        values = [
            {"key": 10},  # number
            {"key": "10"},  # string
            {"key": [10]},  # list
            {"key": None},  # None
            {"key": {"v": 10}},  # dict
        ]

        for v in values:
            result = safe_float(v.get("key"))
            if result is not None:
                assert result >= 0  # This comparison is now safe
                assert result <= 1000  # This comparison is now safe

    def test_safe_int_before_comparison(self):
        """Int comparisons should use safe_int."""
        from dashboard.data_validation import safe_int

        values = [
            {"count": 5},
            {"count": "5"},
            {"count": [5]},
            {"count": None},
            {"count": {"v": 5}},
        ]

        for v in values:
            result = safe_int(v.get("count"), default=0)
            # This comparison is now safe
            assert result >= 0
