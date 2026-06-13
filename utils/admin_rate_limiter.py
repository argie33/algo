#!/usr/bin/env python3
"""
Admin Endpoint Rate Limiting

Protects sensitive admin operations from abuse by rate limiting per-user access
to admin endpoints beyond the global API Gateway throttling.

SECURITY: Admin endpoints are high-value targets for attackers. Per-endpoint
rate limiting provides defense-in-depth against brute force and DoS attacks.
"""

import hashlib
import logging
import os
from time import time
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# In-memory rate limit tracker: {user_endpoint: [(timestamp, count), ...]}
# Note: This is per-Lambda-instance. For distributed rate limiting, use DynamoDB.
_admin_rate_limits: Dict[str, list] = {}


def _get_rate_limit_key(user_id: str, endpoint: str) -> str:
    """Generate a unique key for rate limit tracking."""
    return f"{user_id}:{endpoint}"


def check_admin_rate_limit(
    user_id: str,
    endpoint: str,
    max_requests: int = 10,
    window_seconds: int = 60,
    use_dynamodb: bool = False,
) -> Tuple[bool, Optional[str]]:
    """
    Check if user has exceeded admin endpoint rate limit.

    Args:
        user_id: Cognito user ID from JWT
        endpoint: Admin endpoint path (e.g., '/api/admin/system-health')
        max_requests: Max requests allowed in time window
        window_seconds: Time window in seconds
        use_dynamodb: If True, use DynamoDB for distributed rate limiting
                      If False, use in-memory (single Lambda instance only)

    Returns:
        (is_allowed: bool, error_msg: Optional[str])
    """
    now = time()
    window_start = now - window_seconds

    if use_dynamodb:
        return _check_dynamodb_rate_limit(user_id, endpoint, max_requests, window_seconds, window_start)
    else:
        return _check_memory_rate_limit(user_id, endpoint, max_requests, window_start, now)


def _check_memory_rate_limit(
    user_id: str,
    endpoint: str,
    max_requests: int,
    window_start: float,
    now: float,
) -> Tuple[bool, Optional[str]]:
    """Check rate limit using in-memory tracking."""
    global _admin_rate_limits

    key = _get_rate_limit_key(user_id, endpoint)

    # Initialize or get request times for this user:endpoint
    if key not in _admin_rate_limits:
        _admin_rate_limits[key] = []

    # Remove old requests outside the window
    recent_requests = [t for t in _admin_rate_limits[key] if t >= window_start]
    _admin_rate_limits[key] = recent_requests

    # Check if limit exceeded
    if len(recent_requests) >= max_requests:
        logger.warning(
            f"Admin rate limit exceeded for user {user_id} on {endpoint}: "
            f"{len(recent_requests)} requests in window"
        )
        return False, f"Rate limit exceeded: max {max_requests} requests per minute"

    # Record this request
    _admin_rate_limits[key].append(now)
    return True, None


def _check_dynamodb_rate_limit(
    user_id: str,
    endpoint: str,
    max_requests: int,
    window_seconds: int,
    window_start: float,
) -> Tuple[bool, Optional[str]]:
    """Check rate limit using DynamoDB (distributed across Lambda instances)."""
    try:
        import boto3
        from botocore.exceptions import ClientError

        # Create unique key for DynamoDB
        key = _get_rate_limit_key(user_id, endpoint)
        table_name = os.getenv('ADMIN_RATE_LIMIT_TABLE')

        if not table_name:
            logger.warning("ADMIN_RATE_LIMIT_TABLE not configured, using in-memory limit")
            return _check_memory_rate_limit(user_id, endpoint, max_requests, window_start, time())

        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)

        now = int(time())
        response = table.get_item(Key={'user_endpoint': key})
        item = response.get('Item', {})
        request_times = item.get('request_times', [])

        # Remove old requests
        recent_requests = [t for t in request_times if t > int(window_start)]

        if len(recent_requests) >= max_requests:
            logger.warning(
                f"Admin rate limit exceeded (DynamoDB) for user {user_id} on {endpoint}: "
                f"{len(recent_requests)} requests"
            )
            return False, f"Rate limit exceeded: max {max_requests} requests per minute"

        # Record this request
        recent_requests.append(now)
        table.put_item(Item={
            'user_endpoint': key,
            'request_times': recent_requests,
            'ttl': now + window_seconds,
        })

        return True, None

    except Exception as e:
        logger.error(f"DynamoDB rate limit check failed: {e}, falling back to in-memory")
        return _check_memory_rate_limit(user_id, endpoint, max_requests, window_start, time())


# Rate limit profiles for different admin endpoints
ADMIN_RATE_LIMITS = {
    '/api/admin/loader-status': {'max_requests': 30, 'window': 60},  # OK to check frequently
    '/api/admin/system-health': {'max_requests': 30, 'window': 60},   # Health checks
    '/api/admin/database-stats': {'max_requests': 20, 'window': 60},  # Expensive queries
    '/api/admin/data-quality': {'max_requests': 10, 'window': 60},    # Full scan - expensive
    '/api/algo/status': {'max_requests': 10, 'window': 60},           # High-value endpoint
    '/api/algo/trades': {'max_requests': 10, 'window': 60},           # Sensitive data
    '/api/algo/positions': {'max_requests': 10, 'window': 60},        # Sensitive data
    '/api/algo/patrol': {'max_requests': 5, 'window': 300},           # Triggers expensive operation
    '/api/algo/pre-trade-impact': {'max_requests': 5, 'window': 300}, # Triggers expensive operation
    '/api/algo/daily-return-histogram': {'max_requests': 20, 'window': 60},  # Dashboard histogram
    '/api/algo/trade-distribution': {'max_requests': 20, 'window': 60},      # Dashboard histogram
    '/api/algo/holding-period-distribution': {'max_requests': 20, 'window': 60},  # Dashboard histogram
    '/api/algo/stage-distribution': {'max_requests': 20, 'window': 60},  # Dashboard histogram
}
