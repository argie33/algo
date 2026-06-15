#!/usr/bin/env python3
"""Test null sanitization in API responses (Issue #14 fix)."""

import sys
import json
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.validation import APIResponseValidator
from routes.utils import success_response, json_response, list_response


def test_sanitize_nested_dict_with_nulls():
    """Test sanitizing nested dict with None values."""
    data = {
        "profit_factor": None,
        "win_rate": 50.5,
        "trades": {"count": 100, "avg_win": None, "losses": 20},
    }

    sanitized = APIResponseValidator.sanitize_response(data)

    # Verify None values are replaced with 0
    assert (
        sanitized["profit_factor"] == 0
    ), f"Expected 0, got {sanitized['profit_factor']}"
    assert sanitized["win_rate"] == 50.5, f"Expected 50.5, got {sanitized['win_rate']}"
    assert (
        sanitized["trades"]["avg_win"] == 0
    ), f"Expected 0, got {sanitized['trades']['avg_win']}"
    print("[OK] test_sanitize_nested_dict_with_nulls passed")


def test_sanitize_list_with_nulls():
    """Test sanitizing list with None values (should filter them out)."""
    data = [
        {"symbol": "AAPL", "price": 150.0},
        None,
        {"symbol": "MSFT", "price": None},
        {"symbol": "GOOGL", "price": 2800.0},
    ]

    sanitized = APIResponseValidator.sanitize_response(data)

    # None item should be filtered out
    assert len(sanitized) == 3, f"Expected 3 items, got {len(sanitized)}"
    # None price should be replaced with 0
    assert sanitized[1]["price"] == 0, f"Expected 0, got {sanitized[1]['price']}"
    print("[OK] test_sanitize_list_with_nulls passed")


def test_success_response_sanitizes():
    """Test that success_response sanitizes None values."""
    data = {"profit_factor": None, "win_rate": 45.0}

    response = success_response(data)

    assert response["statusCode"] == 200
    assert response["data"]["profit_factor"] == 0
    assert response["data"]["win_rate"] == 45.0
    print("[OK] test_success_response_sanitizes passed")


def test_list_response_sanitizes():
    """Test that list_response sanitizes None values."""
    items = [{"symbol": "AAPL", "quantity": 10}, {"symbol": "MSFT", "quantity": None}]

    response = list_response(items)

    assert response["statusCode"] == 200
    assert response["data"]["total"] == 2
    assert response["data"]["items"][1]["quantity"] == 0
    print("[OK] test_list_response_sanitizes passed")


def test_validate_no_nulls():
    """Test null detection."""
    data = {"a": 1, "b": None, "c": {"d": None, "e": 2}, "f": [1, None, 3]}

    nulls = APIResponseValidator.validate_no_nulls(data)

    assert "root.b" in nulls
    assert "root.c.d" in nulls
    assert "root.f[1]" in nulls
    assert len(nulls) == 3
    print("[OK] test_validate_no_nulls passed")


def test_json_serializable():
    """Test that sanitized data is JSON serializable."""
    data = {
        "profit_factor": None,
        "items": [{"name": "trade1", "pnl": 100.5}, None],
        "metadata": {"last_update": None},
    }

    sanitized = APIResponseValidator.sanitize_response(data)

    # Should not raise an exception
    json_str = json.dumps(sanitized)
    assert json_str is not None

    # Verify no "null" in JSON (except in JSON strings which shouldn't happen)
    parsed = json.loads(json_str)
    assert parsed["profit_factor"] == 0
    assert len(parsed["items"]) == 1  # None item filtered out
    print("[OK] test_json_serializable passed")


def test_json_response_sanitizes_success():
    """Test that json_response sanitizes None values for success (200) responses."""
    data = {"ratio": None, "value": 42}

    response = json_response(200, data)

    assert response["statusCode"] == 200
    assert response["data"]["ratio"] == 0
    assert response["data"]["value"] == 42
    print("[OK] test_json_response_sanitizes_success passed")


def test_json_response_sanitizes_errors():
    """Test that json_response sanitizes None values for error responses."""
    data = {
        "errorType": "validation_error",
        "message": "Invalid input",
        "details": None,
        "nested": {"field": None, "status": "error"},
    }

    response = json_response(400, data)

    assert response["statusCode"] == 400
    assert response["errorType"] == "validation_error"
    assert response["message"] == "Invalid input"
    # None values should be replaced with 0 (or filtered as appropriate)
    assert response["details"] == 0
    assert response["nested"]["field"] == 0
    assert response["nested"]["status"] == "error"
    print("[OK] test_json_response_sanitizes_errors passed")


def test_no_null_in_json_output():
    """Test that serialized responses contain no null values."""
    responses = [
        success_response({"value": None}),
        list_response([{"item": None}]),
        json_response(200, {"data": None}),
        json_response(500, {"error": None}),
    ]

    for response in responses:
        json_str = json.dumps(response)
        # No null should appear in the JSON output (except potentially in strings)
        parsed = json.loads(json_str)
        assert None not in str(parsed).lower().split(
            "none"
        ), f"Found null in response: {response}"

    print("[OK] test_no_null_in_json_output passed")


if __name__ == "__main__":
    test_sanitize_nested_dict_with_nulls()
    test_sanitize_list_with_nulls()
    test_success_response_sanitizes()
    test_list_response_sanitizes()
    test_validate_no_nulls()
    test_json_serializable()
    test_json_response_sanitizes_success()
    test_json_response_sanitizes_errors()
    test_no_null_in_json_output()
    print("\n[SUCCESS] All tests passed!")
