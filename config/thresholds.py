#!/usr/bin/env python3
"""
Unified Threshold Configuration - Fail-Fast, Single Source of Truth

Consolidates all signal grades, risk levels, and market indicators that were
previously scattered across 5+ files and hardcoded defaults.

Architecture (CRITICAL SAFETY):
- Database (algo_config table) is PRIMARY and ONLY source of truth
- NO fallback defaults - all thresholds must be explicitly configured in database
- NO secondary sources - direct database lookup only
- FAIL-FAST: Missing or invalid thresholds raise RuntimeError immediately
- No silent degradation, no trading with undefined safety gates

All thresholds are validated at:
1. Startup (AlgoConfig initialization with full schema validation)
2. Runtime (this module re-validates on each query)
3. Hot-reload (when database values are updated)

Usage:
    from config.thresholds import ThresholdConfig
    max_daily_loss = ThresholdConfig.max_daily_loss_pct()  # Raises error if not configured
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ThresholdConfig:
    """Unified threshold configuration - delegates to algo_config."""

    @staticmethod
    def _get_config_value(key: str) -> Any:
        """Load a config value from AlgoConfig.

        FAIL-FAST: All thresholds are CRITICAL and must exist in database.
        No fallback defaults, no secondary sources, no silent degradation.

        Args:
            key: Configuration key in algo_config table

        Returns:
            Config value from database

        Raises:
            RuntimeError: If key missing from database or config system unavailable.
                         This is intentional - trading must fail rather than proceed
                         with undefined thresholds.
        """
        try:
            from algo.infrastructure import get_config

            val = get_config().get(key)
            if val is not None:
                return val

            # FAIL-FAST: Threshold missing from database - this is fatal
            raise RuntimeError(
                f"[CONFIG FATAL] Threshold '{key}' not found in algo_config table. "
                "All trading thresholds must be explicitly configured in database. "
                "No fallback defaults allowed - trading cannot proceed with undefined safety gates. "
                "Action: Ensure algo_config table is populated with all required thresholds."
            )
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"[CONFIG FATAL] Failed to load threshold '{key}': {e}. "
                "Cannot proceed without authoritative config values from database. "
                "Check database connectivity and algo_config table availability."
            ) from e

    # ═══════════════════════════════════════════════════════════════════════════
    # SIGNAL STRENGTH THRESHOLDS (0-100 scale)
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def signal_weak_threshold() -> float:
        """Score below this = weak signal. CRITICAL: must be configured."""
        return float(ThresholdConfig._get_config_value("signal_weak_threshold"))

    @staticmethod
    def signal_medium_threshold() -> float:
        """Score below medium = weak-medium boundary. CRITICAL: must be configured."""
        return float(ThresholdConfig._get_config_value("signal_medium_threshold"))

    @staticmethod
    def signal_strong_threshold() -> float:
        """Score below strong = medium-strong boundary. CRITICAL: must be configured."""
        return float(ThresholdConfig._get_config_value("signal_strong_threshold"))

    @staticmethod
    def get_signal_strength_thresholds() -> dict[str, float]:
        return {
            "weak": ThresholdConfig.signal_weak_threshold(),
            "medium": ThresholdConfig.signal_medium_threshold(),
            "strong": ThresholdConfig.signal_strong_threshold(),
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # GRADE CLASSIFICATION THRESHOLDS (0-100 scale)
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def advanced_filters_grade_thresholds() -> dict[str, int]:
        return {
            "aplus": int(ThresholdConfig._get_config_value("advanced_filters_grade_threshold_aplus")),
            "a": int(ThresholdConfig._get_config_value("advanced_filters_grade_threshold_a")),
            "b": int(ThresholdConfig._get_config_value("advanced_filters_grade_threshold_b")),
            "c": int(ThresholdConfig._get_config_value("advanced_filters_grade_threshold_c")),
            "d": int(ThresholdConfig._get_config_value("advanced_filters_grade_threshold_d")),
        }

    @staticmethod
    def dashboard_grade_thresholds() -> dict[str, int]:
        return {
            "a": int(ThresholdConfig._get_config_value("dashboard_grade_threshold_a")),
            "b": int(ThresholdConfig._get_config_value("dashboard_grade_threshold_b")),
            "c": int(ThresholdConfig._get_config_value("dashboard_grade_threshold_c")),
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # DATA QUALITY & FRESHNESS THRESHOLDS
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def data_staleness_fresh_days() -> int:
        """Data age (days) considered fresh. CRITICAL: blocks trading if not met."""
        return int(ThresholdConfig._get_config_value("data_staleness_fresh_days"))

    @staticmethod
    def data_staleness_stale_days_monday() -> int:
        """Data age (days) on Monday to be considered stale. CRITICAL: blocks trading if exceeded."""
        return int(ThresholdConfig._get_config_value("data_staleness_stale_days_monday"))

    @staticmethod
    def data_staleness_stale_days_other() -> int:
        """Data age (days) on non-Monday to be considered stale. CRITICAL: blocks trading if exceeded."""
        return int(ThresholdConfig._get_config_value("data_staleness_stale_days_other"))

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
        """Dashboard minimum quality score (0-100). CRITICAL: must be configured."""
        return float(ThresholdConfig._get_config_value("dashboard_min_quality_threshold"))

    @staticmethod
    def min_close_quality_pct() -> float:
        """Signal entry close quality gate: stock must close at or above N% of day's range.

        Range is (day_high - day_low). Quality gate filters weak closes (near day lows)
        which often indicate distribution/selling pressure rather than accumulation.
        CRITICAL: Gate determines signal validity. Must be explicitly configured in database.
        """
        return float(ThresholdConfig._get_config_value("min_close_quality_pct"))

    @staticmethod
    def dashboard_metrics_max_age_minutes() -> int:
        """Dashboard: maximum age of metrics in minutes before warning. CRITICAL: must be configured."""
        return int(ThresholdConfig._get_config_value("dashboard_metrics_max_age_minutes"))

    @staticmethod
    def dashboard_fetcher_failure_threshold() -> float:
        """Dashboard: if >N% of fetchers fail, enter degraded mode. CRITICAL: must be configured."""
        return float(ThresholdConfig._get_config_value("dashboard_fetcher_failure_threshold"))

    # ═══════════════════════════════════════════════════════════════════════════
    # LOADER OPERATIONAL THRESHOLDS
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def loader_rate_limit_circuit_break_threshold_eod() -> int:
        """Circuit break threshold (seconds) during EOD. CRITICAL: loader timeout management."""
        return int(ThresholdConfig._get_config_value("loader_rate_limit_circuit_break_threshold_eod"))

    @staticmethod
    def loader_rate_limit_circuit_break_threshold_morning() -> int:
        """Circuit break threshold (seconds) during morning prep. CRITICAL: loader timeout management."""
        return int(ThresholdConfig._get_config_value("loader_rate_limit_circuit_break_threshold_morning"))

    @staticmethod
    def loader_emergency_mode_threshold_multiplier() -> float:
        """Emergency mode triggered at N% of task timeout. CRITICAL: must be configured."""
        return float(ThresholdConfig._get_config_value("loader_emergency_mode_threshold_multiplier"))

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
        """VIX level to halt trading. CRITICAL: safety circuit breaker."""
        return float(ThresholdConfig._get_config_value("vix_max_threshold"))

    @staticmethod
    def vix_alert_threshold() -> float:
        """VIX level to trigger RED alert. CRITICAL: market condition monitoring."""
        return float(ThresholdConfig._get_config_value("vix_alert_threshold"))

    @staticmethod
    def vix_caution_threshold() -> float:
        """VIX level to reduce positions. CRITICAL: risk management."""
        return float(ThresholdConfig._get_config_value("vix_caution_threshold"))

    @staticmethod
    def halt_drawdown_pct() -> float:
        """Portfolio drawdown % to halt trading. CRITICAL: loss limit."""
        return float(ThresholdConfig._get_config_value("halt_drawdown_pct"))

    @staticmethod
    def max_daily_loss_pct() -> float:
        """Max daily loss % before halt. CRITICAL: daily risk limit."""
        return float(ThresholdConfig._get_config_value("max_daily_loss_pct"))

    @staticmethod
    def max_total_risk_pct() -> float:
        """Max total open risk %. CRITICAL: portfolio risk limit."""
        return float(ThresholdConfig._get_config_value("max_total_risk_pct"))

    @staticmethod
    def portfolio_variance_threshold() -> float:
        """Portfolio variance threshold to trigger CB circuit breaker. CRITICAL: must be configured."""
        return float(ThresholdConfig._get_config_value("portfolio_variance_threshold"))

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
