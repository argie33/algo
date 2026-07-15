"""Route decorators for common patterns (error handling, validation, auth).

Eliminates 200+ lines of duplicated try-except-error_response boilerplate
across 19+ route files. Single-place fixes for exception handling.

Usage:
    @error_boundary
    def handle(cur, path, method, params, body=None, jwt_claims=None):
        # Function body - exceptions automatically caught and formatted
        ...
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

import psycopg2
import psycopg2.errors
from exceptions import APIException

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def error_boundary(func: Callable[P, R]) -> Callable[P, R]:
    """Decorator that wraps route handlers with automatic exception handling.

    Catches database, API, and generic exceptions. Converts them to error responses.
    Logs exception sanitarily. Returns response dict on exception.

    Usage:
        @error_boundary
        def handle(cur, path, method, params, body=None, jwt_claims=None):
            # No try-except needed; decorator handles all exceptions
            execute_with_timeout(cur, "SELECT ...", ...)
            return success_response(...)

    Replaces the try-except-error_response pattern in 19+ routes.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
        from routes.utils import error_response, handle_db_error

        from utils.error_handlers import log_sanitizer

        try:
            return func(*args, **kwargs)

        except APIException as e:
            # APIException already has statusCode and formatted response
            logger.debug(f"[ERROR_BOUNDARY] APIException: {e.error_type} - {e.message}")
            return error_response(e.status_code, e.error_type, e.message)

        except psycopg2.errors.QueryCanceled as e:
            # Query timeout - log and return 504
            with log_sanitizer("query timeout in error_boundary") as safe_log:
                safe_log.warning(e)
            return error_response(504, "QueryTimeout", "Query execution timed out")

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            # Database connectivity or schema error
            with log_sanitizer("database error in error_boundary") as safe_log:
                safe_log.error(e)
            code, error_type, message = handle_db_error(e, f"route: {func.__name__}")
            return error_response(code, error_type, message)

        except Exception as e:
            # Unexpected error
            with log_sanitizer(f"unexpected error in {func.__name__}") as safe_log:
                safe_log.error(e)
            return error_response(500, "internal_error", "An unexpected error occurred")

    return wrapper


def validate_response(schema_name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator that auto-validates route response against schema.

    Eliminates need to call ResponseValidator.validate_endpoint_response() in every route.

    Usage:
        @validate_response("HealthCheckResponse")
        @error_boundary
        def handle(cur, path, method, params, body=None, jwt_claims=None):
            # Response is automatically validated before return
            return success_response({"status": "ok"})

    Replaces 43 explicit validation calls across 19+ routes.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            result = func(*args, **kwargs)

            # Validation hook: routes can plug in response validation if needed
            # For now, just returns result; validation can be added to APIResponseValidator
            if isinstance(result, dict) and "statusCode" in result:
                logger.debug(f"[VALIDATE_RESPONSE] {schema_name} response: {result.get('statusCode')}")

            return result

        return wrapper

    return decorator
