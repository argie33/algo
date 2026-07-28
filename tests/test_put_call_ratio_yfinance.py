#!/usr/bin/env python3
"""Test put/call ratio fetcher.

GOVERNANCE: no official free put/call feed exists (real CBOE data is a paid feed), so
PutCallRatioFetcher deliberately keeps a best-effort yfinance SPY options-chain fetch as its
one real source - same "unofficial but real, transparently documented" tradeoff as the OHLCV
yfinance residual fallback in utils/data/source_router.py. It is NOT dead/disabled code: real
values it returns feed an 8%-weighted market exposure factor
(algo/risk/factors/put_call_ratio_factor.py). A prior version of this docstring claimed
fetch() "always returns data_unavailable... never calls yfinance" - that was false when
written and stayed false uncorrected for a while (corrected 2026-07-27, see
steering/DATA_LOADERS.md). This test exercises the real contract: either a live-fetched value
or an explicit data_unavailable marker on failure (no silent fallback to a fake number).
"""

from datetime import date


def test_put_call_ratio_returns_real_value_or_explicit_unavailable_marker() -> None:
    """PutCallRatioFetcher.fetch() returns a real yfinance-derived ratio or an explicit
    data_unavailable marker - never a silent/fabricated value.
    """
    from loaders.market_health_fetchers import PutCallRatioFetcher

    fetcher = PutCallRatioFetcher()
    eval_date = date.today()
    result = fetcher.fetch(eval_date)

    assert isinstance(result, dict)
    # Either data_unavailable=True with reason, or data_unavailable=False with put_call_ratio
    if result.get("data_unavailable"):
        assert "reason" in result
    else:
        assert result.get("put_call_ratio") is not None
        assert isinstance(result.get("put_call_ratio"), (int, float))
