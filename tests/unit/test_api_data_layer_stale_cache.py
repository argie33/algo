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
