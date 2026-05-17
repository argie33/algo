"""
Per-endpoint rate limiting configuration.

Defines rate limits for each API endpoint based on computational cost:
- VERY_CHEAP (1000+ req/min): Simple lookups, no DB queries
- CHEAP (500 req/min): Single table scans, no JOINs
- MODERATE (200 req/min): 1-2 JOINs, full table aggregations
- EXPENSIVE (50 req/min): 5+ JOINs, complex window functions, multi-table aggregations
- VERY_EXPENSIVE (10 req/min): Real-time computation, full dataset processing

Prevents DoS attacks on expensive endpoints while allowing reasonable traffic on cheap ones.
"""

import re
from typing import Tuple, Optional


class RateLimitConfig:
    """Per-endpoint rate limit configuration."""

    # Format: (max_requests_per_window, window_seconds)
    LIMITS = {
        # VERY EXPENSIVE (10 req/min) - Full dataset analysis, real-time computation
        '/api/stocks/backtesting': (10, 60),
        '/api/algo/equity-curve': (10, 60),
        '/api/algo/sector-rotation': (10, 60),
        '/api/algo/sector-breadth': (10, 60),
        '/api/algo/rejection-funnel': (10, 60),
        '/api/algo/patrol-log': (10, 60),
        '/api/market/correlation-matrix': (10, 60),
        '/api/stocks/correlation': (10, 60),
        '/api/portfolio/optimization': (10, 60),

        # EXPENSIVE (50 req/min) - Complex joins, multi-table aggregations
        '/api/algo/trades': (50, 60),
        '/api/algo/positions': (50, 60),
        '/api/algo/performance': (50, 60),
        '/api/algo/swing-scores-history': (50, 60),
        '/api/signals/ranked': (50, 60),
        '/api/stocks/screener': (50, 60),
        '/api/economic/leading-indicators': (50, 60),
        '/api/market/breadth': (50, 60),
        '/api/market/sector-performance': (50, 60),
        '/api/sentiment/fear-greed': (50, 60),
        '/api/portfolio/analytics': (50, 60),

        # MODERATE (200 req/min) - Simple joins, small aggregations
        '/api/algo/status': (200, 60),
        '/api/algo/circuit-breakers': (200, 60),
        '/api/algo/data-status': (200, 60),
        '/api/algo/notifications': (200, 60),
        '/api/algo/swing-scores': (200, 60),
        '/api/algo/markets': (200, 60),
        '/api/signals/stocks': (200, 60),
        '/api/signals/etfs': (200, 60),
        '/api/prices/daily': (200, 60),
        '/api/prices/weekly': (200, 60),
        '/api/prices/monthly': (200, 60),
        '/api/stocks/list': (200, 60),
        '/api/stocks/summary': (200, 60),
        '/api/stocks/details': (200, 60),
        '/api/stocks/financials': (200, 60),
        '/api/sectors/list': (200, 60),
        '/api/market/health': (200, 60),
        '/api/market/holidays': (200, 60),
        '/api/economic/indicators': (200, 60),
        '/api/economic/calendar': (200, 60),
        '/api/portfolio/summary': (200, 60),
        '/api/portfolio/holdings': (200, 60),

        # CHEAP (500 req/min) - Single table lookups, no joins
        '/api/stocks/symbols': (500, 60),
        '/api/market/calendar': (500, 60),
        '/api/health': (500, 60),
        '/api/config': (500, 60),

        # VERY CHEAP (1000+ req/min) - Static responses, no DB queries
        '/api/version': (1000, 60),
        '/health': (1000, 60),
        '/': (1000, 60),
    }

    # Wildcard patterns for endpoint categories (regex)
    WILDCARD_LIMITS = [
        # Pattern: (regex, max_requests, window_seconds)
        (r'^/api/admin/', 20, 60),  # Admin endpoints: very low limit
        (r'^/api/internal/', 50, 60),  # Internal endpoints: restricted
        (r'^/api/.*', 100, 60),  # Default for any /api/* endpoint not explicitly listed
    ]

    @classmethod
    def get_limit(cls, path: str) -> Tuple[int, int]:
        """
        Get rate limit for endpoint.

        Returns: (max_requests, window_seconds)
        """
        # Check exact match first (highest priority)
        if path in cls.LIMITS:
            return cls.LIMITS[path]

        # Check wildcard patterns
        for pattern, max_requests, window_seconds in cls.WILDCARD_LIMITS:
            if re.match(pattern, path):
                return max_requests, window_seconds

        # Default fallback: 100 req/min
        return 100, 60

    @classmethod
    def get_limit_description(cls, path: str) -> str:
        """Get human-readable limit description."""
        max_requests, window_seconds = cls.get_limit(path)

        if window_seconds == 60:
            return f'Max {max_requests} requests per minute'
        elif window_seconds == 3600:
            return f'Max {max_requests} requests per hour'
        else:
            return f'Max {max_requests} requests per {window_seconds} seconds'

    @classmethod
    def is_expensive_endpoint(cls, path: str) -> bool:
        """Check if endpoint is expensive (< 50 req/min)."""
        max_requests, _ = cls.get_limit(path)
        return max_requests <= 50

    @classmethod
    def categorize_endpoint(cls, path: str) -> str:
        """Categorize endpoint by cost."""
        max_requests, _ = cls.get_limit(path)

        if max_requests >= 1000:
            return 'VERY_CHEAP'
        elif max_requests >= 500:
            return 'CHEAP'
        elif max_requests >= 200:
            return 'MODERATE'
        elif max_requests >= 50:
            return 'EXPENSIVE'
        else:
            return 'VERY_EXPENSIVE'


def check_endpoint_rate_limit(
    ip: str,
    path: str,
    rate_limit_tracker: dict,
    rate_limit_check_count: int
) -> Tuple[bool, str, int]:
    """
    Check if request to endpoint is allowed under rate limit.

    Returns: (allowed, description, http_status_code)
    """
    import time

    current_time = time.time()
    max_requests, window_seconds = RateLimitConfig.get_limit(path)

    # Periodic cleanup
    rate_limit_check_count += 1
    if rate_limit_check_count % 100 == 0:
        for tracked_ip in list(rate_limit_tracker.keys()):
            rate_limit_tracker[tracked_ip] = [
                t for t in rate_limit_tracker[tracked_ip]
                if current_time - t < window_seconds
            ]
            if not rate_limit_tracker[tracked_ip]:
                del rate_limit_tracker[tracked_ip]

    # Initialize tracking for IP if needed
    if ip not in rate_limit_tracker:
        rate_limit_tracker[ip] = []

    # Remove old requests outside window
    rate_limit_tracker[ip] = [
        t for t in rate_limit_tracker[ip]
        if current_time - t < window_seconds
    ]

    # Check if limit exceeded
    if len(rate_limit_tracker[ip]) >= max_requests:
        description = RateLimitConfig.get_limit_description(path)
        return False, description, 429

    # Record this request
    rate_limit_tracker[ip].append(current_time)
    return True, 'OK', 200


__all__ = [
    'RateLimitConfig',
    'check_endpoint_rate_limit',
]
