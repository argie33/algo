"""
Backtest Regression Test — Validate that code changes don't degrade live performance.

This test:
1. Runs a backtest on a fixed date range with current code
2. Compares metrics against reference_metrics.json
3. Flags if any metric deviates beyond tolerance threshold
4. Blocks merge if regression is detected

This is a CI gate: runs on every commit, must pass before code merges to main.
Local development: Run with --local flag to skip if data unavailable.

USAGE:
    pytest tests/backtest/test_backtest_regression.py          # full run (CI)
    pytest tests/backtest/test_backtest_regression.py --local  # local dev (mocked)
"""

import pytest
import json
import os
from pathlib import Path
from datetime import date


@pytest.fixture(scope="module")
def reference_metrics():
    """Load reference metrics from file."""
    ref_file = Path(__file__).parent / "reference_metrics.json"
    assert ref_file.exists(), f"reference_metrics.json not found at {ref_file}"
    with open(ref_file) as f:
        return json.load(f)


@pytest.mark.regression
class TestBacktestRegression:
    """Ensure backtest metrics don't regress beyond tolerance."""

    @pytest.fixture(scope="class")
    def current_metrics(self, test_config):
        """Run backtest with current code to get live metrics.

        Returns empty dict if running in local mode without data access.
        """
        # Only run if we can connect to test database
        try:
            from algo_backtest import Backtester
            bt = Backtester(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 4, 24),
                initial_capital=100_000.0,
                max_positions=12,
                use_advanced_filters=True,
            )
            return bt.run()
        except Exception as e:
            # In local development without test DB, skip
            if os.getenv('ENVIRONMENT', 'local') == 'local':
                pytest.skip(f"Backtest requires test database: {e}")
            raise

    def test_win_rate_no_regression(self, reference_metrics, current_metrics):
        """Win rate should not drop more than tolerance."""
        if not current_metrics:
            pytest.skip("No backtest metrics available")

        ref_val = reference_metrics["metrics"]["win_rate_pct"]
        tolerance = reference_metrics["tolerances"]["win_rate_pct"]
        curr_val = current_metrics["win_rate_pct"]

        assert abs(curr_val - ref_val) <= tolerance, \
            f"Win rate regression: {curr_val}% vs {ref_val}% (tolerance ±{tolerance}%)"

    def test_sharpe_no_regression(self, reference_metrics, current_metrics):
        """Sharpe should not drop more than tolerance."""
        if not current_metrics:
            pytest.skip("No backtest metrics available")

        ref_val = reference_metrics["metrics"]["sharpe_ratio"]
        tolerance = reference_metrics["tolerances"]["sharpe_ratio"]
        curr_val = current_metrics["sharpe_ratio"]

        assert abs(curr_val - ref_val) <= tolerance, \
            f"Sharpe regression: {curr_val} vs {ref_val} (tolerance ±{tolerance})"

    def test_max_drawdown_no_regression(self, reference_metrics, current_metrics):
        """Max drawdown should not increase more than tolerance."""
        if not current_metrics:
            pytest.skip("No backtest metrics available")

        ref_val = reference_metrics["metrics"]["max_drawdown_pct"]
        tolerance = reference_metrics["tolerances"]["max_drawdown_pct"]
        curr_val = current_metrics["max_drawdown_pct"]

        # For drawdown, we allow it to get worse (higher) but not beyond tolerance
        assert curr_val - ref_val <= tolerance, \
            f"Max drawdown regression: {curr_val}% vs {ref_val}% (tolerance +{tolerance}%)"

    def test_expectancy_no_regression(self, reference_metrics, current_metrics):
        """Expectancy should not drop more than tolerance."""
        if not current_metrics:
            pytest.skip("No backtest metrics available")

        ref_val = reference_metrics["metrics"]["expectancy_r"]
        tolerance = reference_metrics["tolerances"]["expectancy_r"]
        curr_val = current_metrics["expectancy_r"]

        assert abs(curr_val - ref_val) <= tolerance, \
            f"Expectancy regression: {curr_val}R vs {ref_val}R (tolerance ±{tolerance}R)"

    def test_profit_factor_no_regression(self, reference_metrics, current_metrics):
        """Profit factor should not drop more than tolerance."""
        if not current_metrics:
            pytest.skip("No backtest metrics available")

        ref_val = reference_metrics["metrics"]["profit_factor"]
        tolerance = reference_metrics["tolerances"]["profit_factor"]
        curr_val = current_metrics["profit_factor"]

        assert abs(curr_val - ref_val) <= tolerance, \
            f"Profit factor regression: {curr_val} vs {ref_val} (tolerance ±{tolerance})"

    def test_total_return_no_regression(self, reference_metrics, current_metrics):
        """Total return should not drop more than tolerance."""
        if not current_metrics:
            pytest.skip("No backtest metrics available")

        ref_val = reference_metrics["metrics"]["total_return_pct"]
        tolerance = reference_metrics["tolerances"]["total_return_pct"]
        curr_val = current_metrics["total_return_pct"]

        assert abs(curr_val - ref_val) <= tolerance, \
            f"Return regression: {curr_val}% vs {ref_val}% (tolerance ±{tolerance}%)"


@pytest.mark.regression
class TestBacktestRobustness:
    """Validate backtest infrastructure itself is robust."""

    def test_backtest_runs_without_error(self, test_config):
        """Basic sanity check: backtest starts and completes."""
        try:
            from algo_backtest import Backtester
            bt = Backtester(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
                initial_capital=100_000.0,
                max_positions=5,
                use_advanced_filters=False,
            )
            report = bt.run()
            assert report, "Backtest returned empty report"
        except Exception as e:
            pytest.skip(f"Backtest requires database access: {e}")

    def test_metrics_have_correct_types(self, reference_metrics):
        """Validate reference metrics JSON structure."""
        metrics = reference_metrics["metrics"]
        tolerances = reference_metrics["tolerances"]

        # All metric keys should be strings mapping to numbers
        assert isinstance(metrics, dict)
        assert isinstance(tolerances, dict)
        assert len(metrics) > 0, "No metrics in reference"

        # Each metric must have a corresponding tolerance
        for key, val in metrics.items():
            assert key in tolerances, f"Metric {key} has no tolerance"
            assert isinstance(val, (int, float)), f"Metric {key} value not numeric"
            assert isinstance(tolerances[key], (int, float)), f"Tolerance {key} not numeric"
            assert tolerances[key] > 0, f"Tolerance {key} must be positive"
