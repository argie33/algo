"""Core exception hierarchy with standard HTTP status codes and error types."""

import os
import uuid
from typing import Any


class BaseAPIError(Exception):
    """Base exception for all API/application errors.

    Every exception has:
    - status_code: HTTP status code to return
    - error_type: Machine-readable error identifier
    - message: User-friendly error message
    - context: Optional dict with debugging info (not exposed to client)
    - correlation_id: For tracing errors across systems
    """

    status_code = 500
    error_type = "internal_error"

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_type: str | None = None,
        context: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ):
        self.message = message
        self.status_code = status_code or self.status_code
        self.error_type = error_type or self.error_type
        # Explicitly handle None for context (don't silently default to {})
        self.context = context if context is not None else {}
        self.correlation_id = correlation_id or os.getenv("CORRELATION_ID", str(uuid.uuid4())[:8])
        super().__init__(self.message)

    def to_response(self) -> dict[str, Any]:
        """Convert to standardized API error response."""
        return {
            "statusCode": self.status_code,
            "errorType": self.error_type,
            "message": self.message,
            "_error": self.error_type,
            "context": self.context,
        }

    def to_log_dict(self) -> dict[str, Any]:
        """Convert to log-safe dict (includes sensitive context)."""
        return {
            "statusCode": self.status_code,
            "errorType": self.error_type,
            "message": self.message,
            "context": self.context,
            "correlation_id": self.correlation_id,
        }


# Database Errors (5xx)


class DatabaseError(BaseAPIError):
    """Generic database error."""

    status_code = 503
    error_type = "database_error"


class DatabaseConnectionError(DatabaseError):
    """Database connection failed (unreachable)."""

    error_type = "connection_error"
    message = "Database connection failed"


class DatabaseQueryTimeoutError(DatabaseError):
    """Query execution exceeded timeout."""

    status_code = 504
    error_type = "timeout"
    message = "Database query exceeded timeout"


class DatabaseSchemaError(DatabaseError):
    """Database schema mismatch (missing tables/columns)."""

    error_type = "schema_error"
    message = "Database schema issue"


class DatabaseConstraintViolationError(DatabaseError):
    """Constraint violation (unique key, foreign key, etc)."""

    status_code = 409
    error_type = "constraint_violation"
    message = "Data constraint violated"


# Validation Errors (4xx)


class ValidationError(BaseAPIError):
    """Generic validation error."""

    status_code = 400
    error_type = "validation_error"


class InputValidationError(ValidationError):
    """Invalid user input (parameters, body, etc)."""

    error_type = "bad_request"
    message = "Invalid input provided"


class DataQualityError(ValidationError):
    """Data quality issue (NaN, out of range, etc)."""

    error_type = "data_quality_error"
    message = "Data quality validation failed"


class SchemaValidationError(ValidationError):
    """Schema validation error."""

    error_type = "schema_validation"
    message = "Invalid data structure"


# Timeout Errors (5xx)


class TimeoutOperationError(BaseAPIError):
    """Generic timeout error."""

    status_code = 504
    error_type = "timeout"
    message = "Operation timed out"


class DatabaseTimeoutError(TimeoutOperationError):
    """Database query timeout."""

    error_type = "database_timeout"


class ExternalAPITimeoutError(TimeoutOperationError):
    """External API call timeout."""

    error_type = "api_timeout"


class LoaderTimeoutError(TimeoutOperationError):
    """Data loader execution timeout."""

    error_type = "loader_timeout"


# External API Errors (5xx)


class ExternalAPIError(BaseAPIError):
    """Generic external API error."""

    status_code = 502
    error_type = "external_api_error"
    message = "External API call failed"


class HTTPError(ExternalAPIError):
    """HTTP error from external API."""

    error_type = "http_error"


class RateLimitedError(ExternalAPIError):
    """Rate limit exceeded by external API."""

    status_code = 429
    error_type = "rate_limited"
    message = "Too many requests to external service"


class ServiceUnavailableError(ExternalAPIError):
    """External service unavailable (503, 502)."""

    status_code = 503
    error_type = "service_unavailable"
    message = "External service temporarily unavailable"


# Data Errors (4xx/5xx)


class DataError(BaseAPIError):
    """Generic data-related error."""

    status_code = 422
    error_type = "data_error"


class MissingDataError(DataError):
    """Required data is missing."""

    error_type = "no_data"
    message = "Required data is not available"


class StaleDataError(DataError):
    """Data is too old to be useful."""

    error_type = "stale_data"
    message = "Data is outdated"


class IncompleteDataError(DataError):
    """Data is incomplete (insufficient coverage, missing fields)."""

    error_type = "incomplete_data"
    message = "Data is incomplete"


# Internal Errors (5xx)


class InternalError(BaseAPIError):
    """Generic internal/unexpected error."""

    status_code = 500
    error_type = "internal_error"
    message = "An internal error occurred"


class UnexpectedError(InternalError):
    """Unexpected/unclassified error."""

    error_type = "unexpected_error"


class ProcessingError(InternalError):
    """Error during data processing."""

    error_type = "processing_error"
    message = "Error during processing"


BaseAPIException = BaseAPIError
