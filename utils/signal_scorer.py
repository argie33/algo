#!/usr/bin/env python3
"""
Unified Signal Scorer — Consolidates scoring logic across all signal types.

All signal types (momentum, patterns, trend, options) use this scorer
for consistent scoring, thresholding, and result formatting.

Prevents different modules from implementing the same scoring logic multiple ways.
"""

import logging
from typing import Dict, Any, Optional, Tuple
from datetime import date

logger = logging.getLogger(__name__)


class SignalScorer:
    """Unified interface for scoring all signal types."""

    # Standard score ranges
    SCORE_MIN = 0.0
    SCORE_MAX = 100.0

    # Standard signal strength thresholds (can be overridden per signal type)
    WEAK_THRESHOLD = 40.0      # Below this = weak signal
    MEDIUM_THRESHOLD = 60.0    # 40-60 = medium
    STRONG_THRESHOLD = 80.0    # 60-80 = strong, >= 80 = very strong

    @staticmethod
    def normalize_score(raw_score: float, min_val: float = 0, max_val: float = 100) -> float:
        """
        Normalize a raw score to 0-100 scale.

        Args:
            raw_score: Score in original range
            min_val: Minimum expected value in original range
            max_val: Maximum expected value in original range

        Returns:
            Normalized score (0-100)
        """
        if max_val <= min_val:
            return SignalScorer.SCORE_MIN
        return max(SignalScorer.SCORE_MIN, min((raw_score - min_val) / (max_val - min_val) * 100, SignalScorer.SCORE_MAX))

    @staticmethod
    def classify_strength(score: float, weak_threshold: float = WEAK_THRESHOLD,
                         medium_threshold: float = MEDIUM_THRESHOLD,
                         strong_threshold: float = STRONG_THRESHOLD) -> str:
        """
        Classify signal strength based on score.

        Args:
            score: Signal score (0-100)
            weak_threshold: Score below which signal is weak (default 40)
            medium_threshold: Score above which signal is medium (default 60)
            strong_threshold: Score above which signal is strong (default 80)

        Returns:
            Strength classification: 'very_weak', 'weak', 'medium', 'strong', 'very_strong'
        """
        if score < weak_threshold:
            return 'very_weak' if score < weak_threshold / 2 else 'weak'
        elif score < medium_threshold:
            return 'medium'
        elif score < strong_threshold:
            return 'strong'
        else:
            return 'very_strong'

    @staticmethod
    def format_result(signal_type: str, symbol: str, eval_date: date,
                     score: float, strength: str = None, details: Dict[str, Any] = None,
                     threshold: float = MEDIUM_THRESHOLD) -> Dict[str, Any]:
        """
        Format a standardized signal result.

        Args:
            signal_type: Type of signal (e.g., 'momentum', 'pattern', 'trend')
            symbol: Stock ticker
            eval_date: Date of evaluation
            score: Signal score (0-100)
            strength: Optional override for strength classification
            details: Optional dict of component details (e.g., {'rsv': 60.5, 'volume_ratio': 1.2})
            threshold: Threshold for signal pass/fail

        Returns:
            Standardized dict with signal result
        """
        if strength is None:
            strength = SignalScorer.classify_strength(score)

        return {
            'signal_type': signal_type,
            'symbol': symbol,
            'eval_date': str(eval_date),
            'score': round(score, 1),
            'strength': strength,
            'pass': score >= threshold,
            'details': details or {},
        }

    @staticmethod
    def blend_scores(scores: Dict[str, Tuple[float, float]], weights: Dict[str, float] = None) -> float:
        """
        Blend multiple component scores using weights.

        Args:
            scores: Dict of {component_name: (score, max_points)}
            weights: Optional dict of {component_name: weight}. If None, uses equal weights.

        Returns:
            Weighted blend of scores (0-100)
        """
        if not scores:
            return SignalScorer.SCORE_MIN

        # Default to equal weights if not provided
        if weights is None:
            weights = {name: 1.0 for name in scores.keys()}

        total_weighted = 0.0
        total_weight = 0.0

        for component_name, (score, max_pts) in scores.items():
            weight = weights.get(component_name, 1.0)
            # Normalize score to 0-100
            normalized = (score / max_pts * 100) if max_pts > 0 else 0
            total_weighted += normalized * weight
            total_weight += weight

        if total_weight <= 0:
            return SignalScorer.SCORE_MIN

        blended = total_weighted / total_weight
        return round(max(SignalScorer.SCORE_MIN, min(blended, SignalScorer.SCORE_MAX)), 1)

    @staticmethod
    def validate_score(score: float, min_val: float = SCORE_MIN, max_val: float = SCORE_MAX) -> bool:
        """Validate that a score is in the expected range."""
        return min_val <= score <= max_val
