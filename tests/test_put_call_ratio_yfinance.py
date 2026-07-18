#!/usr/bin/env python3
"""Test put/call ratio fetching from yfinance options chain."""

import logging
from datetime import date, timedelta

import pytest

logger = logging.getLogger(__name__)


def test_put_call_ratio_yfinance() -> None:
    """Test fetching put/call ratio from yfinance SPY options chain."""
    from loaders.market_health_fetchers import PutCallRatioFetcher

    fetcher = PutCallRatioFetcher()

    # Test today's put/call ratio
    eval_date = date.today()
    result = fetcher.fetch(eval_date)

    print(f"\n{'=' * 60}")
    print("Put/Call Ratio Test Results")
    print(f"{'=' * 60}")
    print(f"Date: {eval_date}")
    print(f"Result type: {type(result).__name__}")
    print(f"Result: {result}")

    # Verify result structure
    if isinstance(result, (float, int)):
        print(f"[PASS] Got float result: {result:.4f}")
        assert 0.2 <= result <= 3.0, f"P/C ratio out of realistic range: {result}"
    elif isinstance(result, dict) and result.get("data_unavailable"):
        print(f"[WARN] Data unavailable: {result.get('reason')}")
        pytest.skip("Put/call ratio data unavailable")
    else:
        pytest.fail(f"Unexpected result type: {type(result)}")


@pytest.mark.skip(reason="Integration test requires real market data and database connection")
def test_put_call_in_market_health() -> None:
    """Test put/call ratio integration in market status loader (consolidated).

    Note: MarketStatusDailyLoader (Phase 2) replaces MarketHealthDailyLoader.
    It consolidates market_health_daily + market_exposure_daily + market_sentiment.

    This test requires:
    - Database connection to market_health_daily table
    - Real market data (not mock data)
    - SPY options chain data from yfinance

    Marked as skip - use only for manual integration testing.
    """
    from loaders.load_market_status_daily import MarketStatusDailyLoader

    loader = MarketStatusDailyLoader()
    start_date = date.today() - timedelta(days=5)
    rows = loader.fetch_incremental(symbol="SPY", since=start_date)

    assert rows, "No rows returned from loader"

    latest = rows[-1]
    pcr = latest.get("put_call_ratio")
    print(f"Latest PCR: {pcr}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("\nTest 1: Direct yfinance options chain fetch")
    test1 = test_put_call_ratio_yfinance()

    print("\n\nTest 2: Integration with market health loader")
    test2 = test_put_call_in_market_health()

    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"Direct fetch: {('[PASS]' if test1 else '[WARN]')}")
    print(f"Integration: {('[PASS]' if test2 else '[FAIL]')}")
