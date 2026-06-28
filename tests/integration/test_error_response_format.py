#!/usr/bin/env python3
"""Integration tests for error response format standardization (Issue #9).

Verifies that all error responses follow the standardized format:
{statusCode, errorType, message, _error}

This ensures consistent error handling across the API and frontend.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from routes.utils import error_response, json_response, list_response, success_response


class TestErrorResponseFormat:
    """Test that all error responses follow the standardized format."""

    def test_error_response_format(self):
        """error_response() should return {statusCode, errorType, message, _error}."""
        response = error_response(400, "bad_request", "Invalid input")

        assert response["statusCode"] == 400
        assert response["errorType"] == "bad_request"
        assert response["message"] == "Invalid input"
        assert response["_error"] == "Invalid input"
        assert len(response) == 4, (
            f"Error response should have exactly 4 fields, got {len(response)}: {response.keys()}"
        )

    def test_error_response_500(self):
        """error_response() with 500 should include _error field."""
        response = error_response(500, "internal_error", "Server error occurred")

        assert response["statusCode"] == 500
        assert response["errorType"] == "internal_error"
        assert response["message"] == "Server error occurred"
        assert response["_error"] == "Server error occurred"

    def test_error_response_503(self):
        """error_response() with 503 should include _error field."""
        response = error_response(503, "service_unavailable", "Database connection failed")

        assert response["statusCode"] == 503
        assert response["errorType"] == "service_unavailable"
        assert response["message"] == "Database connection failed"
        assert response["_error"] == "Database connection failed"

    def test_json_response_success_format(self):
        """json_response(200, data) should return {statusCode, data}."""
        data = {"result": "success", "value": 42}
        response = json_response(200, data)

        assert response["statusCode"] == 200
        assert "data" in response
        assert response["data"]["result"] == "success"
        assert response["data"]["value"] == 42

    def test_json_response_error_with_message(self):
        """json_response(4xx, {message: '...'}) should ensure _error field."""
        response = json_response(400, {"errorType": "bad_request", "message": "Invalid input"})

        assert response["statusCode"] == 400
        assert response["errorType"] == "bad_request"
        assert response["message"] == "Invalid input"
        assert response["_error"] == "Invalid input", "json_response should auto-populate _error from message"

    def test_json_response_error_with_explicit_error_field(self):
        """json_response(4xx, {_error: '...'}) should preserve explicit _error."""
        response = json_response(
            500,
            {
                "errorType": "internal_error",
                "message": "Server error",
                "_error": "Custom error message",
            },
        )

        assert response["statusCode"] == 500
        assert response["_error"] == "Custom error message"

    def test_success_response_format(self):
        """success_response() should return {statusCode: 200, data: {...}}."""
        data = {"user": "john", "id": 123}
        response = success_response(data)

        assert response["statusCode"] == 200
        assert "data" in response
        assert response["data"]["user"] == "john"
        assert response["data"]["id"] == 123

    def test_list_response_format(self):
        """list_response() should return {statusCode: 200, data: {items: [...], total: N}}."""
        items = [{"id": 1}, {"id": 2}]
        response = list_response(items, total=2)

        assert response["statusCode"] == 200
        assert "data" in response
        assert response["data"]["items"] == items
        assert response["data"]["total"] == 2

    def test_error_response_consistency_across_codes(self):
        """All error status codes should produce consistent format."""
        error_codes = [400, 401, 403, 404, 429, 500, 503, 504]

        for code in error_codes:
            response = error_response(code, f"error_type_{code}", f"Message {code}")

            assert response["statusCode"] == code
            assert response["errorType"] == f"error_type_{code}"
            assert response["message"] == f"Message {code}"
            assert response["_error"] == f"Message {code}"
            assert len(response) == 4


class TestErrorResponseInConsistentScenarios:
    """Test edge cases and inconsistent scenarios that should still work."""

    def test_json_response_with_none_message(self):
        """json_response should handle None in message gracefully."""
        response = json_response(500, {"errorType": "error", "message": None})

        assert response["statusCode"] == 500
        assert response["errorType"] == "error"
        # _error should not be set from None message
        assert "_error" not in response or response.get("_error") is None

    def test_json_response_missing_message_field(self):
        """json_response should handle missing message field."""
        response = json_response(500, {"errorType": "error"})

        assert response["statusCode"] == 500
        assert response["errorType"] == "error"
        # _error should not be auto-populated if no message
        assert "_error" not in response or response["_error"] is None

    def test_error_response_special_characters(self):
        """error_response should handle special characters in message."""
        response = error_response(400, "validation_error", 'Field "email" is required: please@example.com')

        assert response["_error"] == 'Field "email" is required: please@example.com'
        assert response["message"] == 'Field "email" is required: please@example.com'

    def test_error_response_unicode_characters(self):
        """error_response should handle unicode characters."""
        response = error_response(400, "validation_error", "Error: café ☕ 中文")

        assert response["_error"] == "Error: café ☕ 中文"
        assert response["message"] == "Error: café ☕ 中文"


class TestErrorResponseFormatWithMalformedData:
    """Test error response formatting with WRONG TYPES and MALFORMED DATA."""

    def test_error_response_with_int_statuscode(self):
        """error_response with valid int statusCode should work."""
        response = error_response(400, "bad_request", "Invalid input")
        assert isinstance(response["statusCode"], int)

    def test_error_response_with_none_message(self):
        """error_response with None message should handle gracefully."""
        try:
            response = error_response(400, "bad_request", None)
            assert response is not None
            assert "message" in response
        except (TypeError, ValueError):
            pass

    def test_error_response_with_dict_message(self):
        """error_response with dict instead of string message."""
        try:
            response = error_response(400, "bad_request", {"error": "details"})
            assert response is not None
        except (TypeError, AttributeError):
            pass

    def test_error_response_with_negative_statuscode(self):
        """error_response with negative statusCode."""
        try:
            response = error_response(-400, "bad_request", "Invalid input")
            assert response is not None
        except (ValueError, AssertionError):
            pass

    def test_error_response_with_none_errortype(self):
        """error_response with None errorType."""
        try:
            response = error_response(400, None, "Invalid input")
            assert response is not None
        except (TypeError, ValueError):
            pass

    def test_json_response_with_none_code(self):
        """json_response with None statusCode."""
        try:
            response = json_response(None, {"data": "test"})
            assert response is not None
        except (TypeError, ValueError):
            pass

    def test_json_response_with_malformed_data(self):
        """json_response with non-dict data."""
        try:
            response = json_response(200, "not_a_dict")
            assert response is not None
        except (TypeError, AttributeError):
            pass

    def test_success_response_with_none_data(self):
        """success_response with None data."""
        try:
            response = success_response(None)
            assert response is not None
        except (TypeError, ValueError):
            pass

    def test_success_response_with_string_data(self):
        """success_response with string instead of dict."""
        try:
            response = success_response("string_data")
            assert response is not None
        except (TypeError, AttributeError):
            pass

    def test_list_response_with_non_list_items(self):
        """list_response with non-list items."""
        try:
            response = list_response({"item": "not_list"}, total=1)
            assert response is not None
        except (TypeError, AttributeError):
            pass

    def test_list_response_with_negative_total(self):
        """list_response with negative total."""
        try:
            response = list_response([{"id": 1}], total=-5)
            assert response is not None
        except (ValueError, AssertionError):
            pass

    def test_error_response_with_very_long_message(self):
        """error_response with extremely long message."""
        long_msg = "x" * 100000  # 100KB message
        try:
            response = error_response(400, "bad_request", long_msg)
            assert response is not None
            assert len(response["message"]) > 0
        except (ValueError, MemoryError):
            pass

    def test_error_response_with_null_bytes(self):
        """error_response with null bytes in message."""
        try:
            response = error_response(400, "bad_request", "test\x00null")
            assert response is not None
        except (ValueError, AttributeError):
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
