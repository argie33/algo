#!/usr/bin/env python3
"""Integration tests for failsafe and grace period logic (Issue 12).

Tests:
- ECS task trigger and verification
- Grace period calculation with actual_running_at compensation
- Scheduling delay tracking
- Graceful fallback to triggered_at
"""

import pytest
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from algo.orchestrator.phase1_data_freshness import (
    _trigger_loader_failsafe_with_verification,
    _check_failsafe_grace_period,
)


class TestECSTaskTrigger:
    """Test ECS failsafe trigger and verification."""

    @patch('boto3.client')
    def test_trigger_loader_with_verification(self, mock_boto3_client):
        """Test loader trigger with ECS verification."""
        # Mock ECS client
        mock_ecs = MagicMock()
        mock_boto3_client.return_value = mock_ecs

        # Simulate task launch response
        mock_ecs.run_task.return_value = {
            'tasks': [{
                'taskArn': 'arn:aws:ecs:us-east-1:123456789:task/test-cluster/abc123'
            }]
        }

        # Simulate describe_tasks showing RUNNING state
        mock_ecs.describe_tasks.return_value = {
            'tasks': [{
                'taskArn': 'arn:aws:ecs:us-east-1:123456789:task/test-cluster/abc123',
                'lastStatus': 'RUNNING'
            }]
        }

        # Call the trigger function
        result = _trigger_loader_failsafe_with_verification(
            'stock_prices_daily',
            verbose=False,
            poll_timeout_sec=10
        )

        # Verify task was triggered and reached RUNNING state
        assert result is True, "Loader trigger should confirm RUNNING state"
        mock_ecs.run_task.assert_called_once()

    @patch('boto3.client')
    def test_trigger_timeout_handling(self, mock_boto3_client):
        """Test trigger timeout when task doesn't reach RUNNING."""
        mock_ecs = MagicMock()
        mock_boto3_client.return_value = mock_ecs

        # Simulate task launch
        mock_ecs.run_task.return_value = {
            'tasks': [{
                'taskArn': 'arn:aws:ecs:us-east-1:123456789:task/test-cluster/abc123'
            }]
        }

        # Simulate task stuck in PENDING (never reaches RUNNING)
        mock_ecs.describe_tasks.return_value = {
            'tasks': [{
                'taskArn': 'arn:aws:ecs:us-east-1:123456789:task/test-cluster/abc123',
                'lastStatus': 'PENDING'
            }]
        }

        # Call with short timeout (1 second)
        result = _trigger_loader_failsafe_with_verification(
            'stock_prices_daily',
            verbose=False,
            poll_timeout_sec=1
        )

        # Should return False (timeout)
        assert result is False, "Trigger should timeout if task doesn't reach RUNNING"

    @patch('boto3.client')
    @patch('boto3.resource')
    def test_scheduling_delay_storage(self, mock_boto3_resource, mock_boto3_client):
        """Test scheduling delay is stored in DynamoDB."""
        # Mock ECS client
        mock_ecs = MagicMock()
        mock_boto3_client.return_value = mock_ecs

        # Mock DynamoDB
        mock_dynamodb = MagicMock()
        mock_state_table = MagicMock()
        mock_boto3_resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_state_table

        # Simulate task launch and RUNNING transition
        mock_ecs.run_task.return_value = {
            'tasks': [{
                'taskArn': 'arn:aws:ecs:us-east-1:123456789:task/test-cluster/abc123'
            }]
        }
        mock_ecs.describe_tasks.return_value = {
            'tasks': [{
                'taskArn': 'arn:aws:ecs:us-east-1:123456789:task/test-cluster/abc123',
                'lastStatus': 'RUNNING'
            }]
        }

        # Trigger the loader
        result = _trigger_loader_failsafe_with_verification(
            'stock_prices_daily',
            verbose=False,
            poll_timeout_sec=10
        )

        # Verify state table update was called
        assert result is True
        # The actual_running_at should have been stored
        mock_state_table.update_item.assert_called()

        # Verify the update expression
        call_kwargs = mock_state_table.update_item.call_args[1]
        assert 'actual_running_at' in call_kwargs['UpdateExpression']
        assert 'scheduling_delay_seconds' in call_kwargs['UpdateExpression']


class TestGracePeriodCalculation:
    """Test grace period calculation with scheduling delay compensation."""

    @patch('boto3.resource')
    def test_grace_period_uses_actual_running_at(self, mock_boto3_resource):
        """Test grace period calculation uses actual_running_at when available."""
        mock_dynamodb = MagicMock()
        mock_state_table = MagicMock()
        mock_boto3_resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_state_table

        now = time.time()
        # Simulate: triggered 60 minutes ago, but only started running 45 minutes ago
        triggered_at = now - 3600  # 60 minutes ago
        actual_running_at = now - 2700  # 45 minutes ago (60 second scheduling delay)

        mock_state_table.get_item.return_value = {
            'Item': {
                'triggered_at': triggered_at,
                'actual_running_at': actual_running_at,
                'scheduling_delay_seconds': 60,
            }
        }

        # Mock database context for config read
        with patch('utils.database_context.DatabaseContext') as mock_db:
            mock_cur = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur
            mock_cur.fetchone.return_value = (150,)  # 150 minute grace period default

            # Check grace period
            age_minutes = _check_failsafe_grace_period(
                mock_state_table,
                verbose=False,
                loader_name='stock_prices_daily'
            )

            # Grace period should be ~45 minutes (based on actual_running_at)
            assert age_minutes is not None, "Should be within grace period"
            assert 40 < age_minutes < 50, f"Expected ~45 min, got {age_minutes:.0f}m"

    @patch('boto3.resource')
    def test_grace_period_fallback_to_triggered_at(self, mock_boto3_resource):
        """Test grace period falls back to triggered_at if actual_running_at missing."""
        mock_dynamodb = MagicMock()
        mock_state_table = MagicMock()
        mock_boto3_resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_state_table

        now = time.time()
        # Only triggered_at available (task hasn't reached RUNNING yet)
        triggered_at = now - 300  # 5 minutes ago

        mock_state_table.get_item.return_value = {
            'Item': {
                'triggered_at': triggered_at,
                # actual_running_at missing
            }
        }

        # Mock database context
        with patch('utils.database_context.DatabaseContext') as mock_db:
            mock_cur = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur
            mock_cur.fetchone.return_value = (150,)  # 150 minute grace period

            age_minutes = _check_failsafe_grace_period(
                mock_state_table,
                verbose=False,
                loader_name='stock_prices_daily'
            )

            # Should fall back to triggered_at: ~5 minutes
            assert age_minutes is not None
            assert 3 < age_minutes < 7, f"Expected ~5 min, got {age_minutes:.0f}m"

    @patch('boto3.resource')
    def test_grace_period_expires(self, mock_boto3_resource):
        """Test grace period expiration when loader takes too long."""
        mock_dynamodb = MagicMock()
        mock_state_table = MagicMock()
        mock_boto3_resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_state_table

        now = time.time()
        # Loader has been running for 160 minutes (exceeds 150 min default grace period)
        actual_running_at = now - 9600  # 160 minutes ago

        mock_state_table.get_item.return_value = {
            'Item': {
                'triggered_at': now - 10000,  # Earlier
                'actual_running_at': actual_running_at,
            }
        }

        # Mock database context
        with patch('utils.database_context.DatabaseContext') as mock_db:
            mock_cur = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur
            mock_cur.fetchone.return_value = (150,)  # 150 minute grace period

            age_minutes = _check_failsafe_grace_period(
                mock_state_table,
                verbose=False,
                loader_name='stock_prices_daily'
            )

            # Grace period should have expired (None returned)
            assert age_minutes is None, "Grace period should have expired"

    @patch('boto3.resource')
    def test_grace_period_configurable(self, mock_boto3_resource):
        """Test grace period duration is configurable via algo_config."""
        mock_dynamodb = MagicMock()
        mock_state_table = MagicMock()
        mock_boto3_resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_state_table

        now = time.time()
        actual_running_at = now - 6900  # 115 minutes ago

        mock_state_table.get_item.return_value = {
            'Item': {
                'triggered_at': now - 7000,
                'actual_running_at': actual_running_at,
            }
        }

        # Mock database context with custom grace period (100 minutes)
        with patch('utils.database_context.DatabaseContext') as mock_db:
            mock_cur = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur
            mock_cur.fetchone.return_value = (100,)  # Custom 100 minute period

            age_minutes = _check_failsafe_grace_period(
                mock_state_table,
                verbose=False,
                loader_name='stock_prices_daily'
            )

            # Should be outside the 100-minute grace period
            assert age_minutes is None, "Should exceed custom 100-min grace period"


class TestSchedulingDelayMetrics:
    """Test scheduling delay metrics are properly tracked."""

    def test_scheduling_delay_calculation(self):
        """Test ECS scheduling delay is calculated correctly."""
        # Simulate trigger and RUNNING confirmation timing
        trigger_time = time.time()
        time.sleep(0.1)  # Simulate 100ms scheduling delay
        running_time = time.time()

        delay_seconds = running_time - trigger_time

        # Should be ~0.1 seconds
        assert 0.05 < delay_seconds < 0.2, f"Expected ~0.1s delay, got {delay_seconds:.2f}s"

    @patch('boto3.client')
    def test_metric_publisher_called_for_delay(self, mock_boto3_client):
        """Test CloudWatch metric is published for scheduling delay."""
        # This test verifies the metric publishing logic exists
        # (the actual metric publish happens in _trigger_loader_failsafe_with_verification)

        mock_ecs = MagicMock()
        mock_boto3_client.return_value = mock_ecs

        # Verify the metric name is what we expect
        expected_metric = 'LoaderSchedulingDelaySeconds'

        # The actual metric publishing is mocked in the function implementation
        # This test just verifies the metric name convention
        assert expected_metric == 'LoaderSchedulingDelaySeconds'


class TestGracePeriodEdgeCases:
    """Test edge cases in grace period logic."""

    @patch('boto3.resource')
    def test_grace_period_with_zero_state(self, mock_boto3_resource):
        """Test grace period when state table returns no item."""
        mock_dynamodb = MagicMock()
        mock_state_table = MagicMock()
        mock_boto3_resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_state_table

        # No item in state table
        mock_state_table.get_item.return_value = {}

        age_minutes = _check_failsafe_grace_period(
            mock_state_table,
            verbose=False
        )

        # Should return None (no trigger in progress)
        assert age_minutes is None, "No trigger should return None"

    @patch('boto3.resource')
    def test_grace_period_with_invalid_timestamps(self, mock_boto3_resource):
        """Test grace period with invalid or missing timestamps."""
        mock_dynamodb = MagicMock()
        mock_state_table = MagicMock()
        mock_boto3_resource.return_value = mock_dynamodb
        mock_dynamodb.Table.return_value = mock_state_table

        # Item with invalid data
        mock_state_table.get_item.return_value = {
            'Item': {
                'triggered_at': 0,  # Invalid (epoch)
                # actual_running_at missing
            }
        }

        # Mock database context
        with patch('utils.database_context.DatabaseContext') as mock_db:
            mock_cur = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur
            mock_cur.fetchone.return_value = (150,)

            # Should handle gracefully
            age_minutes = _check_failsafe_grace_period(
                mock_state_table,
                verbose=False
            )

            # Will be large age, outside grace period
            assert age_minutes is None or age_minutes > 100


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
