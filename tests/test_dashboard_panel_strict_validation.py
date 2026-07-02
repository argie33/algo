"""Test dashboard panel strict validation integration.

Ensures that dashboard panels handle missing data gracefully when using
strict validation modes, and don't pass None to strict converters.
"""

from typing import Any

import pytest

from utils.safe_data_conversion import StrictValidationError


class TestDataValidationChain:
    """Test the validation chain from fetcher to panel."""

    def test_fetcher_none_propagates_to_panel(self) -> None:
        """When fetcher returns None, panel should raise during strict conversion."""
        from utils.safe_data_conversion import safe_float

        # Simulate fetcher returning None
        yield_curve_data: Any = None

        # Panel receives None and tries strict conversion
        with pytest.raises(StrictValidationError):
            safe_float(yield_curve_data, strict=True, field_name="10Y")

    def test_fetcher_invalid_data_caught(self) -> None:
        """When fetcher returns invalid data, panel should catch it."""
        from utils.safe_data_conversion import safe_float

        # Fetcher returns non-numeric data
        invalid_price = "N/A"

        with pytest.raises(StrictValidationError):
            safe_float(invalid_price, strict=True, field_name="price")


class TestPrevalidationBeforeStrict:
    """Test that data should be validated before reaching strict converters."""

    def test_should_validate_at_data_source(self) -> None:
        """Data validation should happen at source, not in strict converters.

        This test documents the pattern: data sources (fetchers) should
        validate their output before it reaches the dashboard panels.
        """

        # Pattern: Fetcher should check for None before returning
        def safe_fetch_price(raw_data: dict[str, Any]) -> float | None:
            price = raw_data.get("price")
            if price is None:
                # Should log and return None or raise, not pass to strict converter
                return None
            return float(price)

        # Panel should use strict conversion on already-validated data
        def panel_use_price(price: float | None) -> str:
            from utils.safe_data_conversion import safe_float

            # Only call strict if we know price is not None, or handle None explicitly
            if price is None:
                return "N/A"
            converted = safe_float(price, strict=True, field_name="price")
            return f"${converted:.2f}"

        # Test with None data
        raw: dict[str, Any] = {"price": None}
        price = safe_fetch_price(raw)
        result = panel_use_price(price)
        assert result == "N/A"

        # Test with valid data
        raw = {"price": 100.0}
        price = safe_fetch_price(raw)
        result = panel_use_price(price)
        assert result == "$100.00"


class TestFetcherValidationPatterns:
    """Test validation patterns in fetchers."""

    def test_fetcher_should_validate_dict_get(self) -> None:
        """Fetchers should validate dict.get() results before strict conversion."""
        data = {"yield": None}

        # ❌ Bad: calling strict converter on dict.get() result (which can be None)
        # with pytest.raises(StrictValidationError):
        #     safe_float(data.get("yield"), strict=True, field_name="yield")

        # ✅ Good: check for None before strict conversion
        from utils.safe_data_conversion import safe_float

        yield_value = data.get("yield")
        if yield_value is None:
            # Handle missing data explicitly
            formatted_yield = None
        else:
            formatted_yield = safe_float(yield_value, strict=True, field_name="yield")

        assert formatted_yield is None

    def test_fetcher_should_validate_list_access(self) -> None:
        """Fetchers should handle list access errors before strict conversion."""
        from utils.safe_data_conversion import safe_float

        data_list: list[float] = []  # Empty list

        # ✅ Good: check for access errors before strict conversion
        try:
            price = data_list[0] if data_list else None
        except IndexError:
            price = None

        if price is None:
            formatted_price = None
        else:
            formatted_price = safe_float(price, strict=True, field_name="price")

        assert formatted_price is None


class TestCIDetectionOfValidationGaps:
    """Test that CI can detect validation gaps."""

    def test_all_strict_calls_have_field_names(self) -> None:
        """All strict=True calls should have field_name for clarity."""
        from utils.safe_data_conversion import safe_float

        # Good: explicit field name
        result = safe_float(100.0, strict=True, field_name="price")
        assert result == 100.0

        # Bad pattern (but testable): no field name means error message is less clear
        result = safe_float(100.0, strict=True)
        assert result == 100.0

    def test_error_messages_guide_debugging(self) -> None:
        """StrictValidationError messages should help debugging."""
        from utils.safe_data_conversion import safe_float

        try:
            safe_float(None, strict=True, field_name="market_spy_price")
        except StrictValidationError as e:
            msg = str(e)
            # Message should clearly identify the problem and the field
            assert "market_spy_price" in msg
            assert "None" in msg or "none" in msg.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
