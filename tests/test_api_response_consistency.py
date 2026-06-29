#!/usr/bin/env python3
"""Test Issue 1.1 FIX: Verify consistent API response handling.

Tests that _unwrap_api_response() correctly handles different response formats
and that all data fetchers can work with the unwrapped responses.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dashboard.api_data_layer import _unwrap_api_response


def test_unwrap_single_object_response():
    """Test unwrapping json_response format."""
    response = {
        "statusCode": 200,
        "data": {
            "run_id": "test-123",
            "portfolio": {"total_value": 100000, "daily_return_pct": 1.5},
        },
    }
    unwrapped = _unwrap_api_response(response)
    assert unwrapped["statusCode"] == 200, "statusCode should be preserved for error detection"
    assert "data" not in unwrapped, "data wrapper should be extracted"
    assert unwrapped["portfolio"]["total_value"] == 100000
    assert unwrapped["run_id"] == "test-123"
    print("[OK] Single object response unwrapping works")


def test_unwrap_list_response():
    """Test unwrapping list_response format."""
    response = {
        "statusCode": 200,
        "items": [{"symbol": "AAPL", "price": 150}, {"symbol": "MSFT", "price": 320}],
        "total": 2,
        "pagination": {"limit": 10, "offset": 0},
    }
    unwrapped = _unwrap_api_response(response)
    assert unwrapped["statusCode"] == 200, "statusCode should be preserved for error detection"
    assert "items" in unwrapped, "items field should remain"
    assert len(unwrapped["items"]) == 2
    print("[OK] List response unwrapping works")


def test_unwrap_direct_fields_response():
    """Test unwrapping response with direct fields."""
    response = {
        "statusCode": 200,
        "n": 5,
        "total": 10,
        "buy_sigs": [{"symbol": "ABC"}],
        "grades": {"a": 2, "b": 3},
    }
    unwrapped = _unwrap_api_response(response)
    assert unwrapped["statusCode"] == 200, "statusCode should be preserved for error detection"
    assert unwrapped["n"] == 5, "Direct fields should remain"
    assert unwrapped["total"] == 10
    assert len(unwrapped["buy_sigs"]) == 1
    print("[OK] Direct fields response unwrapping works")


def test_unwrap_preserves_metadata():
    """Test that data_freshness and other metadata is preserved."""
    response = {
        "statusCode": 200,
        "items": [{"id": 1}],
        "data_freshness": {"is_stale": False, "data_age_days": 0},
    }
    unwrapped = _unwrap_api_response(response)
    assert unwrapped["statusCode"] == 200, "statusCode should be preserved"
    assert "items" in unwrapped
    assert "data_freshness" in unwrapped
    print("[OK] Metadata preservation works")


def test_unwrap_empty_response():
    """Test unwrapping empty response."""
    response = {"statusCode": 200}
    unwrapped = _unwrap_api_response(response)
    assert unwrapped == {"statusCode": 200}, "statusCode should be preserved"
    print("[OK] Empty response unwrapping works")


def test_data_fetcher_error_detection():
    """Test that callers can distinguish errors from successful responses via statusCode."""
    # Successful response
    response = {"statusCode": 200, "data": {"key": "value"}}
    unwrapped = _unwrap_api_response(response)
    assert unwrapped["statusCode"] == 200, "Success status should be detectable"
    assert unwrapped.get("key") == "value", "Payload should be available"

    # Error response with error details in data field
    response = {"statusCode": 400, "error": "invalid_param", "details": "x is required"}
    unwrapped = _unwrap_api_response(response)
    assert unwrapped["statusCode"] == 400, "Error status should be detectable"
    assert unwrapped.get("error") == "invalid_param", "Error details should be preserved"
    assert unwrapped.get("details") == "x is required", "Error details should be preserved"

    print("[OK] Error detection via statusCode works")


class TestUnwrapWithMalformedData:
    """Test that _unwrap_api_response handles corrupted data gracefully."""

    def test_statuscode_as_string(self):
        """If statusCode is string instead of int, should still preserve it."""
        response = {"statusCode": "200"}  # String instead of int
        unwrapped = _unwrap_api_response(response)
        assert unwrapped["statusCode"] == "200", "statusCode should be preserved as-is"

    def test_data_as_string_instead_of_dict(self):
        """If data is string instead of dict, update() should handle gracefully."""
        response = {"statusCode": 200, "data": "corrupted_string"}
        # Should not crash - just return what's passed
        result = _unwrap_api_response(response)
        assert result is not None

    def test_items_as_string_instead_of_list(self):
        """If items is string instead of list, len() downstream might fail."""
        response = {"statusCode": 200, "items": "not_a_list"}
        unwrapped = _unwrap_api_response(response)
        assert unwrapped["items"] == "not_a_list", "Should preserve malformed items"

    def test_nested_dict_is_string(self):
        """If nested dict is string, accessing its fields crashes."""
        response = {
            "statusCode": 200,
            "data": {"portfolio": "not_a_dict"}
        }
        unwrapped = _unwrap_api_response(response)
        # This preserves the malformed structure
        # Downstream code should handle or this should be caught earlier
        assert unwrapped["portfolio"] == "not_a_dict"

    def test_pagination_missing(self):
        """If pagination is missing from response, should handle gracefully."""
        response = {
            "statusCode": 200,
            "items": [{"id": 1}],
            # Missing "pagination"
        }
        unwrapped = _unwrap_api_response(response)
        assert "pagination" not in unwrapped or unwrapped.get("pagination") is None

    def test_response_not_dict(self):
        """If response itself is not a dict, should raise RuntimeError (fail-fast on corruption)."""
        response = "not_a_dict"  # type: ignore
        with pytest.raises(RuntimeError, match="API response is not a dict"):
            _unwrap_api_response(response)  # type: ignore

    def test_response_is_none(self):
        """If response is None, should raise RuntimeError (fail-fast on corruption)."""
        response = None  # type: ignore
        with pytest.raises(RuntimeError, match="API response is not a dict"):
            _unwrap_api_response(response)  # type: ignore


if __name__ == "__main__":
    try:
        test_unwrap_single_object_response()
        test_unwrap_list_response()
        test_unwrap_direct_fields_response()
        test_unwrap_preserves_metadata()
        test_unwrap_empty_response()
        test_data_fetcher_error_detection()

        # Test malformed data scenarios
        malformed_tests = TestUnwrapWithMalformedData()
        malformed_tests.test_statuscode_as_string()
        malformed_tests.test_data_as_string_instead_of_dict()
        malformed_tests.test_items_as_string_instead_of_list()
        malformed_tests.test_nested_dict_is_string()
        malformed_tests.test_pagination_missing()
        malformed_tests.test_response_not_dict()
        malformed_tests.test_response_is_none()

        print("\n[PASS] All tests passed! Issue 1.1 response consistency fix verified.")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
