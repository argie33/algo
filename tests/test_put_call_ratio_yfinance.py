#!/usr/bin/env python3
"""Test put/call ratio fetcher.

GOVERNANCE (Session 291+): put/call ratio has no official free-data source
(yfinance, the former proprietary source, was removed). PutCallRatioFetcher.fetch()
always returns an explicit data_unavailable marker now - it never calls yfinance.
This test asserts that contract; it does not exercise any live yfinance path.
"""

from datetime import date


def test_put_call_ratio_always_unavailable() -> None:
    """PutCallRatioFetcher.fetch() must return an explicit data_unavailable marker."""
    from loaders.market_health_fetchers import PutCallRatioFetcher

    fetcher = PutCallRatioFetcher()
    eval_date = date.today()
    result = fetcher.fetch(eval_date)

    assert isinstance(result, dict)
    assert result.get("data_unavailable") is True
    assert result.get("eval_date") == eval_date.isoformat()
    assert "reason" in result
