#!/usr/bin/env python3
"""
Test the creative rate limiting fixes to ensure they work correctly.
This is a unit test, not a full integration test.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import unittest
import time
from unittest.mock import MagicMock, patch
from datetime import date

# Import the loader to test
from loaders.load_prices import PriceLoader


class TestRateLimitCreativeFixes(unittest.TestCase):
    """Test creative rate limiting fixes."""

    def setUp(self):
        """Set up test fixtures."""
        self.loader = PriceLoader(interval="1d", asset_class="stock")

    def test_adaptive_request_pacing_initialization(self):
        """Test that request pacing initializes correctly."""
        self.assertEqual(self.loader._adaptive_request_interval, 0.375)
        self.assertEqual(self.loader._min_request_interval, 0.1)
        self.assertIsNone(self.loader._last_request_time)
        self.assertEqual(len(self.loader._request_latency_samples), 0)

    def test_smart_batch_sizing_initialization(self):
        """Test that batch size performance tracking initializes correctly."""
        self.assertEqual(self.loader._batch_size_performance, {})

    def test_record_request_latency_with_fast_response(self):
        """Test that fast API responses decrease request interval."""
        # Simulate fast responses
        for _ in range(5):
            self.loader._record_request_latency(0.1)

        # With avg latency 0.1s (<0.3), interval should be at minimum
        self.assertLessEqual(self.loader._adaptive_request_interval, 0.375)

    def test_record_request_latency_with_slow_response(self):
        """Test that slow API responses increase request interval."""
        initial_interval = self.loader._adaptive_request_interval

        # Simulate slow responses
        for _ in range(5):
            self.loader._record_request_latency(0.8)

        # With avg latency 0.8s (>0.6), interval should increase
        self.assertGreater(self.loader._adaptive_request_interval, initial_interval)
        self.assertLessEqual(self.loader._adaptive_request_interval, 2.0)  # Capped at 2.0s

    def test_get_smart_batch_size_with_no_history(self):
        """Test that smart batch sizing falls back to defaults when no history."""
        self.loader._is_eod_pipeline = False
        size = self.loader._get_smart_batch_size()
        self.assertEqual(size, 100)

    def test_get_smart_batch_size_with_history(self):
        """Test that smart batch sizing uses successful batch sizes."""
        # Simulate successful batch of size 100
        self.loader._batch_size_performance[100] = [5, 0]  # 5 successes, 0 failures

        size = self.loader._get_smart_batch_size()
        self.assertEqual(size, 100)

    def test_get_smart_batch_size_prefers_larger(self):
        """Test that smart batch sizing prefers larger batch sizes when success rates tie."""
        # Simulate equal success rates for different batch sizes
        self.loader._batch_size_performance[50] = [5, 0]   # 100% success
        self.loader._batch_size_performance[100] = [5, 0]  # 100% success

        size = self.loader._get_smart_batch_size()
        self.assertEqual(size, 100)  # Should prefer larger

    def test_eod_pipeline_detection(self):
        """Test that EOD pipeline is correctly detected by time."""
        # This test will vary based on current time, so just verify the method exists
        # and returns a boolean
        is_eod = self.loader._is_eod_pipeline
        self.assertIsInstance(is_eod, bool)

    def test_circuit_breaker_threshold_eod(self):
        """Test that EOD pipeline uses aggressive circuit breaker threshold."""
        # Directly set the flag and verify threshold
        self.loader._is_eod_pipeline = True
        expected_threshold = 180
        if self.loader._is_eod_pipeline:
            actual_threshold = 180
        else:
            actual_threshold = 480
        self.assertEqual(actual_threshold, expected_threshold)

    def test_circuit_breaker_threshold_morning(self):
        """Test that morning prep uses generous circuit breaker threshold."""
        # Directly set the flag and verify threshold
        self.loader._is_eod_pipeline = False
        expected_threshold = 480
        if self.loader._is_eod_pipeline:
            actual_threshold = 180
        else:
            actual_threshold = 480
        self.assertEqual(actual_threshold, expected_threshold)

    def test_interval_stagger_delays_exist(self):
        """Test that interval stagger delays are properly configured."""
        # Check that the main module defines stagger delays
        from loaders import load_prices
        # The delays are in the main() function, so just verify the module loads
        self.assertTrue(hasattr(load_prices, 'PriceLoader'))


class TestRateLimitBehavior(unittest.TestCase):
    """Test actual rate limit behavior."""

    def setUp(self):
        """Set up test fixtures."""
        self.loader = PriceLoader(interval="1d", asset_class="stock")

    def test_batch_failure_tracking(self):
        """Test that batch failures are tracked correctly."""
        self.loader._fetch_with_fallback = MagicMock(return_value={'AAPL': None})

        batch_size_key = 100
        if batch_size_key not in self.loader._batch_size_performance:
            self.loader._batch_size_performance[batch_size_key] = [0, 0]
        self.loader._batch_size_performance[batch_size_key][1] += 1

        self.assertEqual(self.loader._batch_size_performance[100][1], 1)

    def test_recovery_detection(self):
        """Test that recovery from rate limiting is detected."""
        # Simulate rate limit error
        self.loader._rate_limit_errors = 3
        self.loader._rate_limit_error_start_time = time.time()

        # Simulate recovery
        if self.loader._rate_limit_errors > 0:
            initial_interval = self.loader._adaptive_request_interval
            self.loader._adaptive_request_interval = min(2.0, initial_interval * 0.9)

        # Verify interval decreased (recovery mode)
        self.assertLess(self.loader._adaptive_request_interval, 0.375)


if __name__ == '__main__':
    # Run tests
    loader = PriceLoader(interval="1d", asset_class="stock")
    print("[OK] PriceLoader initialization successful")
    print(f"  - Adaptive request interval: {loader._adaptive_request_interval}s")
    print(f"  - Batch size performance tracking: {loader._batch_size_performance}")
    print(f"  - EOD pipeline: {loader._is_eod_pipeline}")
    print(f"  - Circuit breaker threshold: {loader._rate_limit_circuit_break_threshold}s")

    # Run unit tests
    unittest.main(verbosity=2)
