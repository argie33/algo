#!/usr/bin/env python3
"""Signal data scale validation to prevent percentage/ratio mismatches."""

import logging
from typing import Any


logger = logging.getLogger(__name__)


def validate_signal_data_scale(metrics: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize signal metrics to consistent percentage (0-100) scale.

    Financial metrics should be in percentage scale (0-100) for consistency:
    - Institutional ownership: 0-100 (percent)
    - Short interest: 0-100 (percent)
    - Insider ownership: 0-100 (percent)
    - Signal strength: 0-100 (score)
    - Quality score: 0-100 (score)

    Args:
        metrics: Dict of signal metrics to validate

    Returns:
        Dict with metrics normalized to percentage scale

    Raises:
        ValueError: If detected scale mismatch indicates data corruption
    """
    if not metrics:
        return metrics

    percentage_fields = [
        "institutional_ownership",
        "short_interest",
        "insider_ownership",
        "signal_strength",
        "score_quality",
        "score_growth",
        "rs_percentile",
    ]

    for field in percentage_fields:
        if field not in metrics or metrics[field] is None:
            continue

        try:
            val = float(metrics[field])
        except (ValueError, TypeError):
            logger.warning(f"Cannot convert {field}={metrics[field]} to float, skipping validation")
            continue

        # Validation rules for percentage fields
        if val < 0:
            raise ValueError(
                f"{field}={val} is negative; percentage fields must be >= 0. "
                f"Check data source for corruption."
            )

        # Detect scale mismatch: if 0 < val < 1, likely decimal (0.35) not percentage (35)
        if 0 < val < 1:
            logger.warning(f"Scaling {field} from decimal {val} to percentage {val * 100:.2f}")
            metrics[field] = val * 100

        # Alert on unusual high values (>200% or >100% for most fields except composite scores)
        if val > 100 and field not in ("score_quality", "score_growth", "signal_strength"):
            logger.warning(
                f"{field}={val} exceeds 100%, may indicate scale mismatch or data corruption"
            )

    return metrics
