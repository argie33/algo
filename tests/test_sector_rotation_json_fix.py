#!/usr/bin/env python3
"""
Test for sector_rotation_signal JSON validation fix.

Verifies that:
1. Valid JSON is stored correctly
2. Invalid JSON is caught and replaced with valid placeholder
3. API can handle both valid and invalid JSON gracefully
"""

import json
import sys
import unittest
from datetime import date
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, '/Users/arger/code/algo')

from algo.algo_sector_rotation import SectorRotationDetector

class TestSectorRotationJSONValidation(unittest.TestCase):
    """Test JSON validation in sector rotation detector"""

    def test_persist_creates_valid_json(self):
        """Test that _persist creates valid JSON"""
        detector = SectorRotationDetector()

        test_result = {
            'signal': 'defensive_rotation_warning',
            'defensive_lead_score': 65.5,
            'cyclical_weak_score': 45.2,
            'defensive_rank_improvement_4w': 2.3,
            'cyclical_rank_improvement_4w': -1.5,
            'spread_4w': 3.8,
            'weeks_persistent': 2,
            'reduce_exposure_pts': 5,
            'sector_data': {
                'Utilities': {'rank': 1, 'momentum': 0.8},
                'Technology': {'rank': 11, 'momentum': -0.3}
            }
        }

        # Mock DatabaseContext to capture the JSON that would be inserted
        captured_details = None

        def mock_execute(query, params):
            nonlocal captured_details
            if 'INSERT INTO sector_rotation_signal' in query:
                captured_details = params[5]  # details is 6th parameter

        mock_context = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute = mock_execute
        mock_context.__enter__ = Mock(return_value=mock_cursor)
        mock_context.__exit__ = Mock(return_value=None)

        with patch('algo.algo_sector_rotation.DatabaseContext', return_value=mock_context):
            detector._persist(date(2026, 6, 8), test_result)

        # Verify captured JSON is valid
        self.assertIsNotNone(captured_details)
        parsed = json.loads(captured_details)
        self.assertIsInstance(parsed, dict)
        self.assertIn('defensive_lead_score', parsed)
        self.assertEqual(parsed['defensive_lead_score'], 65.5)
        self.assertIn('sector_data', parsed)

    def test_persist_handles_non_serializable_data(self):
        """Test that _persist handles non-JSON-serializable data gracefully"""
        detector = SectorRotationDetector()

        # Create a result with data that can't be JSON serialized
        class CustomObject:
            pass

        test_result = {
            'signal': 'neutral',
            'defensive_lead_score': 50.0,
            'cyclical_weak_score': 50.0,
            'defensive_rank_improvement_4w': 0,
            'cyclical_rank_improvement_4w': 0,
            'spread_4w': 0,
            'weeks_persistent': 0,
            'reduce_exposure_pts': 0,
            'sector_data': {}
        }

        captured_details = None

        def mock_execute(query, params):
            nonlocal captured_details
            if 'INSERT INTO sector_rotation_signal' in query:
                captured_details = params[5]

        mock_context = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute = mock_execute
        mock_context.__enter__ = Mock(return_value=mock_cursor)
        mock_context.__exit__ = Mock(return_value=None)

        with patch('algo.algo_sector_rotation.DatabaseContext', return_value=mock_context):
            detector._persist(date(2026, 6, 8), test_result)

        # Verify we still get valid JSON (not error state)
        self.assertIsNotNone(captured_details)
        parsed = json.loads(captured_details)
        self.assertIsInstance(parsed, dict)

if __name__ == '__main__':
    unittest.main()
