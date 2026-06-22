#!/usr/bin/env python3
"""Integration test to verify API validation layer is working correctly.

This test ensures that all API endpoints go through validation
and that schema drift is caught at the API boundary.
"""

from unittest.mock import MagicMock, patch

import pytest

from tools.dashboard.api_data_layer import api_call


def test_api_call_validates_portfolio_response():
    """Verify that api_call validates portfolio responses."""
    with patch("tools.dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
        with patch("tools.dashboard.api_data_layer._http_session.get") as mock_get:
            # Mock a valid portfolio response
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "statusCode": 200,
                "data": {
                    "total_portfolio_value": 100000.0,
                    "total_cash": 25000.0,
                    "position_count": 5,
                },
            }
            mock_get.return_value = mock_resp

            result = api_call("/api/algo/portfolio")
            # Should return unwrapped data with statusCode preserved
            assert result["total_portfolio_value"] == 100000.0
            assert result["total_cash"] == 25000.0
            assert result["position_count"] == 5
            assert result["statusCode"] == 200


def test_api_call_catches_missing_portfolio_field():
    """Verify that api_call catches missing required fields in portfolio response."""
    with patch("tools.dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
        with patch("tools.dashboard.api_data_layer._http_session.get") as mock_get:
            # Mock a portfolio response missing position_count (required field)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "statusCode": 200,
                "data": {
                    "total_portfolio_value": 100000.0,
                    "total_cash": 25000.0,
                    # Missing position_count - should trigger validation error
                },
            }
            mock_get.return_value = mock_resp

            result = api_call("/api/algo/portfolio")
            # Should return error dict
            assert "_error" in result
            assert "position_count" in result["_error"].lower() or "missing" in result["_error"].lower()


def test_api_call_validates_trades_response():
    """Verify that api_call validates trades endpoint responses."""
    with patch("tools.dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
        with patch("tools.dashboard.api_data_layer._http_session.get") as mock_get:
            # Mock a valid trades response
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "statusCode": 200,
                "data": {
                    "items": [
                        {"symbol": "AAPL", "quantity": 10},
                        {"symbol": "MSFT", "quantity": 5},
                    ]
                },
            }
            mock_get.return_value = mock_resp

            result = api_call("/api/algo/trades")
            assert result["items"]
            assert len(result["items"]) == 2


def test_api_call_catches_invalid_trades_items():
    """Verify that api_call catches invalid items in trades response."""
    with patch("tools.dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
        with patch("tools.dashboard.api_data_layer._http_session.get") as mock_get:
            # Mock a trades response with non-list items
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "statusCode": 200,
                "data": {
                    "items": "not_a_list"  # Should be list
                },
            }
            mock_get.return_value = mock_resp

            result = api_call("/api/algo/trades")
            # Should return error dict
            assert "_error" in result
            assert "list" in result["_error"].lower()


def test_api_call_generic_validation_for_unknown_endpoint():
    """Verify that unknown endpoints still get basic validation."""
    with patch("tools.dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
        with patch("tools.dashboard.api_data_layer._http_session.get") as mock_get:
            # Mock a response for an endpoint without specific validator
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"statusCode": 200, "data": {"some_field": "some_value"}}
            mock_get.return_value = mock_resp

            result = api_call("/api/unknown/endpoint")
            # Should pass through (generic validator accepts any dict)
            assert result["some_field"] == "some_value"


def test_api_call_generic_validation_rejects_non_dict():
    """Verify that generic validator rejects non-dict responses."""
    with patch("tools.dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
        with patch("tools.dashboard.api_data_layer._http_session.get") as mock_get:
            # Mock a response that returns non-dict
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "statusCode": 200,
                "data": "not_a_dict",  # Should be dict
            }
            mock_get.return_value = mock_resp

            result = api_call("/api/unknown/endpoint")
            # Should return error dict
            assert "_error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
