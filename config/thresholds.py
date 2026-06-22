#!/usr/bin/env python3
"""
Unified Threshold Configuration — Single Source of Truth

Consolidates all signal grades, risk levels, and market indicators that were
previously scattered across 5+ files and hardcoded defaults.

All thresholds are defined in algo_config.py DEFAULTS and can be:
1. Overridden at runtime via database updates (hot-reload)
2. Overridden per-session via environment variables
3. Queried via this unified interface

Architecture:
- Database (algo_config table) is primary source of truth
- This module queries algo_config with fallback to built-in defaults
- No hardcoded thresholds anywhere else in the codebase
"""

import logging
from typing import Any


logger = logging.getLogger(__name__)


class ThresholdConfig:
    """Unified threshold configuration — delegates to algo_config."""

    @staticmethod
    def _get_config_value(key: str, default):
        """Load a config value from AlgoConfig.

        Args:
            key: Configuration key in algo_config table
            default: Fallback used if key is absent from the DB (allows loaders to
                     start before migration 092 is applied; DB value takes precedence
                     once the row exists)

        Returns:
            Config value

        Raises:
            RuntimeError: If config cannot be loaded and no default is provided.
        """
        import logging

        try:
            from algo.infrastructure import get_config

            val = get_config().get(key)
            if val is not None:
                return val
            if default is not None:
                logging.getLogger(__name__).warning(
                    f"[CONFIG FALLBACK] Key '{key}' missing from algo_config table. "
                    f"Using code default: {default}. Apply pending migrations to resolve."
                )
                return default
            raise RuntimeError(
                f"[CONFIG] Missing required configuration key: '{key}'. "
                "No hardcoded fallback allowed. Check algo_config table for this key."
            )
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"[CONFIG] Failed to load configuration: {e}. "
                "Cannot proceed without authoritative config values. Check infrastructure config availability."
            )

    # ═══════════════════════════════════════════════════════════════════════════
    # SIGNAL STRENGTH THRESHOLDS (0-100 scale)
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def signal_weak_threshold() -> float:
        """Score below this = weak signal."""
        return float(ThresholdConfig._get_config_value("signal_weak_threshold", 40.0))

    @staticmethod
    def signal_medium_threshold() -> float:
        """Score 40-60 (by default) = medium strength."""
        return float(ThresholdConfig._get_config_value("signal_medium_threshold", 60.0))

    @staticmethod
    def signal_strong_threshold() -> float:
        """Score 60-80 = strong, >=80 = very strong."""
        return float(ThresholdConfig._get_config_value("signal_strong_threshold", 80.0))

    @staticmethod
    def get_signal_strength_thresholds() -> dict[str, float]:
        """Get all signal strength thresholds as dict."""
        return {
            "weak": ThresholdConfig.signal_weak_threshold(),
            "medium": ThresholdConfig.signal_medium_threshold(),
            "strong": ThresholdConfig.signal_strong_threshold(),
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # GRADE CLASSIFICATION THRESHOLDS (0-100 scale)
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def swing_grade_thresholds() -> dict[str, int]:
        """Get swing trader score grade thresholds."""
        return {
            "aplus": int(ThresholdConfig._get_config_value("swing_grade_threshold_aplus", 85)),
            "a": int(ThresholdConfig._get_config_value("swing_grade_threshold_a", 75)),
            "b": int(ThresholdConfig._get_config_value("swing_grade_threshold_b", 65)),
            "c": int(ThresholdConfig._get_config_value("swing_grade_threshold_c", 55)),
            "d": int(ThresholdConfig._get_config_value("swing_grade_threshold_d", 45)),
        }

    @staticmethod
    def advanced_filters_grade_thresholds() -> dict[str, int]:
        """Get advanced filters (IBD composite) grade thresholds."""
        return {
            "aplus": int(ThresholdConfig._get_config_value("advanced_filters_grade_threshold_aplus", 90)),
            "a": int(ThresholdConfig._get_config_value("advanced_filters_grade_threshold_a", 80)),
            "b": int(ThresholdConfig._get_config_value("advanced_filters_grade_threshold_b", 70)),
            "c": int(ThresholdConfig._get_config_value("advanced_filters_grade_threshold_c", 60)),
            "d": int(ThresholdConfig._get_config_value("advanced_filters_grade_threshold_d", 50)),
        }

    @staticmethod
    def dashboard_grade_thresholds() -> dict[str, int]:
        """Get dashboard signals grade thresholds."""
        return {
            "a": int(ThresholdConfig._get_config_value("dashboard_grade_threshold_a", 80)),
            "b": int(ThresholdConfig._get_config_value("dashboard_grade_threshold_b", 60)),
            "c": int(ThresholdConfig._get_config_value("dashboard_grade_threshold_c", 40)),
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # DATA QUALITY & FRESHNESS THRESHOLDS
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def data_staleness_fresh_days() -> int:
        """Data age (days) considered fresh."""
        return int(ThresholdConfig._get_config_value("data_staleness_fresh_days", 3))

    @staticmethod
    def data_staleness_stale_days_monday() -> int:
        """Data age (days) on Monday to be considered stale."""
        return int(ThresholdConfig._get_config_value("data_staleness_stale_days_monday", 10))

    @staticmethod
    def data_staleness_stale_days_other() -> int:
        """Data age (days) on non-Monday to be considered stale."""
        return int(ThresholdConfig._get_config_value("data_staleness_stale_days_other", 3))

    @staticmethod
    def get_data_staleness_days(is_monday: bool) -> int:
        """Get staleness threshold for current day.

        Args:
            is_monday: Whether today is Monday

        Returns:
            Maximum data age in days
        """
        return (
            ThresholdConfig.data_staleness_stale_days_monday()
            if is_monday
            else ThresholdConfig.data_staleness_stale_days_other()
        )

    @staticmethod
    def dashboard_min_quality_threshold() -> float:
        """Dashboard minimum quality score (0-100)."""
        return float(ThresholdConfig._get_config_value("dashboard_min_quality_threshold", 40.0))

    @staticmethod
    def min_close_quality_pct() -> float:
        """Signal entry close quality gate: stock must close at or above N% of day's range.

        Range is (day_high - day_low). Quality gate filters weak closes (near day lows)
        which often indicate distribution/selling pressure rather than accumulation.
        For example, 40% means close must be in the upper 60% of the day's range.
        """
        return float(ThresholdConfig._get_config_value("min_close_quality_pct", 40.0))

    @staticmethod
    def dashboard_metrics_max_age_minutes() -> int:
        """Dashboard: maximum age of metrics in minutes before warning."""
        return int(ThresholdConfig._get_config_value("dashboard_metrics_max_age_minutes", 120))

    @staticmethod
    def dashboard_fetcher_failure_threshold() -> float:
        """Dashboard: if >N% of fetchers fail, enter degraded mode."""
        return float(ThresholdConfig._get_config_value("dashboard_fetcher_failure_threshold", 0.5))

    # ═══════════════════════════════════════════════════════════════════════════
    # LOADER OPERATIONAL THRESHOLDS
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def loader_rate_limit_circuit_break_threshold_eod() -> int:
        """Circuit break threshold (seconds) during EOD."""
        return int(ThresholdConfig._get_config_value("loader_rate_limit_circuit_break_threshold_eod", 180))

    @staticmethod
    def loader_rate_limit_circuit_break_threshold_morning() -> int:
        """Circuit break threshold (seconds) during morning prep."""
        return int(ThresholdConfig._get_config_value("loader_rate_limit_circuit_break_threshold_morning", 480))

    @staticmethod
    def loader_emergency_mode_threshold_multiplier() -> float:
        """Emergency mode triggered at N% of task timeout."""
        return float(ThresholdConfig._get_config_value("loader_emergency_mode_threshold_multiplier", 0.5))

    @staticmethod
    def get_rate_limit_threshold(is_eod_pipeline: bool) -> int:
        """Get rate limit threshold based on pipeline type.

        Args:
            is_eod_pipeline: Whether this is EOD (True) or morning (False) pipeline

        Returns:
            Threshold in seconds
        """
        return (
            ThresholdConfig.loader_rate_limit_circuit_break_threshold_eod()
            if is_eod_pipeline
            else ThresholdConfig.loader_rate_limit_circuit_break_threshold_morning()
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # RISK & MARKET CONDITION THRESHOLDS (via algo_config)
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def vix_max_threshold() -> float:
        """VIX level to halt trading."""
        return float(ThresholdConfig._get_config_value("vix_max_threshold", 35.0))

    @staticmethod
    def vix_alert_threshold() -> float:
        """VIX level to trigger RED alert (dashboard)."""
        return float(ThresholdConfig._get_config_value("vix_alert_threshold", 30.0))

    @staticmethod
    def vix_caution_threshold() -> float:
        """VIX level to reduce positions."""
        return float(ThresholdConfig._get_config_value("vix_caution_threshold", 25.0))

    @staticmethod
    def halt_drawdown_pct() -> float:
        """Portfolio drawdown % to halt trading (CB1)."""
        return float(ThresholdConfig._get_config_value("halt_drawdown_pct", 20.0))

    @staticmethod
    def max_daily_loss_pct() -> float:
        """Max daily loss % before halt."""
        return float(ThresholdConfig._get_config_value("max_daily_loss_pct", 2.0))

    @staticmethod
    def max_total_risk_pct() -> float:
        """Max total open risk %."""
        return float(ThresholdConfig._get_config_value("max_total_risk_pct", 4.0))

    @staticmethod
    def portfolio_variance_threshold() -> float:
        """Portfolio variance threshold to trigger CB circuit breaker."""
        return float(ThresholdConfig._get_config_value("portfolio_variance_threshold", 0.15))

    @staticmethod
    def get_all_thresholds() -> dict[str, Any]:
        """Export all thresholds as a flat dict for inspection/debugging.

        Returns:
            Dict with all threshold keys and values
        """
        return {
            # Signal strength
            "signal_weak": ThresholdConfig.signal_weak_threshold(),
            "signal_medium": ThresholdConfig.signal_medium_threshold(),
            "signal_strong": ThresholdConfig.signal_strong_threshold(),
            # Grade thresholds
            "swing_grades": ThresholdConfig.swing_grade_thresholds(),
            "advanced_filters_grades": ThresholdConfig.advanced_filters_grade_thresholds(),
            "dashboard_grades": ThresholdConfig.dashboard_grade_thresholds(),
            # Data quality
            "data_staleness_fresh_days": ThresholdConfig.data_staleness_fresh_days(),
            "dashboard_min_quality": ThresholdConfig.dashboard_min_quality_threshold(),
            "dashboard_fetcher_failure": ThresholdConfig.dashboard_fetcher_failure_threshold(),
            # Loaders
            "loader_rate_limit_eod": ThresholdConfig.loader_rate_limit_circuit_break_threshold_eod(),
            "loader_rate_limit_morning": ThresholdConfig.loader_rate_limit_circuit_break_threshold_morning(),
            # Risk
            "vix_max": ThresholdConfig.vix_max_threshold(),
            "vix_alert": ThresholdConfig.vix_alert_threshold(),
            "vix_caution": ThresholdConfig.vix_caution_threshold(),
            "halt_drawdown": ThresholdConfig.halt_drawdown_pct(),
            "max_daily_loss": ThresholdConfig.max_daily_loss_pct(),
            "max_total_risk": ThresholdConfig.max_total_risk_pct(),
        }
