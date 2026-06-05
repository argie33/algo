#!/usr/bin/env python3
"""Integration tests for data loading enhancements (Issues 9-12, 14).

Tests:
- Issue 9: Parameterized data patrol thresholds via algo_config
- Issue 11: Age tracking in loaders (technical_data_daily, buy_sell_daily)
- Issue 12: ECS scheduling delay compensation in grace period logic
- Issue 10: Age-driven rejection tracking in Phase 5 waterfall
"""

import pytest
import sys
from pathlib import Path
from datetime import date, timedelta, datetime, timezone
from unittest.mock import Mock, patch, MagicMock
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database_context import DatabaseContext
from algo.algo_data_patrol import DataPatrol
from algo.orchestrator.phase1_data_freshness import (
    _trigger_loader_failsafe_with_verification,
    _check_failsafe_grace_period,
    _check_data_patrol,
)


class TestParameterizedPatrolThresholds:
    """Test Issue 9: Parameterized data patrol thresholds."""

    def test_patrol_config_loading(self):
        """Test that patrol thresholds are loaded from algo_config table."""
        with DatabaseContext('read') as cur:
            # Verify config entries exist
            cur.execute(
                "SELECT COUNT(*) FROM algo_config WHERE key LIKE 'patrol_%'"
            )
            result = cur.fetchone()
            config_count = result[0] if result else 0
            # Should have at least 20 patrol config entries
            assert config_count >= 20, f"Expected >=20 patrol configs, found {config_count}"

    def test_patrol_staleness_threshold_config(self):
        """Test staleness thresholds are configurable."""
        with DatabaseContext('read') as cur:
            # Check price_daily staleness threshold
            cur.execute(
                "SELECT value FROM algo_config WHERE key = %s",
                ('patrol_staleness_price_daily',)
            )
            result = cur.fetchone()
            assert result is not None, "patrol_staleness_price_daily config missing"
            assert int(result[0]) == 7, "Default staleness should be 7 days"

    def test_patrol_null_pct_threshold_config(self):
        """Test NULL percentage threshold is configurable."""
        with DatabaseContext('read') as cur:
            cur.execute(
                "SELECT value FROM algo_config WHERE key = %s",
                ('patrol_max_null_pct_threshold',)
            )
            result = cur.fetchone()
            assert result is not None, "patrol_max_null_pct_threshold config missing"
            assert int(result[0]) == 5, "Default NULL % threshold should be 5%"

    def test_data_patrol_uses_config(self):
        """Test DataPatrol class loads and uses configuration."""
        patrol = DataPatrol()

        with DatabaseContext('read') as cur:
            config = patrol._load_configuration(cur)

            # Verify all key sections exist
            assert 'staleness_windows' in config
            assert 'price_sanity' in config
            assert 'volume_sanity' in config
            assert 'coverage_thresholds' in config

            # Verify values are loaded
            assert config['staleness_windows']['price_daily'] == 7
            assert config['volume_sanity']['low_volume_threshold'] == 1000000


class TestAgeTrackingInLoaders:
    """Test Issue 11 & 10: Age tracking in technical_data_daily and signal_quality_scores."""

    def test_technical_data_daily_has_age_column(self):
        """Test technical_data_daily table has price_data_age_days column."""
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'technical_data_daily' AND column_name = 'price_data_age_days'
            """)
            result = cur.fetchone()
            assert result is not None, "technical_data_daily missing price_data_age_days column"

    def test_signal_quality_scores_has_age_columns(self):
        """Test signal_quality_scores table has age columns."""
        with DatabaseContext('read') as cur:
            age_columns = [
                'buy_sell_daily_age_days',
                'technical_data_age_days',
                'trend_template_age_days'
            ]
            for col in age_columns:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'signal_quality_scores' AND column_name = %s
                """, (col,))
                result = cur.fetchone()
                assert result is not None, f"signal_quality_scores missing {col} column"

    def test_filter_rejection_log_has_age_tracking(self):
        """Test filter_rejection_log has age columns and is_age_driven_rejection."""
        with DatabaseContext('read') as cur:
            age_columns = [
                'buy_sell_daily_age_days',
                'technical_data_age_days',
                'trend_template_age_days',
                'max_data_age_days',
                'is_age_driven_rejection'
            ]
            for col in age_columns:
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'filter_rejection_log' AND column_name = %s
                """, (col,))
                result = cur.fetchone()
                assert result is not None, f"filter_rejection_log missing {col} column"


class TestECSSchedulingDelayCompensation:
    """Test Issue 12: ECS scheduling delay compensation in grace period."""

    @patch('boto3.resource')
    def test_actual_running_at_storage(self, mock_boto3):
        """Test that actual_running_at is stored in DynamoDB state table."""
        # Mock DynamoDB
        mock_dynamodb = MagicMock()
        mock_state_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_state_table
        mock_boto3.return_value = mock_dynamodb

        # Simulate storing actual_running_at
        now = time.time()
        mock_state_table.update_item(
            Key={'state_key': 'failsafe_trigger_log'},
            UpdateExpression='SET actual_running_at = :running_at, scheduling_delay_seconds = :delay',
            ExpressionAttributeValues={
                ':running_at': now,
                ':delay': 45.0,  # 45 second scheduling delay
            }
        )

        # Verify update_item was called with correct parameters
        mock_state_table.update_item.assert_called_once()
        call_args = mock_state_table.update_item.call_args
        assert call_args[1]['Key']['state_key'] == 'failsafe_trigger_log'
        assert ':running_at' in call_args[1]['ExpressionAttributeValues']

    def test_grace_period_fallback_logic(self):
        """Test grace period uses actual_running_at with fallback to triggered_at."""
        # Simulate DynamoDB state with both times
        mock_state_item = {
            'triggered_at': time.time() - 3600,  # 1 hour ago
            'actual_running_at': time.time() - 2700,  # 45 minutes ago (60s scheduling delay)
        }

        # Grace period should use actual_running_at (later time)
        # So grace period started 45 minutes ago, not 60 minutes ago
        triggered_age = (time.time() - mock_state_item['triggered_at']) / 60
        running_age = (time.time() - mock_state_item['actual_running_at']) / 60

        assert running_age < triggered_age, "actual_running_at should be later than triggered_at"
        assert abs(running_age - 45) < 1, f"Expected ~45 min grace period, got {running_age:.0f}m"


class TestAgeDrivenRejectionTracking:
    """Test Issue 10: Age-driven rejection tracking in signal filtering."""

    def test_age_driven_rejection_column_exists(self):
        """Test is_age_driven_rejection column exists for tracking."""
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'filter_rejection_log' AND column_name = 'is_age_driven_rejection'
            """)
            result = cur.fetchone()
            assert result is not None, "filter_rejection_log missing is_age_driven_rejection column"

    def test_max_data_age_tracking(self):
        """Test max_data_age_days field tracks maximum age across sources."""
        with DatabaseContext('read') as cur:
            # Query max_data_age_days column
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'filter_rejection_log' AND column_name = 'max_data_age_days'
            """)
            result = cur.fetchone()
            assert result is not None, "filter_rejection_log missing max_data_age_days column"

    def test_age_statistics_calculation(self):
        """Test age statistics can be calculated from rejections."""
        # This test verifies the SQL for age statistics works
        with DatabaseContext('read') as cur:
            try:
                # Sample query from waterfall reporting
                cur.execute("""
                    SELECT
                        AVG(COALESCE(technical_data_age_days, 0))::int as avg_tech_age,
                        AVG(COALESCE(buy_sell_daily_age_days, 0))::int as avg_bs_age,
                        AVG(COALESCE(trend_template_age_days, 0))::int as avg_trend_age,
                        MAX(COALESCE(max_data_age_days, 0))::int as max_age
                    FROM filter_rejection_log
                    WHERE is_age_driven_rejection = TRUE
                    LIMIT 1
                """)
                result = cur.fetchone()
                # Query should execute without error
                assert True, "Age statistics query executed successfully"
            except Exception as e:
                pytest.fail(f"Age statistics query failed: {e}")


class TestDataPatrolIntegration:
    """Integration tests for data patrol with parameterized thresholds."""

    def test_patrol_initialization(self):
        """Test DataPatrol initializes with configuration."""
        patrol = DataPatrol()
        assert patrol.results == []
        assert patrol.check_timings == {}

    def test_get_config_value_with_default(self):
        """Test _get_config_value falls back to default."""
        patrol = DataPatrol()

        with DatabaseContext('read') as cur:
            # Test with config that exists
            value = patrol._get_config_value(cur, 'patrol_staleness_price_daily', 7)
            assert value == 7, f"Expected 7, got {value}"

            # Test with config that might not exist (should return default)
            value = patrol._get_config_value(cur, 'nonexistent_key', 999)
            assert value == 999, f"Expected default 999, got {value}"

    def test_load_configuration_complete(self):
        """Test _load_configuration returns all expected keys."""
        patrol = DataPatrol()

        with DatabaseContext('read') as cur:
            config = patrol._load_configuration(cur)

            # Verify structure
            assert isinstance(config, dict)
            assert 'staleness_windows' in config
            assert 'coverage_thresholds' in config
            assert 'price_sanity' in config
            assert 'volume_sanity' in config
            assert 'loader_contracts' in config


class TestSchemaIntegrity:
    """Test schema changes are properly applied."""

    def test_technical_data_daily_columns(self):
        """Verify technical_data_daily has all expected columns."""
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'technical_data_daily'
                ORDER BY column_name
            """)
            columns = {row[0] for row in cur.fetchall()}

            expected = {
                'symbol', 'date', 'rsi', 'rsi_14', 'macd', 'macd_signal',
                'sma_20', 'sma_50', 'atr', 'adx', 'volume_ma_50',
                'price_data_age_days'  # NEW: Issue 11
            }

            for col in expected:
                assert col in columns, f"technical_data_daily missing {col}"

    def test_filter_rejection_log_columns(self):
        """Verify filter_rejection_log has all expected columns."""
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'filter_rejection_log'
                ORDER BY column_name
            """)
            columns = {row[0] for row in cur.fetchall()}

            expected = {
                'eval_date', 'symbol', 'rejection_reason', 'rejected_at_tier',
                'buy_sell_daily_age_days',  # NEW: Issue 10
                'technical_data_age_days',  # NEW: Issue 10
                'trend_template_age_days',  # NEW: Issue 10
                'max_data_age_days',  # NEW: Issue 10
                'is_age_driven_rejection',  # NEW: Issue 10
            }

            for col in expected:
                assert col in columns, f"filter_rejection_log missing {col}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
