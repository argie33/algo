"""Reusable decorators for standardized error handling across all layers.

Provides:
- @db_route_handler: For API route database operations (enhanced)
- @external_api_handler: For external API calls with retry/timeout
- @validation_handler: For input validation with 400 errors
- @timeout_handler: For operations with timeout enforcement
- @transactional: For database transactions with auto-rollback
- @loader_operation: For batch loader operations with status tracking
"""

import functools
import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import psycopg2
import requests

logger = logging.getLogger(__name__)


def db_route_handler(
    operation_name: str,
    default_error_response: Any = None,
    role: str = "read",
    timeout_sec: int | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Catch database errors, log, return standardized error response.

    Usage:
        @db_route_handler('fetch user data')
        def _get_users(cur):
            cur.execute("SELECT * FROM users")
            return json_response(200, cur.fetchall())

    Args:
        operation_name: Description of operation for logging
        default_error_response: DEPRECATED - ignored for compatibility
        role: 'read' or 'write' (for logging/monitoring)
        timeout_sec: Optional timeout in seconds

    Returns:
        Decorated function that catches database errors
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            from utils.error_handlers import make_error_response

            try:
                return func(*args, **kwargs)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                # Use centralized error classification
                context = {
                    "operation": operation_name,
                    "role": role,
                    "function": func.__name__,
                }
                return make_error_response(e, operation_name, context)

        return wrapper

    return decorator


def external_api_handler(
    operation_name: str,
    timeout: int = 10,
    max_retries: int = 3,
    backoff_initial: float = 1.0,
    backoff_multiplier: float = 2.0,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Catch external API errors with automatic retry and timeout.

    Usage:
        @external_api_handler('fetch sentiment', timeout=10, max_retries=3)
        def _get_sentiment(url):
            response = requests.get(url, timeout=10)
            return response.json()

    Args:
        operation_name: Description of operation
        timeout: Timeout in seconds
        max_retries: Number of retry attempts
        backoff_initial: Initial backoff in seconds
        backoff_multiplier: Multiply backoff by this each retry

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            from utils.error_handlers import make_error_response, retry_with_backoff

            def execute_with_timeout():
                return func(*args, **kwargs)

            try:
                # Add timeout enforcement
                import signal

                def timeout_handler(signum, frame):
                    raise TimeoutError(f"{operation_name} exceeded {timeout}s timeout")

                signal.signal(signal.SIGALRM, timeout_handler)  # type: ignore[attr-defined]
                signal.alarm(timeout)  # type: ignore[attr-defined]
                try:
                    return retry_with_backoff(
                        execute_with_timeout,
                        max_attempts=max_retries,
                        initial_backoff_sec=backoff_initial,
                        backoff_multiplier=backoff_multiplier,
                    )
                finally:
                    signal.alarm(0)  # type: ignore[attr-defined]  # Cancel alarm
            except (
                requests.RequestException,
                requests.Timeout,
                json.JSONDecodeError,
            ) as e:
                context = {
                    "operation": operation_name,
                    "timeout_sec": timeout,
                    "max_retries": max_retries,
                }
                return make_error_response(e, operation_name, context)

        return wrapper

    return decorator


def validation_handler(
    operation_name: str,
    schema_class: type[Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Validate input with automatic schema validation.

    Usage:
        from pydantic import BaseModel
        class UserSchema(BaseModel):
            name: str
            email: str

        @validation_handler('create user', schema_class=UserSchema)
        def _create_user(body):
            # body is automatically validated
            return json_response(201, body)

    Args:
        operation_name: Description of operation
        schema_class: Optional Pydantic schema for validation

    Returns:
        Decorated function with validation
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            from utils.error_handlers import make_error_response

            try:
                # Find body argument
                body = kwargs.get("body") or (args[1] if len(args) > 1 else None)

                # Validate if schema provided
                if schema_class and body:
                    try:
                        validated = schema_class.parse_obj(body)
                        # Replace body with validated version
                        if "body" in kwargs:
                            kwargs["body"] = validated
                        else:
                            args_list = list(args)
                            args_list[1] = validated
                            args = tuple(args_list)
                    except Exception as e:
                        from utils.exceptions import InputValidationError

                        raise InputValidationError(
                            f"Invalid input: {e!s}",
                            context={"validation_error": str(e)},
                        ) from e

                return func(*args, **kwargs)
            except Exception as e:
                context = {"operation": operation_name}
                return make_error_response(e, operation_name, context)

        return wrapper

    return decorator


def timeout_handler(
    operation_name: str,
    timeout_sec: int = 25,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Enforce timeout on operation.

    Usage:
        @timeout_handler('fetch market data', timeout_sec=15)
        def _get_market(cur):
            ...

    Args:
        operation_name: Description of operation
        timeout_sec: Timeout in seconds

    Returns:
        Decorated function with timeout enforcement
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            import signal

            from utils.error_handlers import make_error_response

            def timeout_signal_handler(signum, frame):
                raise TimeoutError(f"{operation_name} exceeded {timeout_sec}s timeout")

            # Set timeout signal (Unix only)
            try:
                signal.signal(signal.SIGALRM, timeout_signal_handler)
                signal.alarm(timeout_sec)
            except (AttributeError, ValueError):
                # Windows or already set
                pass

            try:
                return func(*args, **kwargs)
            except Exception as e:
                context = {
                    "operation": operation_name,
                    "timeout_sec": timeout_sec,
                }
                return make_error_response(e, operation_name, context)
            finally:
                try:
                    signal.alarm(0)  # Cancel alarm
                except (AttributeError, ValueError):
                    pass

        return wrapper

    return decorator


def transactional(
    operation_name: str,
    should_rollback: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Wrap transaction with automatic rollback on error.

    Usage:
        @transactional('reconcile positions')
        def reconcile(cur):
            cur.execute("INSERT INTO positions ...")
            cur.execute("UPDATE portfolio ...")
            # Auto-commit/rollback handled

    Args:
        operation_name: Description of operation
        should_rollback: Whether to rollback on error

    Returns:
        Decorated function with transaction handling
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            from utils.error_handlers import make_error_response

            cur = args[0] if args else None

            try:
                result = func(*args, **kwargs)
                # Auto-commit (connection commits on context exit)
                return result
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                # Auto-rollback
                if cur and should_rollback:
                    try:
                        cur.connection.rollback()
                        logger.error(f"Rolled back transaction for {operation_name}")
                    except (
                        psycopg2.DatabaseError,
                        psycopg2.OperationalError,
                    ) as rollback_err:
                        logger.error(f"Failed to rollback: {rollback_err}")

                context = {"operation": operation_name}
                return make_error_response(e, operation_name, context)

        return wrapper

    return decorator


def loader_operation(
    table_name: str,
    operation_type: str = "insert",
    symbol: str | None = None,
    correlation_id: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Wrap loader operation with auto-logging and status tracking.

    Usage:
        @loader_operation(table_name='price_daily', symbol='AAPL')
        def load_prices(symbol):
            return fetch_and_insert_prices(symbol)

    Args:
        table_name: Target table name
        operation_type: 'insert', 'update', 'fetch', 'transform'
        symbol: Optional symbol for tracking
        correlation_id: Correlation ID for audit trail

    Returns:
        Decorated function with error tracking
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            from utils.error_handlers import log_error_with_context

            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                logger.info(f"[{operation_type.upper()}] {table_name} ({symbol or 'all'}) completed in {duration:.2f}s")
                return result
            except Exception as e:
                duration = time.time() - start_time
                context = {
                    "table_name": table_name,
                    "operation_type": operation_type,
                    "symbol": symbol,
                    "correlation_id": correlation_id,
                    "duration_sec": duration,
                }
                log_error_with_context(e, f"loader[{table_name}]", context)
                # Return structured error result instead of raising
                return {
                    "success": False,
                    "rows_processed": 0,
                    "rows_inserted": 0,
                    "error": str(e),
                    "duration_sec": duration,
                }

        return wrapper

    return decorator


def rate_limit_handler(
    operation_name: str,
    max_requests: int = 10,
    window_seconds: int = 60,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Rate limit operation to prevent abuse.

    Usage:
        @rate_limit_handler('expensive_query', max_requests=5, window_seconds=60)
        def expensive_operation():
            ...

    Args:
        operation_name: Operation identifier
        max_requests: Max requests allowed
        window_seconds: Time window in seconds

    Returns:
        Decorated function with rate limiting
    """
    import threading

    request_times: list[float] = []
    lock = threading.Lock()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            from utils.error_handlers import make_error_response
            from utils.exceptions import RateLimitedError

            nonlocal request_times

            with lock:
                now = time.time()
                # Remove old requests outside window
                request_times = [t for t in request_times if now - t < window_seconds]

                if len(request_times) >= max_requests:
                    error = RateLimitedError(
                        f"Rate limit exceeded: {max_requests} requests per {window_seconds}s",
                        context={"operation": operation_name},
                    )
                    return make_error_response(error, operation_name)

                request_times.append(now)

            try:
                return func(*args, **kwargs)
            except Exception as e:
                context = {"operation": operation_name}
                return make_error_response(e, operation_name, context)

        return wrapper

    return decorator


def circuit_breaker(
    operation_name: str,
    failure_threshold: int = 5,
    recovery_timeout_sec: int = 300,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Circuit breaker pattern: fail-fast after N consecutive failures.

    Usage:
        @circuit_breaker('external_api_call', failure_threshold=3, recovery_timeout_sec=60)
        def call_external_api():
            ...

    Args:
        operation_name: Operation identifier
        failure_threshold: Number of failures before tripping
        recovery_timeout_sec: Timeout before attempting recovery

    Returns:
        Decorated function with circuit breaker
    """
    failures = 0
    last_failure_time: float | None = None
    lock = threading.Lock()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal failures, last_failure_time

            with lock:
                # Check if circuit is open (too many failures)
                if failures >= failure_threshold:
                    now = time.time()
                    if last_failure_time and now - last_failure_time < recovery_timeout_sec:
                        from utils.error_handlers import make_error_response
                        from utils.exceptions import ServiceUnavailableError

                        error = ServiceUnavailableError(
                            f"Circuit breaker open for {operation_name}",
                            context={"failures": failures},
                        )
                        return make_error_response(error, operation_name)
                    else:
                        # Recovery timeout expired, reset
                        failures = 0
                        last_failure_time = None

            try:
                result = func(*args, **kwargs)
                with lock:
                    failures = 0  # Reset on success
                return result
            except Exception as e:
                with lock:
                    failures += 1
                    last_failure_time = time.time()

                from utils.error_handlers import make_error_response

                context = {"operation": operation_name, "failure_count": failures}
                return make_error_response(e, operation_name, context)

        return wrapper

    return decorator
