"""Unified exception hierarchy for algo trading system.

All exceptions should inherit from AlgoError to enable consistent error handling,
logging, recovery strategies, and API responses. Each exception includes:
- error_category: Classification (TRANSIENT, PERMANENT, DATA_QUALITY)
- retry_eligible: Whether automatic retry is appropriate
- recovery_suggestion: Guidance for handling/recovery
- context: Additional context about the error (file, data, etc.)
"""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Error categorization for consistent handling and recovery."""

    TRANSIENT = "transient"  # Temporary issue, automatic retry recommended (API timeout, network)
    PERMANENT = "permanent"  # Operation will never succeed, fail-fast (invalid config, logic error)
    DATA_QUALITY = "data_quality"  # Data issue, may recover with different data (missing field, NaN)


class AlgoError(Exception):
    """Base exception for all algo trading system errors."""

    def __init__(
        self,
        message: str,
        error_category: ErrorCategory = ErrorCategory.PERMANENT,
        retry_eligible: bool = False,
        recovery_suggestion: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        """Initialize error with structured error info.

        Args:
            message: Human-readable error description
            error_category: Classification (TRANSIENT, PERMANENT, DATA_QUALITY)
            retry_eligible: Whether automatic retry could resolve this
            recovery_suggestion: Guidance for recovery/handling
            context: Additional context (file, data, field names, etc.)
        """
        super().__init__(message)
        self.message = message
        self.error_category = error_category
        self.retry_eligible = retry_eligible
        self.recovery_suggestion = recovery_suggestion
        self.context = context or {}

        # Warn for critical errors raised without diagnostic context
        if not context and error_category in (ErrorCategory.DATA_QUALITY, ErrorCategory.PERMANENT):
            logger.warning(
                f"[ERROR_CONTEXT_MISSING] {error_category.value} error raised without diagnostic context: {message}. "
                f"Pass 'context' dict with relevant details (field, table, data) for better troubleshooting."
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to structured dict for API responses."""
        return {
            "_error": self.message,
            "_error_category": self.error_category.value,
            "_retry_eligible": self.retry_eligible,
            "_recovery": self.recovery_suggestion,
            "_context": self.context,
        }


class DataLoadError(AlgoError):
    """Failed to load required data (database, API, files)."""

    def __init__(
        self,
        source: str,
        message: str,
        retry_eligible: bool = True,
        context: dict[str, Any] | None = None,
    ):
        """Init data load error.

        Args:
            source: Data source name (database, yfinance, AWS, etc.)
            message: What went wrong
            retry_eligible: Whether retry could help (True for network, False for schema)
            context: Additional data (table, file, date range, etc.)
        """
        category = ErrorCategory.TRANSIENT if retry_eligible else ErrorCategory.DATA_QUALITY
        recovery = (
            f"Verify {source} is available and accessible"
            if retry_eligible
            else f"Check data schema and {source} format"
        )
        ctx = {"source": source, **(context or {})}
        super().__init__(
            message=f"[{source}] Data load failed: {message}",
            error_category=category,
            retry_eligible=retry_eligible,
            recovery_suggestion=recovery,
            context=ctx,
        )


class ValidationError(AlgoError):
    """Data validation failed (missing fields, type errors, business logic violations)."""

    def __init__(
        self,
        field: str,
        value: object,
        expected: str,
        context: dict[str, Any] | None = None,
    ):
        """Init validation error.

        Args:
            field: Field that failed validation
            value: Actual value received
            expected: What was expected
            context: Additional validation context
        """
        ctx = {
            "field": field,
            "value": str(value),
            "expected": expected,
            **(context or {}),
        }
        super().__init__(
            message=f"Validation failed for {field}: got {value!r}, expected {expected}",
            error_category=ErrorCategory.DATA_QUALITY,
            retry_eligible=False,
            recovery_suggestion=f"Check {field} format and value range",
            context=ctx,
        )


class ConfigError(AlgoError):
    """Configuration loading or validation failed."""

    def __init__(
        self,
        config_key: str,
        message: str,
        context: dict[str, Any] | None = None,
    ):
        """Init config error.

        Args:
            config_key: Configuration key that failed
            message: What went wrong
            context: Additional config context
        """
        ctx = {"config_key": config_key, **(context or {})}
        super().__init__(
            message=f"Config error for '{config_key}': {message}",
            error_category=ErrorCategory.PERMANENT,
            retry_eligible=False,
            recovery_suggestion=f"Update configuration for {config_key}",
            context=ctx,
        )


class CircuitBreakerError(AlgoError):
    """Circuit breaker triggered - too many recent failures."""

    def __init__(
        self,
        breaker_name: str,
        failure_count: int,
        threshold: int,
        context: dict[str, Any] | None = None,
    ):
        """Init circuit breaker error.

        Args:
            breaker_name: Name of the circuit breaker
            failure_count: Number of consecutive failures
            threshold: Failure threshold that triggered the breaker
            context: Additional context
        """
        ctx = {
            "breaker": breaker_name,
            "failures": failure_count,
            "threshold": threshold,
            **(context or {}),
        }
        super().__init__(
            message=f"Circuit breaker '{breaker_name}' triggered: {failure_count} failures >= {threshold}",
            error_category=ErrorCategory.TRANSIENT,
            retry_eligible=True,
            recovery_suggestion=f"Wait for '{breaker_name}' recovery period before retrying",
            context=ctx,
        )


class PortfolioError(AlgoError):
    """Error related to portfolio state, positions, or cash balance."""

    def __init__(
        self,
        message: str,
        retry_eligible: bool = False,
        context: dict[str, Any] | None = None,
    ):
        """Init portfolio error."""
        super().__init__(
            message=f"Portfolio error: {message}",
            error_category=(ErrorCategory.DATA_QUALITY if not retry_eligible else ErrorCategory.TRANSIENT),
            retry_eligible=retry_eligible,
            recovery_suggestion="Verify portfolio snapshot is current and complete",
            context=context,
        )


class PositionError(AlgoError):
    """Error related to position state or trading."""

    def __init__(
        self,
        symbol: str,
        message: str,
        context: dict[str, Any] | None = None,
    ):
        """Init position error."""
        ctx = {"symbol": symbol, **(context or {})}
        super().__init__(
            message=f"[{symbol}] Position error: {message}",
            error_category=ErrorCategory.PERMANENT,
            retry_eligible=False,
            recovery_suggestion=f"Check {symbol} position state and market conditions",
            context=ctx,
        )


class DataContractError(AlgoError):
    """Data contract violation between phases or components."""

    def __init__(
        self,
        message: str,
        context: dict[str, Any] | None = None,
    ):
        """Init data contract error."""
        super().__init__(
            message=message,
            error_category=ErrorCategory.PERMANENT,
            retry_eligible=False,
            recovery_suggestion="Verify data contracts are met between phases",
            context=context,
        )


class MissingPhaseDataError(DataContractError):
    """Required phase data is missing or phase execution failed."""

    def __init__(
        self,
        message: str,
        context: dict[str, Any] | None = None,
    ):
        """Init missing phase data error."""
        super().__init__(message, context)


class DataSourceError(AlgoError):
    """All data sources failed for a request."""

    def __init__(
        self,
        request_desc: str,
        sources_attempted: list[str],
        last_error: Exception | None = None,
        context: dict[str, Any] | None = None,
    ):
        """Init data source error.

        Args:
            request_desc: Description of what was being requested
            sources_attempted: List of sources that were tried
            last_error: Last exception encountered
            context: Additional context
        """
        ctx = {
            "request": request_desc,
            "sources_attempted": sources_attempted,
            "last_error": str(last_error) if last_error else None,
            **(context or {}),
        }
        super().__init__(
            message=f"All data sources failed for {request_desc} (tried: {', '.join(sources_attempted)})",
            error_category=ErrorCategory.TRANSIENT,
            retry_eligible=True,
            recovery_suggestion="Verify data sources are available and network connectivity is working",
            context=ctx,
        )


class LockAcquisitionError(AlgoError):
    """Failed to acquire distributed lock for critical operation."""

    def __init__(
        self,
        lock_key: str,
        reason: str,
        context: dict[str, Any] | None = None,
    ):
        """Init lock acquisition error.

        Args:
            lock_key: Key that couldn't be locked
            reason: Why the lock couldn't be acquired
            context: Additional context
        """
        ctx = {"lock_key": lock_key, "reason": reason, **(context or {})}
        super().__init__(
            message=f"Failed to acquire lock for {lock_key}: {reason}",
            error_category=ErrorCategory.TRANSIENT,
            retry_eligible=True,
            recovery_suggestion=(
                "Verify distributed lock service (DynamoDB) is available; retry when another instance releases the lock"
            ),
            context=ctx,
        )
