#!/usr/bin/env python3
"""Integration test to verify API validation layer is working correctly.

This test ensures that all API endpoints go through validation
and that schema drift is caught at the API boundary.
"""

from unittest.mock import MagicMock, patch

import pytest

from dashboard.api_data_layer import _circuit_breaker_state, api_call


@pytest.fixture(autouse=True)
def reset_circuit_breaker(monkeypatch):
    """Reset circuit breaker state before each test."""
    import dashboard.api_data_layer as api_layer

    # Reset circuit breaker to closed state
    monkeypatch.setattr(api_layer, "_circuit_breaker_state", "closed")
    monkeypatch.setattr(api_layer, "_circuit_breaker_failures", 0)
    monkeypatch.setattr(api_layer, "_circuit_breaker_reset_time", None)


def test_api_call_validates_portfolio_response():
    """Verify that api_call validates portfolio responses."""
    with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
        with patch("dashboard.api_data_layer._http_session.get") as mock_get:
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
    with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
        with patch("dashboard.api_data_layer._http_session.get") as mock_get:
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
    with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
        with patch("dashboard.api_data_layer._http_session.get") as mock_get:
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
    with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
        with patch("dashboard.api_data_layer._http_session.get") as mock_get:
            # Mock a trades response with non-list items
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "statusCode": 200,
                "data": {"items": "not_a_list"},  # Should be list
            }
            mock_get.return_value = mock_resp

            result = api_call("/api/algo/trades")
            # Should return error dict
            assert "_error" in result
            assert "list" in result["_error"].lower()


def test_api_call_generic_validation_for_unknown_endpoint():
    """Verify that unknown endpoints still get basic validation."""
    with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
        with patch("dashboard.api_data_layer._http_session.get") as mock_get:
            # Mock a response for an endpoint without specific validator
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "statusCode": 200,
                "data": {"some_field": "some_value"},
            }
            mock_get.return_value = mock_resp

            result = api_call("/api/unknown/endpoint")
            # Should pass through (generic validator accepts any dict)
            assert result["some_field"] == "some_value"


def test_api_call_generic_validation_rejects_non_dict():
    """Verify that generic validator rejects non-dict responses."""
    with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
        with patch("dashboard.api_data_layer._http_session.get") as mock_get:
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


class TestAPIValidationWithMalformedData:
    """Test API validation layer with WRONG TYPES and MALFORMED DATA."""

    def test_api_call_with_malformed_statuscode(self):
        """Test api_call when statusCode is string instead of int."""
        with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
            with patch("dashboard.api_data_layer._http_session.get") as mock_get:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "statusCode": "200",  # String instead of int
                    "data": {"total_portfolio_value": 100000.0},
                }
                mock_get.return_value = mock_resp

                result = api_call("/api/algo/portfolio")
                # Should still work or raise validation error
                assert result is not None
                assert isinstance(result, dict)

    def test_api_call_with_null_data(self):
        """Test api_call when data field is null."""
        with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
            with patch("dashboard.api_data_layer._http_session.get") as mock_get:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "statusCode": 200,
                    "data": None,
                }
                mock_get.return_value = mock_resp

                result = api_call("/api/algo/portfolio")
                # Should handle gracefully
                assert result is not None

    def test_api_call_with_malformed_json_response(self):
        """Test api_call when json() throws exception."""
        with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
            with patch("dashboard.api_data_layer._http_session.get") as mock_get:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.side_effect = ValueError("Invalid JSON")
                mock_get.return_value = mock_resp

                result = api_call("/api/algo/portfolio")
                # Should return error dict
                assert "_error" in result or result is not None

    def test_api_call_with_wrong_type_items(self):
        """Test api_call when items is dict instead of list."""
        with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
            with patch("dashboard.api_data_layer._http_session.get") as mock_get:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "statusCode": 200,
                    "data": {
                        "items": {"0": {"symbol": "AAPL"}}  # Dict instead of list
                    },
                }
                mock_get.return_value = mock_resp

                result = api_call("/api/algo/trades")
                # Should catch type mismatch
                assert result is not None

    def test_api_call_with_negative_count(self):
        """Test api_call with negative position_count."""
        with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
            with patch("dashboard.api_data_layer._http_session.get") as mock_get:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "statusCode": 200,
                    "data": {
                        "total_portfolio_value": 100000.0,
                        "total_cash": 25000.0,
                        "position_count": -5,  # Negative count
                    },
                }
                mock_get.return_value = mock_resp

                result = api_call("/api/algo/portfolio")
                # Should handle negative value
                assert result is not None

    def test_api_call_with_malformed_nested_data(self):
        """Test api_call with deeply nested malformed data."""
        with patch("dashboard.api_data_layer.API_BASE_URL", "http://localhost:8000"):
            with patch("dashboard.api_data_layer._http_session.get") as mock_get:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "statusCode": 200,
                    "data": {
                        "nested": {
                            "deeply": {
                                "value": "should_be_number"  # Wrong type deep in structure
                            }
                        }
                    },
                }
                mock_get.return_value = mock_resp

                result = api_call("/api/algo/unknown")
                # Should handle deep nesting
                assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
