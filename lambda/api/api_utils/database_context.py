#!/usr/bin/env python3
"""
REST API Database Context (Re-export from utils)

DO NOT CONSOLIDATE WITH utils/database_context.py without understanding the split:

LOADER VERSION (utils/database_context.py):
- Auto-tracks correlation_id in SQL comments for audit trails
- Used by: all load_*.py, orchestrator/*.py, algo/*.py (batch operations)
- Timeout: 30s (longer batch tasks)
- Correlation tracking: ENABLED by default

API VERSION (THIS FILE - api_utils/database_context.py):
- No correlation tracking (per-request context)
- Used by: lambda/api/lambda_function.py (REST API only)
- Timeout: 20s (API Gateway hard limit is 29s)
- Correlation tracking: DISABLED (enable_correlation_tracking=False)

Why separate behavior?
- Loaders need audit trails (correlation_id in SQL comments for end-to-end tracing)
- API requests are stateless (no batch context to trace)
- Different timeout reflects operational pattern (batch vs. per-request)

This file re-exports utils.DatabaseContext with API-appropriate defaults.
"""

# Import the unified implementation from utils
import sys
from typing import Optional

from psycopg2.extras import DictCursor


sys.path.insert(0, "/".join(__file__.split("/")[:-4]))  # Navigate to root
from utils.db.context import DatabaseContext as _DatabaseContext


__all__ = ["DatabaseContext"]


class DatabaseContext(_DatabaseContext):
    """REST API database context with disabled correlation tracking.

    Re-exports utils.DatabaseContext but:
    - Sets timeout=20 (API Gateway limit)
    - Disables correlation_id tracking (enable_correlation_tracking=False)

    Usage (REST API):
        with DatabaseContext('read') as cur:
            cur.execute("SELECT * FROM table")
            rows = cur.fetchall()
    """

    def __init__(
        self,
        role: str = "read",
        timeout: int = 20,
        cursor_factory=DictCursor,
        correlation_id: Optional[str] = None,
    ):
        """Initialize REST API context with disabled correlation tracking.

        Args:
            role: 'read' or 'write'
            timeout: Connection timeout in seconds (default 20s for API Gateway)
            cursor_factory: psycopg2 cursor factory
            correlation_id: Not used for API (always disabled)
        """
        # Always disable correlation tracking for API calls
        super().__init__(
            role=role,
            timeout=timeout,
            cursor_factory=cursor_factory,
            correlation_id=None,
            enable_correlation_tracking=False,
        )
