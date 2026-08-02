#!/usr/bin/env python3
"""Test Phase 8 price data freshness guard.

CRITICAL: This guard prevents trades on stale data when price loader fails
between Phase 1 (9 AM) and Phase 8 (1-5 PM).
"""

import unittest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase8_entry_execution import _check_price_data_freshness


class TestPhase8PriceFreshnessGuard(unittest.TestCase):
    """Test that Phase 8 validates price data freshness for afternoon/evening runs."""

    def test_price_data_fresh_same_day(self) -> None:
        """Price data for today should be considered fresh."""
        run_date = date(2026, 8, 2)

        with patch('algo.orchestrator.phase8_entry_execution.DatabaseContext') as mock_db:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = (date(2026, 8, 2),)  # max_date = today
            mock_db.return_value.__enter__.return_value = mock_cur

            is_fresh, msg = _check_price_data_freshness(run_date)

            self.assertTrue(is_fresh, "Price data from today should be fresh")
            self.assertIn("fresh", msg.lower())

    def test_price_data_stale_yesterday(self) -> None:
        """Price data from yesterday should be rejected for today's run."""
        run_date = date(2026, 8, 2)

        with patch('algo.orchestrator.phase8_entry_execution.DatabaseContext') as mock_db:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = (date(2026, 8, 1),)  # max_date = yesterday
            mock_db.return_value.__enter__.return_value = mock_cur

            is_fresh, msg = _check_price_data_freshness(run_date)

            self.assertFalse(is_fresh, "Price data from yesterday should be stale")
            self.assertIn("stale", msg.lower())
            self.assertIn("before run_date", msg.lower())

    def test_price_data_empty_table(self) -> None:
        """Empty price_daily table should pass (defer to later validation)."""
        run_date = date(2026, 8, 2)

        with patch('algo.orchestrator.phase8_entry_execution.DatabaseContext') as mock_db:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = (None,)  # No data yet
            mock_db.return_value.__enter__.return_value = mock_cur

            is_fresh, msg = _check_price_data_freshness(run_date)

            self.assertTrue(is_fresh, "Empty price_daily should pass (defer to technical data fetch)")
            self.assertIn("no price data yet", msg.lower())

    def test_price_data_no_rows(self) -> None:
        """Missing result from query should be treated as empty."""
        run_date = date(2026, 8, 2)

        with patch('algo.orchestrator.phase8_entry_execution.DatabaseContext') as mock_db:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = None  # Query returned no rows
            mock_db.return_value.__enter__.return_value = mock_cur

            is_fresh, msg = _check_price_data_freshness(run_date)

            self.assertTrue(is_fresh, "No rows returned should pass (defer to technical data fetch)")

    def test_price_data_future_data(self) -> None:
        """Price data from future dates should be considered fresh."""
        run_date = date(2026, 8, 2)

        with patch('algo.orchestrator.phase8_entry_execution.DatabaseContext') as mock_db:
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = (date(2026, 8, 3),)  # max_date = tomorrow
            mock_db.return_value.__enter__.return_value = mock_cur

            is_fresh, msg = _check_price_data_freshness(run_date)

            self.assertTrue(is_fresh, "Future price data should be fresh")
            self.assertIn("fresh", msg.lower())

    def test_price_data_db_error_handling(self) -> None:
        """Database errors should be handled gracefully by returning False."""
        run_date = date(2026, 8, 2)

        with patch('algo.orchestrator.phase8_entry_execution.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.side_effect = Exception("Database connection failed")

            is_fresh, msg = _check_price_data_freshness(run_date)

            self.assertFalse(is_fresh, "Database errors should block Phase 8")
            self.assertIn("could not verify", msg.lower())

    def test_risk_scenario_afternoon_run_stale_data(self) -> None:
        """Verify the risk scenario: afternoon run with stale morning data."""
        # Risk scenario from docstring:
        # 9:00 AM: Phase 1 validates today's close price (ok at that time)
        # 1:00 PM: Price loader fails (network issue)
        # 1:05 PM: Phase 8 would execute trades on STALE 9 AM prices (WITHOUT this guard)

        run_date = date(2026, 8, 2)  # Today is Aug 2

        with patch('algo.orchestrator.phase8_entry_execution.DatabaseContext') as mock_db:
            mock_cur = MagicMock()
            # Price loader failed, max_date is still Aug 1 (yesterday's close)
            mock_cur.fetchone.return_value = (date(2026, 8, 1),)
            mock_db.return_value.__enter__.return_value = mock_cur

            is_fresh, msg = _check_price_data_freshness(run_date)

            self.assertFalse(is_fresh, "Should block Phase 8 when price loader fails between Phase 1 and Phase 8")
            self.assertIn("loader may have failed", msg.lower())


if __name__ == "__main__":
    unittest.main()
