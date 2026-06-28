"""Test suite for fail-fast finance validation patterns.

Verifies that critical data paths raise exceptions instead of falling back to defaults.
These tests ensure financial accuracy by catching missing/invalid data early.
"""

import pytest

from utils.finance_data_validation import (
    FinanceValidationError,
    require_non_empty_dict,
    require_non_empty_list,
    strict_get_dict,
    strict_get_float,
    strict_get_int,
    strict_get_list,
)


class TestStrictGetDict:
    """Test strict_get_dict validation."""

    def test_returns_value_when_key_exists(self):
        """Should return value when key exists and is not None."""
        data = {"close": 150.25, "symbol": "AAPL"}
        result = strict_get_dict(data, "close")
        assert result == 150.25

    def test_raises_when_data_is_none(self):
        """Should raise FinanceValidationError when data is None."""
        with pytest.raises(FinanceValidationError) as exc_info:
            strict_get_dict(None, "close", source="prices")
        error_msg = str(exc_info.value).lower()
        assert "none" in error_msg
        assert "prices" in str(exc_info.value)

    def test_raises_when_key_missing(self):
        """Should raise FinanceValidationError when key is missing."""
        data = {"symbol": "AAPL"}
        with pytest.raises(FinanceValidationError) as exc_info:
            strict_get_dict(data, "close", source="price_daily")
        assert "close" in str(exc_info.value)
        assert "missing" in str(exc_info.value).lower()

    def test_raises_when_value_is_none(self):
        """Should raise FinanceValidationError when value is None."""
        data = {"close": None}
        with pytest.raises(FinanceValidationError) as exc_info:
            strict_get_dict(data, "close", source="prices")
        assert "close" in str(exc_info.value)
        assert "none" in str(exc_info.value).lower()


class TestStrictGetList:
    """Test strict_get_list validation."""

    def test_returns_list_when_not_none(self):
        """Should return list when not None."""
        data = [{"symbol": "AAPL"}, {"symbol": "GOOGL"}]
        result = strict_get_list(data)
        assert result == data

    def test_returns_empty_list_when_empty(self):
        """Should return empty list (empty is valid, None is not)."""
        result = strict_get_list([])
        assert result == []

    def test_raises_when_none(self):
        """Should raise FinanceValidationError when list is None."""
        with pytest.raises(FinanceValidationError) as exc_info:
            strict_get_list(None, source="buy_signals")
        assert "none" in str(exc_info.value).lower()
        assert "buy_signals" in str(exc_info.value)


class TestStrictGetFloat:
    """Test strict_get_float validation."""

    def test_parses_float_strings(self):
        """Should parse float from string."""
        result = strict_get_float("150.25", source="close_price")
        assert result == 150.25

    def test_accepts_float_values(self):
        """Should accept float values directly."""
        result = strict_get_float(150.25, source="close_price")
        assert result == 150.25

    def test_raises_when_none(self):
        """Should raise when value is None."""
        with pytest.raises(FinanceValidationError) as exc_info:
            strict_get_float(None, source="close_price")
        assert "none" in str(exc_info.value).lower()

    def test_raises_when_zero(self):
        """Should raise when value is zero."""
        with pytest.raises(FinanceValidationError) as exc_info:
            strict_get_float(0.0, source="close_price")
        assert "zero" in str(exc_info.value).lower()

    def test_raises_when_invalid_format(self):
        """Should raise when value cannot be parsed as float."""
        with pytest.raises(FinanceValidationError) as exc_info:
            strict_get_float("not_a_number", source="close_price")
        assert "cannot parse" in str(exc_info.value).lower()

    def test_allows_negative_for_pnl(self):
        """Should allow negative values for PnL-type fields."""
        result = strict_get_float(-100.50, source="pnl")
        assert result == -100.50

    def test_raises_negative_for_price(self):
        """Should raise for negative prices."""
        with pytest.raises(FinanceValidationError) as exc_info:
            strict_get_float(-150.25, source="close_price")
        assert "negative" in str(exc_info.value).lower()


class TestStrictGetInt:
    """Test strict_get_int validation."""

    def test_parses_int_strings(self):
        """Should parse int from string."""
        result = strict_get_int("100", source="quantity")
        assert result == 100

    def test_accepts_int_values(self):
        """Should accept int values directly."""
        result = strict_get_int(100, source="quantity")
        assert result == 100

    def test_raises_when_none(self):
        """Should raise when value is None."""
        with pytest.raises(FinanceValidationError) as exc_info:
            strict_get_int(None, source="quantity")
        assert "none" in str(exc_info.value).lower()

    def test_raises_when_zero_without_flag(self):
        """Should raise when value is zero and allow_zero is False."""
        with pytest.raises(FinanceValidationError) as exc_info:
            strict_get_int(0, source="position_count", allow_zero=False)
        assert "zero" in str(exc_info.value).lower()

    def test_allows_zero_with_flag(self):
        """Should allow zero when allow_zero is True."""
        result = strict_get_int(0, source="position_count", allow_zero=True)
        assert result == 0

    def test_raises_when_negative(self):
        """Should raise when value is negative."""
        with pytest.raises(FinanceValidationError) as exc_info:
            strict_get_int(-1, source="quantity")
        assert "negative" in str(exc_info.value).lower()


class TestRequireNonEmptyDict:
    """Test require_non_empty_dict validation."""

    def test_returns_dict_when_valid(self):
        """Should return dict when not None and not empty."""
        data = {"key": "value"}
        result = require_non_empty_dict(data)
        assert result == data

    def test_raises_when_none(self):
        """Should raise when dict is None."""
        with pytest.raises(FinanceValidationError) as exc_info:
            require_non_empty_dict(None, source="positions")
        assert "none" in str(exc_info.value).lower()

    def test_raises_when_empty(self):
        """Should raise when dict is empty."""
        with pytest.raises(FinanceValidationError) as exc_info:
            require_non_empty_dict({}, source="positions")
        assert "empty" in str(exc_info.value).lower()


class TestRequireNonEmptyList:
    """Test require_non_empty_list validation."""

    def test_returns_list_when_valid(self):
        """Should return list when not None and not empty."""
        data = [1, 2, 3]
        result = require_non_empty_list(data)
        assert result == data

    def test_raises_when_none(self):
        """Should raise when list is None."""
        with pytest.raises(FinanceValidationError) as exc_info:
            require_non_empty_list(None, source="prices")
        assert "none" in str(exc_info.value).lower()

    def test_raises_when_empty(self):
        """Should raise when list is empty."""
        with pytest.raises(FinanceValidationError) as exc_info:
            require_non_empty_list([], source="prices")
        assert "empty" in str(exc_info.value).lower()


class TestFinanceValidationError:
    """Test FinanceValidationError exception."""

    def test_is_runtime_error(self):
        """Should be a RuntimeError subclass."""
        err = FinanceValidationError("test")
        assert isinstance(err, RuntimeError)

    def test_preserves_message(self):
        """Should preserve error message."""
        msg = "[CRITICAL] Data validation failed"
        err = FinanceValidationError(msg)
        assert msg in str(err)


# ── Integration Tests ────────────────────────────────────────────────────────


class TestEconomicMetricsFailFast:
    """Test that economic metrics loader fails fast on data issues."""

    def test_missing_cpi_data_raises(self):
        """Should raise when CPI data is None."""
        with pytest.raises(FinanceValidationError):
            strict_get_float(None, source="cpi_yoy", context="CPI is critical")

    def test_missing_spy_price_raises(self):
        """Should raise when SPY price is None."""
        with pytest.raises(FinanceValidationError):
            strict_get_float(None, source="spy_price", context="SPY price is critical")

    def test_missing_yield_curve_raises(self):
        """Should raise when yield curve data is None."""
        with pytest.raises(FinanceValidationError):
            require_non_empty_dict(None, source="yield_curve")


class TestSignalProcessingFailFast:
    """Test that signal processing fails fast on missing data."""

    def test_missing_buy_signals_raises(self):
        """Should raise when buy signals list is None."""
        with pytest.raises(FinanceValidationError):
            strict_get_list(None, source="buy_signals")

    def test_missing_phase_results_raises(self):
        """Should raise when phase results list is None."""
        with pytest.raises(FinanceValidationError):
            strict_get_list(None, source="phase_results")


class TestPriceValidationFailFast:
    """Test that price data validation fails fast."""

    def test_zero_price_raises(self):
        """Should raise for zero price."""
        with pytest.raises(FinanceValidationError):
            strict_get_float(0.0, source="close_price", context="SPY")

    def test_negative_price_raises(self):
        """Should raise for negative price."""
        with pytest.raises(FinanceValidationError):
            strict_get_float(-10.0, source="close_price", context="AAPL")

    def test_missing_price_raises(self):
        """Should raise for missing price."""
        with pytest.raises(FinanceValidationError):
            strict_get_float(None, source="close_price", context="GOOGL")


class TestPositionSizingValidation:
    """Test position sizing validation."""

    def test_zero_position_size_raises(self):
        """Should raise for zero position size."""
        with pytest.raises(FinanceValidationError):
            strict_get_float(0.0, source="position_size", context="Entry order")

    def test_negative_position_size_raises(self):
        """Should raise for negative position size."""
        with pytest.raises(FinanceValidationError):
            strict_get_float(-100.0, source="position_size", context="Entry order")

    def test_valid_position_size_accepted(self):
        """Should accept valid position size."""
        result = strict_get_float(100.0, source="position_size", context="Entry order")
        assert result == 100.0


class TestDataAvailabilityVsZero:
    """Test that missing data is distinct from zero data."""

    def test_none_vs_zero_dividend(self):
        """None dividend (missing) should fail; 0 dividend should fail too without explicit flag."""
        with pytest.raises(FinanceValidationError):
            strict_get_float(None, source="dividend")
        with pytest.raises(FinanceValidationError):
            strict_get_float(0.0, source="dividend")

    def test_none_vs_zero_count(self):
        """None count (missing) should fail; 0 count should pass with flag."""
        with pytest.raises(FinanceValidationError):
            strict_get_int(None, source="entry_count", allow_zero=True)
        # Zero should pass for counts
        result = strict_get_int(0, source="entry_count", allow_zero=True)
        assert result == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
