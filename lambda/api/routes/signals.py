"""Route: signals - DEPRECATED (Session 267)

Deprecated: These endpoints queried stale buy_sell_daily tables.
Dashboard now uses /api/algo/dashboard-signals for fresh signal data.

See: SESSION_267_FIXES_COMPLETE.md + STALE_TABLES_DECISION_MATRIX.md
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import error_response, handle_db_error

logger = logging.getLogger(__name__)


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle /api/signals/* endpoints - DEPRECATED (Session 267).

    DEPRECATED: These endpoints query stale buy_sell_daily tables that are no longer
    maintained by the orchestrator. Dashboard uses /api/algo/dashboard-signals instead.
    These endpoints are removed to eliminate dead code querying stale data.

    See: SESSION_267_FIXES_COMPLETE.md + STALE_TABLES_DECISION_MATRIX.md
    """
    return error_response(
        410,
        "gone",
        "The /api/signals endpoints have been deprecated as of Session 267. "
        "These endpoints queried stale buy_sell_daily tables no longer maintained by the orchestrator. "
        "Use /api/algo/dashboard-signals instead for fresh trading signal data (from algo_signals table). "
        "Migration: https://github.com/argie33/algo/blob/main/SESSION_267_FIXES_COMPLETE.md"
    )
