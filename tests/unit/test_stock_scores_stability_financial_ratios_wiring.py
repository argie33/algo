#!/usr/bin/env python3
"""Regression test for StockScoresLoader._get_stability_metrics wiring
debt_to_equity/current_ratio/quick_ratio/cash_per_share and downside_volatility_60d/30d
into the stability score (loaders/load_stock_scores.py).

_score_financial_stability (called by _score_stability for its 20%-weighted "Financial
Stability" sub-score) has always read metrics["debt_to_equity"] (30%),
metrics["current_ratio"]/["quick_ratio"] (30% combined liquidity), and
metrics["cash_per_share"] (15%) - but _get_stability_metrics never supplied any of the
four, because they live on quality_metrics, not stability_metrics, and this function only
ever queried stability_metrics. Only debt_to_assets (25% of that sub-score) could ever
fire - 75% of the Financial Stability sub-score was structurally dead in every real score.
Separately, downside_volatility_60d/30d columns exist on stability_metrics itself but were
never in the SELECT list, even though _score_stability has scored them (7.5%/5%) since the
2026-08-16 "60d/30d now scored too" fix - that fix's data-fetching half was never done.

Fixed by merging debt_to_equity/current_ratio/quick_ratio/cash_per_share in from the
already-loaded self._quality_cache (same table load_stock_scores.py already reads for
quality scoring - no new query needed), and adding the two missing columns to the existing
stability_metrics SELECT. Same bug class as
[[momentum_score_sma_dead_weight_fix_20260816]] - scoring logic existed and referenced a
field, but the metrics-fetching function never actually supplied it.
"""

import pytest

from loaders.load_stock_scores import StockScoresLoader


class TestStabilityMetricsFinancialRatiosWiring:
    def test_financial_ratios_merged_from_quality_cache(self):
        loader = StockScoresLoader()
        # stability_row = (vol_252d, vol_60d, vol_30d, beta, debt_to_assets,
        #                   dvol_252d, dvol_60d, dvol_30d, max_drawdown_1y, data_unavailable)
        loader._stability_cache = {"AAPL": (0.25, 0.22, 0.20, 1.1, 0.35, 0.20, 0.18, 0.16, -12.0, False)}
        # quality_row indices per _get_quality_metrics: 4=debt_to_equity, 5=current_ratio,
        # 6=quick_ratio, 20=cash_per_share (rest zero-filled, unused by this test)
        quality_row = [0.0] * 25
        quality_row[4] = 1.2
        quality_row[5] = 1.8
        quality_row[6] = 1.3
        quality_row[20] = 15.0
        loader._quality_cache = {"AAPL": tuple(quality_row)}
        loader._segment_cache = {}

        metrics = loader._get_stability_metrics(None, "AAPL")

        assert metrics["debt_to_equity"] == pytest.approx(1.2)
        assert metrics["current_ratio"] == pytest.approx(1.8)
        assert metrics["quick_ratio"] == pytest.approx(1.3)
        assert metrics["cash_per_share"] == pytest.approx(15.0)
        assert metrics["downside_volatility_60d"] == pytest.approx(0.18)
        assert metrics["downside_volatility_30d"] == pytest.approx(0.16)

    def test_missing_quality_row_does_not_crash(self):
        loader = StockScoresLoader()
        loader._stability_cache = {"NOQUAL": (0.25, 0.22, 0.20, 1.1, 0.35, 0.20, 0.18, 0.16, -12.0, False)}
        loader._quality_cache = {}
        loader._segment_cache = {}

        metrics = loader._get_stability_metrics(None, "NOQUAL")

        assert "debt_to_equity" not in metrics
        assert metrics["downside_volatility_60d"] == pytest.approx(0.18)

    def test_financial_stability_subscore_actually_moves_with_ratios(self):
        """End-to-end: with volatility/beta held fixed, a symbol with healthy debt/liquidity
        ratios must score higher than one with poor ratios - proving the 75%-of-sub-score
        weight (debt_to_equity + current/quick ratio + cash_per_share) is now live."""
        loader = StockScoresLoader()
        base = {"volatility_252d": 0.20, "volatility_60d": 0.20, "volatility_30d": 0.20, "beta": 1.0}

        healthy = dict(
            base,
            debt_to_equity=0.3,
            current_ratio=2.5,
            quick_ratio=2.0,
            cash_per_share=50.0,
        )
        weak = dict(
            base,
            debt_to_equity=3.0,
            current_ratio=0.4,
            quick_ratio=0.2,
            cash_per_share=0.5,
        )

        score_healthy = loader._score_stability(healthy, "HEALTHY")
        score_weak = loader._score_stability(weak, "WEAK")

        assert isinstance(score_healthy, float)
        assert isinstance(score_weak, float)
        assert score_healthy > score_weak
