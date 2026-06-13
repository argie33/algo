#!/usr/bin/env python3
"""
Unified Grade Classification Engine

Single source of truth for tier/grade classification across all modules.
Consolidates duplicate logic from algo_swing_score, algo_advanced_filters,
and load_swing_trader_scores.

Grade System: A+ (85+), A (75+), B (65+), C (55+), D (45+), F (<45)
Thresholds are configurable via algo_config table.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class GradeClassifier:
    """Unified grade classification with configurable thresholds."""

    # Default thresholds (can be overridden via algo_config)
    DEFAULT_THRESHOLDS = {
        'aplus': 85,
        'a': 75,
        'b': 65,
        'c': 55,
        'd': 45,
    }

    @staticmethod
    def _load_config_val(key: str, default):
        """Load a config value from AlgoConfig, with fallback to default."""
        try:
            from algo.infrastructure import get_config
            val = get_config().get(key)
            return val if val is not None else default
        except Exception as e:
            logger.debug(f"_load_config_val({key}) failed: {e}")
            return default

    @staticmethod
    def classify(
        score: float,
        config_prefix: str = 'grade',
        thresholds: Optional[dict] = None,
    ) -> str:
        """
        Classify a numeric score into a letter grade.

        Args:
            score: Numeric score (0-100 scale)
            config_prefix: Prefix for config keys (e.g., 'swing_' for swing_grade_threshold_aplus)
                         If empty string, uses just 'grade_threshold_aplus'
            thresholds: Optional explicit thresholds dict. If provided, ignores config_prefix.
                       Format: {'aplus': 85, 'a': 75, 'b': 65, 'c': 55, 'd': 45}

        Returns:
            Grade as string: 'A+', 'A', 'B', 'C', 'D', 'F'
        """
        if thresholds is None:
            # Load from config using prefix
            prefix = f"{config_prefix}_" if config_prefix else ""
            thresholds = {
                'aplus': GradeClassifier._load_config_val(f'{prefix}grade_threshold_aplus', GradeClassifier.DEFAULT_THRESHOLDS['aplus']),
                'a': GradeClassifier._load_config_val(f'{prefix}grade_threshold_a', GradeClassifier.DEFAULT_THRESHOLDS['a']),
                'b': GradeClassifier._load_config_val(f'{prefix}grade_threshold_b', GradeClassifier.DEFAULT_THRESHOLDS['b']),
                'c': GradeClassifier._load_config_val(f'{prefix}grade_threshold_c', GradeClassifier.DEFAULT_THRESHOLDS['c']),
                'd': GradeClassifier._load_config_val(f'{prefix}grade_threshold_d', GradeClassifier.DEFAULT_THRESHOLDS['d']),
            }

        score = float(score)
        if score >= thresholds['aplus']:
            return 'A+'
        elif score >= thresholds['a']:
            return 'A'
        elif score >= thresholds['b']:
            return 'B'
        elif score >= thresholds['c']:
            return 'C'
        elif score >= thresholds['d']:
            return 'D'
        else:
            return 'F'

    @staticmethod
    def classify_swing_score(score: float) -> str:
        """Classify swing trader score using swing_grade_threshold_* config keys."""
        return GradeClassifier.classify(score, config_prefix='swing')

    @staticmethod
    def classify_ibd_composite(score: float) -> str:
        """Classify IBD composite score using advanced_filters_grade_threshold_* config keys."""
        return GradeClassifier.classify(score, config_prefix='advanced_filters')

    @staticmethod
    def get_thresholds(config_prefix: str = 'grade') -> dict:
        """
        Get current thresholds for a grading system.

        Args:
            config_prefix: Prefix for config keys

        Returns:
            Dict with keys: aplus, a, b, c, d (each with numeric threshold)
        """
        prefix = f"{config_prefix}_" if config_prefix else ""
        return {
            'aplus': GradeClassifier._load_config_val(f'{prefix}grade_threshold_aplus', GradeClassifier.DEFAULT_THRESHOLDS['aplus']),
            'a': GradeClassifier._load_config_val(f'{prefix}grade_threshold_a', GradeClassifier.DEFAULT_THRESHOLDS['a']),
            'b': GradeClassifier._load_config_val(f'{prefix}grade_threshold_b', GradeClassifier.DEFAULT_THRESHOLDS['b']),
            'c': GradeClassifier._load_config_val(f'{prefix}grade_threshold_c', GradeClassifier.DEFAULT_THRESHOLDS['c']),
            'd': GradeClassifier._load_config_val(f'{prefix}grade_threshold_d', GradeClassifier.DEFAULT_THRESHOLDS['d']),
        }
