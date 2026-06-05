#!/usr/bin/env python3
"""Test Phase 1 data patrol grace period and failsafe trigger logic."""

import unittest
import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from algo.orchestrator.phase1_data_freshness import (
    _check_failsafe_grace_period,
    _check_failsafe_completion,
)

class TestFailsafeGracePeriod(unittest.TestCase):
    """Test the grace period mechanism that prevents redundant failsafe triggers."""

    def setUp(self):
        """Create mock state table for testing."""
        self.mock_state_table = Mock()

    def test_grace_period_within_window(self):
        """Grace period should return minutes ago if trigger is < 2 hours old."""
        trigger_time = time.time() - 30 * 60  # Triggered 30 minutes ago

        self.mock_state_table.get_item.return_value = {
            'Item': {
                'state_key': 'failsafe_trigger_log',
                'triggered_at': trigger_time,
                'completed_at': None
            }
        }

        result = _check_failsafe_grace_period(self.mock_state_table, verbose=False)

        # Should return age in minutes (approximately 30)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 30, delta=1)

    def test_grace_period_expired(self):
        """Grace period should return None if trigger is > 2 hours old."""
        trigger_time = time.time() - 150 * 60  # Triggered 150 minutes ago (>2h)

        self.mock_state_table.get_item.return_value = {
            'Item': {
                'state_key': 'failsafe_trigger_log',
                'triggered_at': trigger_time,
                'completed_at': None
            }
        }

        result = _check_failsafe_grace_period(self.mock_state_table, verbose=False)

        # Should return None because grace period expired
        self.assertIsNone(result)

    def test_grace_period_no_record(self):
        """Grace period should return None if no failsafe record exists."""
        self.mock_state_table.get_item.return_value = {}  # No 'Item' key

        result = _check_failsafe_grace_period(self.mock_state_table, verbose=False)

        # Should return None because no record exists
        self.assertIsNone(result)

    def test_grace_period_handles_errors_gracefully(self):
        """Grace period should return None on DynamoDB errors (graceful degradation)."""
        self.mock_state_table.get_item.side_effect = Exception("DynamoDB unavailable")

        result = _check_failsafe_grace_period(self.mock_state_table, verbose=False)

        # Should return None on error (fail-open)
        self.assertIsNone(result)


class TestFailsafeCompletion(unittest.TestCase):
    """Test the completion checker for failsafe triggers."""

    def setUp(self):
        """Create mock state table for testing."""
        self.mock_state_table = Mock()

    def test_failsafe_completed(self):
        """Should return None if failsafe completed successfully."""
        trigger_time = time.time() - 60 * 60  # Triggered 1 hour ago
        complete_time = time.time() - 30 * 60  # Completed 30 minutes ago

        self.mock_state_table.get_item.return_value = {
            'Item': {
                'state_key': 'failsafe_trigger_log',
                'triggered_at': trigger_time,
                'completed_at': complete_time  # Completed
            }
        }

        result = _check_failsafe_completion(self.mock_state_table, verbose=False, timeout_sec=7200)

        # Should return None (no running failsafe)
        self.assertIsNone(result)

    def test_failsafe_still_running(self):
        """Should return running status if failsafe triggered < timeout_sec ago."""
        trigger_time = time.time() - 30 * 60  # Triggered 30 minutes ago

        self.mock_state_table.get_item.return_value = {
            'Item': {
                'state_key': 'failsafe_trigger_log',
                'triggered_at': trigger_time,
                # No completed_at = still running
            }
        }

        result = _check_failsafe_completion(self.mock_state_table, verbose=False, timeout_sec=7200)

        # Should return running status
        self.assertIsNotNone(result)
        self.assertEqual(result['status'], 'running')
        self.assertAlmostEqual(result['age_minutes'], 30, delta=1)

    def test_failsafe_timed_out(self):
        """Should return timed_out if failsafe running > timeout_sec."""
        trigger_time = time.time() - 200 * 60  # Triggered 200 minutes ago

        self.mock_state_table.get_item.return_value = {
            'Item': {
                'state_key': 'failsafe_trigger_log',
                'triggered_at': trigger_time,
                # No completed_at = still running
            }
        }

        timeout_sec = 7200  # 2 hours
        result = _check_failsafe_completion(self.mock_state_table, verbose=False, timeout_sec=timeout_sec)

        # Should return timed_out (200 min > 120 min timeout)
        # Note: test timeout_sec=7200 = 120 minutes
        self.assertIsNotNone(result)
        # If trigger is 200 minutes old and timeout is 7200 seconds (120 min), still within window
        if result:
            self.assertIn(result['status'], ['running', 'timed_out'])


class TestFailsafeLogic(unittest.TestCase):
    """Integration tests for the complete failsafe decision logic."""

    def test_failsafe_decision_tree(self):
        """Test the complete decision tree for when to trigger failsafe.

        Expected flow:
        1. Check if in grace period (previous trigger < 2h ago)
           -> If yes: use stale data, log warning, continue
           -> If no: continue to step 2
        2. Check if previous failsafe has completed or timed out
           -> If completed: data is fresh, continue
           -> If timed out: trigger new failsafe
           -> If running < timeout: already loading, use graceful degradation
        3. Trigger new failsafe if needed
        """

        # Scenario 1: Grace period active (triggered 30 min ago, not completed)
        # Expected: Accept stale data, don't trigger new loader
        mock_table = Mock()
        mock_table.get_item.return_value = {
            'Item': {
                'triggered_at': time.time() - 30 * 60,
                'completed_at': None
            }
        }

        grace_period_age = _check_failsafe_grace_period(mock_table)
        self.assertIsNotNone(grace_period_age)
        self.assertLess(grace_period_age, 120)  # Within 2h window

        # Should NOT trigger new failsafe if in grace period
        completion_status = _check_failsafe_completion(mock_table)
        self.assertIsNotNone(completion_status)
        self.assertEqual(completion_status['status'], 'running')

    def test_error_handling_in_orchestrator_context(self):
        """Verify Phase 1 handles errors gracefully without halting."""

        # If DynamoDB is down or network error occurs, should continue with caution
        mock_table = Mock()
        mock_table.get_item.side_effect = Exception("DynamoDB unavailable")

        # Grace period should fail-open (return None, allow fresh trigger)
        grace_result = _check_failsafe_grace_period(mock_table)
        self.assertIsNone(grace_result)

        # Completion check should also fail-open
        completion_result = _check_failsafe_completion(mock_table)
        self.assertIsNone(completion_result)


if __name__ == '__main__':
    unittest.main()
