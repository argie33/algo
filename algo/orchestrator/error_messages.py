#!/usr/bin/env python3
"""Centralized error message templates for orchestrator phases.

Single source of truth for error messages ensures consistency and makes
global updates (e.g., adding runbook links) possible without grep-and-replace.
"""

from typing import Any


class PhaseErrorMessages:
    """Error message templates for phase execution."""

    # Data Freshness & Availability
    NO_FRESH_PRICE_DATA = "Cannot proceed without complete price data. Check data pipeline freshness (Phase 1 logs)."
    STALE_TECHNICAL_INDICATORS = "Technical indicator data (ATR, SMA) stale or missing. Cannot compute position sizing."
    MISSING_SIGNAL_DATA = "No buy/sell signals generated. Check Phase 7 output and data pipeline status."
    MISSING_EXPOSURE_CONSTRAINTS = "Exposure constraints from Phase 5 unavailable. Cannot execute trades safely."

    # Configuration Issues
    MISSING_CONFIG_KEY = "Configuration missing required key: {key}. Check algo_config table."
    INVALID_CONFIG_VALUE = (
        "Configuration value {key}={value} outside valid range [{min}, {max}]. Check algo_config table."
    )
    INVALID_EXECUTION_MODE = "Invalid execution_mode='{mode}'. Must be 'paper', 'dry', 'review', or 'auto'."
    MISSING_EXPLICIT_THRESHOLD = (
        "Cannot proceed without explicit {param} threshold (no hardcoded fallback). Check algo_config."
    )

    # Database Connectivity & Health
    DATABASE_UNAVAILABLE = (
        "Database connectivity failed. Check database health, RDS credentials, or schema consistency."
    )
    QUERY_TIMEOUT = "Database query timeout. Orchestrator may be under heavy load. Retrying..."
    LOCK_ACQUISITION_FAILED = (
        "Could not acquire orchestrator lock after {retries} retries. Another instance may be running."
    )

    # Halt Conditions
    CIRCUIT_BREAKER_TRIGGERED = "Circuit breaker triggered: {reason}. Halting new entries to protect capital."
    POSITION_MONITORING_FAILED = "Position monitoring failed (Phase 3). Cannot exit safely."
    TRADING_HOURS_GUARD = "Cannot execute entries outside market hours (9:30 AM - 4:00 PM ET). Skipping Phase 8."

    # Dependency & Phase Failures
    UPSTREAM_PHASE_HALTED = "Cannot proceed: upstream Phase {phase} halted due to {reason}."
    PHASE_EXECUTION_ERROR = "Phase {phase} execution failed: {error}. Check logs for details."
    MISSING_PHASE_PREREQUISITE = "Phase {phase} missing required output from Phase {required_phase}."

    # Type & Validation Errors
    INVALID_TYPE_CONVERSION = "Cannot convert {value} (type {type_name}) to {target_type}: {error}."
    MISSING_REQUIRED_FIELD = "Missing required field {field} in {context}. Check data source."

    # Alpaca & Broker Integration
    ALPACA_AUTH_FAILED = "Alpaca authentication failed. Check API credentials and network connectivity."
    ALPACA_ORDER_SUBMISSION_FAILED = (
        "Order submission to Alpaca failed: {error}. Check market hours and account status."
    )

    @staticmethod
    def format(template: str, **kwargs: Any) -> str:
        """Format error message template with provided kwargs.

        Args:
            template: Error message string (may contain {key} placeholders)
            **kwargs: Values to substitute into placeholders

        Returns:
            Formatted error message
        """
        try:
            return template.format(**kwargs)
        except KeyError as e:
            return f"{template} (Missing placeholder: {e})"
