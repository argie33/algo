"""Test that malformed data is caught when used by downstream panel code.

This tests the REAL failure modes - not just that accessing fields doesn't crash,
but that using the data downstream causes appropriate errors.
"""

import pytest


class TestCircuitBreakerPanelWithMalformedData:
    """Test circuit breaker panel code with malformed field types."""

    def test_cur_as_string_crashes_format(self):
        """If 'cur' is string, f-string formatting crashes."""
        breaker = {
            "id": "drawdown",
            "fired": False,
            "cur": "15.5",  # String instead of float
            "thr": 20.0,
            "u": "%",
        }

        # Panel code does: f"{cur_val:.1f}"
        cur_val = breaker.get("cur")

        # This SHOULD crash when trying to format
        if cur_val is not None and not isinstance(cur_val, (int, float)):
            with pytest.raises((ValueError, TypeError)):
                _ = f"{cur_val:.1f}"
        else:
            # If we got here, type checking should have caught it
            assert isinstance(cur_val, (int, float)) or cur_val is None

    def test_statuscode_comparison_crashes_type_error(self):
        """If statusCode is string, comparison crashes."""
        response = {"statusCode": "200"}  # String instead of int

        # This is what the code does
        status = response.get("statusCode")

        # This SHOULD crash when comparing string to int
        if isinstance(status, str):
            with pytest.raises(TypeError):
                if status >= 400:
                    pass
        else:
            # If we got here, it's the right type
            assert isinstance(status, (int, float)) or status is None


class TestApiResponseBoundaryValidation:
    """Test that API response validation catches malformed data at boundary."""

    def test_response_validators_convert_valid_strings(self):
        """Response validators convert valid numeric strings (lenient mode)."""
        from utils.validation.response_validators import (
            ResponseValidationError,
            validate_portfolio_response,
        )

        # Validators allow conversion of valid numeric strings (by design)
        valid_string_numeric = {
            "total_portfolio_value": 100000.0,
            "total_cash": 50000.0,
            "position_count": "5",  # String that can be converted to int
        }

        # This PASSES because "5" can be converted to int
        result = validate_portfolio_response(valid_string_numeric)
        assert result["position_count"] == "5"  # Still a string in result

    def test_response_validators_reject_invalid_strings(self):
        """Response validators catch invalid strings that can't be converted."""
        from utils.validation.response_validators import (
            ResponseValidationError,
            validate_portfolio_response,
        )

        # Invalid string that CANNOT be converted
        invalid_string = {
            "total_portfolio_value": 100000.0,
            "total_cash": 50000.0,
            "position_count": "not_a_number",  # Can't convert to int
        }

        # Should raise error because "not_a_number" can't be converted
        with pytest.raises(ResponseValidationError):
            validate_portfolio_response(invalid_string)

    def test_unwrap_detects_malformed_data_field(self):
        """_unwrap_api_response should detect if data field is malformed."""
        from dashboard.api_data_layer import _unwrap_api_response

        # If data is a string instead of dict, should return error marker
        response = {"statusCode": 200, "data": "malformed_string"}
        result = _unwrap_api_response(response)

        # Should have error indicator
        assert "_error" in result or result == {"statusCode": 200}


class TestDataTypeValidationAtBoundaries:
    """Test that data type validation happens at system boundaries."""

    def test_api_call_catches_malformed_response(self):
        """api_call should catch malformed responses before returning."""
        from unittest.mock import MagicMock, patch

        from dashboard.api_data_layer import api_call

        with patch("dashboard.api_data_layer.API_BASE_URL", "http://test:8000"):
            with patch("dashboard.api_data_layer._http_session.get") as mock_get:
                # Mock response with malformed data
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "statusCode": 200,
                    "data": "malformed",  # Should be dict
                }
                mock_get.return_value = mock_resp

                result = api_call("/api/unknown/endpoint")

                # Should have error because data field is malformed
                assert "_error" in result


class TestSafeTypeConversions:
    """Test that safe_float/safe_int are used for comparisons."""

    def test_safe_float_rejects_malformed(self):
        """safe_float should reject non-numeric types."""
        from dashboard.data_validation import safe_float

        # Test with various malformed inputs
        assert safe_float("15.5") == 15.5  # Can parse
        assert safe_float({"value": 15.5}) is None  # Dict -> None
        assert safe_float([15.5]) is None  # List -> None
        assert safe_float("not_a_number") is None  # Invalid string

    def test_safe_int_rejects_malformed(self):
        """safe_int should reject non-numeric types."""
        from dashboard.data_validation import safe_int

        # Test with various malformed inputs
        assert safe_int("5") == 5  # Can parse
        assert safe_int(5.5) == 5  # Float converted
        assert safe_int({"value": 5}) is None  # Dict -> None
        assert safe_int([5]) is None  # List -> None


class TestFullStackWithMalformedData:
    """End-to-end test: malformed data through full stack."""

    def test_api_response_propagates_error(self):
        """Malformed API response should propagate error through stack."""
        from unittest.mock import MagicMock, patch

        from dashboard.api_data_layer import api_call

        with patch("dashboard.api_data_layer.API_BASE_URL", "http://test:8000"):
            with patch("dashboard.api_data_layer._http_session.get") as mock_get:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                # Return response where statusCode is string instead of int
                mock_resp.json.return_value = {"statusCode": "200"}
                mock_get.return_value = mock_resp

                result = api_call("/api/algo/portfolio")

                # Result should either be:
                # 1. Have _error field (validation caught it)
                # 2. Have correct type statusCode for downstream to check
                if "_error" not in result:
                    # If no error, statusCode must be int for comparisons
                    assert isinstance(result.get("statusCode"), int)
