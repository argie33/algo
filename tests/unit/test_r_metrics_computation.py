"""Unit tests for R-metrics computation (avg_win_r, avg_loss_r, expectancy)."""

import unittest
from datetime import date
from unittest.mock import MagicMock, patch


class TestRMetricsComputation(unittest.TestCase):
    """Test R-metrics calculation from trades."""

    def test_r_metrics_with_equal_trades(self):
        """Test expectancy with equal wins and losses."""
        # avg_win_r = 2.0, avg_loss_r = 1.0, win_rate = 0.5, loss_rate = 0.5
        # expectancy = (0.5 x 2.0) - (0.5 x 1.0) = 1.0 - 0.5 = 0.5
        avg_win_r = 2.0
        avg_loss_r = 1.0
        win_count = 5
        loss_count = 5
        total_trades = 10

        win_rate = win_count / total_trades
        loss_rate = loss_count / total_trades
        expectancy = (win_rate * avg_win_r) - (loss_rate * avg_loss_r)

        self.assertAlmostEqual(expectancy, 0.5, places=2)

    def test_r_metrics_with_more_wins(self):
        """Test expectancy with more winning trades."""
        # 7 wins, 3 losses: win_rate=0.7, loss_rate=0.3
        # expectancy = (0.7 x 2.0) - (0.3 x 1.5) = 1.4 - 0.45 = 0.95
        avg_win_r = 2.0
        avg_loss_r = 1.5
        win_count = 7
        loss_count = 3
        total_trades = 10

        win_rate = win_count / total_trades
        loss_rate = loss_count / total_trades
        expectancy = (win_rate * avg_win_r) - (loss_rate * avg_loss_r)

        self.assertAlmostEqual(expectancy, 0.95, places=2)

    def test_r_metrics_with_negative_expectancy(self):
        """Test expectancy with more losing trades."""
        # 3 wins, 7 losses: win_rate=0.3, loss_rate=0.7
        # expectancy = (0.3 x 1.0) - (0.7 x 2.0) = 0.3 - 1.4 = -1.1
        avg_win_r = 1.0
        avg_loss_r = 2.0
        win_count = 3
        loss_count = 7
        total_trades = 10

        win_rate = win_count / total_trades
        loss_rate = loss_count / total_trades
        expectancy = (win_rate * avg_win_r) - (loss_rate * avg_loss_r)

        self.assertAlmostEqual(expectancy, -1.1, places=2)

    def test_r_metrics_formula_correctness(self):
        """Verify the expectancy formula: E = (WR x Avg Win R) - (LR x Avg Loss R)."""
        # Test case: profitable system with good risk-reward
        avg_win_r = 3.0  # Average win is 3R
        avg_loss_r = 1.0  # Average loss is 1R
        win_count = 6
        loss_count = 4
        total_trades = 10

        win_rate = win_count / total_trades  # 0.6
        loss_rate = loss_count / total_trades  # 0.4
        expectancy = (win_rate * avg_win_r) - (loss_rate * avg_loss_r)

        # Expected: (0.6 x 3.0) - (0.4 x 1.0) = 1.8 - 0.4 = 1.4
        self.assertAlmostEqual(expectancy, 1.4, places=2)
        self.assertGreater(expectancy, 0, "Profitable system should have positive expectancy")


if __name__ == "__main__":
    unittest.main()
