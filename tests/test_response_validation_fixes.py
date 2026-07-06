"""Test fixes for 5xx validation errors in dashboard API endpoints."""

import pytest
from shared_contracts.response_validator import ResponseValidator
from shared_contracts.dashboard_api_contract import DASHBOARD_ENDPOINTS


class TestResponseValidatorLeniency:
    """Test that ResponseValidator is lenient about extra fields."""

    def test_extra_fields_with_warning(self):
        """Extra fields should be allowed with warning, not fail."""
        # Response with extra field not in schema
        response = {
            "items": [],
            "total": 0,
            "limit": 10,
            "offset": 0,
            "data_freshness": {"is_stale": False},
            "extra_field_not_in_schema": "should be ignored",
        }

        is_valid, error_msg = ResponseValidator.validate_endpoint_response("audit", response)

        # Should be valid (extra field is allowed)
        assert is_valid is True
        assert error_msg is None

    def test_nested_schema_allows_dynamic_fields(self):
        """Endpoints with nested_schema should allow any fields."""
        # Config endpoint has nested_schema={"*": dict}
        response = {
            "enabled": True,
            "mode": "paper_trading",
            "any_arbitrary_field": "allowed",
            "another_dynamic_field": 12345,
        }

        is_valid, error_msg = ResponseValidator.validate_endpoint_response("cfg", response)

        # Should be valid
        assert is_valid is True
        assert error_msg is None

    def test_missing_required_fields_still_fail(self):
        """Missing required fields should still cause validation to fail."""
        # stocks endpoint requires ["items", "total"]
        response = {
            "items": [],
            # Missing "total" which is required
        }

        is_valid, error_msg = ResponseValidator.validate_endpoint_response("stocks", response)

        # Should be invalid
        assert is_valid is False
        assert "total" in error_msg

    def test_type_validation_still_works(self):
        """Type mismatches should still be caught."""
        response = {
            "items": "not_a_list",  # Should be list
            "total": 5,
        }

        is_valid, error_msg = ResponseValidator.validate_endpoint_response("stocks", response)

        # Should be invalid
        assert is_valid is False


class TestEndpointSchemasComplete:
    """Test that endpoint schemas include all fields they return."""

    @pytest.mark.parametrize("endpoint_name", [
        "audit",
        "activity",
        "exec_hist",
        "sentiment",
        "sig_eval",
        "sec_rot",
        "cb",
        "srank",
    ])
    def test_list_endpoints_have_data_freshness(self, endpoint_name):
        """List endpoints should include data_freshness in optional_fields."""
        endpoint = DASHBOARD_ENDPOINTS.get(endpoint_name)
        assert endpoint is not None, f"Endpoint {endpoint_name} not defined"

        response_schema = endpoint.get("response_schema")
        assert response_schema is not None

        # data_freshness should be in optional_fields
        assert "data_freshness" in response_schema.optional_fields, \
            f"Endpoint {endpoint_name} missing data_freshness in optional_fields"

    def test_sentiment_includes_label(self):
        """Sentiment endpoint should include label field."""
        endpoint = DASHBOARD_ENDPOINTS.get("sentiment")
        response_schema = endpoint.get("response_schema")

        # label should be in optional_fields
        assert "label" in response_schema.optional_fields, \
            "Sentiment endpoint missing label in optional_fields"

    def test_all_critical_endpoints_have_critical_flag(self):
        """All endpoints must have explicit critical flag."""
        for endpoint_name, endpoint_def in DASHBOARD_ENDPOINTS.items():
            assert "critical" in endpoint_def, \
                f"Endpoint {endpoint_name} missing required 'critical' field"


class TestValidationResponseFormat:
    """Test that validation errors have proper format."""

    def test_validation_error_response_structure(self):
        """Error responses should have proper structure."""
        # Response missing required field
        response = {
            "items": []
            # Missing "total"
        }

        is_valid, error_msg = ResponseValidator.validate_endpoint_response("stocks", response)

        assert is_valid is False
        assert isinstance(error_msg, str)
        assert len(error_msg) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
