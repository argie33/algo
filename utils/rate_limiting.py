#!/usr/bin/env python3
"""
Unified Rate Limiting Strategy

Three-layer approach:
1. API Gateway (10,000 RPS global limit) — terraform/modules/services/main.tf
2. Application layer (this module) — per-endpoint rate limits
3. External APIs (yfinance, FRED) — utils/validation/rate_limit.py

This module handles Application Layer: per-endpoint, per-user/per-IP rate limiting
to prevent DoS attacks and protect expensive operations.
"""

import logging
import os
from time import time
from typing import TypedDict

import requests

logger = logging.getLogger(__name__)

# =====================================================================
# Rate Limit Constants
# =====================================================================

DEFAULT_TIME_WINDOW = 60  # seconds

# Public endpoint limits (high-frequency market data)
PUBLIC_ENDPOINT_LIMIT = 100
PUBLIC_DOC_ENDPOINT_LIMIT = 50

# Admin endpoint limits
ADMIN_HEALTH_CHECK_LIMIT = 30
ADMIN_EXPENSIVE_QUERY_LIMIT = 10
ADMIN_FULL_TABLE_SCAN_LIMIT = 20
ADMIN_HEAVY_COMPUTATION_LIMIT = 5
ADMIN_DASHBOARD_QUERY_LIMIT = 20

# Time windows for specific operations
EXPENSIVE_OPERATION_WINDOW = 60
TRIGGER_OPERATION_WINDOW = 300  # 5 minutes for patrol endpoint

# =====================================================================
# In-memory rate limit tracking (per-Lambda-instance)
# For distributed rate limiting across Lambda fleet, set use_dynamodb=True
# =====================================================================

_admin_rate_limits: dict[str, list[float]] = {}  # {user_endpoint: [timestamps, ...]}
_public_rate_limits: dict[str, list[float]] = {}  # {endpoint: [timestamps, ...]}


def _get_admin_rate_limit_key(user_id: str, endpoint: str) -> str:
    return f"{user_id}:{endpoint}"


class _RateLimitConfig(TypedDict):
    max_requests: int
    window: int
    description: str


# =====================================================================
# PUBLIC ENDPOINTS (No Authentication Required)
# Global per-endpoint rate limiting to prevent DoS attacks
# =====================================================================

PUBLIC_RATE_LIMITS: dict[str, _RateLimitConfig] = {
    # Market data endpoints (commonly accessed)
    "/api/algo/markets": {
        "max_requests": PUBLIC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Market regime data",
    },
    "/api/algo/market": {
        "max_requests": PUBLIC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Simplified market data",
    },
    "/api/algo/market-factors": {
        "max_requests": PUBLIC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Market factor analysis",
    },
    "/api/algo/swing-scores": {
        "max_requests": PUBLIC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Swing trading scores",
    },
    "/api/algo/swing-scores-history": {
        "max_requests": PUBLIC_DOC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Historical swing scores",
    },
    # Documentation endpoints (rarely accessed, prevent scraping)
    "/api/openapi.json": {
        "max_requests": PUBLIC_DOC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "OpenAPI specification",
    },
    "/api/swagger": {
        "max_requests": PUBLIC_DOC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Swagger documentation",
    },
    "/api/redoc": {
        "max_requests": PUBLIC_DOC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "ReDoc documentation",
    },
    # Dashboard endpoints (public for dev mode)
    "/api/algo/notifications": {
        "max_requests": PUBLIC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Notifications (dashboard dev mode)",
    },
    "/api/algo/execution/recent": {
        "max_requests": PUBLIC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Recent execution history (dashboard dev mode)",
    },
}


def check_public_rate_limit(
    endpoint: str,
    max_requests: int | None = None,
    window_seconds: int | None = None,
) -> tuple[bool, str | None]:
    """
    Check if a public endpoint has exceeded its global rate limit.

    Args:
        endpoint: API endpoint path (e.g., '/api/algo/markets')
        max_requests: Max requests allowed in time window (uses config if not specified)
        window_seconds: Time window in seconds (uses config if not specified)

    Returns:
        (is_allowed: bool, error_msg: Optional[str])
    """
    # Resolve max_requests and window_seconds with defaults
    if max_requests is None:
        if endpoint in PUBLIC_RATE_LIMITS:
            max_requests = PUBLIC_RATE_LIMITS[endpoint]["max_requests"]
        else:
            max_requests = PUBLIC_ENDPOINT_LIMIT

    if window_seconds is None:
        if endpoint in PUBLIC_RATE_LIMITS:
            window_seconds = PUBLIC_RATE_LIMITS[endpoint]["window"]
        else:
            window_seconds = DEFAULT_TIME_WINDOW

    now = time()
    window_start = now - window_seconds

    if endpoint not in _public_rate_limits:
        _public_rate_limits[endpoint] = []

    recent_requests = [t for t in _public_rate_limits[endpoint] if t >= window_start]
    _public_rate_limits[endpoint] = recent_requests

    if len(recent_requests) >= max_requests:
        logger.warning(
            f"Public endpoint rate limit exceeded for {endpoint}: "
            f"{len(recent_requests)} requests in {window_seconds}s window"
        )
        return (
            False,
            f"Rate limit exceeded: max {max_requests} requests per {window_seconds} seconds",
        )

    _public_rate_limits[endpoint].append(now)
    return True, None


# =====================================================================
# ADMIN ENDPOINTS (Authentication Required: Admin Group)
# Per-user, per-endpoint rate limiting to prevent abuse
# =====================================================================

ADMIN_RATE_LIMITS: dict[str, _RateLimitConfig] = {
    # Health checks (OK to poll frequently)
    "/api/admin/loader-status": {
        "max_requests": ADMIN_HEALTH_CHECK_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Check data loader freshness",
    },
    "/api/admin/system-health": {
        "max_requests": ADMIN_HEALTH_CHECK_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "System health snapshot (database, APIs, services)",
    },
    # Expensive queries (full table scans)
    "/api/admin/database-stats": {
        "max_requests": ADMIN_FULL_TABLE_SCAN_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Database statistics (table sizes, query counts)",
    },
    "/api/admin/data-quality": {
        "max_requests": ADMIN_EXPENSIVE_QUERY_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Full data quality scan (expensive - full table walk)",
    },
    # Portfolio endpoints (accessible to authenticated users)
    "/api/algo/status": {
        "max_requests": PUBLIC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Algorithm status (trades, positions, circuit breakers)",
    },
    "/api/algo/trades": {
        "max_requests": PUBLIC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Trade history with filtering/pagination",
    },
    "/api/algo/positions": {
        "max_requests": PUBLIC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Current open positions",
    },
    "/api/algo/performance": {
        "max_requests": PUBLIC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Performance metrics (returns, Sharpe, drawdown, etc.)",
    },
    "/api/algo/circuit-breakers": {
        "max_requests": PUBLIC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Circuit breaker status",
    },
    "/api/algo/equity-curve": {
        "max_requests": PUBLIC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Equity curve chart data",
    },
    "/api/algo/data-status": {
        "max_requests": PUBLIC_ENDPOINT_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Data freshness and loader status",
    },
    # Trigger operations (expensive async jobs - very low limits)
    "/api/algo/patrol": {
        "max_requests": ADMIN_HEAVY_COMPUTATION_LIMIT,
        "window": TRIGGER_OPERATION_WINDOW,
        "description": "Trigger data validation scan across all tables",
    },
    "/api/algo/pre-trade-impact": {
        "max_requests": ADMIN_FULL_TABLE_SCAN_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Estimate market impact of potential trade",
    },
    # Dashboard histogram endpoints (aggregation queries)
    "/api/algo/daily-return-histogram": {
        "max_requests": ADMIN_DASHBOARD_QUERY_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Daily returns distribution for dashboard",
    },
    "/api/algo/trade-distribution": {
        "max_requests": ADMIN_DASHBOARD_QUERY_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Trade outcome distribution for dashboard",
    },
    "/api/algo/holding-period-distribution": {
        "max_requests": ADMIN_DASHBOARD_QUERY_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Position holding period distribution for dashboard",
    },
    "/api/algo/stage-distribution": {
        "max_requests": ADMIN_DASHBOARD_QUERY_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Market stage distribution for dashboard",
    },
    # Risk dashboard endpoints
    "/api/algo/risk-dashboard": {
        "max_requests": ADMIN_DASHBOARD_QUERY_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Risk dashboard overview",
    },
    "/api/algo/risk-dashboard/drawdown": {
        "max_requests": ADMIN_DASHBOARD_QUERY_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Drawdown risk details",
    },
    "/api/algo/risk-dashboard/exposure-tier": {
        "max_requests": ADMIN_DASHBOARD_QUERY_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Sector/industry exposure analysis",
    },
    "/api/algo/risk-dashboard/position-sizing-audit": {
        "max_requests": ADMIN_DASHBOARD_QUERY_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Position sizing compliance audit",
    },
    "/api/algo/risk-dashboard/stop-loss-audit": {
        "max_requests": ADMIN_DASHBOARD_QUERY_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Stop-loss placement audit",
    },
    # Admin data endpoints
    "/api/audit/trail": {
        "max_requests": ADMIN_DASHBOARD_QUERY_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Audit trail query",
    },
    "/api/audit/trades": {
        "max_requests": ADMIN_DASHBOARD_QUERY_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Trade audit log",
    },
    "/api/audit/config": {
        "max_requests": ADMIN_DASHBOARD_QUERY_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Configuration audit log",
    },
    "/api/audit/safeguards": {
        "max_requests": ADMIN_DASHBOARD_QUERY_LIMIT,
        "window": DEFAULT_TIME_WINDOW,
        "description": "Safeguard execution audit",
    },
}


def check_admin_rate_limit(
    user_id: str,
    endpoint: str,
    max_requests: int | None = None,
    window_seconds: int | None = None,
    use_dynamodb: bool = False,
) -> tuple[bool, str | None]:
    """
    Check if user has exceeded admin endpoint rate limit.

    Args:
        user_id: Cognito user ID from JWT
        endpoint: Admin endpoint path (e.g., '/api/admin/system-health')
        max_requests: Max requests allowed in time window (uses config if not specified)
        window_seconds: Time window in seconds (uses config if not specified)
        use_dynamodb: If True, use DynamoDB for distributed rate limiting across Lambda fleet
                      If False, use in-memory (single Lambda instance only)

    Returns:
        (is_allowed: bool, error_msg: Optional[str])
    """
    # Resolve max_requests and window_seconds with defaults
    if max_requests is None:
        if endpoint in ADMIN_RATE_LIMITS:
            max_requests = ADMIN_RATE_LIMITS[endpoint]["max_requests"]
        else:
            max_requests = ADMIN_HEALTH_CHECK_LIMIT

    if window_seconds is None:
        if endpoint in ADMIN_RATE_LIMITS:
            window_seconds = ADMIN_RATE_LIMITS[endpoint]["window"]
        else:
            window_seconds = DEFAULT_TIME_WINDOW

    now = time()
    window_start = now - window_seconds

    if use_dynamodb:
        return _check_dynamodb_rate_limit(user_id, endpoint, max_requests, window_seconds, window_start)
    else:
        return _check_memory_rate_limit(user_id, endpoint, max_requests, window_seconds, window_start, now)


def _check_memory_rate_limit(
    user_id: str,
    endpoint: str,
    max_requests: int,
    window_seconds: int,
    window_start: float,
    now: float,
) -> tuple[bool, str | None]:
    key = _get_admin_rate_limit_key(user_id, endpoint)

    if key not in _admin_rate_limits:
        _admin_rate_limits[key] = []

    recent_requests = [t for t in _admin_rate_limits[key] if t >= window_start]
    _admin_rate_limits[key] = recent_requests

    if len(recent_requests) >= max_requests:
        logger.warning(
            f"Admin rate limit exceeded for user {user_id} on {endpoint}: {len(recent_requests)} requests in window"
        )
        return (
            False,
            f"Rate limit exceeded: max {max_requests} requests per {window_seconds} seconds",
        )

    _admin_rate_limits[key].append(now)
    return True, None


def _check_dynamodb_rate_limit(
    user_id: str,
    endpoint: str,
    max_requests: int,
    window_seconds: int,
    window_start: float,
) -> tuple[bool, str | None]:
    try:
        import boto3

        key = _get_admin_rate_limit_key(user_id, endpoint)
        table_name = os.getenv("ADMIN_RATE_LIMIT_TABLE")

        if not table_name:
            logger.warning("ADMIN_RATE_LIMIT_TABLE not configured, falling back to in-memory")
            now = time()
            return _check_memory_rate_limit(user_id, endpoint, max_requests, window_seconds, window_start, now)

        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(table_name)

        now = int(time())
        response = table.get_item(Key={"user_endpoint": key})
        item = response.get("Item")
        request_times = item.get("request_times")

        recent_requests = [t for t in request_times if t > int(window_start)]

        if len(recent_requests) >= max_requests:
            logger.warning(
                f"Admin rate limit exceeded (DynamoDB) for user {user_id} on {endpoint}: "
                f"{len(recent_requests)} requests"
            )
            return (
                False,
                f"Rate limit exceeded: max {max_requests} requests per {window_seconds} seconds",
            )

        recent_requests.append(now)
        table.put_item(
            Item={
                "user_endpoint": key,
                "request_times": recent_requests,
                "ttl": now + window_seconds,
            }
        )

        return True, None

    except (requests.RequestException, requests.Timeout) as e:
        logger.error(f"DynamoDB rate limit check failed: {e}, falling back to in-memory")
        now = time()
        return _check_memory_rate_limit(user_id, endpoint, max_requests, window_seconds, window_start, now)
