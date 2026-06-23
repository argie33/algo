#!/usr/bin/env python3
"""Test that verifies 503 stale cache fallback doesn't permanently block API recovery.

This test ensures that when _get_markets_cached() falls back to stale data on a 503,
the stale data is NOT cached in _markets_cache, so the next call will retry the API
and immediately recover when the API comes back online.

Without the fix: _markets_cache would be set to stale data, so next call returns
                 stale without trying API (API recovery is missed)
With the fix:    _markets_cache is NOT set on stale fallback, so next call retries
                 API (immediate recovery when API comes back)
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.api_data_layer import (
    _response_cache,
    _response_cache_lock,
)


def test_stale_cache_not_cached_in_memory():
    """Verify that stale cache fallback is NOT stored in _markets_cache.

    Scenario:
    1. First call: API returns 503 → falls back to stale cache and returns it
    2. Clear the API response cache to simulate API recovery (next refresh window)
    3. Second call: API is back online and returns good data
    4. Verify we got the fresh data, not the stale data from before

    Without the fix: _markets_cache would have stale data, blocking API retry
    With the fix:    _markets_cache is empty, so we call API and get fresh data
    """
    from dashboard.fetchers_market import _get_markets_cached, _markets_cache, _markets_lock

    good_market_data = {
        "current": {
            "exposure_pct": 65.0,
            "raw_score": 0.65,
            "regime": "healthy_uptrend",
            "factors": {"momentum": 0.7},
            "spy_close": 500.5,
            "halt_reasons": [],
            "distribution_days": 0,
        },
        "market_health": {
            "vix_level": 15.2,
            "market_stage": "accumulation",
            "market_trend": "up",
            "spy_change_pct": 1.5,
            "up_volume_percent": 60.0,
            "advance_decline_ratio": 1.5,
            "new_highs_count": 150,
            "new_lows_count": 20,
            "put_call_ratio": 0.85,
            "breadth_momentum_10d": 0.7,
            "yield_curve_slope": 0.5,
            "fed_rate_environment": "neutral",
        },
    }

    recovered_data = {
        "current": {
            "exposure_pct": 70.0,  # Different value to verify fresh data
            "raw_score": 0.70,
            "regime": "confirmed_uptrend",  # Changed regime
            "factors": {"momentum": 0.8},
            "spy_close": 505.5,  # Higher SPY
            "halt_reasons": [],
            "distribution_days": 1,
        },
        "market_health": {
            "vix_level": 14.0,  # Lower VIX
            "market_stage": "markup",  # Different stage
            "market_trend": "up",
            "spy_change_pct": 2.0,
            "up_volume_percent": 65.0,
            "advance_decline_ratio": 1.8,
            "new_highs_count": 200,
            "new_lows_count": 10,
            "put_call_ratio": 0.75,
            "breadth_momentum_10d": 0.8,
            "yield_curve_slope": 0.6,
            "fed_rate_environment": "accommodative",
        },
    }

    # Setup: Pre-populate cache with good data
    with _response_cache_lock:
        _response_cache.clear()
        _response_cache["/api/algo/markets"] = {
            "data": good_market_data,
            "timestamp": datetime.now(timezone.utc),
        }

    # Clear in-memory cache
    with _markets_lock:
        _markets_cache.clear()

    # Step 1: First call - API returns 503, falls back to stale cache
    call_count = 0

    def mock_api_call_503(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return {
            "_error": "API error 503 after 4 attempts",
            "_is_transient_503": True,
        }

    with patch("dashboard.fetchers_market.api_call", side_effect=mock_api_call_503):
        result1 = _get_markets_cached()

    # Verify we got stale data with the _data_stale flag
    assert result1.get("_data_stale") is True, "Should have stale flag"
    assert result1.get("current", {}).get("spy_close") == 500.5, "Should have old SPY value"
    assert call_count == 1, f"Should have called API once, got {call_count}"

    # Verify _markets_cache is EMPTY (not populated with stale data)
    # This is the key assertion - stale data should NOT be in the in-memory cache
    assert "result" not in _markets_cache, "Stale data should NOT be cached in _markets_cache"

    # Step 2: Clear in-memory cache for next scenario, simulate API recovery
    # Update the response cache with fresh data (simulating API recovery)
    with _response_cache_lock:
        _response_cache["/api/algo/markets"] = {
            "data": recovered_data,
            "timestamp": datetime.now(timezone.utc),
        }

    # Step 3: Second call - API is now back online with fresh data
    call_count = 0

    def mock_api_call_success(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Return the recovered data (simulating API recovery)
        return recovered_data

    with patch("dashboard.fetchers_market.api_call", side_effect=mock_api_call_success):
        result2 = _get_markets_cached()

    # Verify we got FRESH data (not the old stale data)
    assert result2.get("_data_stale") is not True, "Should NOT have stale flag on fresh data"
    assert result2.get("current", {}).get("spy_close") == 505.5, "Should have NEW SPY value (505.5)"
    assert result2.get("current", {}).get("regime") == "confirmed_uptrend", "Should have NEW regime"
    assert call_count == 1, f"Should have called API again for fresh data, got {call_count}"

    print(
        "[OK] Stale cache fallback correctly allows API recovery:\n"
        f"  Step 1: 503 -> returned stale data with SPY={result1.get('current', {}).get('spy_close')}\n"
        f"  Step 2: API recovered -> returned fresh data with SPY={result2.get('current', {}).get('spy_close')}\n"
        "  Key: Stale data was NOT cached in _markets_cache, allowing next call to retry API"
    )


if __name__ == "__main__":
    print("=" * 70)
    print("Test: 503 Stale Cache Doesn't Block API Recovery")
    print("=" * 70)
    test_stale_cache_not_cached_in_memory()
    print("\n[PASS] Fix verified: stale cache fallback allows API recovery!")
    print("=" * 70)
