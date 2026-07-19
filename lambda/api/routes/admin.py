"""Route: admin - System administration and inventory endpoints"""

from __future__ import annotations

from routes.algo_handlers.inventory import _get_table_inventory


def handle(cur, path: str, method: str, params: dict, body: dict | None = None, jwt_claims: dict | None = None):
    """Handle /api/admin/* endpoints."""
    if path == "/api/admin/inventory":
        return _get_table_inventory(cur)
    else:
        from routes.utils import error_response
        return error_response(404, "not_found", f"No admin handler for {path}")
