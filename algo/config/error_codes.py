"""Standardized error codes for orchestrator and critical paths.

PHASE 3: Ensures all errors are properly classified and can be handled consistently.
"""

from enum import Enum
from typing import Any


class ErrorCode(Enum):
    """Standard error codes for orchestrator failure modes."""

    # Configuration Errors (100-199)
    ENV_VAR_MISSING = "ENV_001"
    ENV_VAR_INVALID = "ENV_002"
    CONFIG_KEY_MISSING = "CONFIG_001"
    CONFIG_VALUE_INVALID = "CONFIG_002"
    CONFIG_LOAD_FAILED = "CONFIG_003"

    # Database Errors (200-299)
    DB_CONNECTION_FAILED = "DB_001"
    DB_TIMEOUT = "DB_002"
    DB_QUERY_FAILED = "DB_003"
    DB_SCHEMA_MISSING = "DB_004"
    DB_TABLE_NOT_FOUND = "DB_005"
    DB_VIEW_NOT_FOUND = "DB_006"

    # Loader Errors (300-399)
    LOADER_MISSING = "LOADER_001"
    LOADER_STALE = "LOADER_002"
    LOADER_INCOMPLETE = "LOADER_003"
    LOADER_HUNG = "LOADER_004"
    LOADER_FAILED = "LOADER_005"
    DATA_QUALITY_INSUFFICIENT = "LOADER_006"

    # Orchestrator Errors (400-499)
    ORCHESTRATOR_INIT_FAILED = "ORCH_001"
    ORCHESTRATOR_LOCK_FAILED = "ORCH_002"
    ORCHESTRATOR_PHASE_FAILED = "ORCH_003"
    ORCHESTRATOR_TIMEOUT = "ORCH_004"
    ORCHESTRATOR_HALTED = "ORCH_005"

    # Credential Errors (500-599)
    ALPACA_AUTH_FAILED = "CRED_001"
    AWS_AUTH_FAILED = "CRED_002"
    CREDENTIAL_MISSING = "CRED_003"

    # Market Errors (600-699)
    MARKET_CLOSED = "MARKET_001"
    MARKET_DATA_UNAVAILABLE = "MARKET_002"
    MARKET_API_ERROR = "MARKET_003"

    # Trade Execution Errors (700-799)
    TRADE_REJECTED = "TRADE_001"
    TRADE_INSUFFICIENT_FUNDS = "TRADE_002"
    TRADE_POSITION_LIMIT = "TRADE_003"
    TRADE_CIRCUIT_BREAKER = "TRADE_004"

    # Unknown Errors (999)
    UNKNOWN = "UNKNOWN_001"

    @property
    def error_number(self) -> str:
        """Get the numeric error code."""
        return self.value


class ErrorSeverity(Enum):
    """Error severity levels for routing and alerting."""

    INFO = "INFO"  # Informational (not an error)
    WARNING = "WARNING"  # Warning (may need attention)
    ERROR = "ERROR"  # Error (operation failed)
    CRITICAL = "CRITICAL"  # Critical (system halted)


ERROR_SEVERITY_MAP = {
    # Configuration errors are CRITICAL (system won't start)
    ErrorCode.ENV_VAR_MISSING: ErrorSeverity.CRITICAL,
    ErrorCode.CONFIG_KEY_MISSING: ErrorSeverity.CRITICAL,
    # Database errors are CRITICAL (can't access data)
    ErrorCode.DB_CONNECTION_FAILED: ErrorSeverity.CRITICAL,
    ErrorCode.DB_SCHEMA_MISSING: ErrorSeverity.CRITICAL,
    # Loader errors are CRITICAL (no data = no trading)
    ErrorCode.LOADER_MISSING: ErrorSeverity.CRITICAL,
    ErrorCode.LOADER_STALE: ErrorSeverity.CRITICAL,
    ErrorCode.DATA_QUALITY_INSUFFICIENT: ErrorSeverity.CRITICAL,
    # Orchestrator failures are CRITICAL
    ErrorCode.ORCHESTRATOR_PHASE_FAILED: ErrorSeverity.CRITICAL,
    ErrorCode.ORCHESTRATOR_HALTED: ErrorSeverity.CRITICAL,
    # Credential errors are CRITICAL
    ErrorCode.ALPACA_AUTH_FAILED: ErrorSeverity.CRITICAL,
    # Trade execution can be ERROR (single trade failure)
    ErrorCode.TRADE_REJECTED: ErrorSeverity.ERROR,
    ErrorCode.TRADE_CIRCUIT_BREAKER: ErrorSeverity.ERROR,
    # Timeouts are WARNING (can retry)
    ErrorCode.DB_TIMEOUT: ErrorSeverity.WARNING,
    ErrorCode.ORCHESTRATOR_TIMEOUT: ErrorSeverity.WARNING,
    # Default
    ErrorCode.UNKNOWN: ErrorSeverity.ERROR,
}


def get_severity(error_code: ErrorCode) -> ErrorSeverity:
    """Get severity for an error code."""
    return ERROR_SEVERITY_MAP.get(error_code, ErrorSeverity.ERROR)


class OrchestrationError(Exception):
    """Base class for orchestration errors with standardized codes."""

    def __init__(self, error_code: ErrorCode, message: str, details: dict[str, Any] | None = None):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        self.severity = get_severity(error_code)

        super().__init__(f"[{error_code.value}] {message}")

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for logging/alerting."""
        return {
            "error_code": self.error_code.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
        }
