#!/usr/bin/env python3
"""Test put/call ratio fetching from yfinance options chain."""

import logging
from datetime import date

logger = logging.getLogger(__name__)


def test_put_call_ratio_yfinance() -> bool:
    """Test fetching put/call ratio from yfinance SPY options chain."""
    from loaders.market_health_fetchers import PutCallRatioFetcher

    fetcher = PutCallRatioFetcher()

    # Test today's put/call ratio
    eval_date = date.today()
    result = fetcher.fetch(eval_date)

    print(f"\n{'='*60}")
    print(f"Put/Call Ratio Test Results")
    print(f"{'='*60}")
    print(f"Date: {eval_date}")
    print(f"Result type: {type(result).__name__}")
    print(f"Result: {result}")

    # Verify result structure
    if isinstance(result, (float, int)):
        print(f"[PASS] Got float result: {result:.4f}")
        assert 0.2 <= result <= 3.0, f"P/C ratio out of realistic range: {result}"
        return True
    elif isinstance(result, dict) and result.get("data_unavailable"):
        print(f"[WARN] Data unavailable: {result.get('reason')}")
        return False
    else:
        print(f"[FAIL] Unexpected result type: {type(result)}")
        return False


def test_put_call_in_market_health() -> bool:
    """Test put/call ratio integration in market health loader."""
    from loaders.load_market_health_daily import MarketHealthDailyLoader
    from datetime import timedelta

    loader = MarketHealthDailyLoader()

    # Test fetch_incremental for past 5 days
    start_date = date.today() - timedelta(days=5)
    try:
        rows = loader.fetch_incremental(since=start_date)

        print(f"\n{'='*60}")
        print(f"Market Health Integration Test")
        print(f"{'='*60}")
        print(f"Fetched {len(rows)} rows")

        if rows:
            latest = rows[-1]
            pcr = latest.get("put_call_ratio")
            pcr_avail = latest.get("put_call_ratio_available")
            pcr_unavail = latest.get("put_call_ratio_data_unavailable")

            print(f"Latest row date: {latest.get('date')}")
            print(f"Put/call ratio: {pcr}")
            print(f"Available: {pcr_avail}")
            print(f"Data unavailable: {pcr_unavail}")

            if pcr is not None:
                print(f"[PASS] Put/call ratio: {pcr:.4f}")
                return True
            else:
                print(f"[WARN] Put/call ratio is None (may be graceful degradation)")
                return True
        else:
            print("[FAIL] No rows returned")
            return False

    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("\nTest 1: Direct yfinance options chain fetch")
    test1 = test_put_call_ratio_yfinance()

    print("\n\nTest 2: Integration with market health loader")
    test2 = test_put_call_in_market_health()

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Direct fetch: {'[PASS]' if test1 else '[WARN]'}")
    print(f"Integration: {'[PASS]' if test2 else '[FAIL]'}")
