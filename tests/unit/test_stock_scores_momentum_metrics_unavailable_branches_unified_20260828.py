#!/usr/bin/env python3
"""Regression test: StockScoresLoader._get_momentum_metrics treats "no momentum_metrics row"
and "momentum_metrics row present but data_unavailable=True" identically (loaders/load_stock_scores.py).

Before this fix, the two cases had opposite outcomes for the same real-world condition
(no usable price-return momentum for a symbol):
- row present, data_unavailable=True -> RSI/MACD/SMA still scored as a partial momentum signal.
- row absent entirely                -> hard data_unavailable marker, RSI/MACD/SMA discarded,
                                         even when available (Session 416 "no metric-class
                                         mixing" fix, applied to only one of the two branches).

Live-DB-verified 2026-08-28 (exclude_etfs=True universe, matching what this loader actually
processes): the "row absent" branch was dead code for the current universe (5,102/5,102 real
stocks already have a momentum_metrics row), so this closes a latent inconsistency rather than
changing any symbol's current live score - but it removes a landmine if the momentum_metrics
loader's universe and stock_scores' universe ever drift apart.
"""

import pytest

from loaders.load_stock_scores import StockScoresLoader


class TestMomentumMetricsUnavailableBranchesUnified:
    def test_row_present_data_unavailable_scores_partial_from_technical(self):
        loader = StockScoresLoader()
        loader._technical_cache = {"AAPL": (65.0, 1.2, 190.0, 180.0, 200.0, 5.0, 8.0, 12.0, 20.0)}
        loader._momentum_cache = {"AAPL": (None, None, None, None, True)}

        metrics = loader._get_momentum_metrics(None, "AAPL")

        assert metrics.get("data_unavailable") is not True
        assert metrics["momentum_1m"] is None
        assert metrics["momentum_3m"] is None
        assert metrics["rsi_14"] == pytest.approx(65.0)
        assert metrics["macd"] == pytest.approx(1.2)
        assert metrics["price_vs_sma_50"] is not None

    def test_row_absent_entirely_scores_partial_from_technical(self):
        """Symbol has no momentum_metrics row at all, but RSI/MACD/SMA are available -
        must now score a partial momentum signal, same as the row-present-unavailable case,
        instead of being discarded entirely."""
        loader = StockScoresLoader()
        loader._technical_cache = {"NEWCO": (72.0, -0.5, 50.0, 48.0, 55.0, 3.0, 6.0, 9.0, 15.0)}
        loader._momentum_cache = {}

        metrics = loader._get_momentum_metrics(None, "NEWCO")

        assert metrics.get("data_unavailable") is not True
        assert metrics["momentum_1m"] is None
        assert metrics["momentum_3m"] is None
        assert metrics["rsi_14"] == pytest.approx(72.0)
        assert metrics["macd"] == pytest.approx(-0.5)
        assert metrics["price_vs_sma_50"] is not None
        assert metrics["price_vs_sma_200"] is not None

    def test_row_absent_and_no_technical_data_returns_data_unavailable(self):
        loader = StockScoresLoader()
        loader._technical_cache = {}
        loader._momentum_cache = {}

        metrics = loader._get_momentum_metrics(None, "GHOST")

        assert metrics["data_unavailable"] is True
        assert metrics["reason"] == "no_momentum_data_available"

    def test_row_present_unavailable_and_no_technical_data_returns_data_unavailable(self):
        loader = StockScoresLoader()
        loader._technical_cache = {}
        loader._momentum_cache = {"DEAD": (None, None, None, None, True)}

        metrics = loader._get_momentum_metrics(None, "DEAD")

        assert metrics["data_unavailable"] is True
        assert metrics["reason"] == "momentum_metrics_loader_failed"

    def test_both_unavailable_branches_produce_identical_score(self):
        """Same RSI/MACD/SMA inputs via either "no row" or "row present, unavailable=True"
        must yield the exact same momentum_score - proving the two paths are now unified,
        not just individually non-crashing."""
        loader = StockScoresLoader()
        tech_row = (55.0, 0.3, 100.0, 95.0, 105.0, 4.0, 7.0, 10.0, 18.0)

        loader._technical_cache = {"ROW_ABSENT": tech_row}
        loader._momentum_cache = {}
        metrics_absent = loader._get_momentum_metrics(None, "ROW_ABSENT")

        loader._technical_cache = {"ROW_UNAVAILABLE": tech_row}
        loader._momentum_cache = {"ROW_UNAVAILABLE": (None, None, None, None, True)}
        metrics_unavailable = loader._get_momentum_metrics(None, "ROW_UNAVAILABLE")

        score_absent = loader._score_momentum(metrics_absent, "ROW_ABSENT")
        score_unavailable = loader._score_momentum(metrics_unavailable, "ROW_UNAVAILABLE")

        assert isinstance(score_absent, float)
        assert isinstance(score_unavailable, float)
        assert score_absent == pytest.approx(score_unavailable)
