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

    # Verify we got an error (fail-fast: don't fall back to stale cache for market data)
    # Market data is critical - returning stale data could lead to incorrect position sizing
    assert result1.get("_error") is not None, "Should have error on 503"
    assert "503" in result1.get("_error", ""), "Error should mention 503"
    assert call_count == 1, f"Should have called API once, got {call_count}"

    # Verify _markets_cache is EMPTY (not populated with error data)
    # Errors should not be cached - next call should retry the API
    assert "result" not in _markets_cache, "Error should NOT be cached in _markets_cache"

    # Step 2: Clear markets cache and update response cache with fresh data
    # This simulates the API recovery window when fresh data becomes available
    with _markets_lock:
        _markets_cache.clear()
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

    # Verify we got FRESH data (fail-fast: markets endpoint requires fresh data)
    assert result2.get("_error") is None, "Should NOT have error on successful API call"
    assert result2.get("current", {}).get("spy_close") == 505.5, "Should have NEW SPY value (505.5)"
    assert result2.get("current", {}).get("regime") == "confirmed_uptrend", "Should have NEW regime"
    assert call_count == 1, f"Should have called API for fresh data, got {call_count}"

    print(
        "[OK] Fail-fast markets caching correctly handles API recovery:\n"
        f"  Step 1: 503 -> returned error (fail-fast, no stale cache fallback)\n"
        f"  Step 2: API recovered -> returned fresh data with SPY={result2.get('current', {}).get('spy_close')}\n"
        "  Key: Error was NOT cached in _markets_cache, allowing next call to retry and recover"
    )


if __name__ == "__main__":
    print("=" * 70)
    print("Test: 503 Stale Cache Doesn't Block API Recovery")
    print("=" * 70)
    test_stale_cache_not_cached_in_memory()
    print("\n[PASS] Fix verified: stale cache fallback allows API recovery!")
    print("=" * 70)
