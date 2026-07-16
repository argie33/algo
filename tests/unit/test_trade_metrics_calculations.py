"""Unit tests for trade metrics calculations."""

import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from utils.trade_metrics import (
    calculate_exit_r_multiple,
    calculate_mae_pct,
    calculate_mfe_pct,
    calculate_trade_duration_days,
)


class TestCalculateExitRMultiple(unittest.TestCase):
    """Test R-multiple calculation: R = (exit - entry) / (entry - stop)."""

    def test_winning_trade(self):
        """Test profitable trade: exit > entry."""
        # Entry at 100, Exit at 120, Stop at 95
        # R = (120 - 100) / (100 - 95) = 20 / 5 = 4.0
        result = calculate_exit_r_multiple(100, 120, 95)
        self.assertAlmostEqual(float(result), 4.0, places=2)

    def test_losing_trade(self):
        """Test losing trade: exit < entry but above stop."""
        # Entry at 100, Exit at 92, Stop at 90
        # R = (92 - 100) / (100 - 90) = -8 / 10 = -0.8
        result = calculate_exit_r_multiple(100, 92, 90)
        self.assertAlmostEqual(float(result), -0.8, places=2)

    def test_stop_loss_hit(self):
        """Test trade closed at stop loss."""
        # Entry at 100, Exit at 90, Stop at 90
        # R = (90 - 100) / (100 - 90) = -10 / 10 = -1.0
        result = calculate_exit_r_multiple(100, 90, 90)
        self.assertAlmostEqual(float(result), -1.0, places=2)

    def test_invalid_stop_loss_above_entry(self):
        """Test invalid: stop loss >= entry price."""
        # Stop at entry: risk = 0, division by zero → None
        result = calculate_exit_r_multiple(100, 120, 100)
        self.assertIsNone(result)

        # Stop above entry: risk <= 0 → None
        result = calculate_exit_r_multiple(100, 120, 105)
        self.assertIsNone(result)

    def test_decimal_precision(self):
        """Test Decimal precision for financial calculations."""
        # Using Decimal inputs for precise arithmetic
        result = calculate_exit_r_multiple(Decimal("100.50"), Decimal("115.75"), Decimal("98.25"))
        # R = (115.75 - 100.50) / (100.50 - 98.25) = 15.25 / 2.25 ≈ 6.78
        self.assertIsNotNone(result)
        self.assertGreater(float(result), 6.7)
        self.assertLess(float(result), 6.8)

    def test_string_input_conversion(self):
        """Test that string inputs are properly converted."""
        result = calculate_exit_r_multiple("100", "120", "95")
        self.assertAlmostEqual(float(result), 4.0, places=2)

    def test_invalid_price_types(self):
        """Test that invalid price types return None."""
        result = calculate_exit_r_multiple("invalid", 120, 95)
        self.assertIsNone(result)

        result = calculate_exit_r_multiple(100, None, 95)
        self.assertIsNone(result)

    def test_zero_prices(self):
        """Test that zero prices are handled gracefully."""
        result = calculate_exit_r_multiple(0, 120, 95)
        self.assertIsNone(result)  # entry=0, can't validate risk

        result = calculate_exit_r_multiple(100, 0, 95)
        # R = (0 - 100) / (100 - 95) = -100 / 5 = -20
        self.assertAlmostEqual(float(result), -20.0, places=2)


class TestCalculateTradeDurationDays(unittest.TestCase):
    """Test trade duration calculation."""

    def test_single_day_trade(self):
        """Test trade entered and exited same day."""
        entry = date(2026, 7, 15)
        exit_d = date(2026, 7, 15)
        result = calculate_trade_duration_days(entry, exit_d)
        self.assertEqual(result, 0)

    def test_multi_day_trade(self):
        """Test trade held for multiple days."""
        entry = date(2026, 7, 10)
        exit_d = date(2026, 7, 15)
        result = calculate_trade_duration_days(entry, exit_d)
        self.assertEqual(result, 5)

    def test_overnight_trade(self):
        """Test trade held overnight (1 day)."""
        entry = date(2026, 7, 14)
        exit_d = date(2026, 7, 15)
        result = calculate_trade_duration_days(entry, exit_d)
        self.assertEqual(result, 1)

    def test_missing_dates(self):
        """Test that missing dates return None."""
        result = calculate_trade_duration_days(None, date(2026, 7, 15))
        self.assertIsNone(result)

        result = calculate_trade_duration_days(date(2026, 7, 10), None)
        self.assertIsNone(result)

        result = calculate_trade_duration_days(None, None)
        self.assertIsNone(result)

    def test_iso_string_dates(self):
        """Test that ISO format strings are parsed correctly."""
        result = calculate_trade_duration_days("2026-07-10", "2026-07-15")
        self.assertEqual(result, 5)

    def test_invalid_date_strings(self):
        """Test that invalid date strings return None."""
        result = calculate_trade_duration_days("2026-13-45", "2026-07-15")
        self.assertIsNone(result)

        result = calculate_trade_duration_days("not-a-date", "2026-07-15")
        self.assertIsNone(result)


class TestCalculateMFEPct(unittest.TestCase):
    """Test Maximum Favorable Excursion calculation."""

    @patch("utils.trade_metrics.cursor")
    def test_positive_mfe(self, mock_cursor_class):
        """Test MFE when price goes up after entry."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"max_price": 120}

        result = calculate_mfe_pct(mock_cursor, "TEST", 100, date(2026, 7, 10), date(2026, 7, 15))

        # MFE = (120 - 100) / 100 * 100 = 20%
        self.assertAlmostEqual(float(result), 20.0, places=1)

    @patch("utils.trade_metrics.cursor")
    def test_no_favorable_excursion(self, mock_cursor_class):
        """Test MFE when price never goes above entry."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"max_price": 95}  # Below entry

        result = calculate_mfe_pct(mock_cursor, "TEST", 100, date(2026, 7, 10), date(2026, 7, 15))

        # MFE = (95 - 100) / 100 * 100 = -5%
        self.assertAlmostEqual(float(result), -5.0, places=1)

    @patch("utils.trade_metrics.cursor")
    def test_missing_price_data(self, mock_cursor_class):
        """Test MFE returns None when no price data available."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"max_price": None}

        result = calculate_mfe_pct(mock_cursor, "TEST", 100, date(2026, 7, 10), date(2026, 7, 15))
        self.assertIsNone(result)

        # No rows returned
        mock_cursor.fetchone.return_value = None
        result = calculate_mfe_pct(mock_cursor, "TEST", 100, date(2026, 7, 10), date(2026, 7, 15))
        self.assertIsNone(result)

    @patch("utils.trade_metrics.cursor")
    def test_missing_dates(self, mock_cursor_class):
        """Test MFE returns None with missing dates."""
        mock_cursor = MagicMock()

        result = calculate_mfe_pct(mock_cursor, "TEST", 100, None, date(2026, 7, 15))
        self.assertIsNone(result)

        result = calculate_mfe_pct(mock_cursor, "TEST", 100, date(2026, 7, 10), None)
        self.assertIsNone(result)

        # Verify query was never executed
        mock_cursor.execute.assert_not_called()

    @patch("utils.trade_metrics.cursor")
    def test_invalid_entry_price(self, mock_cursor_class):
        """Test MFE returns None for invalid entry price."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"max_price": 120}

        result = calculate_mfe_pct(mock_cursor, "TEST", 0, date(2026, 7, 10), date(2026, 7, 15))
        self.assertIsNone(result)

        result = calculate_mfe_pct(mock_cursor, "TEST", -100, date(2026, 7, 10), date(2026, 7, 15))
        self.assertIsNone(result)


class TestCalculateMAEPct(unittest.TestCase):
    """Test Maximum Adverse Excursion calculation."""

    @patch("utils.trade_metrics.cursor")
    def test_adverse_excursion(self, mock_cursor_class):
        """Test MAE when price goes down after entry."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"min_price": 90}

        result = calculate_mae_pct(mock_cursor, "TEST", 100, date(2026, 7, 10), date(2026, 7, 15))

        # MAE = (90 - 100) / 100 * 100 = -10%
        self.assertAlmostEqual(float(result), -10.0, places=1)

    @patch("utils.trade_metrics.cursor")
    def test_no_adverse_excursion(self, mock_cursor_class):
        """Test MAE when price never goes below entry."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"min_price": 105}  # Above entry

        result = calculate_mae_pct(mock_cursor, "TEST", 100, date(2026, 7, 10), date(2026, 7, 15))

        # MAE = (105 - 100) / 100 * 100 = 5%
        self.assertAlmostEqual(float(result), 5.0, places=1)

    @patch("utils.trade_metrics.cursor")
    def test_missing_price_data(self, mock_cursor_class):
        """Test MAE returns None when no price data available."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"min_price": None}

        result = calculate_mae_pct(mock_cursor, "TEST", 100, date(2026, 7, 10), date(2026, 7, 15))
        self.assertIsNone(result)

    @patch("utils.trade_metrics.cursor")
    def test_query_date_range(self, mock_cursor_class):
        """Test that query uses correct date range."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"min_price": 95}

        entry_date = date(2026, 7, 10)
        exit_date = date(2026, 7, 15)

        calculate_mae_pct(mock_cursor, "TEST", 100, entry_date, exit_date)

        # Verify the query was called with correct parameters
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        # Parameters are in call_args[0][1] (second element of positional args)
        params = call_args[0][1]  # The tuple of parameters
        self.assertIn("TEST", params)  # Symbol in params
        self.assertIn(entry_date, params)  # Entry date in params
        self.assertIn(exit_date, params)  # Exit date in params


class TestTradeMetricsIntegration(unittest.TestCase):
    """Integration tests for trade metrics calculations."""

    def test_realistic_profitable_trade(self):
        """Test a realistic profitable trade."""
        entry_price = 150.50
        exit_price = 175.25
        stop_loss = 140.00

        r_multiple = calculate_exit_r_multiple(entry_price, exit_price, stop_loss)
        duration = calculate_trade_duration_days(date(2026, 7, 10), date(2026, 7, 15))

        # R = (175.25 - 150.50) / (150.50 - 140.00) = 24.75 / 10.50 ≈ 2.36
        self.assertIsNotNone(r_multiple)
        self.assertAlmostEqual(float(r_multiple), 2.36, places=1)
        self.assertEqual(duration, 5)

    def test_realistic_loss_trade(self):
        """Test a realistic losing trade."""
        entry_price = 100.00
        exit_price = 92.50
        stop_loss = 95.00

        r_multiple = calculate_exit_r_multiple(entry_price, exit_price, stop_loss)
        duration = calculate_trade_duration_days(date(2026, 7, 14), date(2026, 7, 15))

        # R = (92.50 - 100.00) / (100.00 - 95.00) = -7.50 / 5.00 = -1.5
        self.assertIsNotNone(r_multiple)
        self.assertAlmostEqual(float(r_multiple), -1.5, places=1)
        self.assertEqual(duration, 1)

    def test_edge_case_scalp_trade(self):
        """Test a scalp trade (very tight stop loss)."""
        entry_price = 100.00
        exit_price = 100.50
        stop_loss = 99.90

        r_multiple = calculate_exit_r_multiple(entry_price, exit_price, stop_loss)

        # R = (100.50 - 100.00) / (100.00 - 99.90) = 0.50 / 0.10 = 5.0
        # High R-multiple from tight stop loss
        self.assertIsNotNone(r_multiple)
        self.assertAlmostEqual(float(r_multiple), 5.0, places=1)


if __name__ == "__main__":
    unittest.main()
