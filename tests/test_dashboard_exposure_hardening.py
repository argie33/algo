"""Test dashboard exposure panels with hardened error handling.

This test suite verifies that exposure panels handle missing/malformed data
with explicit error logging and data_unavailable markers instead of silent
empty returns.

REWRITTEN 2026-08-23 for the pillar redesign (see algo/risk/market_exposure.py's
module docstring and dashboard/panels/exposure.py's PILLAR_MAP): the flat 19-key
factors dict ("trend_30wk", "positioning", "aaii_sentiment", ...) was replaced by 3
top-level pillar keys ("pillar_trend", "pillar_risk", "pillar_confirm"), each carrying
its own sub-signal detail under "components". The panel's log wording changed from
"factor %s ..." to "pillar %s ..." to match - test assertions below were updated to
match, not just the mock data shape.
"""

import logging

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
            "factors": {"pillar_trend": {"pts": 30.0, "max": 45.0}},
        }

        with caplog.at_level(logging.ERROR):
            result = panel_exposure_compact(malformed_exp)

        # Should log error about missing required field
        assert any("Required fields missing from API response" in record.message for record in caplog.records)
        # Should NOT silently return None or []
        assert result is not None
        assert not isinstance(result, list)

    def test_missing_pillar_in_response(self, caplog):
        """If a pillar is missing from the response, should log warning."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "pillar_trend": {"pts": 30.0, "max": 45.0},
                # Missing pillar_risk and pillar_confirm
            },
        }

        with caplog.at_level(logging.WARNING):
            panel_exposure_compact(exp_data)

        # Should log warning for missing pillar
        assert any(
            "pillar" in record.message and "not in response" in record.message
            for record in caplog.records
            if record.levelno == logging.WARNING
        )


class TestExposureCompactInvalidFactorData:
    """Compact panel should handle invalid pillar data gracefully."""

    def test_pillar_is_not_dict(self, caplog):
        """If a pillar value is not a dict, should log warning."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "pillar_trend": "not_a_dict",  # WRONG TYPE
            },
        }

        with caplog.at_level(logging.WARNING):
            result = panel_exposure_compact(exp_data)

        # Should log warning about invalid pillar type
        assert any(
            "pillar" in record.message and "invalid type" in record.message
            for record in caplog.records
            if record.levelno == logging.WARNING
        )
        # Should still return a result (not crash or return None/[])
        assert result is not None

    def test_missing_pts_field_in_pillar(self, caplog):
        """If pts is missing, should show explicit reason."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "pillar_trend": {
                    "reason": "insufficient_data",
                    # Missing 'pts' field
                },
            },
        }

        with caplog.at_level(logging.WARNING):
            result = panel_exposure_compact(exp_data)

        # Should log warning about missing pts
        assert any(
            "missing pts field" in record.message for record in caplog.records if record.levelno == logging.WARNING
        )
        # Should show the reason in the UI (not generic "N/A")
        assert result is not None


class TestExposureCompactOptionalPillars:
    """A pillar missing from the response should not fail silently."""

    def test_pillar_not_available(self, caplog):
        """If a pillar like pillar_confirm is missing, should log warning (not silent)."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "pillar_trend": {"pts": 30.0, "max": 45.0},
                # Missing pillar_risk and pillar_confirm
            },
        }

        with caplog.at_level(logging.WARNING):
            result = panel_exposure_compact(exp_data)

        # Should log warning for missing pillar (not silent)
        assert any(
            "pillar" in record.message and "not in response" in record.message
            for record in caplog.records
            if record.levelno == logging.WARNING
        )
        assert result is not None

    def test_pillar_invalid_type(self, caplog):
        """If a pillar has wrong type, should log warning."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "pillar_trend": {"pts": 30.0, "max": 45.0},
                "pillar_confirm": "not_a_dict",  # WRONG TYPE (should be a dict)
            },
        }

        with caplog.at_level(logging.WARNING):
            result = panel_exposure_compact(exp_data)

        # Should log about invalid type
        assert any(
            "pillar_confirm" in record.message and "invalid type" in record.message
            for record in caplog.records
            if record.levelno == logging.WARNING
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
            "factors": {"pillar_trend": {"pts": 30.0, "max": 45.0}},
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
            "factors": {"pillar_trend": {"pts": 30.0, "max": 45.0}},
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
            "factors": {"pillar_trend": {"pts": 30.0, "max": 45.0}},
        }

        with caplog.at_level(logging.WARNING):
            result = panel_exposure_expanded(exp_data)

        # Should log warning about regime field
        assert any("regime field" in record.message for record in caplog.records)
        # Should still return result
        assert result is not None


class TestExposureExpandedMalformedFactorData:
    """Expanded panel should handle malformed pillar data."""

    def test_pillar_missing_pts(self, caplog):
        """If a pillar has no pts, should show explicit reason (not silent)."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "pillar_trend": {
                    "reason": "stale_data",
                    # Missing 'pts'
                },
            },
        }

        with caplog.at_level(logging.ERROR):
            result = panel_exposure_expanded(exp_data)

        # Should log about data_unavailable when pts is missing
        assert any("data_unavailable" in record.message for record in caplog.records if record.levelno == logging.ERROR)
        # Should return a Panel
        assert isinstance(result, Panel)

    def test_pillar_data_unavailable_with_pts_zero(self, caplog):
        """A pillar flagged data_unavailable with pts=0.0 must still render as N/A, not a
        real filled 0-point bar indistinguishable from a genuine zero score - defensive
        handling for malformed/legacy cached rows, even though compute() itself never
        marks a whole pillar data_unavailable today (only individual components within it).
        """
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "pillar_risk": {
                    "data_unavailable": True,
                    "reason": "Independent Risk Layers pillar could not be computed",
                    "pts": 0.0,
                    "max": 30.0,
                },
            },
        }

        with caplog.at_level(logging.ERROR):
            result = panel_exposure_expanded(exp_data)

        # Should hit the N/A branch (and surface the real reason), not render pts=0.0 as a
        # genuine score.
        assert any(
            "data_unavailable" in record.message and "pillar=pillar_risk" in record.message
            for record in caplog.records
            if record.levelno == logging.ERROR
        )
        assert isinstance(result, Panel)

    def test_stale_data_marker(self, caplog):
        """If a pillar is marked as stale, should log explicitly."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "pillar_trend": {
                    "stale": True,
                    # Missing 'pts' and 'reason'
                },
            },
        }

        with caplog.at_level(logging.ERROR):
            result = panel_exposure_expanded(exp_data)

        # Should log about stale marker (reason will be "stale" when marker present without explicit reason)
        assert any("reason=stale" in record.message for record in caplog.records if record.levelno == logging.ERROR)
        # Should return a Panel
        assert isinstance(result, Panel)

    def test_pillar_invalid_type(self, caplog):
        """If a pillar value is not a dict, should log warning."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "pillar_trend": "not_a_dict",  # WRONG TYPE
            },
        }

        with caplog.at_level(logging.WARNING):
            result = panel_exposure_expanded(exp_data)

        # Should log about invalid type
        assert any("invalid type" in record.message for record in caplog.records if record.levelno == logging.WARNING)
        # Should return a Panel
        assert isinstance(result, Panel)


class TestExposureExpandedRemainingPillars:
    """Every declared pillar should be handled explicitly, not just pillar_trend."""

    def test_pillar_risk_missing_pts(self, caplog):
        """If pillar_risk is present but pts missing, should log error."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "pillar_trend": {"pts": 30.0, "max": 45.0},
                "pillar_risk": {
                    "reason": "data_unavailable",
                    # Missing 'pts'
                },
            },
        }

        with caplog.at_level(logging.ERROR):
            result = panel_exposure_expanded(exp_data)

        # Should log error about data unavailable (missing pts)
        assert any(
            "data_unavailable" in record.message and "pillar_risk" in record.message
            for record in caplog.records
            if record.levelno == logging.ERROR
        )
        # Should return a Panel (not crash)
        assert isinstance(result, Panel)

    def test_pillar_confirm_missing_pts(self, caplog):
        """If pillar_confirm is present but pts missing, should log error."""
        exp_data = {
            "raw_score": 50.0,
            "exposure_pct": 50.0,
            "regime": "normal",
            "factors": {
                "pillar_trend": {"pts": 30.0, "max": 45.0},
                "pillar_confirm": {
                    "reason": "delayed_report",
                    # Missing 'pts'
                },
            },
        }

        with caplog.at_level(logging.ERROR):
            result = panel_exposure_expanded(exp_data)

        # Should log error about data unavailable (missing pts)
        assert any(
            "data_unavailable" in record.message and "pillar_confirm" in record.message
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
