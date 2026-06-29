"""Test dashboard exposure panels with hardened error handling.

This test suite verifies that exposure panels handle missing/malformed data
with explicit error logging and data_unavailable markers instead of silent
empty returns.
"""

import logging
from unittest.mock import patch

import pytest
from rich.panel import Panel
from rich.text import Text

from dashboard.panels.exposure import panel_exposure_compact, panel_exposure_expanded


class TestExposureCompactMissingFields:
    """Compact exposure panel should handle missing required fields."""

    def test_missing_factors_field(self, caplog):
        """If 'factors' field is missing, should log error and return error text."""
        malformed_exp = {
            "raw_score": 45.0,
            "exposure_pct": 55.0,
            "regime": "normal",
            # Missing 'factors' field
        }

        with caplog.at_level(logging.ERROR):
            result = panel_exposure_compact(malformed_exp)

        # Should log error
        assert any("Required fields missing from API response" in record.message for record in caplog.records)
        # Should return error text (not silent empty list)
        assert isinstance(result, Text)
        assert "✗" in result.plain
        assert "incomplete" in result.plain.lower()

    def test_factors_field_is_not_dict(self, caplog):
        """If 'factors' is not a dict (e.g., list), should log error."""
        malformed_exp = {
            "raw_score": 45.0,
            "exposure_pct": 55.0,
            "regime": "normal",
            "factors": ["not", "a", "dict"],  # WRONG TYPE
        }

        with caplog.at_level(logging.ERROR):
            result = panel_exposure_compact(malformed_exp)

        # Should log error about invalid type
        assert any("factors is not dict" in record.message for record in caplog.records)
        assert isinstance(result, Text)
        assert "✗" in result.plain

    def test_missing_regime_field(self, caplog):
        """If 'regime' is missing, should log error."""
        malformed_exp = {
            "raw_score": 45.0,
            "exposure_pct": 55.0,
            # Missing 'regime' field entirely
            "factors": {"trend_30wk": {"pts": 10.0}},
        }

        with caplog.at_level(logging.ERROR):
            result = panel_exposure_compact(malformed_exp)

        # Should log error about missing required field
        assert any("Required fields missing from API response" in record.message for record in caplog.records)
        # Should NOT silently return None or []
        assert result is not None
        assert not isinstance(result, list)

    def test_missing_factor_in_list(self, caplog):
        """If a factor is missing from response, should log debug."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "trend_30wk": {"pts": 12.0},
                # Missing many other factors
            },
        }

        with caplog.at_level(logging.DEBUG):
            panel_exposure_compact(exp_data)

        # Should log debug for missing factors
        assert any(
            "factor" in record.message and "not in response" in record.message
            for record in caplog.records
            if record.levelno == logging.DEBUG
        )


class TestExposureCompactInvalidFactorData:
    """Compact panel should handle invalid factor data gracefully."""

    def test_factor_is_not_dict(self, caplog):
        """If a factor value is not a dict, should log warning."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "trend_30wk": "not_a_dict",  # WRONG TYPE
            },
        }

        with caplog.at_level(logging.WARNING):
            result = panel_exposure_compact(exp_data)

        # Should log warning about invalid factor type
        assert any(
            "factor" in record.message and "invalid type" in record.message
            for record in caplog.records
            if record.levelno == logging.WARNING
        )
        # Should still return a result (not crash or return None/[])
        assert result is not None

    def test_missing_pts_field_in_factor(self, caplog):
        """If pts is missing, should show explicit reason."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "trend_30wk": {
                    "reason": "insufficient_data",
                    # Missing 'pts' field
                },
            },
        }

        with caplog.at_level(logging.DEBUG):
            result = panel_exposure_compact(exp_data)

        # Should log debug about missing pts
        assert any(
            "missing pts field" in record.message for record in caplog.records if record.levelno == logging.DEBUG
        )
        # Should show the reason in the UI (not generic "N/A")
        assert result is not None


class TestExposureCompactOptionalFactors:
    """Optional factors like sector_rotation should not fail silently."""

    def test_sector_rotation_not_available(self, caplog):
        """If sector_rotation is missing, should log debug."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "trend_30wk": {"pts": 10.0},
                # Missing sector_rotation
            },
        }

        with caplog.at_level(logging.DEBUG):
            result = panel_exposure_compact(exp_data)

        # Should log at DEBUG (not silent)
        assert any(
            "sector_rotation" in record.message and "not available" in record.message
            for record in caplog.records
            if record.levelno == logging.DEBUG
        )
        assert result is not None

    def test_sector_rotation_invalid_type(self, caplog):
        """If sector_rotation has wrong type, should log debug."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "trend_30wk": {"pts": 10.0},
                "sector_rotation": "not_a_dict",  # WRONG TYPE
            },
        }

        with caplog.at_level(logging.DEBUG):
            result = panel_exposure_compact(exp_data)

        # Should log about invalid type
        assert any(
            "sector_rotation" in record.message and "invalid type" in record.message
            for record in caplog.records
            if record.levelno == logging.DEBUG
        )
        assert result is not None


class TestExposureExpandedMissingFields:
    """Expanded exposure panel should handle missing fields with data_unavailable markers."""

    def test_missing_factors_field(self, caplog):
        """If 'factors' field is missing, should log error and return panel."""
        malformed_exp = {
            "raw_score": 45.0,
            "exposure_pct": 55.0,
            "regime": "normal",
            # Missing 'factors' field
        }

        with caplog.at_level(logging.ERROR):
            result = panel_exposure_expanded(malformed_exp)

        # Should log error
        assert any("[EXPOSURE_EXPANDED] factors field missing" in record.message for record in caplog.records)
        # Should return a Panel (not raw list/dict)
        assert isinstance(result, Panel)

    def test_missing_raw_score(self, caplog):
        """If raw_score is missing, should log warning and show data_unavailable marker."""
        malformed_exp = {
            # Missing raw_score
            "exposure_pct": 55.0,
            "regime": "normal",
            "factors": {"trend_30wk": {"pts": 10.0}},
        }

        with caplog.at_level(logging.WARNING):
            result = panel_exposure_expanded(malformed_exp)

        # Should log warning about missing field
        assert any("[EXPOSURE_EXPANDED] raw_score field missing" in record.message for record in caplog.records)
        # Should return Panel with explicit message (not crash)
        assert isinstance(result, Panel)

    def test_missing_exposure_pct(self, caplog):
        """If exposure_pct is missing, should log warning and show data_unavailable marker."""
        malformed_exp = {
            "raw_score": 45.0,
            # Missing exposure_pct
            "regime": "normal",
            "factors": {"trend_30wk": {"pts": 10.0}},
        }

        with caplog.at_level(logging.WARNING):
            result = panel_exposure_expanded(malformed_exp)

        # Should log warning
        assert any("[EXPOSURE_EXPANDED] exposure_pct field missing" in record.message for record in caplog.records)
        # Should return Panel
        assert isinstance(result, Panel)

    def test_missing_regime_field(self, caplog):
        """If regime is missing, should log warning."""
        exp_data = {
            "raw_score": 45.0,
            "exposure_pct": 55.0,
            "regime": "",  # Empty
            "factors": {"trend_30wk": {"pts": 10.0}},
        }

        with caplog.at_level(logging.WARNING):
            result = panel_exposure_expanded(exp_data)

        # Should log warning about regime field
        assert any("regime field" in record.message for record in caplog.records)
        # Should still return result
        assert result is not None


class TestExposureExpandedMalformedFactorData:
    """Expanded panel should handle malformed factor data."""

    def test_factor_missing_pts(self, caplog):
        """If factor has no pts, should show explicit reason (not silent)."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "trend_30wk": {
                    "reason": "stale_data",
                    # Missing 'pts'
                },
            },
        }

        with caplog.at_level(logging.DEBUG):
            result = panel_exposure_expanded(exp_data)

        # Should log about missing pts and reason
        assert any("missing pts" in record.message for record in caplog.records if record.levelno == logging.DEBUG)
        # Should return a Panel
        assert isinstance(result, Panel)

    def test_stale_data_marker(self, caplog):
        """If factor marked as stale, should log explicitly."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "trend_30wk": {
                    "stale": True,
                    # Missing 'pts' and 'reason'
                },
            },
        }

        with caplog.at_level(logging.DEBUG):
            result = panel_exposure_expanded(exp_data)

        # Should log about stale marker
        assert any("marked stale" in record.message for record in caplog.records if record.levelno == logging.DEBUG)
        # Should return a Panel
        assert isinstance(result, Panel)

    def test_factor_invalid_type(self, caplog):
        """If factor value is not a dict, should log warning."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "trend_30wk": "not_a_dict",  # WRONG TYPE
            },
        }

        with caplog.at_level(logging.WARNING):
            result = panel_exposure_expanded(exp_data)

        # Should log about invalid type
        assert any("invalid type" in record.message for record in caplog.records if record.levelno == logging.WARNING)
        # Should return a Panel
        assert isinstance(result, Panel)


class TestExposureExpandedOptionalAdjustments:
    """Optional adjustments should be handled explicitly."""

    def test_sector_rotation_missing_pts(self, caplog):
        """If sector_rotation present but pts missing, should log error."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "trend_30wk": {"pts": 10.0},
                "sector_rotation": {
                    "signal": "underweight",
                    # Missing 'pts'
                },
            },
        }

        with caplog.at_level(logging.ERROR):
            result = panel_exposure_expanded(exp_data)

        # Should log error about missing pts
        assert any(
            "sector_rotation" in record.message and "missing 'pts' field" in record.message
            for record in caplog.records
            if record.levelno == logging.ERROR
        )
        # Should return a Panel (not crash)
        assert isinstance(result, Panel)

    def test_economic_overlay_missing_pts(self, caplog):
        """If economic_overlay present but pts missing, should log error."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "trend_30wk": {"pts": 10.0},
                "economic_overlay": {
                    "error": "recession_risk",
                    # Missing 'pts'
                },
            },
        }

        with caplog.at_level(logging.ERROR):
            result = panel_exposure_expanded(exp_data)

        # Should log error about missing pts
        assert any(
            "economic_overlay" in record.message and "missing 'pts' field" in record.message
            for record in caplog.records
            if record.levelno == logging.ERROR
        )
        # Should return a Panel
        assert isinstance(result, Panel)


class TestExposureNoSilentEmptyReturns:
    """Verify that no silent empty returns occur."""

    def test_compact_never_returns_empty_list(self):
        """Compact panel should never return empty list (should return Text/Panel)."""
        # Completely empty data
        result = panel_exposure_compact({})
        assert result is not None
        assert not isinstance(result, list)
        assert not result == []

    def test_expanded_never_returns_empty_list(self):
        """Expanded panel should never return empty list (should return Panel/Group)."""
        # Completely empty data
        result = panel_exposure_expanded({})
        assert result is not None
        assert not isinstance(result, list)
        assert not result == []

    def test_compact_never_returns_empty_dict(self):
        """Compact panel should never return empty dict."""
        result = panel_exposure_compact({})
        assert not isinstance(result, dict) or result

    def test_expanded_never_returns_empty_dict(self):
        """Expanded panel should never return empty dict."""
        result = panel_exposure_expanded({})
        assert not isinstance(result, dict) or result
