#!/usr/bin/env python3
"""PositionAggregator - synthesizes health flags into recommendations."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PositionAggregator:
    """Aggregates health scores and flags into position recommendations."""

    FLAG_WEIGHTS = {
        "rs_degradation": 1.0,
        "sector_weakness": 0.8,
        "peak_distance": 0.9,
        "earnings_proximity": 1.2,
        "distribution_pressure": 0.7,
        "time_decay": 0.8,
    }

    def __init__(self, config: Any = None) -> None:
        """Initialize aggregator with config.

        Args:
            config: Algorithm configuration with halt_flag_count, etc.
        """
        self.config = config or {}

    def aggregate_flags(self, health_scores: dict[str, Any]) -> dict[str, Any]:
        """Convert health scores into flags with severity.

        Args:
            health_scores: Dict of {factor: (score, status)} tuples

        Returns:
            Dict with 'flags', 'severity_count', 'recommendation' keys
        """
        flags = {}

        # Extract RED flags (warnings)
        for factor, (score, status) in health_scores.items():
            if factor not in self.FLAG_WEIGHTS:
                raise ValueError(
                    f"[CRITICAL] Health factor '{factor}' has no weight defined in FLAG_WEIGHTS. "
                    f"Cannot calculate position health without weight for all factors. "
                    f"Configured factors: {list(self.FLAG_WEIGHTS.keys())}. "
                    f"Add '{factor}' to FLAG_WEIGHTS or check health scoring logic."
                )

            weight = self.FLAG_WEIGHTS[factor]
            if status == "RED":
                flags[factor] = {
                    "status": "RED",
                    "score": score,
                    "weight": weight,
                }
            elif status == "YELLOW":
                flags[factor] = {
                    "status": "YELLOW",
                    "score": score,
                    "weight": weight,
                }

        # Count flags
        severity: float = sum(1 for f in flags.values() if f["status"] == "RED")
        severity += 0.5 * sum(1 for f in flags.values() if f["status"] == "YELLOW")

        if "halt_flag_count_for_early_exit" not in self.config:
            raise ValueError(
                "CRITICAL CONFIG: halt_flag_count_for_early_exit missing from position aggregator config. "
                "Cannot determine when to exit positions for health reasons — this is required configuration."
            )
        halt_flag_count = self.config["halt_flag_count_for_early_exit"]

        recommendation = "HOLD"
        if severity >= halt_flag_count:
            recommendation = "CONSIDER_EXIT"
        elif severity >= halt_flag_count * 0.5:
            recommendation = "MONITOR_CLOSELY"

        return {
            "flags": flags,
            "severity_count": round(severity, 1),
            "recommendation": recommendation,
            "halt_flag_count": halt_flag_count,
        }

    def should_exit_early(self, flags_result: dict[str, Any]) -> bool:
        """Check if position should exit early based on flags.

        Args:
            flags_result: Result from aggregate_flags()

        Returns:
            True if recommendation is CONSIDER_EXIT
        """
        return flags_result.get("recommendation") == "CONSIDER_EXIT"

    def format_flag_summary(self, flags_result: dict[str, Any]) -> str:
        """Format flags into human-readable summary.

        Args:
            flags_result: Result from aggregate_flags()

        Returns:
            Formatted summary string
        """
        required_keys = ["flags", "severity_count", "recommendation"]
        missing = [k for k in required_keys if k not in flags_result]
        if missing:
            raise ValueError(
                f"Incomplete flags_result from aggregate_flags: missing keys {missing}. "
                f"Cannot format summary without complete health evaluation data."
            )
        flags = flags_result["flags"]
        severity = flags_result["severity_count"]
        recommendation = flags_result["recommendation"]

        if not flags:
            return f"✓ No warnings (recommendation: {recommendation})"

        flag_lines = []
        for factor, flag_data in flags.items():
            status = flag_data["status"]
            score = flag_data["score"]
            icon = "🔴" if status == "RED" else "🟡"
            flag_lines.append(f"  {icon} {factor}: {score:.0f}/100")

        summary = f"⚠️ Severity: {severity:.1f} flags (recommendation: {recommendation})\n"
        summary += "\n".join(flag_lines)
        return summary
