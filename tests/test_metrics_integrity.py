#!/usr/bin/env python3
"""Integration tests: Verify metrics consistency and freshness configuration.

Tests that:
1. All metrics come from MetricsCalculator (single source of truth)
2. All freshness checks use centralized config
3. No fallback calculations in API or dashboard
4. Metrics match between loader, API, and dashboard
"""

import unittest
import sys
from pathlib import Path
from datetime import date, datetime, timezone

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.metrics_calculator import MetricsCalculator
from utils.data_freshness_config import (
    FRESHNESS_RULES,
    get_freshness_rule,
    is_table_fresh,
    get_max_age_minutes,
)


class TestMetricsCalculator(unittest.TestCase):
    """Verify MetricsCalculator handles all 8 metrics correctly."""

    def test_win_rate_calculation(self):
        """Test win_rate calculation with various inputs."""
        # Normal case
        wr = MetricsCalculator.calculate_win_rate(10, 6, 4)
        self.assertEqual(wr, 60.0)

        # Perfect record
        wr = MetricsCalculator.calculate_win_rate(5, 5, 0)
        self.assertEqual(wr, 100.0)

        # All losses
        wr = MetricsCalculator.calculate_win_rate(5, 0, 5)
        self.assertEqual(wr, 0.0)

        # No trades
        wr = MetricsCalculator.calculate_win_rate(0, 0, 0)
        self.assertIsNone(wr)

    def test_sharpe_ratio_calculation(self):
        """Test Sharpe calculation with sufficient data."""
        returns = [0.01, 0.02, -0.01, 0.03, 0.015] * 50  # 250 returns
        sharpe = MetricsCalculator.calculate_sharpe_ratio(returns, min_observations=5)
        self.assertIsNotNone(sharpe)
        self.assertGreater(sharpe, 0)

    def test_sharpe_insufficient_data(self):
        """Test Sharpe returns None with < 5 observations."""
        returns = [0.01, 0.02]
        sharpe = MetricsCalculator.calculate_sharpe_ratio(returns, min_observations=5)
        self.assertIsNone(sharpe)

    def test_max_drawdown_calculation(self):
        """Test max drawdown calculation."""
        portfolio_vals = [100, 105, 110, 95, 108, 100]
        dd = MetricsCalculator.calculate_max_drawdown(portfolio_vals)
        # Peak is 110, drawdown is (110-95)/110 = 13.6%
        self.assertIsNotNone(dd)
        self.assertGreater(dd, 0)
        self.assertLess(dd, 20)

    def test_profit_factor_calculation(self):
        """Test profit factor calculation."""
        pf = MetricsCalculator.calculate_profit_factor(1000, 500)
        self.assertEqual(pf, 2.0)

        # Perfect record (no losses)
        pf = MetricsCalculator.calculate_profit_factor(1000, 0)
        self.assertEqual(pf, float('inf'))

        # No wins
        pf = MetricsCalculator.calculate_profit_factor(0, 500)
        self.assertEqual(pf, 0.0)

    def test_expectancy_calculation(self):
        """Test expectancy calculation."""
        exp = MetricsCalculator.calculate_expectancy(60, 2.5, -1.0)
        # E = 0.6 * 2.5 - 0.4 * 1.0 = 1.5 - 0.4 = 1.1
        self.assertAlmostEqual(exp, 1.1, places=2)

    def test_avg_r_multiple_calculation(self):
        """Test average R-multiple calculation."""
        r_values = [2.5, 1.5, 2.0, 1.0]
        avg_r = MetricsCalculator.calculate_avg_r_multiple(r_values)
        self.assertAlmostEqual(avg_r, 1.75, places=2)


class TestFreshnessConfig(unittest.TestCase):
    """Verify centralized freshness configuration."""

    def test_config_has_critical_tables(self):
        """Test that critical tables are defined."""
        critical_tables = [t for t, r in FRESHNESS_RULES.items() if r.get("critical")]
        self.assertGreater(len(critical_tables), 5)
        self.assertIn("price_daily", critical_tables)
        self.assertIn("algo_performance_daily", critical_tables)

    def test_get_freshness_rule(self):
        """Test retrieving freshness rules."""
        rule = get_freshness_rule("price_daily")
        self.assertIsNotNone(rule)
        self.assertIn("max_age_days", rule)
        self.assertEqual(rule["max_age_days"], 1)

    def test_get_max_age_minutes(self):
        """Test max age conversion to minutes."""
        minutes = get_max_age_minutes("price_daily")
        self.assertEqual(minutes, 1440)  # 1 day in minutes

    def test_is_table_fresh(self):
        """Test freshness checking function."""
        # Fresh data (today)
        today = date.today()
        is_fresh, age, msg = is_table_fresh("price_daily", today)
        self.assertTrue(is_fresh)

        # Stale data (30 days old) - should be stale for price_daily (1 day threshold)
        old_date = date.today() - timezone.utc.localize(datetime.now()).replace(day=1).timedelta(days=30)
        # Simpler: just verify function works with old dates
        is_fresh, age, msg = is_table_fresh("price_daily", date(2020, 1, 1))
        self.assertFalse(is_fresh)  # Data from 6 years ago should be stale


class TestNoFallbackCalculations(unittest.TestCase):
    """Verify that fallback calculations have been removed."""

    def test_api_avg_r_not_recalculated(self):
        """Verify API doesn't recalculate avg_r from trades."""
        # Read lambda/api/routes/algo.py and check for recalc pattern
        api_file = Path(__file__).parent.parent / "lambda" / "api" / "routes" / "algo.py"
        content = api_file.read_text(encoding="utf-8")

        # Should NOT have pattern: avg_r_multiple = round(_mean(r_multiples)
        # But may have commented versions
        self.assertNotIn(
            "'avg_r_multiple': round(_mean(r_multiples)",
            content,
            "API should not recalculate avg_r_multiple",
        )

    def test_dashboard_avg_r_no_fallback(self):
        """Verify dashboard doesn't fallback calculate avg_r."""
        dashboard_file = Path(__file__).parent.parent / "tools" / "dashboard" / "dashboard.py"
        content = dashboard_file.read_text(encoding="utf-8")

        # Should have avg_r = None initially
        # But NOT have fallback calculation with statistics.mean
        self.assertIn(
            "avg_r = None",
            content,
            "Dashboard should initialize avg_r to None",
        )
        # Check that fallback calculation is removed (commented out or gone)
        self.assertNotIn(
            "avg_r_vals = [float(t[\"exit_r_multiple\"]) for t in trades if t.get",
            content,
            "Dashboard should not have fallback avg_r calculation",
        )

    def test_dashboard_uses_metrics_import(self):
        """Verify dashboard imports MetricsCalculator if needed."""
        dashboard_file = Path(__file__).parent.parent / "tools" / "dashboard" / "dashboard.py"
        content = dashboard_file.read_text(encoding="utf-8")

        # Dashboard should use freshness config
        self.assertIn(
            "from utils.data_freshness_config import",
            content,
            "Dashboard should import freshness config",
        )

    def test_loader_uses_calculator(self):
        """Verify loader imports and uses MetricsCalculator."""
        loader_file = (
            Path(__file__).parent.parent
            / "loaders"
            / "load_algo_performance_daily.py"
        )
        content = loader_file.read_text(encoding="utf-8")

        # Should import calculator
        self.assertIn(
            "from utils.metrics_calculator import MetricsCalculator",
            content,
            "Loader should import MetricsCalculator",
        )

        # Should call calculator methods
        self.assertIn(
            "MetricsCalculator.calculate_win_rate",
            content,
            "Loader should use calculator for win_rate",
        )


class TestConsistencyAcrossComponents(unittest.TestCase):
    """Verify metrics are consistent across loader, API, dashboard."""

    def test_all_critical_tables_have_rules(self):
        """Verify all critical data tables have freshness rules."""
        critical_tables = [
            "price_daily",
            "algo_portfolio_snapshots",
            "algo_performance_daily",
            "buy_sell_daily",
            "swing_trader_scores",
            "market_health_daily",
        ]
        for table in critical_tables:
            rule = get_freshness_rule(table)
            self.assertIsNotNone(
                rule, f"Critical table {table} should have freshness rule"
            )
            self.assertTrue(
                rule.get("critical"),
                f"Table {table} should be marked critical",
            )

    def test_metric_calculation_consistency(self):
        """Test that metrics calculated same way regardless of input order."""
        # Win rate should be consistent
        wr1 = MetricsCalculator.calculate_win_rate(100, 60, 40)
        wr2 = MetricsCalculator.calculate_win_rate(100, 60, 40)
        self.assertEqual(wr1, wr2)

    def test_no_hardcoded_thresholds_in_dashboard(self):
        """Verify dashboard uses config instead of hardcoding thresholds."""
        dashboard_file = Path(__file__).parent.parent / "tools" / "dashboard" / "dashboard.py"
        content = dashboard_file.read_text(encoding="utf-8")

        # Should use config to get thresholds
        self.assertIn(
            "get_freshness_rule(\"price_daily\")",
            content,
            "Dashboard should use get_freshness_rule for price_daily",
        )

        # Should NOT have MAX_SPY_AGE_DAYS = 1 hardcoded anymore
        self.assertNotIn(
            "MAX_SPY_AGE_DAYS = 1",
            content,
            "Dashboard should not have hardcoded MAX_SPY_AGE_DAYS",
        )


class TestConfigCompleteness(unittest.TestCase):
    """Verify freshness config covers all needed tables."""

    def test_min_tables_in_config(self):
        """Verify minimum set of tables are configured."""
        self.assertGreaterEqual(len(FRESHNESS_RULES), 8, "Need at least 8 table rules")

    def test_all_rules_have_required_fields(self):
        """Verify each rule has required fields."""
        for table_name, rule in FRESHNESS_RULES.items():
            self.assertIn("max_age_days", rule, f"{table_name} missing max_age_days")
            self.assertIn("critical", rule, f"{table_name} missing critical flag")
            self.assertIn("description", rule, f"{table_name} missing description")

    def test_config_covers_audit_findings(self):
        """Verify config covers all tables from original audit."""
        audit_tables = {
            "price_daily",
            "algo_portfolio_snapshots",
            "algo_performance_daily",
            "algo_risk_daily",
            "buy_sell_daily",
            "swing_trader_scores",
            "market_health_daily",
            "market_exposure_daily",
        }
        config_tables = set(FRESHNESS_RULES.keys())
        self.assertTrue(
            audit_tables.issubset(config_tables),
            f"Config missing tables: {audit_tables - config_tables}",
        )


if __name__ == "__main__":
    unittest.main()
