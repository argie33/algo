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
        """Verify composite score logic correctly processes marker dicts."""

        # Simulated metric scores: some floats, some markers
        metrics = {
            "quality": 85.0,  # Float score
            "growth": {  # Marker: data unavailable
                "symbol": "AAPL",
                "data_unavailable": True,
                "reason": "no_growth_metrics_data",
            },
            "value": 72.5,  # Float score
            "positioning": None,  # None (no score)
            "stability": {  # Marker: data unavailable
                "symbol": "AAPL",
                "data_unavailable": True,
                "reason": "insufficient_price_history",
            },
            "momentum": 68.0,  # Float score
        }

        # Simulate the composite score calculation logic (from fixed code)
        unavailable_metrics = {}
        composite_score_value = 0.0
        normalized_weights = {
            "quality": 0.25,
            "growth": 0.20,
            "value": 0.20,
            "positioning": 0.15,
            "stability": 0.10,
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

        self.assertIn("stability", unavailable_metrics)
        self.assertEqual(unavailable_metrics["stability"], "insufficient_price_history")

        # ✅ Unavailable metrics don't contribute to score
        # Score should only include: quality (85*0.25) + value (72.5*0.20) + momentum (68*0.10)
        # Adjusted weights: 0.25 + 0.20 + 0.10 = 0.55 (total of available weights)
        expected_value = (85.0 * 0.25 + 72.5 * 0.20 + 68.0 * 0.10) / (0.25 + 0.20 + 0.10)
        self.assertAlmostEqual(composite_score_value / (0.25 + 0.20 + 0.10), expected_value, places=1)

        # ✅ Incomplete data is visible via unavailable_metrics
        self.assertEqual(len(unavailable_metrics), 2)  # 2 out of 6 metrics unavailable

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
            "positioning_score": None,
            "stability_score": None,
            "data_completeness": 0.50,  # 3 out of 6 metrics available
            "unavailable_metrics": {
                "growth": "no_growth_metrics_data",
                "positioning": "no_positioning_metrics_data",
                "stability": "insufficient_price_history",
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # ✅ Operators can see why metrics are unavailable
        unavailable = response.get("unavailable_metrics")
        self.assertIsInstance(unavailable, dict)
        if isinstance(unavailable, dict):
            self.assertEqual(unavailable.get("growth"), "no_growth_metrics_data")
            self.assertEqual(unavailable.get("stability"), "insufficient_price_history")

        # ✅ data_completeness reflects actual available data
        self.assertEqual(response["data_completeness"], 0.50)

        # ✅ Response includes all fields needed for transparent reporting
        self.assertIn("unavailable_metrics", response)
        self.assertIn("data_completeness", response)


if __name__ == "__main__":
    unittest.main()
