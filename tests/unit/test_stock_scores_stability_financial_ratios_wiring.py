#!/usr/bin/env python3
"""Regression test for StockScoresLoader's debt/leverage wiring
(loaders/load_stock_scores.py).

CLEANUP 2026-08-16 moved debt_to_equity/current_ratio/quick_ratio/cash_per_share/
debt_to_assets (_score_financial_stability) out of Stability's _score_stability (where they
had been a 20%-weighted sub-score) and into Quality's _enhance_quality_score (a bounded
+/-3 adjustment) - these are balance-sheet fundamentals, not price-volatility signals, so
they belong under Quality. This file replaces the old
test_stock_scores_stability_financial_ratios_wiring assertions (which tested the
now-removed Stability wiring) with equivalent coverage for the new Quality wiring, plus a
guard that _get_stability_metrics no longer merges quality-cache fields in (the bug class
from [[momentum_score_sma_dead_weight_fix_20260816]] returning the other way).

CLEANUP 2026-08-18: current_ratio/quick_ratio/cash_per_share removed from
_score_financial_stability entirely (not factor-score inputs anymore, per user request -
"cash/share ended up popping in but that does not belong in our scores"). Updated
TestQualityScoreFinancialStabilityWiring to exercise only the remaining
debt_to_equity/debt_to_assets inputs, and added a guard that the three removed ratios no
longer move the score.

REMOVED 2026-08-26 (Quality literature audit): TestQualityScoreFinancialStabilityWiring
deleted - _enhance_quality_score and _score_financial_stability (the functions it tested)
no longer exist. debt_to_assets is now scored directly in the base quality_score composite
(load_value_quality_growth_metrics.py); debt_to_equity was removed entirely as a redundant
transform of debt_to_assets (literature: "pick D/A or D/E, not both" - see _score_quality's
docstring in loaders/load_stock_scores.py). There is no longer a Quality-side "financial
ratios wiring" step in load_stock_scores.py to test - the whole computation moved upstream.
TestStabilityMetricsNoLongerMergeFinancialRatios below is unaffected and still valid.
"""

import pytest

from loaders.load_stock_scores import StockScoresLoader


class TestStabilityMetricsNoLongerMergeFinancialRatios:
    def test_get_stability_metrics_does_not_include_quality_ratios(self):
        """Guard against debt_to_equity/current_ratio/quick_ratio/cash_per_share
        re-appearing in stability metrics - they were intentionally removed 2026-08-16
        in favor of feeding Quality instead, and _get_stability_metrics no longer reads
        self._quality_cache at all."""
        loader = StockScoresLoader()
        # stability_row = (vol_252d, vol_60d, vol_30d, beta, downside_252d/60d/30d, max_drawdown_1y, data_unavailable)
        loader._stability_cache = {"AAPL": (0.25, 0.22, 0.20, 1.1, 0.20, 0.18, 0.16, -12.0, False)}

        metrics = loader._get_stability_metrics(None, "AAPL")

        assert "debt_to_equity" not in metrics
        assert "current_ratio" not in metrics
        assert "quick_ratio" not in metrics
        assert "cash_per_share" not in metrics
        assert "debt_to_assets" not in metrics
        assert "revenue_concentration_hhi" not in metrics
        assert metrics["downside_volatility_60d"] == pytest.approx(0.18)
        assert metrics["downside_volatility_30d"] == pytest.approx(0.16)


# TestQualityScoreFinancialStabilityWiring removed 2026-08-26 - see module docstring.
