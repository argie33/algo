"""API exceptions with proper HTTP status codes.

Instead of returning error response dicts from route handlers, raise these exceptions.
The error boundary middleware in api_router catches them and formats standardized responses.
"""

import logging


logger = logging.getLogger(__name__)


class APIException(Exception):  # noqa: N818
    """Base exception for all API errors.

    Maps to HTTP status code and error type. Subclasses automatically
    set correct status_code for middleware to use.
    """

    status_code = 500
    error_type = "internal_error"

    def __init__(self, message: str, error_type: str | None = None, status_code: int | None = None):
        self.message = message
        if error_type is not None:
            self.error_type = error_type
        if status_code is not None:
            self.status_code = status_code
        super().__init__(message)


class BadRequest(APIException):
    """400 Bad Request - Invalid input parameters."""

    status_code = 400
    error_type = "bad_request"


class Unauthorized(APIException):
    """401 Unauthorized - Missing or invalid authentication."""

    status_code = 401
    error_type = "unauthorized"


class Forbidden(APIException):
    """403 Forbidden - User lacks permission for this operation."""

    status_code = 403
    error_type = "forbidden"


class NotFound(APIException):
    """404 Not Found - Resource or endpoint does not exist."""

    status_code = 404
    error_type = "not_found"


class Conflict(APIException):
    """409 Conflict - Request conflicts with current state (e.g., duplicate idempotency key)."""

    status_code = 409
    error_type = "conflict"


class UnprocessableEntity(APIException):
    """422 Unprocessable Entity - Request validation failed (semantic error)."""

    status_code = 422
    error_type = "unprocessable_entity"


class TooManyRequests(APIException):
    """429 Too Many Requests - Rate limit exceeded."""

    status_code = 429
    error_type = "rate_limit_exceeded"


class ServiceUnavailable(APIException):
    """503 Service Unavailable - Database or dependency is down."""

    status_code = 503
    error_type = "service_unavailable"


class QueryTimeout(APIException):
    """504 Gateway Timeout - Query exceeded timeout threshold."""

    status_code = 504
    error_type = "timeout"


class DataNotAvailable(APIException):
    """503 Service Unavailable - Required data has not been loaded yet."""

    status_code = 503
    error_type = "no_data"
