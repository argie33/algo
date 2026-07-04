#!/usr/bin/env python3
"""
Structured Database Operation Logging

Captures full context for database errors:
- SQL query that failed (sanitized to avoid exposing sensitive data)
- Parameters/arguments passed to query
- Operational context (stock ID, trade ID, position ID, loader name, etc.)
- Retry attempt number and max attempts
- Error type and traceback

This enables fast RCA when phases fail without needing to enable verbose
query logging across the entire database.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class StructuredDBLogger:
    """Formats and logs database errors with full operational context."""

    @staticmethod
    def format_query_for_logs(query: str, max_length: int = 500) -> str:
        """Sanitize query for safe logging.

        Removes:
        - correlation_id comments (already logged separately)
        - Newlines/extra whitespace
        - Sensitive correlation_id values
        """
        if not query:
            return "<empty query>"

        # Handle psycopg2.sql.Composed objects and other non-strings
        if hasattr(query, "as_string"):
            try:
                query = str(query)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"[STRUCTURED_LOGGING] Failed to convert query to string: {e}")
                return f"<{type(query).__name__} query (failed_to_convert: {type(e).__name__})>"
        elif not isinstance(query, str):
            return f"<{type(query).__name__} query>"

        # Remove SQL comments (contain correlation_id)
        query = query.split("/*")[0].strip()

        # Compress whitespace
        query = " ".join(query.split())

        # Truncate if too long
        if len(query) > max_length:
            query = query[: max_length - 3] + "..."

        return query

    @staticmethod
    def _format_param_value(param: Any) -> str:
        """Format a single parameter value."""
        if param is None:
            return "None"
        if isinstance(param, str):
            val = param if len(param) <= 50 else param[:47] + "..."
            return f'"{val}"'
        if isinstance(param, (int, float, bool)):
            return str(param)
        return str(type(param).__name__)

    @staticmethod
    def _format_list_params(params: list[Any] | tuple[Any, ...], max_items: int) -> str:
        """Format list/tuple parameters."""
        if len(params) == 0:
            return "[]"
        formatted = [StructuredDBLogger._format_param_value(p) for p in params[:max_items]]
        result = "[" + ", ".join(formatted)
        if len(params) > max_items:
            result += f", +{len(params) - max_items} more]"
        else:
            result += "]"
        return result

    @staticmethod
    def _format_dict_params(params: dict[str, Any], max_items: int) -> str:
        """Format dictionary parameters."""
        if len(params) == 0:
            return "{}"
        formatted = []
        for key, val in list(params.items())[:max_items]:
            if val is None:
                formatted.append(f"{key}: None")
            elif isinstance(val, str):
                v = val if len(val) <= 30 else val[:27] + "..."
                formatted.append(f'{key}: "{v}"')
            elif isinstance(val, (int, float, bool)):
                formatted.append(f"{key}: {val}")
            else:
                formatted.append(f"{key}: <{type(val).__name__}>")
        result = "{" + ", ".join(formatted)
        if len(params) > max_items:
            result += f", +{len(params) - max_items} more}}"
        else:
            result += "}"
        return result

    @staticmethod
    def format_parameters(params: Any, max_items: int = 10) -> str:
        """Format query parameters for logging.

        Shows first N parameters (to avoid log spam for bulk operations).
        Truncates long values.
        """
        if params is None:
            return "None"
        if isinstance(params, (list, tuple)):
            return StructuredDBLogger._format_list_params(params, max_items)
        if isinstance(params, dict):
            return StructuredDBLogger._format_dict_params(params, max_items)
        return str(params)

    @staticmethod
    def log_db_error(
        operation_name: str,
        query: str,
        params: Any | None = None,
        error: Exception | None = None,
        context: dict[str, Any] | None = None,
        retry_attempt: int | None = None,
        max_attempts: int | None = None,
    ) -> None:
        """Log a database operation error with full context.

        Args:
            operation_name: Human-readable operation name (e.g., "insert_trade")
            query: SQL query that failed
            params: Query parameters
            error: Exception that was raised
            context: Dict of operational context (stock_id, trade_id, position_id, etc.)
            retry_attempt: Current retry attempt (0-indexed)
            max_attempts: Maximum retry attempts
        """
        formatted_query = StructuredDBLogger.format_query_for_logs(query)
        formatted_params = StructuredDBLogger.format_parameters(params)

        # Build structured error context
        error_data: dict[str, Any] = {
            "operation": operation_name,
            "query": formatted_query,
            "params": formatted_params,
            "error_type": type(error).__name__ if error else "Unknown",
            "error_message": str(error) if error else "No error message",
        }

        # Add retry information if provided
        if retry_attempt is not None:
            error_data["retry"] = {
                "attempt": retry_attempt,
                "max_attempts": max_attempts or 0,
            }

        # Add operational context (stock_id, trade_id, etc.)
        if context:
            error_data["context"] = context

        # Log as structured JSON for easy parsing
        log_message = json.dumps(error_data, default=str)
        logger.error(f"[DB_ERROR] {log_message}")

        # Also log human-readable version with full traceback for debugging
        if error:
            logger.error(
                f"[DB_ERROR_DETAIL] {operation_name} failed\n"
                f"  Query: {formatted_query}\n"
                f"  Params: {formatted_params}\n"
                f"  Error: {type(error).__name__}: {error}",
                exc_info=error,
            )

    @staticmethod
    def log_retry(
        operation_name: str,
        query: str,
        params: Any | None = None,
        error: Exception | None = None,
        attempt: int = 0,
        max_attempts: int = 0,
        delay_seconds: float = 0,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Log a retry attempt with context.

        Args:
            operation_name: Operation name for logging
            query: SQL query being retried
            params: Query parameters
            error: Exception that triggered retry
            attempt: Current attempt number (0-indexed)
            max_attempts: Total allowed attempts
            delay_seconds: Delay before next attempt
            context: Operational context
        """
        formatted_query = StructuredDBLogger.format_query_for_logs(query)
        formatted_params = StructuredDBLogger.format_parameters(params)

        retry_data: dict[str, Any] = {
            "operation": operation_name,
            "attempt": attempt + 1,  # Show 1-indexed for user-readability
            "max_attempts": max_attempts,
            "error_type": type(error).__name__ if error else "Unknown",
            "delay_seconds": delay_seconds,
            "query": formatted_query,
            "params": formatted_params,
        }

        if context:
            retry_data["context"] = context

        log_message = json.dumps(retry_data, default=str)
        logger.warning(f"[DB_RETRY] {log_message}")

    @staticmethod
    def extract_context_from_params(
        params: Any | None,
    ) -> dict[str, Any]:
        """Extract common identifiers from query parameters.

        Looks for common ID patterns in parameters to auto-populate context.
        Examples: stock_id, symbol, trade_id, position_id, etc.
        """
        context: dict[str, Any] = {}

        if params is None:
            return context

        # If params is a dict, extract known keys
        if isinstance(params, dict):
            known_keys = [
                "stock_id",
                "symbol",
                "ticker",
                "trade_id",
                "position_id",
                "order_id",
                "user_id",
                "loader_name",
                "correlation_id",
            ]
            for key in known_keys:
                if params.get(key):
                    context[key] = params[key]
        elif isinstance(params, (list, tuple)) and len(params) > 0:
            # For positional params, try to infer from position
            # This is a heuristic: first string param might be symbol
            for param in params[:3]:
                if isinstance(param, str) and 1 <= len(param) <= 10:
                    # Looks like a symbol/identifier
                    if param.isalpha():
                        context["symbol"] = param.upper()
                        break

        return context
