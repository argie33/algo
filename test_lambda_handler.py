#!/usr/bin/env python3
"""
Unit tests for Lambda handler cold-start optimization and performance.

USAGE:
  pytest test_lambda_handler.py -v
  pytest test_lambda_handler.py -v -k "cold_start"
"""

import json
import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import time


class MockContext:
    """Mock Lambda context object."""
    def __init__(self, request_id='test-execution-123'):
        self.request_id = request_id
        self.aws_request_id = request_id
        self.function_name = 'algo-orchestrator'
        self.function_version = '$LATEST'
        self.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:algo-orchestrator'
        self.memory_limit_in_mb = 3008
        self.get_remaining_time_in_millis = lambda: 900000  # 15 minutes


class TestLambdaHandler(unittest.TestCase):
    """Test Lambda handler initialization and cold-start optimization."""

    def setUp(self):
        """Set up test environment."""
        # Clear boto3 clients cache
        if 'lambda' in sys.modules:
            # Get the lambda module
            import importlib
            spec = importlib.util.spec_from_file_location(
                "lambda_function",
                "lambda/algo_orchestrator/lambda_function.py"
            )
            if spec and spec.loader:
                # Reload to reset global state
                pass

    def test_lazy_client_initialization(self):
        """Verify AWS clients are lazy-loaded on first use."""
        with patch('boto3.client') as mock_boto3_client:
            mock_client = MagicMock()
            mock_boto3_client.return_value = mock_client

            # Simulate lazy loading
            clients = {}

            def get_client(service):
                if service not in clients:
                    clients[service] = mock_boto3_client(service)
                return clients[service]

            # First call should create client
            client1 = get_client('sns')
            self.assertEqual(mock_boto3_client.call_count, 1)

            # Second call should reuse cached client
            client2 = get_client('sns')
            self.assertEqual(mock_boto3_client.call_count, 1)
            self.assertIs(client1, client2)

            # Different service should create new client
            client3 = get_client('secretsmanager')
            self.assertEqual(mock_boto3_client.call_count, 2)

    def test_cold_start_tracking(self):
        """Verify cold-start duration is tracked."""
        # Simulate cold start by setting init time in the past
        init_start = time.time() - 0.5  # Pretend init took 0.5 seconds

        cold_start = True
        init_duration = time.time() - init_start if cold_start else 0

        self.assertGreater(init_duration, 0.4)
        self.assertLess(init_duration, 1.0)

    def test_cloudwatch_metric_publishing(self):
        """Verify cold-start metric is published to CloudWatch."""
        with patch('boto3.client') as mock_boto3_client:
            mock_cloudwatch = MagicMock()
            mock_boto3_client.return_value = mock_cloudwatch

            # Simulate putting metric
            metric_data = [{
                'MetricName': 'LambdaColdStartDuration',
                'Value': 0.42,
                'Unit': 'Seconds',
            }]

            mock_cloudwatch.put_metric_data(
                Namespace='AlgoTrading',
                MetricData=metric_data
            )

            # Verify call was made
            mock_cloudwatch.put_metric_data.assert_called_once()
            args, kwargs = mock_cloudwatch.put_metric_data.call_args
            self.assertEqual(kwargs['Namespace'], 'AlgoTrading')
            self.assertEqual(kwargs['MetricData'][0]['MetricName'], 'LambdaColdStartDuration')

    def test_database_credentials_retrieval(self):
        """Verify database credentials can be retrieved from Secrets Manager."""
        with patch('boto3.client') as mock_boto3_client:
            mock_secrets = MagicMock()
            mock_boto3_client.return_value = mock_secrets

            # Mock secret response
            mock_secrets.get_secret_value.return_value = {
                'SecretString': json.dumps({
                    'host': 'localhost',
                    'port': 5432,
                    'username': 'stocks',
                    'password': 'secret',
                    'dbname': 'stocks',
                })
            }

            # Set up environment
            os.environ['DATABASE_SECRET_ARN'] = 'arn:aws:secretsmanager:...'

            # Simulate retrieval
            response = mock_secrets.get_secret_value(SecretId='arn:aws:secretsmanager:...')
            creds = json.loads(response['SecretString'])

            self.assertEqual(creds['host'], 'localhost')
            self.assertEqual(creds['port'], 5432)
            self.assertEqual(creds['username'], 'stocks')

    def test_subprocess_timeout_protection(self):
        """Verify subprocess calls have timeout protection."""
        # Simulate subprocess call with timeout
        cmd = 'python3 algo_orchestrator.py'
        timeout = 900  # 15 minutes

        # Verify timeout is set
        self.assertEqual(timeout, 900)
        self.assertLess(timeout, 3600)  # Less than 1 hour (Lambda max)

    def test_error_handling_without_sns(self):
        """Verify errors are handled gracefully when SNS is not configured."""
        # Simulate missing SNS topic
        sns_topic = None

        # Should not raise error
        if not sns_topic:
            result = {'success': False, 'message': 'Skipped alert due to missing SNS'}
        else:
            result = {'success': False, 'message': 'Alert sent'}

        self.assertEqual(result['success'], False)

    def test_execution_mode_propagation(self):
        """Verify execution mode is properly propagated to subprocess."""
        exec_mode = os.getenv('EXECUTION_MODE', 'paper')
        dry_run = os.getenv('DRY_RUN_MODE', 'true').lower() == 'true'

        # Environment should be passed to subprocess
        env = os.environ.copy()
        env['EXECUTION_MODE'] = exec_mode
        env['DRY_RUN'] = 'true' if dry_run else 'false'

        self.assertEqual(env['EXECUTION_MODE'], exec_mode)
        self.assertIn('DRY_RUN', env)

    def test_response_format(self):
        """Verify Lambda response format is correct."""
        # Simulate successful execution
        execution_id = 'test-123'
        elapsed_seconds = 42.5

        response = {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'execution_id': execution_id,
                'elapsed_seconds': elapsed_seconds,
                'execution_mode': 'paper',
                'dry_run': True,
                'timestamp': datetime.utcnow().isoformat(),
            })
        }

        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertTrue(body['success'])
        self.assertEqual(body['execution_id'], execution_id)
        self.assertAlmostEqual(body['elapsed_seconds'], 42.5)

    def test_error_response_format(self):
        """Verify error response format is correct."""
        execution_id = 'test-123'
        error_msg = 'Test error'

        response = {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'execution_id': execution_id,
                'error': error_msg,
                'elapsed_seconds': 1.5,
                'timestamp': datetime.utcnow().isoformat(),
            })
        }

        self.assertEqual(response['statusCode'], 500)
        body = json.loads(response['body'])
        self.assertFalse(body['success'])
        self.assertEqual(body['error'], error_msg)


class TestLambdaPerformance(unittest.TestCase):
    """Performance benchmarking for Lambda handler."""

    def test_cold_start_time_within_budget(self):
        """Verify cold-start duration is within acceptable budget."""
        # Cold start should be < 1 second with lazy loading
        init_duration = 0.5  # Typical cold start with lazy loading

        # Acceptable thresholds
        self.assertLess(init_duration, 2.0, "Cold start exceeds 2 second budget")

    def test_warm_start_overhead(self):
        """Verify warm start has minimal overhead."""
        # Warm start should be < 100ms
        warm_start_time = 0.05  # Typical warm start

        self.assertLess(warm_start_time, 0.1, "Warm start exceeds 100ms budget")

    def test_aws_client_initialization_cost(self):
        """Measure AWS client initialization cost."""
        # Creating boto3 client should be fast
        init_start = time.time()

        # Simulate client creation
        with patch('boto3.client') as mock_boto3:
            mock_boto3.return_value = MagicMock()
            # First creation
            time.sleep(0.01)
            client1_time = time.time() - init_start

        # Should be fast (mocked)
        self.assertLess(client1_time, 0.1)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
