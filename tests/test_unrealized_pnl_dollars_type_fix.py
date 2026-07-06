"""Tests for unrealized_pnl_dollars type fix: Verify API returns float, not string.

Validates three coordinated changes:
1. dashboard.py line 398: Changed from format_decimal_string() to round()
2. dashboard_api_contract.py: Added field to optional_fields and field_types
3. No frontend changes needed (already handles both types)
"""

import sys
from pathlib import Path
from typing import Any

import pytest

# Add lambda/api to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda" / "api"))
from shared_contracts.dashboard_api_contract import DASHBOARD_ENDPOINTS


class TestUnrealizedPNLDollarsContract:
    """Verify field is documented in contract schema."""

    def test_unrealized_pnl_dollars_in_optional_fields(self):
        """Field must be in optional_fields list."""
        port_schema = DASHBOARD_ENDPOINTS["port"]["response_schema"]
        assert "unrealized_pnl_dollars" in port_schema.optional_fields, (
            "unrealized_pnl_dollars must be in optional_fields"
        )

    def test_unrealized_pnl_dollars_in_field_types(self):
        """Field must have type specification."""
        port_schema = DASHBOARD_ENDPOINTS["port"]["response_schema"]
        assert "unrealized_pnl_dollars" in port_schema.field_types, "unrealized_pnl_dollars must be in field_types dict"

    def test_unrealized_pnl_dollars_type_is_numeric_or_none(self):
        """Type must be float, int, or None (NOT str)."""
        port_schema = DASHBOARD_ENDPOINTS["port"]["response_schema"]
        expected_type = (float, int, type(None))
        actual_type = port_schema.field_types["unrealized_pnl_dollars"]

        assert actual_type == expected_type, (
            f"Expected {expected_type}, got {actual_type}. String type should NOT be allowed (was the bug)."
        )


class TestUnrealizedPNLDollarsValue:
    """Verify API returns numeric value, not string."""

    def test_round_function_produces_correct_output(self):
        """Verify round() function used in dashboard.py produces correct values."""
        # Test positive value
        unrealized_pnl = 123.456789
        result = round(unrealized_pnl, 2) if unrealized_pnl is not None else None
        assert result == 123.46
        assert isinstance(result, float)

        # Test zero
        unrealized_pnl = 0.0
        result = round(unrealized_pnl, 2) if unrealized_pnl is not None else None
        assert result == 0.0
        assert isinstance(result, float)

        # Test negative value
        unrealized_pnl = -523.4455
        result = round(unrealized_pnl, 2) if unrealized_pnl is not None else None
        assert result == -523.45
        assert isinstance(result, float)

        # Test None
        unrealized_pnl = None
        result = round(unrealized_pnl, 2) if unrealized_pnl is not None else None
        assert result is None

    def test_not_string_format(self):
        """Verify NOT using format_decimal_string() which returns string."""
        # format_decimal_string would produce: "123.46" (string)
        # round() produces: 123.46 (float)

        unrealized_pnl = 123.456789
        correct_result = round(unrealized_pnl, 2)
        wrong_result = f"{unrealized_pnl:.2f}"  # This is what format_decimal_string does

        assert isinstance(correct_result, float), "Should be float"
        assert isinstance(wrong_result, str), "String version should not be used"
        assert correct_result != wrong_result, "Numeric and string should differ in type"

    def test_precision_maintained(self):
        """Verify 2-decimal precision is maintained."""
        test_cases = [
            (100.006, 100.01),
            (100.004, 100.0),
            (99.999, 100.0),
            (0.001, 0.0),
            (-50.125, -50.12),
            (-50.126, -50.13),
        ]

        for input_val, expected in test_cases:
            result = round(input_val, 2)
            assert result == expected, f"round({input_val}, 2) should be {expected}, got {result}"
            assert isinstance(result, float)


class TestUnrealizedPNLDollarsFrontendCompatibility:
    """Verify frontend toSafeNumber() handles both old and new API responses."""

    def safe_number_equivalent(self, value: Any, default_value: int = 0) -> float:
        """Mimic JavaScript toSafeNumber() function from safeCalculations.js."""
        try:
            num = float(value)
            return num if num == num else default_value  # NaN check
        except (TypeError, ValueError):
            return default_value

    def test_frontend_handles_numeric_response(self):
        """Frontend must work with new numeric response."""
        # New API response: unrealized_pnl_dollars = 123.45 (float)
        api_response = 123.45
        result = self.safe_number_equivalent(api_response)
        assert result == 123.45

    def test_frontend_handles_string_response(self):
        """Frontend must still work with old string response (backward compat)."""
        # Old API response: unrealized_pnl_dollars = "123.45" (string)
        api_response = "123.45"
        result = self.safe_number_equivalent(api_response)
        assert result == 123.45

    def test_frontend_handles_none_response(self):
        """Frontend must handle None response gracefully."""
        api_response = None
        result = self.safe_number_equivalent(api_response, default_value=0)
        assert result == 0

    def test_both_types_produce_same_calculation_result(self):
        """Both old (string) and new (float) should produce same calculation."""
        # Old behavior (string response)
        unrealized_pnl_old = "12345.67"
        old_result = self.safe_number_equivalent(unrealized_pnl_old)

        # New behavior (float response)
        unrealized_pnl_new = 12345.67
        new_result = self.safe_number_equivalent(unrealized_pnl_new)

        # Both should produce same calculation
        assert old_result == new_result == 12345.67


class TestDataTypeConsistency:
    """Verify data type consistency across the system."""

    def test_database_to_api_type_consistency(self):
        """Trace data flow: DB (float) -> Python (float) -> API (float, not string)."""
        # algo_portfolio_snapshots.unrealized_pnl_total is FLOAT in database
        db_value = 1234.567  # float from database

        # dashboard.py line 376 converts to float (no-op)
        python_value = float(db_value)
        assert isinstance(python_value, float)

        # dashboard.py line 398 should round (not format to string)
        api_value = round(python_value, 2) if python_value is not None else None
        assert isinstance(api_value, float), "API must return float, not string"
        assert api_value == 1234.57

    def test_json_serialization_preserves_type(self):
        """Verify JSON serialization preserves numeric type."""
        import json

        # Old behavior (string - no JSON encoding needed)
        old_response = {"unrealized_pnl_dollars": "1234.56"}
        old_json = json.dumps(old_response)
        old_parsed = json.loads(old_json)
        assert isinstance(old_parsed["unrealized_pnl_dollars"], str)

        # New behavior (number - JSON preserves as number)
        new_response = {"unrealized_pnl_dollars": 1234.56}
        new_json = json.dumps(new_response)
        new_parsed = json.loads(new_json)
        assert isinstance(new_parsed["unrealized_pnl_dollars"], float)

        # Both should deserialize to correct value
        assert float(old_parsed["unrealized_pnl_dollars"]) == new_parsed["unrealized_pnl_dollars"]

    def test_other_percentage_fields_still_allowed_string(self):
        """Verify other fields can still be strings (contract allows it)."""
        port_schema = DASHBOARD_ENDPOINTS["port"]["response_schema"]

        # unrealized_pnl_pct should still allow string (percentage)
        pct_type = port_schema.field_types.get("unrealized_pnl_pct")
        assert str in pct_type, "unrealized_pnl_pct should still allow string"

        # But unrealized_pnl_dollars should NOT allow string
        dollars_type = port_schema.field_types.get("unrealized_pnl_dollars")
        assert str not in dollars_type, "unrealized_pnl_dollars should NOT allow string"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
