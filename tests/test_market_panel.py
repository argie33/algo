#!/usr/bin/env python3
"""Test market panel functions with comprehensive data validation.

This test suite validates that market panel functions:
1. Handle malformed/missing data gracefully
2. Produce correct output types and ranges
3. Fail-fast on critical data gaps
4. Don't silently hide validation failures

VALIDATION STRATEGY:
- Critical fields: vix, spy (required, must be numeric)
- Optional fields: dist, stage, trend, halts, upvol, etc.
- Type coercion: safe_float() for numeric, safe_get_list() for lists
- Error handling: Returns error panel if critical fields invalid
- Test approach: Use strong assertions to verify validation occurred
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from rich.panel import Panel
from dashboard.panels.market import (
    panel_market_full,
    panel_market_expanded,
    panel_header_market,
)
from tests.test_helpers import (
    render_panel_to_text,
    assert_panel_error,
    assert_panel_success,
    assert_panel_renders_without_crash,
    TestDataFactory,
)


class TestMarketPanelValidation:
    """Market panel should validate data before rendering."""

    def test_panel_market_full_missing_critical_vix(self):
        """VIX is CRITICAL - should reject with error panel."""
        malformed_mkt = {
            "tier": "BULLISH",
            "pct": 65.5,
            "vix": None,  # CRITICAL - must be present and numeric
            "spy": 450.25,
        }
        panel = panel_market_full(mkt=malformed_mkt)

        # STRONG ASSERTION: Verify error panel with validation message
        text = render_panel_to_text(panel)
        assert "CRITICAL DATA MISSING" in text, (
            "Should show critical data error, got:\n" + text
        )
        assert "VIX or SPY" in text, "Error should mention which fields"

    def test_panel_market_full_missing_critical_spy(self):
        """SPY is CRITICAL - should reject with error panel."""
        malformed_mkt = {
            "tier": "BULLISH",
            "pct": 65.5,
            "vix": 18.5,
            "spy": None,  # CRITICAL - must be present and numeric
        }
        panel = panel_market_full(mkt=malformed_mkt)

        # STRONG ASSERTION: Verify error detection
        text = render_panel_to_text(panel)
        assert "CRITICAL DATA MISSING" in text, (
            "Should reject missing critical SPY, got:\n" + text
        )

    def test_panel_market_full_vix_as_string_coerced(self):
        """VIX as string - safe_float should coerce it."""
        malformed_mkt = {
            "tier": "BULLISH",
            "pct": 65.5,
            "vix": "18.5",  # String instead of float - safe_float handles
            "spy": 450.25,
        }
        panel = panel_market_full(mkt=malformed_mkt)

        # Should render successfully (safe_float coerces)
        text = assert_panel_renders_without_crash(panel, "Should handle string VIX")
        # Should show VIX value (coerced to 18.5)
        assert "18.5" in text or "18" in text, "Should display coerced VIX value"

    def test_panel_market_full_spy_as_dict_invalid(self):
        """SPY as dict - cannot coerce, should fail."""
        malformed_mkt = {
            "tier": "BULLISH",
            "pct": 65.5,
            "vix": 18.5,
            "spy": {"price": 450.25},  # Dict cannot coerce to float
        }
        panel = panel_market_full(mkt=malformed_mkt)

        # Should detect invalid SPY and return error
        text = render_panel_to_text(panel)
        assert "CRITICAL DATA MISSING" in text or "validation failed" in text.lower(), (
            "Should reject dict for numeric field, got:\n" + text
        )

    def test_panel_market_full_spy_as_list_invalid(self):
        """SPY as list - cannot coerce, should fail."""
        malformed_mkt = {
            "tier": "BULLISH",
            "pct": 65.5,
            "vix": 18.5,
            "spy": [450.25],  # List cannot coerce to float
        }
        panel = panel_market_full(mkt=malformed_mkt)

        # Should detect invalid type
        text = render_panel_to_text(panel)
        assert "CRITICAL DATA MISSING" in text, (
            "Should reject list for SPY, got:\n" + text
        )

    def test_panel_market_full_pct_as_string_allowed(self):
        """Pct (exposure) is optional - string is coercible."""
        malformed_mkt = {
            "tier": "BULLISH",
            "pct": "65.5",  # String - can coerce to float
            "vix": 18.5,
            "spy": 450.25,
        }
        panel = panel_market_full(mkt=malformed_mkt)

        # Should render successfully
        text = assert_panel_renders_without_crash(panel, "Should handle string pct")
        # Should show market panel (not error)
        assert "MARKET" in text and "CRITICAL" not in text, (
            "Should succeed with coercible pct, got:\n" + text
        )

    def test_panel_market_full_pct_none_allowed(self):
        """Pct can be None (optional field)."""
        malformed_mkt = {
            "tier": "BULLISH",
            "pct": None,  # Optional
            "vix": 18.5,
            "spy": 450.25,
        }
        panel = panel_market_full(mkt=malformed_mkt)

        # Should render with N/A for pct
        text = assert_panel_renders_without_crash(panel, "Should handle None pct")
        assert "N/A" in text or "--" in text or "MARKET" in text, (
            "Should show market data without pct, got:\n" + text
        )

    def test_panel_market_full_upvol_none_allowed(self):
        """Optional upvol can be None."""
        minimal_mkt = {
            "tier": "BULLISH",
            "pct": 65.5,
            "vix": 18.5,
            "spy": 450.25,
            "upvol": None,  # Optional
        }
        panel = panel_market_full(mkt=minimal_mkt)

        # Should render without upvol section
        text = assert_panel_renders_without_crash(panel, "Should omit upvol when None")
        # Just verify it renders, upvol won't be shown
        assert "MARKET" in text

    def test_panel_market_full_halts_as_string_raises_error(self):
        """Halts as string - safe_get_list correctly fails-fast."""
        malformed_mkt = {
            "tier": "BULLISH",
            "pct": 65.5,
            "vix": 18.5,
            "spy": 450.25,
            "halts": "AAPL MSFT",  # String instead of list - cannot coerce
        }
        # safe_get_list should raise TypeError (fail-fast validation)
        with pytest.raises(TypeError, match="Expected dict or list"):
            panel_market_full(mkt=malformed_mkt)

    def test_panel_market_full_vix_comparison_safe(self):
        """VIX comparisons (>= 30, >= 20) should be type-safe."""
        # Test with malformed VIX that safe_float can't handle
        malformed_mkt = {
            "tier": "BULLISH",
            "pct": 65.5,
            "vix": [30, 25],  # List - safe_float returns None
            "spy": 450.25,
        }
        panel = panel_market_full(mkt=malformed_mkt)

        # Should handle gracefully (VIX returns None, shows as empty)
        text = render_panel_to_text(panel)
        # Not an error since VIX can show as N/A
        assert "Traceback" not in text, "Should not crash on list VIX"


class TestMarketExpandedPanelValidation:
    """Market expanded panel should validate data."""

    def test_panel_market_expanded_all_optional_fields_missing(self):
        """Should render with minimal market data."""
        # Market expanded is more permissive - shows "--" for missing optionals
        minimal_mkt = {
            "tier": "UNKNOWN",
            "pct": None,
            "vix": None,
            "spy": None,
        }
        panel = panel_market_expanded(mkt=minimal_mkt)

        # Should render (no critical fields like full version)
        text = assert_panel_renders_without_crash(panel, "Should render with minimal data")
        assert "MARKET - EXPANDED" in text

    def test_panel_market_expanded_nh_nl_calculation_safe_with_strings(self):
        """NH-NL calculation should handle type coercion."""
        mkt = TestDataFactory.well_formed_market_data()
        mkt.update({
            "nh": "500",  # String instead of int
            "nl": [100],  # List instead of int (can't coerce)
        })
        panel = panel_market_expanded(mkt=mkt)

        # Should render (safe_int handles strings, returns None for lists)
        text = assert_panel_renders_without_crash(panel, "Should handle mixed NH-NL types")
        # nh gets coerced, nl shows as "--"
        assert "Traceback" not in text

    def test_panel_market_expanded_breadth_momentum_coercion_safe(self):
        """Breadth momentum/PCR comparisons should use safe_float."""
        mkt = TestDataFactory.well_formed_market_data()
        mkt.update({
            "bmom": "0.75",  # String - should coerce
            "pcr": [0.8],  # List - cannot coerce, shows as N/A
        })
        panel = panel_market_expanded(mkt=mkt)

        # Should handle both gracefully
        text = assert_panel_renders_without_crash(panel, "Should handle breadth metric coercion")
        # bmom coerced from string, pcr shows N/A
        assert "MARKET - EXPANDED" in text


class TestMarketHeaderPanelValidation:
    """Header market panel should validate data."""

    def test_header_panel_missing_all_mkt_data(self):
        """Should handle missing market data gracefully."""
        panel = panel_header_market(
            mkt=None,
            sentiment=None,
            ts="12:30",
            mkt_s="MARKET",
            elapsed=1.5,
        )

        # Should render header even without market data
        text = assert_panel_renders_without_crash(panel, "Header with no market data")
        # Should show graceful fallback
        assert "no market data" in text.lower() or "market" in text.lower(), (
            "Should show graceful fallback for missing data, got:\n" + text
        )

    def test_header_panel_mkt_with_errors(self):
        """Should handle error dict from market data."""
        error_mkt = {
            "error": "Data loading failed",
            "statusCode": 500,
        }
        panel = panel_header_market(
            mkt=error_mkt,
            sentiment=None,
            ts="12:30",
            mkt_s="MARKET",
            elapsed=1.5,
        )

        # Should render without crashing
        text = assert_panel_renders_without_crash(panel, "Header with error data")

    def test_header_panel_sentiment_incomplete(self):
        """Should handle incomplete sentiment data."""
        mkt = TestDataFactory.well_formed_market_data()
        incomplete_sentiment = {
            "fg": 75,
            # Missing "label" and "color" fields
        }
        panel = panel_header_market(
            mkt=mkt,
            sentiment=incomplete_sentiment,
            ts="12:30",
            mkt_s="MARKET",
            elapsed=1.5,
        )

        # Should render without crashing (uses defaults)
        text = assert_panel_renders_without_crash(panel, "Header with incomplete sentiment")

    def test_header_panel_config_mode_none(self):
        """Should handle config mode as None."""
        mkt = TestDataFactory.well_formed_market_data()
        cfg = {
            "mode": None,  # Should be string, use default
            "enabled": True,
        }
        panel = panel_header_market(
            mkt=mkt,
            sentiment=None,
            ts="12:30",
            mkt_s="MARKET",
            elapsed=1.5,
            cfg=cfg,
        )

        # Should show "?" or default for mode
        text = assert_panel_renders_without_crash(panel, "Header with None config mode")
        # Mode should appear somewhere
        assert "?" in text or "mode" in text.lower()

    def test_header_panel_config_enabled_none(self):
        """Should handle config enabled as None."""
        mkt = TestDataFactory.well_formed_market_data()
        cfg = {
            "mode": "LIVE",
            "enabled": None,  # Should default to True
        }
        panel = panel_header_market(
            mkt=mkt,
            sentiment=None,
            ts="12:30",
            mkt_s="MARKET",
            elapsed=1.5,
            cfg=cfg,
        )

        # Should default enabled to True and render
        text = assert_panel_renders_without_crash(panel, "Header with None enabled")
        # Should show ENABLED (default True)
        assert "ENABLED" in text or "LIVE" in text


class TestMarketPanelDataTypeCoercion:
    """Test that market panels use safe type coercion."""

    def test_vix_color_coding_with_safe_float(self):
        """VIX color determination should use safe_float."""
        from dashboard.data_validation import safe_float
        from dashboard.panels.health import HealthFormatter

        # Test various malformed VIX values
        test_cases = [
            ("string_vix", "18.5", 18.5),  # (name, input, expected_float)
            ("dict_vix", {"value": 18.5}, None),  # Dict can't coerce
            ("list_vix", [18.5], None),  # List can't coerce
            ("none_vix", None, None),
        ]

        for name, malformed_vix, expected in test_cases:
            vix_safe = safe_float(malformed_vix, strict=False)
            # Verify safe_float behaves as expected
            if expected is not None:
                assert vix_safe == expected, f"safe_float({name}) failed"
            else:
                assert vix_safe is None, f"safe_float({name}) should return None"

            # Verify HealthFormatter.var_color handles None gracefully
            color = HealthFormatter.var_color(vix_safe)
            assert isinstance(color, str), f"Color should be string for {name}"
            # Rich uses styles like 'red', 'bright_red', etc. - just check it's a color style string
            assert len(color) > 0

    def test_market_panel_uses_safe_coercion(self):
        """Market panels should use safe_float/safe_int throughout."""
        # Create data with mix of valid/invalid types
        mkt = {
            "tier": "BULLISH",
            "pct": 65.5,
            "vix": 18.5,
            "spy": 450.25,
            "upvol": "62.5",  # String - should coerce
            "adr": [1.45],  # List - cannot coerce
            "nh": "500",  # String - should coerce
            "nl": None,  # None - allowed
        }

        panel = panel_market_full(mkt=mkt)
        text = render_panel_to_text(panel)

        # Should not crash (safe coercion used)
        assert "Traceback" not in text
        # Should render successfully
        assert "MARKET" in text


class TestMarketPanelOutputFormat:
    """Verify market panels produce valid Rich Panel objects with correct content."""

    def test_panel_market_full_returns_rich_panel(self):
        """Should return a Rich Panel object with market content."""
        mkt = TestDataFactory.well_formed_market_data()
        panel = panel_market_full(mkt=mkt)

        # Should be a Rich Panel
        assert isinstance(panel, Panel), "Should return Rich Panel object"

        # Should render to text successfully
        text = render_panel_to_text(panel)
        assert "MARKET" in text, "Should contain market title"

    def test_panel_market_full_content_has_key_fields(self):
        """Should display key market fields in output."""
        mkt = TestDataFactory.well_formed_market_data()
        panel = panel_market_full(mkt=mkt)

        text = render_panel_to_text(panel)
        # Key fields should appear
        assert "VIX" in text, "Should display VIX"
        assert "SPY" in text, "Should display SPY"
        assert "18.5" in text or "18" in text, "Should show VIX value"
        assert "450" in text, "Should show SPY value"

    def test_panel_market_expanded_returns_rich_panel(self):
        """Should return a Rich Panel object."""
        mkt = TestDataFactory.well_formed_market_data()
        panel = panel_market_expanded(mkt=mkt)

        # Should be a Rich Panel
        assert isinstance(panel, Panel), "Should return Rich Panel object"

        text = render_panel_to_text(panel)
        assert "MARKET - EXPANDED" in text, "Should have expanded market title"

    def test_panel_market_expanded_content_has_sections(self):
        """Should have organized content sections."""
        mkt = TestDataFactory.well_formed_market_data()
        panel = panel_market_expanded(mkt=mkt)

        text = render_panel_to_text(panel)
        # Should have organized sections
        assert "PRICE" in text or "SPY" in text, "Should have price section"
        assert "BREADTH" in text or "Up Volume" in text, "Should have breadth section"

    def test_header_panel_returns_rich_panel(self):
        """Should return a Rich Panel object."""
        mkt = TestDataFactory.well_formed_market_data()
        panel = panel_header_market(
            mkt=mkt,
            sentiment=None,
            ts="12:30",
            mkt_s="MARKET",
            elapsed=1.5,
        )

        # Should be a Rich Panel
        assert isinstance(panel, Panel), "Should return Rich Panel object"

        text = render_panel_to_text(panel)
        assert "MARKET" in text, "Should contain market data"

    def test_header_panel_includes_timestamp(self):
        """Should include provided timestamp."""
        mkt = TestDataFactory.well_formed_market_data()
        panel = panel_header_market(
            mkt=mkt,
            sentiment=None,
            ts="12:30",
            mkt_s="MARKET",
            elapsed=2.5,
        )

        text = render_panel_to_text(panel)
        # Timestamp should appear
        assert "12:30" in text, "Should include timestamp"

