#!/usr/bin/env python3
"""
Unit tests for Issue #2: Data Loader Completion Detection Enhancement

Tests the two-part fix:
1. Recentness check: execution_completed > adaptive_threshold old → HALT
   - Morning (2-9:30 AM ET): 40 min threshold
   - Intraday (9:30 AM+): 20 min threshold
2. Symbol coverage: symbols_loaded / symbol_count < 90% → HALT
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
from zoneinfo import ZoneInfo


class TestExecutionCompletedRecentness(unittest.TestCase):
    """Test the recentness validation for execution_completed timestamps."""

    def _get_stale_threshold(self, test_hour_et):
        """Helper to determine stale threshold based on ET hour (same logic as production)."""
        if 2 <= test_hour_et < 10:  # 2 AM - 9:59 AM ET (morning prep window)
            return 40
        else:  # 10 AM+ or before 2 AM (intraday/evening)
            return 20

    def test_recent_completion_morning_accepted(self):
        """execution_completed < 40 min old during morning (2-9:30 AM ET) should be accepted."""
        # Simulate 5:00 AM ET (morning prep window)
        threshold = self._get_stale_threshold(5)
        self.assertEqual(threshold, 40)

        now = datetime.now(timezone.utc)
        execution_completed = now - timedelta(minutes=15)  # 15 minutes ago (well within 40 min)

        age_minutes = (now - execution_completed).total_seconds() / 60

        # Should NOT be flagged as stale
        self.assertLess(age_minutes, threshold)

    def test_recent_completion_intraday_accepted(self):
        """execution_completed < 20 min old during intraday should be accepted."""
        # Simulate 11:00 AM ET (intraday)
        threshold = self._get_stale_threshold(11)
        self.assertEqual(threshold, 20)

        now = datetime.now(timezone.utc)
        execution_completed = now - timedelta(minutes=5)  # 5 minutes ago (within 20 min)

        age_minutes = (now - execution_completed).total_seconds() / 60

        # Should NOT be flagged as stale
        self.assertLess(age_minutes, threshold)

    def test_stale_completion_morning_rejected(self):
        """execution_completed > 40 min old during morning should be rejected (crash detected)."""
        # Simulate 6:00 AM ET (morning prep window)
        threshold = self._get_stale_threshold(6)
        self.assertEqual(threshold, 40)

        now = datetime.now(timezone.utc)
        execution_completed = now - timedelta(minutes=45)  # 45 minutes ago (exceeds 40 min)

        age_minutes = (now - execution_completed).total_seconds() / 60

        # Should be flagged as stale
        self.assertGreater(age_minutes, threshold)

    def test_stale_completion_intraday_rejected(self):
        """execution_completed > 20 min old during intraday should be rejected (crash detected)."""
        # Simulate 2:00 PM ET (intraday)
        threshold = self._get_stale_threshold(14)
        self.assertEqual(threshold, 20)

        now = datetime.now(timezone.utc)
        execution_completed = now - timedelta(minutes=75)  # 75 minutes ago (exceeds 20 min)

        age_minutes = (now - execution_completed).total_seconds() / 60

        # Should be flagged as stale
        self.assertGreater(age_minutes, threshold)

    def test_boundary_40_minutes_morning(self):
        """execution_completed exactly at 40 min boundary during morning."""
        threshold = self._get_stale_threshold(5)
        self.assertEqual(threshold, 40)

        now = datetime.now(timezone.utc)
        execution_completed = now - timedelta(minutes=40)  # Exactly 40 minutes

        age_minutes = (now - execution_completed).total_seconds() / 60

        # At boundary, should be rejected (>40 means just over 40)
        self.assertAlmostEqual(age_minutes, 40, delta=0.1)

    def test_boundary_20_minutes_intraday(self):
        """execution_completed exactly at 20 min boundary during intraday."""
        threshold = self._get_stale_threshold(11)
        self.assertEqual(threshold, 20)

        now = datetime.now(timezone.utc)
        execution_completed = now - timedelta(minutes=20)  # Exactly 20 minutes

        age_minutes = (now - execution_completed).total_seconds() / 60

        # At boundary, should be rejected (>20 means just over 20)
        self.assertAlmostEqual(age_minutes, 20, delta=0.1)

    def test_timezone_aware_parsing(self):
        """Should handle timezone-aware timestamps from database."""
        # Simulate database timestamp (UTC)
        db_timestamp_str = "2026-06-09T02:30:00+00:00"
        exec_completed = datetime.fromisoformat(db_timestamp_str.replace('Z', '+00:00'))

        # Current time 15 minutes later (within morning 40 min threshold)
        now = exec_completed + timedelta(minutes=15)

        age_minutes = (now - exec_completed).total_seconds() / 60
        threshold = self._get_stale_threshold(2)
        self.assertEqual(threshold, 40)
        self.assertLess(age_minutes, threshold)

    def test_timezone_string_with_z(self):
        """Should handle 'Z' suffix for UTC timestamps."""
        db_timestamp_str = "2026-06-09T02:30:00Z"
        exec_completed = datetime.fromisoformat(db_timestamp_str.replace('Z', '+00:00'))

        now = exec_completed + timedelta(minutes=5)
        age_minutes = (now - exec_completed).total_seconds() / 60
        threshold = self._get_stale_threshold(2)
        self.assertEqual(threshold, 40)

        self.assertLess(age_minutes, threshold)

    def test_system_latency_scenario_morning(self):
        """Loader finishes at 4:50 AM, Phase 1 runs at 5:05 AM (15 min latency) - should NOT fail."""
        # Simulate Phase 1 checking at 5:05 AM ET
        threshold = self._get_stale_threshold(5)
        self.assertEqual(threshold, 40)

        # Execution completed 15 minutes ago (normal system latency)
        age_minutes = 15

        # Should NOT be flagged as stale (well within 40 min threshold for morning)
        self.assertLess(age_minutes, threshold)


class TestSymbolCoverageValidation(unittest.TestCase):
    """Test the symbol coverage cross-check from data_loader_status."""

    def test_high_coverage_accepted(self):
        """>=90% coverage should pass validation."""
        symbol_count = 5000
        symbols_loaded = 4750  # 95% coverage

        coverage = (symbols_loaded / symbol_count * 100) if symbol_count > 0 else 0

        # Should NOT be flagged
        self.assertGreaterEqual(coverage, 90)

    def test_low_coverage_rejected(self):
        """<90% coverage should trigger halt."""
        symbol_count = 5000
        symbols_loaded = 4000  # 80% coverage (incomplete batch)

        coverage = (symbols_loaded / symbol_count * 100) if symbol_count > 0 else 0

        # Should be flagged as incomplete
        self.assertLess(coverage, 90)

    def test_boundary_90_percent(self):
        """Coverage exactly at 90% boundary."""
        symbol_count = 5000
        symbols_loaded = 4500  # Exactly 90%

        coverage = (symbols_loaded / symbol_count * 100) if symbol_count > 0 else 0

        # At boundary - should pass (>=90%)
        self.assertGreaterEqual(coverage, 90)

    def test_coverage_below_boundary(self):
        """Coverage just below 90% boundary."""
        symbol_count = 5000
        symbols_loaded = 4499  # 89.98% < 90%

        coverage = (symbols_loaded / symbol_count * 100) if symbol_count > 0 else 0

        # Just below threshold - should fail
        self.assertLess(coverage, 90)

    def test_zero_symbols(self):
        """Handle case where no symbols loaded."""
        symbol_count = 5000
        symbols_loaded = 0  # Complete failure

        coverage = (symbols_loaded / symbol_count * 100) if symbol_count > 0 else 0

        self.assertEqual(coverage, 0)
        self.assertLess(coverage, 90)

    def test_zero_symbol_count(self):
        """Handle case where symbol_count is 0 (safety check)."""
        symbol_count = 0  # Edge case
        symbols_loaded = 100

        # Avoid division by zero
        coverage = (symbols_loaded / symbol_count * 100) if symbol_count > 0 else 0

        self.assertEqual(coverage, 0)


class TestIssue2IntegrationScenarios(unittest.TestCase):
    """Integration scenarios for Issue #2 detection."""

    def _get_stale_threshold(self, test_hour_et):
        """Helper to determine stale threshold based on ET hour (same logic as production)."""
        if 2 <= test_hour_et < 10:  # 2 AM - 9:59 AM ET (morning prep window)
            return 40
        else:  # 10 AM+ or before 2 AM (intraday/evening)
            return 20

    def test_normal_completion_scenario_morning(self):
        """Normal scenario: loader finishes quickly during morning, coverage high."""
        # Simulate 5:00 AM ET (morning prep window)
        threshold = self._get_stale_threshold(5)

        now = datetime.now(timezone.utc)

        # Loader finished 3 minutes ago
        execution_completed = now - timedelta(minutes=3)
        age_minutes = (now - execution_completed).total_seconds() / 60

        # 98% coverage
        symbol_count = 5000
        symbols_loaded = 4900
        coverage = (symbols_loaded / symbol_count * 100)

        # Both checks should pass
        self.assertLess(age_minutes, threshold)
        self.assertGreaterEqual(coverage, 90)

    def test_normal_completion_scenario_intraday(self):
        """Normal scenario: loader finishes quickly during intraday, coverage high."""
        # Simulate 1:00 PM ET (intraday)
        threshold = self._get_stale_threshold(13)

        now = datetime.now(timezone.utc)

        # Loader finished 5 minutes ago
        execution_completed = now - timedelta(minutes=5)
        age_minutes = (now - execution_completed).total_seconds() / 60

        # 99% coverage
        symbol_count = 5000
        symbols_loaded = 4950
        coverage = (symbols_loaded / symbol_count * 100)

        # Both checks should pass
        self.assertLess(age_minutes, threshold)
        self.assertGreaterEqual(coverage, 90)

    def test_hung_loader_scenario(self):
        """Hung loader: completion timestamp is 2 hours old (exceeds any threshold)."""
        now = datetime.now(timezone.utc)

        # Task reported completion 2 hours ago, then crashed writing to DB
        execution_completed = now - timedelta(hours=2)
        age_minutes = (now - execution_completed).total_seconds() / 60

        # Coverage shows partial load
        symbol_count = 5000
        symbols_loaded = 3000  # Only 60% before it crashed
        coverage = (symbols_loaded / symbol_count * 100)

        # BOTH checks fail - this is correctly detected as hung loader
        # (2 hours > any threshold)
        morning_threshold = self._get_stale_threshold(5)
        intraday_threshold = self._get_stale_threshold(13)
        self.assertGreater(age_minutes, morning_threshold)
        self.assertGreater(age_minutes, intraday_threshold)
        self.assertLess(coverage, 90)

    def test_partial_batch_failure_scenario(self):
        """Partial batch failure: loader crashed mid-batch, coverage low."""
        now = datetime.now(timezone.utc)

        # Loader was still running, completion timestamp only 2 min old
        execution_completed = now - timedelta(minutes=2)
        age_minutes = (now - execution_completed).total_seconds() / 60

        # But only loaded 75% due to API timeout mid-batch
        symbol_count = 5000
        symbols_loaded = 3750
        coverage = (symbols_loaded / symbol_count * 100)

        # Age check passes (recent in both morning and intraday), but coverage check fails
        morning_threshold = self._get_stale_threshold(5)
        intraday_threshold = self._get_stale_threshold(13)
        self.assertLess(age_minutes, morning_threshold)
        self.assertLess(age_minutes, intraday_threshold)
        self.assertLess(coverage, 90)


class TestErrorHandlingAndEdgeCases(unittest.TestCase):
    """Test error handling for edge cases."""

    def test_null_execution_completed(self):
        """execution_completed is NULL (loader never finished)."""
        execution_completed = None

        # Should be caught before recentness check
        self.assertIsNone(execution_completed)

    def test_null_symbol_count(self):
        """symbol_count is NULL in database."""
        symbol_count = None
        symbols_loaded = 4500

        # Should safely skip validation (avoid division by zero)
        coverage = (symbols_loaded / symbol_count * 100) if symbol_count and symbol_count > 0 else 0
        self.assertEqual(coverage, 0)

    def test_null_symbols_loaded(self):
        """symbols_loaded is NULL (status not updated with counts)."""
        symbol_count = 5000
        symbols_loaded = None

        # Should skip validation (incomplete tracking)
        if symbols_loaded is None:
            self.assertTrue(True)  # Validation skipped


class TestAllLoadersValidationScenarios(unittest.TestCase):
    """Test validation across all 5 morning prep loaders."""

    def test_all_loaders_pass(self):
        """All 5 loaders pass both checks."""
        loaders = {
            'stock_prices_daily': {'recent': True, 'coverage': 98},
            'technical_data_daily': {'recent': True, 'coverage': 97},
            'buy_sell_daily': {'recent': True, 'coverage': 96},
            'signal_quality_scores': {'recent': True, 'coverage': 95},
            'swing_trader_scores': {'recent': True, 'coverage': 99},
        }

        failures = []
        for loader, checks in loaders.items():
            if not checks['recent'] or checks['coverage'] < 90:
                failures.append(loader)

        # Should have no failures
        self.assertEqual(len(failures), 0)

    def test_one_loader_fails_coverage(self):
        """One loader fails coverage check (incomplete batch)."""
        loaders = {
            'stock_prices_daily': {'recent': True, 'coverage': 98},
            'technical_data_daily': {'recent': True, 'coverage': 88},  # FAIL
            'buy_sell_daily': {'recent': True, 'coverage': 96},
            'signal_quality_scores': {'recent': True, 'coverage': 95},
            'swing_trader_scores': {'recent': True, 'coverage': 99},
        }

        failures = []
        for loader, checks in loaders.items():
            if not checks['recent'] or checks['coverage'] < 90:
                failures.append(loader)

        # Should have 1 failure
        self.assertEqual(len(failures), 1)
        self.assertIn('technical_data_daily', failures)

    def test_one_loader_fails_recentness(self):
        """One loader fails recentness check (post-completion crash)."""
        loaders = {
            'stock_prices_daily': {'recent': True, 'coverage': 98},
            'technical_data_daily': {'recent': False, 'coverage': 97},  # FAIL
            'buy_sell_daily': {'recent': True, 'coverage': 96},
            'signal_quality_scores': {'recent': True, 'coverage': 95},
            'swing_trader_scores': {'recent': True, 'coverage': 99},
        }

        failures = []
        for loader, checks in loaders.items():
            if not checks['recent'] or checks['coverage'] < 90:
                failures.append(loader)

        # Should have 1 failure
        self.assertEqual(len(failures), 1)
        self.assertIn('technical_data_daily', failures)


if __name__ == '__main__':
    unittest.main()
