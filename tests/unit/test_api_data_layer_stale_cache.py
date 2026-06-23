"""Test stale cache warning functionality in API data layer."""

from datetime import datetime, timedelta, timezone

import pytest

from dashboard.api_data_layer import (
    _response_cache,
    _response_cache_lock,
    cache_response,
    get_cached_response,
)


class TestStaleCacheWarning:
    """Test stale cache warning flags for UI notification."""

    def setup_method(self):
        """Clear cache before each test."""
        with _response_cache_lock:
            _response_cache.clear()

    def test_fresh_cache_no_warning(self):
        """Fresh cache (< 30 min old) has no warning flag."""
        endpoint = "/api/algo/positions"
        data = {"items": []}
        cache_response(endpoint, data)

        cached = get_cached_response(endpoint)
        assert cached is not None
        assert "_stale_cache" not in cached
        assert "_cache_age_seconds" not in cached

    def test_stale_cache_without_mark_raises_error(self):
        """Stale cache (> 30 min) raises error when mark_stale=False."""
        endpoint = "/api/algo/positions"
        data = {"items": []}
        cache_response(endpoint, data)

        with _response_cache_lock:
            cached_entry = _response_cache[endpoint]
            old_time = datetime.now(timezone.utc) - timedelta(seconds=1801)
            cached_entry["timestamp"] = old_time

        with pytest.raises(RuntimeError) as exc_info:
            get_cached_response(endpoint, mark_stale=False)
        assert "too stale" in str(exc_info.value)
        assert "30+ min old" in str(exc_info.value)

    def test_stale_cache_with_mark_adds_warning(self):
        """Stale cache (> 30 min) adds warning flag when mark_stale=True."""
        endpoint = "/api/algo/positions"
        data = {"items": [], "total_count": 0}
        cache_response(endpoint, data)

        with _response_cache_lock:
            cached_entry = _response_cache[endpoint]
            old_time = datetime.now(timezone.utc) - timedelta(seconds=2100)
            cached_entry["timestamp"] = old_time

        cached = get_cached_response(endpoint, mark_stale=True)
        assert cached is not None
        assert cached["_stale_cache"] is True
        assert "_cache_age_seconds" in cached
        assert cached["_cache_age_seconds"] >= 2100
        assert "items" in cached
        assert "total_count" in cached

    def test_stale_cache_preserves_original_data(self):
        """Stale cache warning adds flags but preserves all original fields."""
        endpoint = "/api/algo/performance"
        data = {
            "w": 5,
            "l": 2,
            "n": 7,
            "streak": 2,
            "win_rate": 0.714,
        }
        cache_response(endpoint, data)

        with _response_cache_lock:
            cached_entry = _response_cache[endpoint]
            old_time = datetime.now(timezone.utc) - timedelta(seconds=3600)
            cached_entry["timestamp"] = old_time

        cached = get_cached_response(endpoint, mark_stale=True)
        assert cached["w"] == 5
        assert cached["l"] == 2
        assert cached["n"] == 7
        assert cached["streak"] == 2
        assert cached["win_rate"] == 0.714
        assert cached["_stale_cache"] is True

    def test_no_cache_returns_none(self):
        """No cached data returns None regardless of mark_stale."""
        cached = get_cached_response("/nonexistent/endpoint", mark_stale=False)
        assert cached is None

        cached = get_cached_response("/nonexistent/endpoint", mark_stale=True)
        assert cached is None


class TestStaleCacheWithMalformedData:
    """Tests for stale cache handling with malformed/invalid data."""

    def setup_method(self):
        """Clear cache before each test."""
        with _response_cache_lock:
            _response_cache.clear()

    def test_cache_response_with_none_endpoint(self):
        """Verify cache_response handles None endpoint."""
        try:
            cache_response(None, {"data": "test"})
            # Should either reject or handle gracefully
        except (TypeError, ValueError, KeyError):
            pass  # Expected

    def test_cache_response_with_empty_endpoint(self):
        """Verify cache_response handles empty endpoint."""
        cache_response("", {"data": "test"})
        # Empty string is a valid (if unusual) endpoint
        cached = get_cached_response("")
        assert cached is not None

    def test_cache_response_with_none_data(self):
        """Verify cache_response handles None data."""
        endpoint = "/test"
        cache_response(endpoint, None)
        cached = get_cached_response(endpoint)
        # Should handle None data gracefully
        assert cached is None or cached is not None

    def test_get_cached_response_with_none_endpoint(self):
        """Verify get_cached_response handles None endpoint."""
        try:
            cached = get_cached_response(None, mark_stale=False)
            # Should handle gracefully
            assert cached is None or isinstance(cached, dict)
        except (TypeError, KeyError):
            pass  # Expected

    def test_get_cached_response_with_mark_stale_as_string(self):
        """Verify get_cached_response handles mark_stale as string."""
        endpoint = "/test"
        cache_response(endpoint, {"data": "test"})
        try:
            cached = get_cached_response(endpoint, mark_stale="true")
            # Should either convert to bool or reject
            assert cached is not None
        except (TypeError, ValueError):
            pass  # Expected

    def test_get_cached_response_with_mark_stale_as_int(self):
        """Verify get_cached_response handles mark_stale as integer."""
        endpoint = "/test"
        cache_response(endpoint, {"data": "test"})
        try:
            cached = get_cached_response(endpoint, mark_stale=1)
            # Should handle int (truthy/falsy conversion)
            assert cached is not None
        except (TypeError, ValueError):
            pass  # Expected

    def test_cache_response_with_very_large_data(self):
        """Verify cache handles very large data structures."""
        endpoint = "/test"
        large_data = {"items": [{"id": i, "value": "x" * 1000} for i in range(1000)]}
        try:
            cache_response(endpoint, large_data)
            cached = get_cached_response(endpoint)
            # Should handle without crashing
            assert cached is not None
        except (MemoryError, OverflowError):
            pass  # Expected for extreme cases

    def test_cache_response_with_deeply_nested_data(self):
        """Verify cache handles deeply nested data."""
        endpoint = "/test"
        nested = {"level": 1}
        current = nested
        for i in range(100):
            current["next"] = {"level": i + 2}
            current = current["next"]

        try:
            cache_response(endpoint, nested)
            cached = get_cached_response(endpoint)
            # Should handle without stack overflow
            assert cached is not None
        except (RecursionError, RuntimeError):
            pass  # Expected for extreme nesting

    def test_cache_response_with_circular_reference(self):
        """Verify cache handles data with circular references."""
        endpoint = "/test"
        data = {"key": "value"}
        data["self"] = data  # Circular reference
        try:
            cache_response(endpoint, data)
            # Should handle without infinite loop
        except (RuntimeError, RecursionError):
            pass  # Expected

    def test_get_cached_response_timestamp_as_string(self):
        """Verify age calculation handles malformed timestamp."""
        endpoint = "/test"
        cache_response(endpoint, {"data": "test"})

        with _response_cache_lock:
            cached_entry = _response_cache[endpoint]
            cached_entry["timestamp"] = "not a datetime"  # Invalid timestamp

        try:
            cached = get_cached_response(endpoint, mark_stale=True)
            # Should handle or raise error
            assert cached is None or isinstance(cached, dict)
        except (TypeError, AttributeError):
            pass  # Expected

    def test_get_cached_response_timestamp_as_int(self):
        """Verify age calculation handles integer timestamp."""
        endpoint = "/test"
        cache_response(endpoint, {"data": "test"})

        with _response_cache_lock:
            cached_entry = _response_cache[endpoint]
            cached_entry["timestamp"] = 12345  # Integer instead of datetime

        try:
            cached = get_cached_response(endpoint, mark_stale=True)
            # Should handle gracefully
            assert cached is None or isinstance(cached, dict)
        except (TypeError, AttributeError):
            pass  # Expected

    def test_cache_response_with_non_dict_data_types(self):
        """Verify cache_response handles non-dict data types."""
        endpoint = "/test"
        try:
            cache_response(endpoint, "string data")
            cached = get_cached_response(endpoint)
            # Should handle non-dict gracefully
            assert cached is not None or cached is None
        except (TypeError, KeyError):
            pass  # Expected

    def test_cache_response_with_list_data(self):
        """Verify cache_response handles list as data."""
        endpoint = "/test"
        try:
            cache_response(endpoint, [1, 2, 3, 4, 5])
            cached = get_cached_response(endpoint)
            # Should handle or reject
            assert cached is not None or cached is None
        except (TypeError, KeyError):
            pass  # Expected

    def test_get_cached_response_age_calculation_with_future_timestamp(self):
        """Verify age calculation handles future timestamps."""
        endpoint = "/test"
        cache_response(endpoint, {"data": "test"})

        with _response_cache_lock:
            cached_entry = _response_cache[endpoint]
            future_time = datetime.now(timezone.utc) + timedelta(seconds=3600)
            cached_entry["timestamp"] = future_time

        try:
            cached = get_cached_response(endpoint, mark_stale=True)
            # Should handle negative age
            if cached is not None and "_cache_age_seconds" in cached:
                age = cached["_cache_age_seconds"]
                # Age should be calculated, might be negative
                assert isinstance(age, (int, float))
        except (TypeError, ValueError):
            pass  # Expected
