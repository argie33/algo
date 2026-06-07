#!/usr/bin/env python3
"""
Verification test for Issue #5: Task Termination Failures.

Tests that hung analytics loader tasks are properly terminated and verified
to prevent RDS connection pool exhaustion.
"""

import unittest
import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock, call
import os
import sys

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algo.algo_orchestrator import Orchestrator


class TestIssue5TaskTermination(unittest.TestCase):
    """Test Issue #5: Task termination verification to prevent hung tasks."""

    def setUp(self):
        """Set up test orchestrator."""
        with patch('utils.dynamodb_lock_manager.DynamoDBLockManager'):
            with patch('algo.algo_orchestrator.DatabaseContext'):
                self.orch = Orchestrator(dry_run=True, verbose=False)

    def test_verify_task_stopped_success(self):
        """Test successful task termination verification."""
        mock_ecs = MagicMock()
        cluster = 'test-cluster'
        task_arn = 'arn:aws:ecs:us-east-1:123456789:task/test-cluster/abc123'
        loader_name = 'company_profile'

        # Simulate ECS response with task in STOPPED state
        mock_ecs.describe_tasks.return_value = {
            'tasks': [{
                'taskArn': task_arn,
                'lastStatus': 'STOPPED',
                'desiredStatus': 'STOPPED'
            }]
        }

        result = self.orch._verify_task_stopped(
            mock_ecs, cluster, task_arn, loader_name, max_retries=3, retry_delay_sec=0.1
        )

        self.assertTrue(result, "Should return True when task is STOPPED")
        # Should only call describe_tasks once since it's already stopped
        self.assertEqual(mock_ecs.describe_tasks.call_count, 1)

    def test_verify_task_stopped_with_retry(self):
        """Test task termination with retries waiting for status transition."""
        mock_ecs = MagicMock()
        cluster = 'test-cluster'
        task_arn = 'arn:aws:ecs:us-east-1:123456789:task/test-cluster/abc123'
        loader_name = 'analyst_sentiment'

        # Simulate ECS responses: first RUNNING, then DEPROVISIONING, then STOPPED
        mock_ecs.describe_tasks.side_effect = [
            {
                'tasks': [{
                    'taskArn': task_arn,
                    'lastStatus': 'RUNNING',
                    'desiredStatus': 'STOPPED'
                }]
            },
            {
                'tasks': [{
                    'taskArn': task_arn,
                    'lastStatus': 'DEPROVISIONING',
                    'desiredStatus': 'STOPPED'
                }]
            },
            {
                'tasks': [{
                    'taskArn': task_arn,
                    'lastStatus': 'STOPPED',
                    'desiredStatus': 'STOPPED'
                }]
            }
        ]

        result = self.orch._verify_task_stopped(
            mock_ecs, cluster, task_arn, loader_name, max_retries=3, retry_delay_sec=0.01
        )

        self.assertTrue(result, "Should return True after task transitions to STOPPED")
        # Should call describe_tasks 3 times
        self.assertEqual(mock_ecs.describe_tasks.call_count, 3)

    def test_verify_task_stopped_failure_timeout(self):
        """Test task termination failure when task never stops."""
        mock_ecs = MagicMock()
        cluster = 'test-cluster'
        task_arn = 'arn:aws:ecs:us-east-1:123456789:task/test-cluster/abc123'
        loader_name = 'stability_metrics'

        # Simulate ECS always returning RUNNING status (task never stops)
        mock_ecs.describe_tasks.return_value = {
            'tasks': [{
                'taskArn': task_arn,
                'lastStatus': 'RUNNING',
                'desiredStatus': 'RUNNING'
            }]
        }

        result = self.orch._verify_task_stopped(
            mock_ecs, cluster, task_arn, loader_name, max_retries=3, retry_delay_sec=0.01
        )

        self.assertFalse(result, "Should return False when task never stops")
        # Should retry max_retries times
        self.assertEqual(mock_ecs.describe_tasks.call_count, 3)

    def test_verify_task_stopped_not_found(self):
        """Test task termination verification when task not found."""
        mock_ecs = MagicMock()
        cluster = 'test-cluster'
        task_arn = 'arn:aws:ecs:us-east-1:123456789:task/test-cluster/abc123'
        loader_name = 'value_metrics'

        # Simulate ECS returning empty task list
        mock_ecs.describe_tasks.return_value = {
            'tasks': []
        }

        result = self.orch._verify_task_stopped(
            mock_ecs, cluster, task_arn, loader_name, max_retries=3, retry_delay_sec=0.01
        )

        self.assertFalse(result, "Should return False when task not found")
        # Should retry max_retries times
        self.assertEqual(mock_ecs.describe_tasks.call_count, 3)

    def test_verify_task_stopped_exception_handling(self):
        """Test task termination verification with API exceptions."""
        mock_ecs = MagicMock()
        cluster = 'test-cluster'
        task_arn = 'arn:aws:ecs:us-east-1:123456789:task/test-cluster/abc123'
        loader_name = 'company_profile'

        # Simulate exceptions on first 2 attempts, then success
        mock_ecs.describe_tasks.side_effect = [
            Exception("API rate limit"),
            Exception("API timeout"),
            {
                'tasks': [{
                    'taskArn': task_arn,
                    'lastStatus': 'STOPPED',
                    'desiredStatus': 'STOPPED'
                }]
            }
        ]

        result = self.orch._verify_task_stopped(
            mock_ecs, cluster, task_arn, loader_name, max_retries=3, retry_delay_sec=0.01
        )

        self.assertTrue(result, "Should eventually succeed after exceptions")
        # Should retry 3 times
        self.assertEqual(mock_ecs.describe_tasks.call_count, 3)



if __name__ == '__main__':
    unittest.main()
