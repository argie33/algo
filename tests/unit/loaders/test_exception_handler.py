#!/usr/bin/env python3
"""Tests for standardized loader exception handling."""

import socket
from unittest.mock import MagicMock

import pytest

from utils.loaders.exception_handler import (
    classify_exception,
    handle_connection_error,
    handle_exception,
    handle_invalid_data,
    handle_no_data_found,
    handle_rate_limit_error,
    handle_resource_not_found,
    handle_schema_mismatch,
    handle_timeout_error,
)


class TestExceptionClassification:
    """Test exception classification logic."""

    def test_classify_timeout_error(self):
        """TimeoutError should classify as transient_timeout."""
        error = TimeoutError("API timeout")
        assert classify_exception(error) == "transient_timeout"

    def test_classify_socket_timeout(self):
        """socket.timeout should classify as transient_timeout."""
        error = socket.timeout("Socket timeout")
        assert classify_exception(error) == "transient_timeout"

    def test_classify_connection_error(self):
        """ConnectionError should classify as transient_connection."""
        error = ConnectionError("Connection refused")
        assert classify_exception(error) == "transient_connection"

    def test_classify_key_error(self):
        """KeyError should classify as permanent_schema."""
        error = KeyError("missing_field")
        assert classify_exception(error) == "permanent_schema"

    def test_classify_value_error(self):
        """ValueError should classify as permanent_invalid_data."""
        error = ValueError("invalid number")
        assert classify_exception(error) == "permanent_invalid_data"

    def test_classify_unexpected_error(self):
        """Unknown error types should classify as unexpected."""
        error = RuntimeError("something weird")
        assert classify_exception(error) == "unexpected"


class TestTransientErrorHandlers:
    """Test handlers for transient (retryable) errors."""

    def test_handle_timeout_error(self):
        """Timeout error should return transient data_unavailable marker."""
        error = TimeoutError("API slow")
        result = handle_timeout_error("AAPL", error, "fetching data")

        assert result["symbol"] == "AAPL"
        assert result["data_unavailable"] is True
        assert result["reason"] == "timeout_retryable"
        assert result["reason_type"] == "temporary"

    def test_handle_connection_error(self):
        """Connection error should return transient data_unavailable marker."""
        error = ConnectionError("Network unreachable")
        result = handle_connection_error("MSFT", error, "connecting to API")

        assert result["symbol"] == "MSFT"
        assert result["data_unavailable"] is True
        assert result["reason"] == "connection_error"
        assert result["reason_type"] == "temporary"

    def test_handle_rate_limit_error(self):
        """Rate limit error should return transient data_unavailable marker."""
        error = Exception("429 Too Many Requests")
        result = handle_rate_limit_error("GOOGL", error, "API call")

        assert result["symbol"] == "GOOGL"
        assert result["data_unavailable"] is True
        assert result["reason"] == "rate_limit_or_service_unavailable"
        assert result["reason_type"] == "temporary"

    def test_handle_no_data_found(self):
        """No data found should return temporary marker."""
        result = handle_no_data_found("TSLA", "no recent filings")

        assert result["symbol"] == "TSLA"
        assert result["data_unavailable"] is True
        assert result["reason"] == "no_data_found"
        assert result["reason_type"] == "temporary"


class TestPermanentErrorHandlers:
    """Test handlers for permanent (non-retryable) errors."""

    def test_handle_schema_mismatch(self):
        """Schema mismatch should return permanent loader_failed marker."""
        error = KeyError("expected_field")
        result = handle_schema_mismatch("AAPL", error, "SEC API structure changed")

        assert result["symbol"] == "AAPL"
        assert result["data_unavailable"] is True
        assert result["reason"] == "api_schema_mismatch"
        assert result["reason_type"] == "loader_failed"

    def test_handle_invalid_data(self):
        """Invalid data should return permanent loader_failed marker."""
        error = ValueError("cannot convert to float")
        result = handle_invalid_data("MSFT", error, "parsing share count")

        assert result["symbol"] == "MSFT"
        assert result["data_unavailable"] is True
        assert result["reason"] == "data_invalid"
        assert result["reason_type"] == "loader_failed"

    def test_handle_resource_not_found(self):
        """Resource not found should return permanent loader_failed marker."""
        result = handle_resource_not_found("GOOGL", "CIK", "ticker not in SEC EDGAR")

        assert result["symbol"] == "GOOGL"
        assert result["data_unavailable"] is True
        assert result["reason"] == "cik_not_found"
        assert result["reason_type"] == "loader_failed"


class TestExceptionRouting:
    """Test handle_exception routing to appropriate handler."""

    def test_route_timeout_error(self):
        """TimeoutError should route to timeout handler."""
        error = TimeoutError("slow")
        result = handle_exception("AAPL", error, "fetching data")

        assert result["reason"] == "timeout_retryable"
        assert result["reason_type"] == "temporary"

    def test_route_connection_error(self):
        """ConnectionError should route to connection handler."""
        error = ConnectionError("refused")
        result = handle_exception("MSFT", error, "connecting")

        assert result["reason"] == "connection_error"
        assert result["reason_type"] == "temporary"

    def test_route_key_error(self):
        """KeyError should route to schema handler."""
        error = KeyError("missing")
        result = handle_exception("GOOGL", error, "parsing API")

        assert result["reason"] == "api_schema_mismatch"
        assert result["reason_type"] == "loader_failed"

    def test_route_value_error(self):
        """ValueError should route to invalid data handler."""
        error = ValueError("bad value")
        result = handle_exception("TSLA", error, "converting data")

        assert result["reason"] == "data_invalid"
        assert result["reason_type"] == "loader_failed"

    def test_unexpected_error_raises(self):
        """Unexpected error types should raise/propagate."""
        error = RuntimeError("something weird")

        with pytest.raises(RuntimeError, match="something weird"):
            handle_exception("AAPL", error, "")


class TestErrorMarkerStructure:
    """Test that all error markers have consistent structure."""

    def test_marker_has_required_fields(self):
        """All markers should have symbol, data_unavailable, reason, reason_type."""
        markers = [
            handle_timeout_error("AAPL", TimeoutError()),
            handle_connection_error("MSFT", ConnectionError()),
            handle_schema_mismatch("GOOGL", KeyError()),
            handle_invalid_data("TSLA", ValueError()),
            handle_no_data_found("NVDA"),
            handle_resource_not_found("META", "CIK"),
        ]

        for marker in markers:
            assert "symbol" in marker
            assert "data_unavailable" in marker
            assert "reason" in marker
            assert "reason_type" in marker
            assert marker["data_unavailable"] is True

    def test_reason_types_are_valid(self):
        """Reason types should be one of: temporary, loader_failed."""
        transient_markers = [
            handle_timeout_error("AAPL", TimeoutError()),
            handle_connection_error("MSFT", ConnectionError()),
            handle_rate_limit_error("GOOGL", Exception()),
            handle_no_data_found("TSLA"),
        ]

        for marker in transient_markers:
            assert marker["reason_type"] == "temporary"

        permanent_markers = [
            handle_schema_mismatch("AAPL", KeyError()),
            handle_invalid_data("MSFT", ValueError()),
            handle_resource_not_found("GOOGL", "CIK"),
        ]

        for marker in permanent_markers:
            assert marker["reason_type"] == "loader_failed"
