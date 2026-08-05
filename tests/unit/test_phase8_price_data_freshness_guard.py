#!/usr/bin/env python3
"""Test Phase 8 price data freshness guard.

CRITICAL: This guard prevents trades on stale data when price loader fails
between Phase 1 and Phase 8.

NOTE: Time-dependent tests (INTRADAY vs EOD context) are validated by the actual
orchestrator run where the real datetime is used. Unit tests here verify the
data freshness checking logic with mocked database state.
"""

import unittest
from datetime import date
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

    def test_risk_scenario_afternoon_run_stale_data_eod(self) -> None:
        """Verify the risk scenario: evening run (after 4 PM) with stale data that should have been updated."""
        # Risk scenario:
        # 9:00 AM: Phase 1 validates previous day's close price (correct for MORNING)
        # 4:05 PM: Price loader fails (network issue)
        # 4:10 PM: Phase 8 would execute trades on stale data (WITHOUT this guard)
        # During EOD, we expect today's close to be available

        run_date = date(2026, 8, 5)  # Wednesday
        eod_time = datetime(2026, 8, 5, 16, 10, 0)  # 4:10 PM ET (after market close)

        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = eod_time
            with patch('algo.orchestrator.phase8_entry_execution.DatabaseContext') as mock_db:
                mock_cur = MagicMock()
                # Price loader failed, max_date is still Aug 4 (yesterday's close, not today's)
                mock_cur.fetchone.return_value = (date(2026, 8, 4),)
                mock_db.return_value.__enter__.return_value = mock_cur

                is_fresh, msg = _check_price_data_freshness(run_date)

                self.assertFalse(is_fresh, "Should block Phase 8 when price loader fails and today's close not available during EOD")
                self.assertIn("loader may have failed", msg.lower())

    def test_intraday_run_yesterday_prices_sufficient(self) -> None:
        """Verify that during INTRADAY, having yesterday's prices is sufficient and not stale."""
        # During market hours (INTRADAY), yesterday's close is what we expect
        # It's NOT stale, it's the appropriate baseline for technical signals

        run_date = date(2026, 8, 5)  # Wednesday
        intraday_time = datetime(2026, 8, 5, 14, 30, 0)  # 2:30 PM ET (market open)

        with patch('datetime.datetime') as mock_datetime:
            mock_datetime.now.return_value = intraday_time
            with patch('algo.orchestrator.phase8_entry_execution.DatabaseContext') as mock_db:
                mock_cur = MagicMock()
                # Yesterday's close is available
                mock_cur.fetchone.return_value = (date(2026, 8, 4),)
                mock_db.return_value.__enter__.return_value = mock_cur

                is_fresh, msg = _check_price_data_freshness(run_date)

                self.assertTrue(is_fresh, "During INTRADAY, yesterday's prices are fresh and appropriate")
                self.assertIn("fresh", msg.lower())


if __name__ == "__main__":
    unittest.main()
