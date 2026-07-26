"""Unit tests for API industries endpoint."""

import pytest


def test_industries_list_response_structure():
    """Verify industries/list endpoint returns proper response structure."""
    from shared_contracts.dashboard_api_contract import DASHBOARD_ENDPOINTS

    # Check schema definition
    schema = DASHBOARD_ENDPOINTS.get("industries/list")
    assert schema is not None, "industries/list endpoint not defined in contract"

    # Verify required fields in contract
    response_schema = schema.get("response_schema")
    assert response_schema is not None, "Response schema missing for industries/list"

    # Check allowed fields match what endpoint returns
    allowed_fields = set(response_schema.required_fields) | set(response_schema.optional_fields)
    expected_fields = {"items", "total", "page", "limit", "data_freshness"}

    # All expected fields should be allowed
    assert expected_fields.issubset(allowed_fields), f"Missing fields in schema: {expected_fields - allowed_fields}"


def test_industries_endpoint_validation():
    """Verify response validator accepts proper response structure."""
    from shared_contracts.response_validator import ResponseValidator

    # Test valid response structure
    valid_response = {
        "items": [],
        "total": 0,
        "page": 1,
        "limit": 500,
        "data_freshness": {"data_age_days": 0, "is_stale": False, "warning": None},
    }

    is_valid, error_msg = ResponseValidator.validate_endpoint_response("industries/list", valid_response)
    assert is_valid, f"Valid response failed validation: {error_msg}"


def test_industries_detail_endpoint_validation():
    """Verify detail endpoint response structure is valid."""
    from shared_contracts.dashboard_api_contract import DASHBOARD_ENDPOINTS
    from shared_contracts.response_validator import ResponseValidator

    # Check schema definition
    schema = DASHBOARD_ENDPOINTS.get("industries/detail")
    assert schema is not None, "industries/detail endpoint not defined in contract"

    # Test valid response structure
    valid_response = {
        "industry_name": "Software",
        "stock_count": 100,
        "composite_score": 75.5,
        "momentum_score": 80.0,
        "value_score": 70.0,
        "quality_score": 80.0,
        "growth_score": 85.0,
        "stability_score": 75.0,
        "data_freshness": {"data_age_days": 0, "is_stale": False, "warning": None},
    }

    is_valid, error_msg = ResponseValidator.validate_endpoint_response("industries/detail", valid_response)
    assert is_valid, f"Valid detail response failed validation: {error_msg}"


def test_industries_trend_endpoint_validation():
    """Verify trend endpoint response structure is valid."""
    from shared_contracts.dashboard_api_contract import DASHBOARD_ENDPOINTS
    from shared_contracts.response_validator import ResponseValidator

    # Check schema definition
    schema = DASHBOARD_ENDPOINTS.get("industries/trend")
    assert schema is not None, "industries/trend endpoint not defined in contract"

    # Test valid response structure
    valid_response = {
        "industry": "Software",
        "trendData": [
            {
                "date": "2024-01-01",
                "avgPrice": 100.0,
                "stockCount": 50,
                "dailyStrengthScore": 2.5,
            }
        ],
        "data_freshness": {"data_age_days": 0, "is_stale": False, "warning": None},
    }

    is_valid, error_msg = ResponseValidator.validate_endpoint_response("industries/trend", valid_response)
    assert is_valid, f"Valid trend response failed validation: {error_msg}"
