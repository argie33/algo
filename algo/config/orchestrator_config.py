"""Orchestrator configuration - centralized settings for timeouts, thresholds, and behavior.

Supports environment variable overrides for all settings.
Enables testing with different configurations without code changes.
"""

import os
from typing import Optional


class OrchestratorConfig:
    """Configuration for orchestrator execution, loaders, and database operations."""

    # ─── Database Connection Settings ──────────────────────────────────────
    # Database operation timeouts (seconds)
    DB_TIMEOUT_GENERAL = int(os.getenv("ORCH_DB_TIMEOUT_GENERAL", "10"))
    DB_TIMEOUT_QUICK_CHECK = int(os.getenv("ORCH_DB_TIMEOUT_QUICK", "5"))
    DB_STATEMENT_TIMEOUT_MS = int(os.getenv("ORCH_DB_STATEMENT_TIMEOUT_MS", "5000"))

    # ─── Loader Monitoring ─────────────────────────────────────────────────
    # Loader completion threshold (percentage, >= this = complete)
    LOADER_COMPLETION_THRESHOLD_PCT = int(os.getenv("ORCH_LOADER_COMPLETION_THRESHOLD", "95"))

    # Maximum time to wait for critical loaders before starting Phase 1 (seconds)
    LOADER_WAIT_TIMEOUT_SECONDS = int(os.getenv("ORCH_LOADER_WAIT_TIMEOUT", "600"))

    # Polling interval for checking loader status (seconds)
    LOADER_POLL_INTERVAL_SECONDS = float(os.getenv("ORCH_LOADER_POLL_INTERVAL", "5"))

    # ─── Orchestrator Execution ───────────────────────────────────────────
    # Lock acquisition timeout (seconds) - time to retry getting run lock
    LOCK_ACQUIRE_TIMEOUT_SECONDS = int(os.getenv("ORCH_LOCK_TIMEOUT", "5"))

    # Maximum runtime buffer (minutes) - subtract from total time to prevent kill at edge
    MAX_RUNTIME_BUFFER_MINUTES = int(os.getenv("ORCH_RUNTIME_BUFFER_MINUTES", "15"))

    # Phase execution timeout (seconds) - maximum time a single phase can run
    PHASE_TIMEOUT_SECONDS = int(os.getenv("ORCH_PHASE_TIMEOUT", "900"))

    # ─── Data Quality Thresholds ──────────────────────────────────────────
    # Maximum age for data to be considered fresh (minutes)
    DATA_FRESHNESS_THRESHOLD_MINUTES = int(os.getenv("ORCH_DATA_FRESHNESS_THRESHOLD", "30"))

    # Minimum required data completeness for Phase 1 to proceed (percentage)
    MIN_DATA_COMPLETENESS_PCT = int(os.getenv("ORCH_MIN_DATA_COMPLETENESS", "80"))

    # ─── Error Handling & Retries ──────────────────────────────────────────
    # Maximum database operation retries before failing
    DB_OPERATION_MAX_RETRIES = int(os.getenv("ORCH_DB_MAX_RETRIES", "3"))

    # Retry backoff base (milliseconds) - exponential backoff factor
    DB_RETRY_BACKOFF_MS = int(os.getenv("ORCH_DB_RETRY_BACKOFF_MS", "100"))

    # ─── Feature Flags ────────────────────────────────────────────────────
    # Enable proactive loader waiting (wait for loaders before Phase 1)
    ENABLE_PROACTIVE_LOADER_WAIT = os.getenv("ORCH_ENABLE_PROACTIVE_WAIT", "true").lower() == "true"

    # Enable halt flag checking (check DynamoDB halt before executing)
    ENABLE_HALT_CHECK = os.getenv("ORCH_ENABLE_HALT_CHECK", "true").lower() == "true"

    # Enable data freshness validation (Phase 1 sanity check)
    ENABLE_DATA_FRESHNESS_CHECK = os.getenv("ORCH_ENABLE_DATA_FRESHNESS_CHECK", "true").lower() == "true"

    @classmethod
    def validate(cls) -> tuple[bool, list[str]]:
        """Validate configuration values are in acceptable ranges.

        Returns:
            (is_valid, error_messages): True if all valid, False + list of errors otherwise
        """
        errors = []

        # Validate timeouts (must be positive)
        if cls.DB_TIMEOUT_GENERAL <= 0:
            errors.append(f"DB_TIMEOUT_GENERAL must be positive, got {cls.DB_TIMEOUT_GENERAL}")

        if cls.LOADER_WAIT_TIMEOUT_SECONDS <= 0:
            errors.append(f"LOADER_WAIT_TIMEOUT_SECONDS must be positive, got {cls.LOADER_WAIT_TIMEOUT_SECONDS}")

        if cls.PHASE_TIMEOUT_SECONDS <= 0:
            errors.append(f"PHASE_TIMEOUT_SECONDS must be positive, got {cls.PHASE_TIMEOUT_SECONDS}")

        # Validate thresholds (must be 0-100)
        if not (0 <= cls.LOADER_COMPLETION_THRESHOLD_PCT <= 100):
            errors.append(f"LOADER_COMPLETION_THRESHOLD_PCT must be 0-100, got {cls.LOADER_COMPLETION_THRESHOLD_PCT}")

        if not (0 <= cls.MIN_DATA_COMPLETENESS_PCT <= 100):
            errors.append(f"MIN_DATA_COMPLETENESS_PCT must be 0-100, got {cls.MIN_DATA_COMPLETENESS_PCT}")

        # Validate polling interval (must be reasonable)
        if cls.LOADER_POLL_INTERVAL_SECONDS <= 0 or cls.LOADER_POLL_INTERVAL_SECONDS > 60:
            errors.append(f"LOADER_POLL_INTERVAL_SECONDS must be 0-60, got {cls.LOADER_POLL_INTERVAL_SECONDS}")

        return len(errors) == 0, errors

    @classmethod
    def log_config(cls, logger) -> None:
        """Log all configuration values for debugging."""
        logger.info(
            "ORCHESTRATOR CONFIG: "
            f"db_timeout={cls.DB_TIMEOUT_GENERAL}s, "
            f"loader_wait={cls.LOADER_WAIT_TIMEOUT_SECONDS}s, "
            f"loader_completion_threshold={cls.LOADER_COMPLETION_THRESHOLD_PCT}%, "
            f"phase_timeout={cls.PHASE_TIMEOUT_SECONDS}s, "
            f"halt_check_enabled={cls.ENABLE_HALT_CHECK}, "
            f"proactive_wait_enabled={cls.ENABLE_PROACTIVE_LOADER_WAIT}"
        )
