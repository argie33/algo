#!/usr/bin/env python3
"""Regression test for StockScoresLoader._get_momentum_metrics wiring price_vs_sma_50/200
into the momentum score (loaders/load_stock_scores.py).

_score_momentum has always had an 8%-weighted "SMA positioning" component, and the scores
dashboard (StockScoreAccordion.jsx MOMENTUM_SCHEMA) has advertised price_vs_sma_50/200 as
real `used: true, weight: '8% avg'` inputs since the 2026-08-04 momentum audit. But
_get_momentum_metrics's technical_data_daily cache query only ever selected rsi_14/macd -
never sma_50/sma_200/close - so metrics.get("price_vs_sma_50"/"price_vs_sma_200") was
unconditionally None for every symbol, every run. 8% of the documented momentum_score
formula was structurally dead in every real score ever computed. Fixed by extending the
cache query and computing the decimal-fraction (close-sma)/sma ratio _score_momentum's
formula expects (NOT the *100 percentage scale the scores API computes for display).
"""

import pytest

from loaders.load_stock_scores import StockScoresLoader


class TestMomentumMetricsSmaWiring:
    def test_price_vs_sma_computed_from_technical_cache(self):
        loader = StockScoresLoader()
        # tech_row = (rsi_14, macd, sma_50, sma_200, close)
        loader._technical_cache = {"AAPL": (65.0, 1.2, 190.0, 180.0, 200.0)}
        loader._momentum_cache = {"AAPL": (5.0, 10.0, 15.0, 20.0, False)}

        metrics = loader._get_momentum_metrics(None, "AAPL")

        assert metrics["price_vs_sma_50"] == pytest.approx((200.0 - 190.0) / 190.0)
        assert metrics["price_vs_sma_200"] == pytest.approx((200.0 - 180.0) / 180.0)

    def test_missing_sma_data_yields_none_not_crash(self):
        loader = StockScoresLoader()
        loader._technical_cache = {"AAPL": (65.0, 1.2, None, None, 200.0)}
        loader._momentum_cache = {"AAPL": (5.0, 10.0, 15.0, 20.0, False)}

        metrics = loader._get_momentum_metrics(None, "AAPL")

        assert metrics["price_vs_sma_50"] is None
        assert metrics["price_vs_sma_200"] is None

    def test_missing_technical_row_yields_none_not_crash(self):
        loader = StockScoresLoader()
        loader._technical_cache = {}
        loader._momentum_cache = {"AAPL": (5.0, 10.0, 15.0, 20.0, False)}

        metrics = loader._get_momentum_metrics(None, "AAPL")

        assert metrics["price_vs_sma_50"] is None
        assert metrics["price_vs_sma_200"] is None

    def test_sma_positioning_actually_moves_momentum_score(self):
        """End-to-end: with identical momentum/RSI/MACD inputs, a symbol trading well
        above its SMAs must score higher than one trading well below - proving the 8%
        SMA weight is now live, not dead, in _score_momentum."""
        loader = StockScoresLoader()
        base = {
            "momentum_1m": 0.0,
            "momentum_3m": 0.0,
            "momentum_6m": 0.0,
            "momentum_12m": 0.0,
            "rsi_14": 50.0,
            "macd": 0.0,
        }
        above_sma = dict(base, price_vs_sma_50=0.10, price_vs_sma_200=0.10)
        below_sma = dict(base, price_vs_sma_50=-0.10, price_vs_sma_200=-0.10)

        score_above = loader._score_momentum(above_sma, "ABOVE")
        score_below = loader._score_momentum(below_sma, "BELOW")

        assert isinstance(score_above, float)
        assert isinstance(score_below, float)
        assert score_above > score_below
