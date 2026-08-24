#!/usr/bin/env python3
"""Regression test: load_market_status_daily.py's _compute_market_sentiment() must actually
compute sentiment_score from bullish_pct/bearish_pct, not leave it permanently None.

BUG FOUND 2026-08-24 (goal session logic-soundness audit): sentiment_score was
unconditionally None despite the code's own comment already claiming "computed from
bull/bear/neutral if available" - no computation ever happened. The only real consumer
(lambda/api/routes/algo_handlers/market.py's /api/algo/market-sentiment endpoint) fails
fast on sentiment_score is None (503 "incomplete_data"), so that endpoint would 503 on
every call regardless of whether AAII bullish/bearish data was actually available.
"""

from datetime import date
from unittest.mock import MagicMock

from loaders.load_market_status_daily import MarketStatusDailyLoader


def _make_loader() -> MarketStatusDailyLoader:
    return MarketStatusDailyLoader.__new__(MarketStatusDailyLoader)


class _FakeCursor:
    def __init__(self, aaii_row) -> None:
        self._aaii_row = aaii_row

    def execute(self, query, params=None) -> None:
        pass

    def fetchone(self):
        return self._aaii_row


class _FakeDatabaseContext:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, *a):
        return False


def test_bullish_leaning_sentiment_scores_above_50(monkeypatch) -> None:
    import loaders.load_market_status_daily as mod

    loader = _make_loader()
    loader._persist_market_sentiment = MagicMock()
    # AAII stores fractions (0-1): 60% bullish, 20% bearish, 20% neutral
    cursor = _FakeCursor((date(2026, 8, 24), 0.60, 0.20, 0.20))
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    result = loader._compute_market_sentiment(date(2026, 8, 24), {"vix_level": 18.0, "put_call_ratio": 0.9})

    assert result["bullish_pct"] == 60.0
    assert result["bearish_pct"] == 20.0
    # 50 + (60 - 20) / 2 = 70
    assert result["sentiment_score"] == 70.0


def test_bearish_leaning_sentiment_scores_below_50(monkeypatch) -> None:
    import loaders.load_market_status_daily as mod

    loader = _make_loader()
    loader._persist_market_sentiment = MagicMock()
    cursor = _FakeCursor((date(2026, 8, 24), 0.20, 0.60, 0.20))
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    result = loader._compute_market_sentiment(date(2026, 8, 24), {"vix_level": 18.0, "put_call_ratio": 1.1})

    # 50 + (20 - 60) / 2 = 30
    assert result["sentiment_score"] == 30.0


def test_balanced_sentiment_scores_exactly_50(monkeypatch) -> None:
    import loaders.load_market_status_daily as mod

    loader = _make_loader()
    loader._persist_market_sentiment = MagicMock()
    cursor = _FakeCursor((date(2026, 8, 24), 0.33, 0.33, 0.34))
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    result = loader._compute_market_sentiment(date(2026, 8, 24), {"vix_level": 18.0, "put_call_ratio": 1.0})

    assert result["sentiment_score"] == 50.0


def test_no_aaii_data_leaves_sentiment_score_none(monkeypatch) -> None:
    """AAII data unavailable within the 14-day window -> bullish_pct/bearish_pct stay None,
    sentiment_score must also stay None rather than crash or fabricate a value (fear_greed_index
    from VIX is still available independently, so data_unavailable stays False overall)."""
    import loaders.load_market_status_daily as mod

    loader = _make_loader()
    loader._persist_market_sentiment = MagicMock()
    cursor = _FakeCursor(None)
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    result = loader._compute_market_sentiment(date(2026, 8, 24), {"vix_level": 18.0, "put_call_ratio": 1.0})

    assert result["bullish_pct"] is None
    assert result["sentiment_score"] is None
    assert result["data_unavailable"] is False
    assert result["fear_greed_index"] is not None
