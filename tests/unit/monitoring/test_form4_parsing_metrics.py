#!/usr/bin/env python3
"""Tests for Form 4 parsing metrics tracking."""

import os
import unittest
from unittest.mock import MagicMock, patch

from utils.monitoring.form4_parsing_metrics import (
    put_form4_parsing_metric,
    track_form4_parsing_error,
    track_form4_parsing_success,
)


class TestForm4ParsingMetrics(unittest.TestCase):
    """Test CloudWatch metrics for Form 4 parsing monitoring."""

    @patch.dict(os.environ, {"LOCAL_MODE": "1"})
    def test_local_mode_disabled(self) -> None:
        """Metrics should not call CloudWatch in LOCAL_MODE."""
        # In LOCAL_MODE, metrics are logged to stderr, not sent to CloudWatch
        put_form4_parsing_metric("AAPL", "test_reason", is_failure=True)
        # Should not raise exception

    @patch.dict(os.environ, {"LOCAL_MODE": ""})
    @patch("boto3.client")
    def test_aws_mode_emits_metric(self, mock_boto_client: MagicMock) -> None:
        """Metrics should emit to CloudWatch in AWS mode."""
        mock_cloudwatch = MagicMock()
        mock_boto_client.return_value = mock_cloudwatch

        put_form4_parsing_metric("AAPL", "test_reason", is_failure=True)

        # Verify CloudWatch client was called
        mock_boto_client.assert_called_with("cloudwatch")
        mock_cloudwatch.put_metric_data.assert_called_once()

        # Check the metric structure
        call_args = mock_cloudwatch.put_metric_data.call_args
        assert call_args[1]["Namespace"] == "Algo/Form4Parsing"
        assert call_args[1]["MetricData"][0]["MetricName"] == "ParsingFailure"

    @patch.dict(os.environ, {"LOCAL_MODE": ""})
    @patch("boto3.client")
    def test_track_parsing_error(self, mock_boto_client: MagicMock) -> None:
        """track_form4_parsing_error should emit failure metric."""
        mock_cloudwatch = MagicMock()
        mock_boto_client.return_value = mock_cloudwatch

        track_form4_parsing_error("MSFT", "insider_name_extraction_failed", filing_type="plaintext")

        mock_cloudwatch.put_metric_data.assert_called_once()
        call_args = mock_cloudwatch.put_metric_data.call_args
        assert call_args[1]["MetricData"][0]["MetricName"] == "ParsingFailure"

    @patch.dict(os.environ, {"LOCAL_MODE": ""})
    @patch("boto3.client")
    def test_track_parsing_success(self, mock_boto_client: MagicMock) -> None:
        """track_form4_parsing_success should emit success metric."""
        mock_cloudwatch = MagicMock()
        mock_boto_client.return_value = mock_cloudwatch

        track_form4_parsing_success("GOOGL", filing_type="plaintext")

        mock_cloudwatch.put_metric_data.assert_called_once()
        call_args = mock_cloudwatch.put_metric_data.call_args
        assert call_args[1]["MetricData"][0]["MetricName"] == "ParsingSuccess"

    @patch.dict(os.environ, {"LOCAL_MODE": ""})
    @patch("boto3.client")
    def test_metric_failure_graceful(self, mock_boto_client: MagicMock) -> None:
        """Metric emission failure should not crash parsing."""
        mock_boto_client.side_effect = RuntimeError("AWS credentials not configured")

        # Should not raise exception, just log warning
        put_form4_parsing_metric("TSLA", "test_reason", is_failure=True)
        # Test passes if no exception raised


if __name__ == "__main__":
    unittest.main()
