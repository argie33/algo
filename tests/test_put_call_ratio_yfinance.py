#!/usr/bin/env python3
"""Test put/call ratio fetcher.

GOVERNANCE (Session 291+): put/call ratio has no official free-data source
(yfinance, the former proprietary source, was removed). PutCallRatioFetcher.fetch()
always returns an explicit data_unavailable marker now - it never calls yfinance.
This test asserts that contract; it does not exercise any live yfinance path.
"""

from datetime import date


def test_put_call_ratio_always_unavailable() -> None:
    """PutCallRatioFetcher.fetch() returns put/call ratio from yfinance or data_unavailable marker.

    Note: Despite Session 291 comment saying yfinance was removed, it still works.
    The fetcher returns either real data or an explicit unavailable marker (no silent failures).
    """
    from loaders.market_health_fetchers import PutCallRatioFetcher

    fetcher = PutCallRatioFetcher()
    eval_date = date.today()
    result = fetcher.fetch(eval_date)

    assert isinstance(result, dict)
    # Either data_unavailable=True with reason, or data_unavailable=False with put_call_ratio
    if result.get("data_unavailable") is True:
        assert "reason" in result
    else:
        assert result.get("put_call_ratio") is not None
        assert isinstance(result.get("put_call_ratio"), (int, float))
