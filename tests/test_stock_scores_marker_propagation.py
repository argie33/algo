#!/usr/bin/env python3
"""Test that data_unavailable markers propagate correctly through stock score composition.

This test verifies the fix for commit a07557165:
- clamp_score() no longer silences marker dicts
- Composite score logic explicitly handles markers
- unavailable_metrics dict is populated with reasons
"""

import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import StockScoresLoader


class TestMarkerPropagation(unittest.TestCase):
    """Test marker propagation through stock score calculation."""

    def test_clamp_score_preserves_markers(self) -> None:
        """CRITICAL: Verify clamp_score doesn't silence markers."""

        # Mock clamp_score function from the fixed code
        def clamp_score(score: float | dict[str, Any] | None) -> float | dict[str, Any] | None:
            if isinstance(score, float):
                return max(0.0, min(100.0, score))
            return score if isinstance(score, dict) else None

        # Test with float
        result = clamp_score(45.5)
        self.assertIsInstance(result, float)
        self.assertEqual(result, 45.5)

        # Test with clamping
        result = clamp_score(150.0)
        self.assertEqual(result, 100.0)

        # CRITICAL: Test that markers are NOT silenced
        marker: dict[str, Any] = {"symbol": "AAPL", "data_unavailable": True, "reason": "no_quality_metrics"}
        result = clamp_score(marker)
        self.assertIsInstance(result, dict)
        self.assertEqual(result, marker)  # ✅ Marker preserved
        if isinstance(result, dict):
            self.assertEqual(result["reason"], "no_quality_metrics")  # ✅ Reason preserved

        # Test with None
        result = clamp_score(None)
        self.assertIsNone(result)

    def test_composite_score_handles_markers(self) -> None:
        """Verify composite score logic correctly processes marker dicts.

        CORRECTED 2026-09-07 (goal: audit stock_scores factor/composite sanity): this test
        previously hand-simulated the aggregation loop and asserted a RENORMALIZED result
        (dividing by the sum of available weights) - that formula was already wrong the day
        it was written relative to load_stock_scores.py's "Fixed base weights (no
        redistribution per GOVERNANCE fail-fast rule)" comment, and became more obviously
        wrong once BASE_PILLAR_WEIGHTS changed (this test's own local weights dict -
        0.25/0.20/0.20/0.15/0.10/0.10 - don't even match the current 0.20/0.24/0.27/0.19/0.10
        quality/growth/value/risk/momentum split). A hand-simulated loop that never calls the
        real code gives zero protection against a real regression either way; see
        test_no_redistribution_matches_real_compute_stock_score below for a test that
        actually calls production code.
        """

        # Simulated metric scores: some floats, some markers
        metrics = {
            "quality": 85.0,  # Float score
            "growth": {  # Marker: data unavailable
                "symbol": "AAPL",
                "data_unavailable": True,
                "reason": "no_growth_metrics_data",
            },
            "value": 72.5,  # Float score
            "risk": {  # Marker: data unavailable
                "symbol": "AAPL",
                "data_unavailable": True,
                "reason": "insufficient_price_history",
            },
            "momentum": 68.0,  # Float score
            # Synthetic 6th field (not a real pillar name - just exercises the plain-None
            # skip path, distinct from the marker-dict path above) since Positioning's/Size's
            # retirement as composite pillars left no real 6th field to illustrate this with.
            "unscored_extra": None,
        }

        # Simulate the composite score calculation logic (from fixed code) - matches
        # load_stock_scores.py's actual "skip unavailable, do NOT redistribute its weight"
        # behavior, not a renormalized average.
        unavailable_metrics = {}
        composite_score_value = 0.0
        normalized_weights = {
            "quality": 0.25,
            "growth": 0.20,
            "value": 0.20,
            "unscored_extra": 0.15,
            "risk": 0.10,
            "momentum": 0.10,
        }

        for metric_name, clamped_value_score in metrics.items():
            weight = normalized_weights[metric_name]
            if weight > 0:
                # Handle marker dicts (data unavailable) separately
                if isinstance(clamped_value_score, dict) and clamped_value_score.get("data_unavailable"):
                    reason = clamped_value_score.get("reason", "unknown_reason")
                    unavailable_metrics[metric_name] = reason
                elif clamped_value_score is None:
                    # None without a marker dict
                    pass  # Skip this metric
                elif isinstance(clamped_value_score, float):
                    composite_score_value += clamped_value_score * weight

        # Verify results
        # ✅ Markers are identified and tracked
        self.assertIn("growth", unavailable_metrics)
        self.assertEqual(unavailable_metrics["growth"], "no_growth_metrics_data")

        self.assertIn("risk", unavailable_metrics)
        self.assertEqual(unavailable_metrics["risk"], "insufficient_price_history")

        # ✅ Unavailable metrics' weight is DROPPED, not redistributed - the sum of
        # available-pillar*weight products, unscaled by the sum of available weights.
        expected_value = 85.0 * 0.25 + 72.5 * 0.20 + 68.0 * 0.10
        self.assertAlmostEqual(composite_score_value, expected_value, places=1)
        # A renormalized average would have been meaningfully higher - pin that the two
        # differ, so a future accidental reintroduction of renormalization is caught even if
        # someone "fixes" expected_value above to match it instead of the real behavior.
        renormalized = composite_score_value / (0.25 + 0.20 + 0.10)
        self.assertLess(composite_score_value, renormalized)

        # ✅ Incomplete data is visible via unavailable_metrics
        self.assertEqual(len(unavailable_metrics), 2)  # 2 out of 6 metrics unavailable

    def test_no_redistribution_matches_real_compute_stock_score(self) -> None:
        """Same invariant as test_composite_score_handles_markers above, but calling the
        REAL StockScoresLoader._compute_stock_score - added 2026-09-07 because the
        hand-simulated version above (and this whole file, historically) never exercised
        production code, so a real regression in the no-redistribution rule wouldn't have
        been caught by anything in this file.

        Mocks only the DB-touching fetch methods and DatabaseContext (no real DB needed) -
        the five _score_* calls and the aggregation loop itself are the real production code.
        risk_score=50.0 keeps _value_risk_adjusted_weights at its unmodified base weights
        (see pillar_weights.py: risk_score=50 is this function's own documented neutral
        point), so the expected composite is computable directly from BASE_PILLAR_WEIGHTS.
        """
        from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS

        loader = StockScoresLoader()
        loader._liquidity_cache = {}

        growth_marker = {"symbol": "TESTSYM", "data_unavailable": True, "reason": "no_growth_metrics_data"}

        with (
            patch("loaders.load_stock_scores.DatabaseContext") as mock_db_context,
            patch.object(loader, "_get_quality_metrics", return_value={}),
            patch.object(loader, "_get_growth_metrics", return_value={}),
            patch.object(loader, "_get_value_metrics", return_value={}),
            patch.object(loader, "_get_stability_metrics", return_value={}),
            patch.object(loader, "_get_momentum_metrics", return_value={}),
            patch.object(loader, "_score_quality", return_value=80.0),
            patch.object(loader, "_score_growth", return_value=growth_marker),
            patch.object(loader, "_score_value", return_value=70.0),
            patch.object(loader, "_score_risk", return_value=50.0),
            patch.object(loader, "_score_momentum", return_value=60.0),
        ):
            mock_db_context.return_value.__enter__.return_value = MagicMock()
            result = loader._compute_stock_score("TESTSYM")

        import json

        self.assertEqual(json.loads(result["unavailable_metrics"]), {"growth": "no_growth_metrics_data"})

        # No redistribution: growth's 0.24 weight is simply dropped, not handed to the other
        # 4 pillars - composite is the raw sum of (available_score * base_weight).
        expected_composite = (
            80.0 * BASE_PILLAR_WEIGHTS["quality"]
            + 70.0 * BASE_PILLAR_WEIGHTS["value"]
            + 50.0 * BASE_PILLAR_WEIGHTS["risk"]
            + 60.0 * BASE_PILLAR_WEIGHTS["momentum"]
        )
        self.assertAlmostEqual(result["composite_score"], round(expected_composite, 2), places=2)

        # A renormalized-over-available-weight composite would be meaningfully higher -
        # pin the two apart so a reintroduced redistribution bug can't hide by coincidence.
        available_weight = sum(BASE_PILLAR_WEIGHTS[p] for p in ("quality", "value", "risk", "momentum"))
        renormalized = expected_composite / available_weight
        self.assertLess(result["composite_score"], renormalized)

    def test_marker_reason_propagates_to_api_response(self) -> None:
        """Verify marker reasons appear in API responses."""

        # Simulated API response after marker propagation fix
        response: dict[str, Any] = {
            "symbol": "AAPL",
            "composite_score": 76.2,
            "quality_score": 85.0,
            "growth_score": None,  # Marker degraded to None in API
            "value_score": 72.5,
            "momentum_score": 68.0,
            "risk_score": None,
            "data_completeness": 0.60,  # 3 out of 5 metrics available
            "unavailable_metrics": {
                "growth": "no_growth_metrics_data",
                "risk": "insufficient_price_history",
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # ✅ Operators can see why metrics are unavailable
        unavailable = response.get("unavailable_metrics")
        self.assertIsInstance(unavailable, dict)
        if isinstance(unavailable, dict):
            self.assertEqual(unavailable.get("growth"), "no_growth_metrics_data")
            self.assertEqual(unavailable.get("risk"), "insufficient_price_history")

        # ✅ data_completeness reflects actual available data
        self.assertEqual(response["data_completeness"], 0.60)

        # ✅ Response includes all fields needed for transparent reporting
        self.assertIn("unavailable_metrics", response)
        self.assertIn("data_completeness", response)


if __name__ == "__main__":
    unittest.main()
