"""Test that data extraction functions properly distinguish errors from missing data."""

import pytest

from dashboard.data_extraction import (
    DataExtractionError,
    extract_data_or_empty,
    extract_field,
    extract_items_list,
)


class TestExtractField:
    """Test extract_field() error handling."""

    def test_raises_on_error_response(self):
        """Should raise DataExtractionError when _error is present."""
        error_response = {"_error": "API failed"}
        with pytest.raises(DataExtractionError, match="Error in response"):
            extract_field(error_response, "some_field")

    def test_returns_default_on_missing_field(self):
        """Should return default when field is missing (no error)."""
        valid_response = {"other_field": "value"}
        result = extract_field(valid_response, "missing_field", default="fallback")
        assert result == "fallback"

    def test_returns_field_value(self):
        """Should return field value when present and no error."""
        valid_response = {"my_field": "my_value"}
        result = extract_field(valid_response, "my_field")
        assert result == "my_value"

    def test_handles_non_dict_input(self):
        """Should return default for non-dict inputs."""
        assert extract_field(None, "field", default="fallback") == "fallback"
        assert extract_field("not a dict", "field", default="fallback") == "fallback"


class TestExtractItemsList:
    """Test extract_items_list() error handling."""

    def test_raises_on_error_response(self):
        """Should raise DataExtractionError when _error is present."""
        error_response = {"_error": "API failed"}
        with pytest.raises(DataExtractionError, match="Error in response"):
            extract_items_list(error_response)

    def test_raises_on_missing_items(self):
        """Should raise DataExtractionError when items key missing (critical financial data)."""
        valid_response = {"other_key": "value"}
        with pytest.raises(DataExtractionError, match="missing required 'items' field"):
            extract_items_list(valid_response)

    def test_returns_items_when_present(self):
        """Should return items when present and no error."""
        valid_response = {"items": ["item1", "item2"]}
        result = extract_items_list(valid_response)
        assert result == ["item1", "item2"]

    def test_raises_for_non_list_items(self):
        """Should raise DataExtractionError if items exists but is not a list."""
        valid_response = {"items": "not a list"}
        with pytest.raises(DataExtractionError, match="must be a list"):
            extract_items_list(valid_response)

    def test_raises_on_non_dict_input(self):
        """Should raise DataExtractionError for non-dict inputs."""
        with pytest.raises(DataExtractionError, match="Expected dict response"):
            extract_items_list(None)
        with pytest.raises(DataExtractionError, match="Expected dict response"):
            extract_items_list("not a dict")


class TestExtractDataOrEmpty:
    """Test extract_data_or_empty() error handling."""

    def test_raises_on_error_response_dict(self):
        """Should raise DataExtractionError when _error is present."""
        error_response = {"_error": "API failed"}
        with pytest.raises(DataExtractionError, match="Error in response"):
            extract_data_or_empty(error_response, dict)

    def test_raises_on_missing_data_even_with_allow_empty(self):
        """Should raise even with allow_empty=True (allow_empty is deprecated for financial data)."""
        with pytest.raises(DataExtractionError, match="Required data is missing"):
            extract_data_or_empty(None, dict, allow_empty=True)

    def test_returns_data_when_present(self):
        """Should return data when present and no error."""
        valid_data = {"key": "value"}
        result = extract_data_or_empty(valid_data, dict)
        assert result == {"key": "value"}

    def test_raises_on_missing_list_data(self):
        """Should raise when list data is missing (financial data must not have empty defaults)."""
        with pytest.raises(DataExtractionError, match="Required data is missing"):
            extract_data_or_empty(None, list, allow_empty=True)

    def test_returns_list_data_when_present(self):
        """Should return list data when present and no error."""
        valid_data = [1, 2, 3]
        result = extract_data_or_empty(valid_data, list)
        assert result == [1, 2, 3]

    def test_raises_for_wrong_type(self):
        """Should raise when data type doesn't match (financial data type validation is strict)."""
        with pytest.raises(DataExtractionError, match="Data type mismatch"):
            extract_data_or_empty("string", dict)
        with pytest.raises(DataExtractionError, match="Data type mismatch"):
            extract_data_or_empty({"data": "dict"}, list)
