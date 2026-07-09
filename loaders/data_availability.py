#!/usr/bin/env python3
"""Data availability handling for loaders.

Provides utilities for gracefully handling unavailable data sources:
- AWS Secrets Manager unavailability
- API timeouts and connection errors
- Database query failures
- Schema validation failures

CRITICAL PRINCIPLE: When data is unavailable, mark it explicitly with data_unavailable flag
instead of returning partial/stale data or crashing.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DataUnavailableError(Exception):
    """Raised when data cannot be loaded and should be marked as unavailable.

    Use this instead of silent failures or returning empty/stale data.
    Orchestrator will catch this and mark data as data_unavailable.
    """

    def __init__(self, message: str, reason: str, loader_name: str | None = None) -> None:
        """Initialize error with metadata for logging.

        Args:
            message: User-friendly error message
            reason: Technical reason (e.g., "aws_secrets_manager_unavailable", "api_timeout")
            loader_name: Name of loader that failed (optional)
        """
        self.message = message
        self.reason = reason
        self.loader_name = loader_name
        super().__init__(message)


def handle_credential_failure(secret_name: str, error: Exception, loader_name: str = "unknown") -> dict[str, Any]:
    """Handle AWS credential fetch failure gracefully.

    CRITICAL FIX: Instead of crashing when Secrets Manager is unavailable,
    mark data as unavailable and let orchestrator handle it.

    Args:
        secret_name: Name of secret that failed to fetch
        error: The exception that occurred
        loader_name: Name of loader attempting to fetch credentials

    Returns:
        Dict with data_unavailable marker
    """
    logger.error(
        f"[DATA_UNAVAILABLE] {loader_name} failed to fetch credential '{secret_name}': {error}. "
        f"Data will be marked as unavailable."
    )
    return {
        "data_unavailable": True,
        "reason": "aws_credential_fetch_failed",
        "message": f"Could not fetch credentials for {loader_name}: {error}",
        "loader": loader_name,
    }


def handle_api_timeout(api_name: str, endpoint: str, timeout_seconds: int, loader_name: str = "unknown") -> dict[str, Any]:
    """Handle API timeout gracefully.

    CRITICAL FIX: Mark data as unavailable instead of returning partial/empty results.

    Args:
        api_name: Name of API (e.g., "yfinance", "SEC EDGAR")
        endpoint: Endpoint that timed out
        timeout_seconds: Timeout value in seconds
        loader_name: Name of loader

    Returns:
        Dict with data_unavailable marker
    """
    logger.error(
        f"[DATA_UNAVAILABLE] {api_name} timeout after {timeout_seconds}s on {endpoint} ({loader_name}). "
        f"Data will be marked as unavailable."
    )
    return {
        "data_unavailable": True,
        "reason": f"{api_name}_timeout",
        "message": f"{api_name} request timed out after {timeout_seconds}s",
        "api": api_name,
        "endpoint": endpoint,
        "loader": loader_name,
    }


def handle_database_error(query: str, error: Exception, loader_name: str = "unknown") -> dict[str, Any]:
    """Handle database query error gracefully.

    CRITICAL FIX: Mark data as unavailable instead of returning empty results.

    Args:
        query: SQL query that failed (sanitized, no credentials)
        error: The exception that occurred
        loader_name: Name of loader

    Returns:
        Dict with data_unavailable marker
    """
    logger.error(
        f"[DATA_UNAVAILABLE] Database query failed in {loader_name}: {error} (query: {query[:100]}...)"
    )
    return {
        "data_unavailable": True,
        "reason": "database_query_error",
        "message": f"Database query failed: {error}",
        "loader": loader_name,
    }


def validate_schema(data: Any, required_fields: list[str], loader_name: str = "unknown") -> tuple[bool, str | None]:
    """Validate that data has all required fields.

    CRITICAL FIX: Validate schema at loader startup, not just at runtime.

    Args:
        data: Data to validate (dict or list of dicts)
        required_fields: List of required field names
        loader_name: Name of loader for logging

    Returns:
        Tuple of (is_valid, error_message or None)
    """
    if not isinstance(data, (dict, list)):
        return False, f"Data is not dict/list (got {type(data).__name__})"

    # Handle single dict
    if isinstance(data, dict):
        data = [data]

    # Validate each item
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return False, f"Item {i} is not dict (got {type(item).__name__})"

        missing = [f for f in required_fields if f not in item]
        if missing:
            return False, f"Item {i} missing fields: {missing}"

    logger.info(f"[SCHEMA_VALID] {loader_name} schema validation passed ({len(data)} items, {len(required_fields)} required fields)")
    return True, None


def mark_data_unavailable(reason: str, loader_name: str = "unknown", details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Mark data as unavailable with metadata.

    Use this when a loader cannot produce data and should fail-closed.

    Args:
        reason: Technical reason code (e.g., "api_unavailable", "rate_limited")
        loader_name: Name of loader
        details: Additional metadata (optional)

    Returns:
        Dict with data_unavailable marker
    """
    marker = {
        "data_unavailable": True,
        "reason": reason,
        "loader": loader_name,
    }
    if details:
        marker.update(details)

    logger.warning(f"[DATA_UNAVAILABLE] {loader_name}: {reason} (details: {details})")
    return marker


def is_data_unavailable(data: Any) -> bool:
    """Check if data is marked as unavailable.

    Args:
        data: Data to check

    Returns:
        True if data has data_unavailable=True flag
    """
    if isinstance(data, dict):
        return data.get("data_unavailable") is True
    return False
