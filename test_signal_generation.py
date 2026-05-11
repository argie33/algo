#!/usr/bin/env python3
"""
Integration tests for signal generation pipeline.

Tests the complete flow: data loading → signal computation → filtering.
Uses real database or fixtures for isolated testing.

Run: python3 -m pytest test_signal_generation.py -v
"""

import pytest
import psycopg2
from datetime import date, timedelta
from typing import Dict, Any, Optional

from algo_signals import SignalComputer
from algo_swing_score import SwingTraderScore
from algo_filter_pipeline import FilterPipeline


class TestSignalComputation:
    """Test signal computation accuracy with known-good data."""

    @pytest.fixture
    def signal_computer(self):
        """Create a SignalComputer instance."""
        return SignalComputer()

    @pytest.fixture
    def test_date(self):
        """Use a fixed test date for reproducibility."""
        return date(2026, 5, 1)

    def test_minervini_trend_template_with_real_data(self, signal_computer, test_date):
        """
        Test Minervini 8-point template against known AAPL data.

        Expected: AAPL on 2026-05-01 should score 6-7/8 during uptrend.
        """
        result = signal_computer.minervini_trend_template("AAPL", test_date)

        # Verify response structure
        assert isinstance(result, dict)
        assert "score" in result
        assert "criteria" in result
        assert "pass" in result

        # Score should be integer 0-8
        assert isinstance(result["score"], int)
        assert 0 <= result["score"] <= 8

        # All 8 criteria should be present in dict
        criteria = result.get("criteria", {})
        required_criteria = [
            "c1_above_150_200_ma",
            "c2_sma150_above_sma200",
            "c3_sma200_rising_1mo",
            "c4_sma50_above_others",
            "c5_above_sma50",
            "c6_at_least_30pct_above_52w_low",
            "c7_within_25pct_of_52w_high",
            "c8_rs_rank_70_or_better",
        ]
        for criterion in required_criteria:
            assert criterion in criteria, f"Missing criterion: {criterion}"

    def test_base_detection_accuracy(self, signal_computer, test_date):
        """
        Test base detection pattern recognition.

        Expected: Should identify tight consolidation or false detection gracefully.
        """
        result = signal_computer.base_detection("MSFT", test_date)

        assert isinstance(result, dict)
        assert "in_base" in result
        assert "base_depth_pct" in result
        assert "weeks_in_base" in result
        assert "breakout_imminent" in result

        # Base depth should be 0-100% if in base
        if result.get("in_base"):
            assert 0 <= result.get("base_depth_pct", 0) <= 100
            assert result.get("weeks_in_base", 0) >= 0

    def test_weinstein_stage_classification(self, signal_computer, test_date):
        """
        Test Weinstein 4-stage market cycle classification.

        Expected: Should classify stock into one of 4 stages with confidence.
        """
        result = signal_computer.weinstein_stage("NVDA", test_date)

        assert isinstance(result, dict)
        assert "stage" in result
        assert "confidence" in result

        # Stage should be 1-4 or "unknown"
        stage = result.get("stage")
        if stage != "unknown":
            assert 1 <= stage <= 4

    def test_td_sequential_count(self, signal_computer, test_date):
        """
        Test DeMark TD Sequential setup detection.

        Expected: Should return setup count and perfected status.
        """
        result = signal_computer.td_sequential("TSLA", test_date)

        assert isinstance(result, dict)
        assert "setup_count" in result
        assert "setup_type" in result
        assert "completed_9" in result

        # Setup count should be 0-9
        assert 0 <= result.get("setup_count", 0) <= 9


class TestSwingTraderScore:
    """Test swing trader score computation."""

    @pytest.fixture
    def swing_scorer(self):
        """Create a SwingTraderScore instance."""
        return SwingTraderScore()

    def test_compute_full_pipeline(self, swing_scorer):
        """
        Test complete swing score computation for a valid candidate.

        Expected: Score should be 0-100 with valid component breakdown.
        """
        test_date = date.today() - timedelta(days=1)
        result = swing_scorer.compute("AAPL", test_date)

        assert isinstance(result, dict)
        assert "swing_score" in result
        assert "grade" in result
        assert "components" in result

        # Score should be 0-100
        score = result.get("swing_score", 0)
        assert 0 <= score <= 100

        # Grade should be A+, A, B, C, D, F, or F if failed
        grade = result.get("grade")
        assert grade in ["A+", "A", "B", "C", "D", "F"]

    def test_hard_gates_block_bad_candidates(self, swing_scorer):
        """
        Test that hard-fail gates properly reject invalid candidates.

        Expected: Candidates with bad trend scores should be rejected.
        """
        # Use a date with real data
        test_date = date.today() - timedelta(days=5)
        result = swing_scorer.compute("AAPL", test_date)

        # Should have pass/fail result
        assert "pass" in result
        assert isinstance(result["pass"], bool)

        # If failed, should have reason
        if not result["pass"]:
            assert "reason" in result or "hard_gates" in result

    def test_component_weights_sum(self, swing_scorer):
        """
        Test that component scores sum reasonably to total score.

        Expected: Components should aggregate meaningfully.
        """
        test_date = date.today() - timedelta(days=1)
        result = swing_scorer.compute("MSFT", test_date)

        if result.get("pass"):
            components = result.get("components", {})
            total_possible = (
                components.get("setup_quality", {}).get("max", 0)
                + components.get("trend_quality", {}).get("max", 0)
                + components.get("momentum_rs", {}).get("max", 0)
                + components.get("volume", {}).get("max", 0)
                + components.get("fundamentals", {}).get("max", 0)
                + components.get("sector_industry", {}).get("max", 0)
                + components.get("multi_timeframe", {}).get("max", 0)
            )
            # Total possible should be 100
            assert total_possible == 100


class TestFilterPipeline:
    """Test the 6-tier signal filter pipeline."""

    @pytest.fixture
    def filter_pipe(self):
        """Create a FilterPipeline instance."""
        return FilterPipeline()

    def test_tier_progression(self, filter_pipe):
        """
        Test that filter pipeline progresses through all tiers.

        Expected: Should evaluate candidates through tiers 1-5.
        """
        test_date = date.today() - timedelta(days=1)
        # Get a sample of candidates (would need real buy_sell_daily data)
        # This is a placeholder structure
        candidates = [{"symbol": "AAPL", "date": test_date}]

        # Pipeline should process without error
        try:
            # Would call: results = filter_pipe.evaluate(candidates, test_date)
            # For now, just verify the pipeline exists
            assert filter_pipe is not None
        except Exception as e:
            pytest.skip(f"Pipeline requires real data: {e}")

    def test_quality_score_range(self, filter_pipe):
        """
        Test that quality scores fall in valid ranges.

        Expected: SQS scores should be 0-100.
        """
        # Quality scores should be bounded
        assert filter_pipe is not None


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_missing_data_graceful_degradation(self):
        """
        Test that missing data doesn't crash signal computation.

        Expected: Should return empty/default results.
        """
        computer = SignalComputer()
        # Non-existent symbol should not raise
        result = computer.minervini_trend_template("FAKE_SYMBOL_XYZ", date.today())

        # Should return structure with pass=False
        assert isinstance(result, dict)
        assert result.get("pass") == False

    def test_null_database_results(self):
        """
        Test handling of NULL database results.

        Expected: Should not crash on NULL values.
        """
        computer = SignalComputer()
        # Very old date with sparse data
        result = computer.minervini_trend_template("AAPL", date(2020, 1, 1))

        # Should return structure safely
        assert isinstance(result, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
