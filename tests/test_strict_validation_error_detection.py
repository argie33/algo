"""Test suite for detecting StrictValidationError in strict mode validation.

This test suite ensures that StrictValidationError is properly raised and caught
when using safe_float/safe_int with strict=True on None or invalid values.

The goal is to catch validation errors in CI/CD before they reach production,
specifically catching cases where data parsers pass None to strict converters.
"""

from typing import Any

import pytest
from utils.safe_data_conversion import StrictValidationError, safe_float, safe_int


class TestStrictFloatNoneDetection:
    """Test that safe_float with strict=True catches None values."""

    def test_none_raises_strict_validation_error(self) -> None:
        """safe_float(None, strict=True) should raise StrictValidationError."""
        with pytest.raises(StrictValidationError) as exc_info:
            safe_float(None, strict=True, field_name="test_field")

        error_msg = str(exc_info.value).lower()
        assert "cannot convert none to float" in error_msg
        assert "test_field" in str(exc_info.value)

    def test_none_strict_without_field_name(self) -> None:
        """safe_float(None, strict=True) raises even without field_name."""
        with pytest.raises(StrictValidationError) as exc_info:
            safe_float(None, strict=True)

        error_msg = str(exc_info.value).lower()
        assert "cannot convert none to float" in error_msg

    def test_none_strict_with_context(self) -> None:
        """safe_float(None, strict=True, context="...") raises with context."""
        with pytest.raises(StrictValidationError) as exc_info:
            safe_float(None, strict=True, context="symbol=AAPL")

        error_msg = str(exc_info.value)
        assert "AAPL" in error_msg

    def test_invalid_string_raises_strict_validation_error(self) -> None:
        """safe_float with invalid string and strict=True raises."""
        with pytest.raises(StrictValidationError) as exc_info:
            safe_float("not_a_number", strict=True, field_name="price")

        error_msg = str(exc_info.value).lower()
        assert "cannot convert" in error_msg
        assert "not_a_number" in str(exc_info.value)

    def test_bool_raises_strict_validation_error(self) -> None:
        """safe_float with bool and strict=True raises."""
        with pytest.raises(StrictValidationError) as exc_info:
            safe_float(True, strict=True, field_name="trading_enabled")

        error_msg = str(exc_info.value).lower()
        assert "cannot convert bool to float" in error_msg

    def test_valid_float_passes_strict(self) -> None:
        """safe_float with valid float and strict=True passes."""
        result = safe_float(123.45, strict=True, field_name="price")
        assert result == 123.45

    def test_valid_int_passes_strict(self) -> None:
        """safe_float with valid int and strict=True passes."""
        result = safe_float(100, strict=True, field_name="quantity")
        assert result == 100.0

    def test_valid_string_number_passes_strict(self) -> None:
        """safe_float with valid numeric string and strict=True passes."""
        result = safe_float("456.78", strict=True, field_name="amount")
        assert result == 456.78


class TestStrictIntNoneDetection:
    """Test that safe_int with strict=True catches None values."""

    def test_none_raises_strict_validation_error(self) -> None:
        """safe_int(None, strict=True) should raise StrictValidationError."""
        with pytest.raises(StrictValidationError) as exc_info:
            safe_int(None, strict=True, field_name="trade_count")

        error_msg = str(exc_info.value).lower()
        assert "cannot convert none to int" in error_msg
        assert "trade_count" in str(exc_info.value)

    def test_invalid_string_raises_strict_validation_error(self) -> None:
        """safe_int with invalid string and strict=True raises."""
        with pytest.raises(StrictValidationError) as exc_info:
            safe_int("not_an_int", strict=True, field_name="position_count")

        error_msg = str(exc_info.value).lower()
        assert "cannot convert" in error_msg

    def test_bool_raises_strict_validation_error(self) -> None:
        """safe_int with bool and strict=True raises."""
        with pytest.raises(StrictValidationError) as exc_info:
            safe_int(True, strict=True, field_name="buy_signal")

        error_msg = str(exc_info.value).lower()
        assert "cannot convert bool to int" in error_msg

    def test_valid_int_passes_strict(self) -> None:
        """safe_int with valid int and strict=True passes."""
        result = safe_int(42, strict=True, field_name="quantity")
        assert result == 42

    def test_valid_string_number_passes_strict(self) -> None:
        """safe_int with valid numeric string and strict=True passes."""
        result = safe_int("789", strict=True, field_name="trade_id")
        assert result == 789


class TestDashboardPanelDataValidation:
    """Test validation scenarios from dashboard panels (real-world cases)."""

    def test_market_panel_none_vix_raises(self) -> None:
        """Market panel with None VIX should raise when using strict=True."""
        vix_raw = None
        with pytest.raises(StrictValidationError):
            safe_float(vix_raw, strict=True, field_name="vix")

    def test_portfolio_panel_none_portfolio_value_raises(self) -> None:
        """Portfolio panel with None portfolio value should raise."""
        pv_raw = None
        with pytest.raises(StrictValidationError):
            safe_float(pv_raw, strict=True, field_name="total_portfolio_value")

    def test_portfolio_panel_none_cash_raises(self) -> None:
        """Portfolio panel with None cash should raise."""
        cash_raw = None
        with pytest.raises(StrictValidationError):
            safe_float(cash_raw, strict=True, field_name="total_cash")

    def test_portfolio_panel_none_position_count_raises(self) -> None:
        """Portfolio panel with None position count should raise."""
        npos_raw = None
        with pytest.raises(StrictValidationError):
            safe_int(npos_raw, strict=True, field_name="position_count")

    def test_signal_panel_none_score_raises(self) -> None:
        """Signals panel with None composite score should raise."""
        comp_score = None
        with pytest.raises(StrictValidationError):
            safe_float(comp_score, strict=True, field_name="composite_score")


class TestFetcherDataValidation:
    """Test validation in fetcher functions (data sources)."""

    def test_external_fetcher_none_yield_curve_raises(self) -> None:
        """External fetcher with None yield curve data should raise."""
        curve_data = None
        with pytest.raises(StrictValidationError):
            safe_float(curve_data, strict=True, field_name="curve.10Y")

    def test_portfolio_fetcher_none_sharpe_raises(self) -> None:
        """Portfolio fetcher with None Sharpe ratio should raise."""
        sharpe = None
        with pytest.raises(StrictValidationError):
            safe_float(sharpe, strict=True, field_name="sharpe252")

    def test_signals_fetcher_none_total_raises(self) -> None:
        """Signals fetcher with None total signals should raise."""
        total = None
        with pytest.raises(StrictValidationError):
            safe_int(total, strict=True, field_name="total")


class TestStrictModeDataFlow:
    """Test that strict mode errors propagate correctly through data flow."""

    def test_error_not_swallowed_in_strict_mode(self) -> None:
        """StrictValidationError should propagate, not be caught silently."""
        def fetch_data_strict(value: Any) -> Any:
            """Simulate strict data fetching."""
            return safe_float(value, strict=True, field_name="critical_metric")

        # Should raise, not return None or default
        with pytest.raises(StrictValidationError):
            fetch_data_strict(None)

    def test_error_contains_field_context(self) -> None:
        """Error message should clearly identify which field failed."""
        try:
            safe_float(None, strict=True, field_name="spy_price")
            pytest.fail("Should have raised StrictValidationError")
        except StrictValidationError as e:
            assert "spy_price" in str(e)

    def test_error_distinguishes_none_from_invalid(self) -> None:
        """Error should distinguish between None and other invalid types."""
        none_error = None
        invalid_error = None

        try:
            safe_float(None, strict=True, field_name="test")
        except StrictValidationError as e:
            none_error = str(e).lower()

        try:
            safe_float("not_a_float", strict=True, field_name="test")
        except StrictValidationError as e:
            invalid_error = str(e).lower()

        assert none_error is not None
        assert invalid_error is not None
        assert "none" in none_error
        assert "not_a_float" in invalid_error


class TestIntegrationWithRealDataPatterns:
    """Test integration with real data patterns from fetchers."""

    def test_dict_get_returns_none_with_strict_float(self) -> None:
        """Common pattern: dict.get() returns None, strict=True should raise."""
        data = {"price": 100.0}

        # Existing key works
        result = safe_float(data.get("price"), strict=True, field_name="price")
        assert result == 100.0

        # Missing key returns None, strict=True raises
        with pytest.raises(StrictValidationError):
            safe_float(data.get("missing_key"), strict=True, field_name="missing_key")

    def test_chained_getattr_returns_none_with_strict_float(self) -> None:
        """Pattern: nested attribute access returns None, strict=True raises."""
        class DataObj:
            def __init__(self, value: Any) -> None:
                self.value = value

        obj = DataObj(None)
        with pytest.raises(StrictValidationError):
            safe_float(obj.value, strict=True, field_name="obj.value")

    def test_list_index_out_of_bounds_pattern(self) -> None:
        """Pattern: list index returns None (via try-except), strict=True raises."""
        data_list: list[Any] = []
        value: Any = None
        try:
            value = data_list[0]
        except IndexError:
            value = None

        with pytest.raises(StrictValidationError):
            safe_float(value, strict=True, field_name="data_list[0]")


class TestCIDetectionCapability:
    """Test that CI/CD can detect these validation errors."""

    def test_strict_validation_error_is_exception(self) -> None:
        """StrictValidationError should be a proper Exception."""
        assert issubclass(StrictValidationError, Exception)

    def test_error_message_is_meaningful(self) -> None:
        """Error message should be clear and actionable."""
        try:
            safe_float(None, strict=True, field_name="spy_close")
        except StrictValidationError as e:
            msg = str(e)
            # Should mention the field and the problem
            assert len(msg) > 10
            assert "spy_close" in msg or "None" in msg

    def test_multiple_errors_can_be_collected(self) -> None:
        """Test pattern for collecting multiple validation errors."""
        errors = []
        fields = {
            "price": None,
            "volume": "not_a_number",
            "timestamp": None,
        }

        for field_name, value in fields.items():
            try:
                safe_float(value, strict=True, field_name=field_name)
            except StrictValidationError as e:
                errors.append((field_name, str(e)))

        assert len(errors) == 3
        assert all(field_name in error_msg for field_name, error_msg in errors)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
