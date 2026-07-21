#!/usr/bin/env python3
"""Regression test for MarketExposure's factor-weight-sum invariant.

Guards against silent drift: if a future edit changes one W_* class constant without
updating the others, the composite score would no longer mean "0-100" with nothing in
the pipeline catching it. MarketExposure._validate_weights() runs at __init__ time to
fail fast on that.
"""

import pytest

from algo.risk.market_exposure import MarketExposure


class TestMarketExposureWeightSum:
    def test_current_weights_sum_to_100(self):
        MarketExposure()  # must not raise

    def test_weights_are_the_documented_12_factors(self):
        weights = [
            MarketExposure.W_TREND_30WK,
            MarketExposure.W_SPY_MOMENTUM,
            MarketExposure.W_BREADTH_200,
            MarketExposure.W_SELLING_PRESSURE,
            MarketExposure.W_VIX,
            MarketExposure.W_CREDIT_SPREAD,
            MarketExposure.W_PUT_CALL,
            MarketExposure.W_NEW_HIGHS_LOWS,
            MarketExposure.W_AD_LINE,
            MarketExposure.W_BREADTH_50,
            MarketExposure.W_NAAIM,
            MarketExposure.W_AAII,
        ]
        assert len(weights) == 12
        assert sum(weights) == 100

    def test_drifted_weight_sum_raises(self, monkeypatch):
        monkeypatch.setattr(MarketExposure, "W_AAII", MarketExposure.W_AAII + 1)
        with pytest.raises(ValueError, match="must sum to exactly 100"):
            MarketExposure()

    def test_drifted_weight_sum_below_100_raises(self, monkeypatch):
        monkeypatch.setattr(MarketExposure, "W_TREND_30WK", MarketExposure.W_TREND_30WK - 5)
        with pytest.raises(ValueError, match="must sum to exactly 100"):
            MarketExposure()
