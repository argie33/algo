#!/usr/bin/env python3
"""Verification tests for fallback audit fixes.

Validates that all data unavailable scenarios return explicit marker dicts
with {data_unavailable: True, reason: "..."} instead of bare None.
"""

import pytest

from algo.signals.buy_signal_generator import BuySignalGenerator


class TestSignalGeneratorFallbacks:
    """Test fallback patterns in signal generation."""

    def test_market_stage_ambiguous_sma_returns_marker(self):
        """Market stage should return explicit marker when SMA relationships are ambiguous."""
        gen = BuySignalGenerator()

        # SMA relationships that don't fit any stage (ambiguous)
        # In this case: close (110) is between sma_50 (100) and sma_200 (105)
        # This doesn't match any of the 4 defined stage patterns
        result = gen._determine_market_stage(close=110, sma_50=100, sma_200=105)

        assert isinstance(result, dict), "Should return dict for ambiguous case"
        assert result.get("data_unavailable") is True, "Should have data_unavailable=True"
        assert "reason" in result, "Should have reason field"
        assert "ambiguous" in result["reason"].lower(), "Reason should mention ambiguous"

    def test_market_stage_missing_fields_returns_marker(self):
        """Market stage should return explicit marker when required fields missing."""
        gen = BuySignalGenerator()

        # Missing close price
        result = gen._determine_market_stage(close=None, sma_50=100, sma_200=90)

        assert isinstance(result, dict), "Should return dict when data missing"
        assert result.get("data_unavailable") is True, "Should have data_unavailable=True"
        assert "missing_fields" in result["reason"], "Reason should mention missing fields"

    def test_market_stage_valid_returns_stage_string(self):
        """Market stage should return stage string when all data valid."""
        gen = BuySignalGenerator()

        # Uptrend: close > sma_50 > sma_200 (Stage 2)
        result = gen._determine_market_stage(close=105, sma_50=100, sma_200=95)

        assert isinstance(result, str), "Should return string for valid stage"
        assert result == "Stage 2", f"Expected 'Stage 2', got {result}"


class TestBuySignalGeneratorFallbacks:
    """Test buy signal generator fail-fast patterns."""

    def test_insufficient_data_raises_error(self):
        """Signal generation should fail-fast on insufficient data."""
        gen = BuySignalGenerator()

        with pytest.raises(RuntimeError):
            gen.run("TEST", [], tech_data_age=None)

    def test_poor_data_quality_raises_error(self):
        """Signal generation should fail-fast on poor data quality."""
        gen = BuySignalGenerator()

        # Create data with <95% OHLC completeness
        incomplete_rows = [
            {"date": "2026-01-01", "open": 100, "high": None, "low": 98, "close": 99},  # Missing high
            {"date": "2026-01-02", "open": 99, "high": 101, "low": 98, "close": 100},   # Complete
        ]

        with pytest.raises(ValueError) as exc_info:
            gen.run("TEST", incomplete_rows, tech_data_age=None)

        assert "95%" in str(exc_info.value), "Error should mention 95% threshold"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
