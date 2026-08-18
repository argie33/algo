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


class TestQualityScoreFinancialStabilityWiring:
    def _base_quality_metrics(self) -> dict:
        return {
            "gross_margin": None,
            "ebitda_margin": None,
            "net_margin": None,
            "earnings_growth_yoy": None,
            "fcf_to_net_income": None,
            "roic_pct": None,
            "ocf_to_net_income": None,
        }

    def test_healthy_ratios_score_higher_than_weak_ratios(self):
        """End-to-end: with every other quality signal held absent, a symbol with healthy
        debt ratios must get a higher enhanced quality score than one with weak ratios -
        proving _score_financial_stability's output actually reaches
        _enhance_quality_score's adjustment (the bug this file's predecessor guarded
        against, now on the Quality side instead of Stability)."""
        loader = StockScoresLoader()

        healthy = dict(
            self._base_quality_metrics(),
            debt_to_equity=0.3,
            debt_to_assets=0.2,
        )
        weak = dict(
            self._base_quality_metrics(),
            debt_to_equity=3.0,
            debt_to_assets=0.9,
        )

        score_healthy = loader._enhance_quality_score(50.0, healthy, "HEALTHY")
        score_weak = loader._enhance_quality_score(50.0, weak, "WEAK")

        assert score_healthy > score_weak

    def test_missing_ratios_leaves_adjustment_unchanged(self):
        loader = StockScoresLoader()
        score = loader._enhance_quality_score(50.0, self._base_quality_metrics(), "NO_RATIOS")
        assert score == 50.0

    def test_current_quick_ratio_and_cash_per_share_no_longer_move_the_score(self):
        """current_ratio/quick_ratio/cash_per_share removed 2026-08-18 - a symbol that
        only differs in those three fields must score identically to one without them,
        proving _score_financial_stability no longer reads them."""
        loader = StockScoresLoader()

        base = dict(self._base_quality_metrics(), debt_to_equity=0.5, debt_to_assets=0.3)
        with_extra_ratios = dict(
            base,
            current_ratio=0.1,  # would score very poorly if still wired in
            quick_ratio=0.1,
            cash_per_share=0.01,
        )

        score_base = loader._enhance_quality_score(50.0, base, "BASE")
        score_with_extra = loader._enhance_quality_score(50.0, with_extra_ratios, "WITH_EXTRA")

        assert score_base == score_with_extra
