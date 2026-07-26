"""Route: admin - System administration and inventory endpoints"""

from __future__ import annotations

from typing import Any

from psycopg2.extensions import cursor
from routes import sync_stock_scores
from routes.algo_handlers.inventory import _get_table_inventory


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle /api/admin/* endpoints."""
    if path == "/api/admin/inventory":
        return _get_table_inventory(cur)
    elif path == "/api/admin/sync-stock-scores-rds":
        # CRITICAL: steering/COMMON_OPERATIONS.md documents this as the emergency
        # stock_scores-sync procedure ("Use ONLY when: Scheduled stock_scores loader
        # fails or stalls for >2 hours"), but this module was never dispatched from
        # here - every call 404'd (confirmed live 2026-07-20). The handler itself was
        # complete and already admin-role-gated; it just needed wiring in.
        return sync_stock_scores.handle(cur, path, method, params, body, jwt_claims)
    else:
        from routes.utils import error_response

        return error_response(404, "not_found", f"No admin handler for {path}")
