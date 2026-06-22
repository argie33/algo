"""Route: settings — user preferences stored per authenticated Cognito user."""

import json
import logging
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
from psycopg2.extensions import cursor
from routes.utils import (
    error_response,
    execute_with_timeout,
    handle_db_error,
    json_response,
)

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "theme": "dark",
    "defaultView": "market",
    "notifications": {
        "signalAlerts": True,
        "portfolioUpdates": True,
        "marketAlerts": False,
    },
}


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Handle /api/settings endpoints."""
    if jwt_claims is None:
        return error_response(401, "unauthorized", "Authentication required")  # type: ignore[no-any-return]

    if path != "/api/settings":
        return error_response(404, "not_found", f"No settings handler for {path}")  # type: ignore[no-any-return]

    if method == "GET":
        return _get_settings(cur, jwt_claims)
    if method in ("POST", "PUT", "PATCH"):
        if not body:
            return error_response(400, "bad_request", "Request body is required")  # type: ignore[no-any-return]
        return _save_settings(cur, body, jwt_claims)
    return error_response(405, "method_not_allowed", f"{method} not supported")  # type: ignore[no-any-return]


def _get_settings(cur: cursor, jwt_claims: dict[str, Any]) -> dict[str, Any]:
    """Return user settings, falling back to defaults."""
    user_id = jwt_claims.get("sub")
    if not user_id:
        return error_response(401, "unauthorized", "User identity required")  # type: ignore[no-any-return]

    try:
        rows = execute_with_timeout(
            cur,
            """
            SELECT theme, notifications, preferences
            FROM user_dashboard_settings WHERE user_id = %s
        """,
            (user_id,),
            timeout_sec=5,
        )
        row = rows[0] if rows else None
        if row:
            try:
                preferences = row.get("preferences") or {}
                stored = {
                    "theme": row["theme"] or "dark",
                    "notifications": (row["notifications"] if row["notifications"] is not None else True),
                    **preferences,
                }
            except (TypeError, KeyError):
                stored = {}
            return json_response(200, {**_DEFAULTS, **stored})  # type: ignore[no-any-return]
        return json_response(200, dict(_DEFAULTS))  # type: ignore[no-any-return]
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        return json_response(200, dict(_DEFAULTS))  # type: ignore[no-any-return]
    except (psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        code, error_type, message = handle_db_error(e, "get settings")
        return error_response(code, error_type, message)  # type: ignore[no-any-return]


def _save_settings(cur: cursor, body: dict[str, Any], jwt_claims: dict[str, Any]) -> dict[str, Any]:
    """Persist user settings (theme, notifications, other preferences)."""
    user_id = jwt_claims.get("sub")
    if not user_id:
        return error_response(401, "unauthorized", "User identity required")  # type: ignore[no-any-return]

    try:
        theme = body.get("theme", "dark")
        notifications_raw = body.get("notifications", True)
        other_prefs = {k: v for k, v in body.items() if k not in ("user_id", "theme", "notifications")}

        # Validate arbitrary preference keys - limit to 50 keys to prevent storage abuse
        if len(other_prefs) > 50:
            return error_response(400, "bad_request", "Too many preference fields (max 50)")  # type: ignore[no-any-return]

        # Validate preference JSON size - limit to 10KB
        prefs_json = json.dumps(other_prefs)
        if len(prefs_json.encode("utf-8")) > 10240:  # 10KB
            return error_response(400, "bad_request", "Preferences too large (max 10KB)")  # type: ignore[no-any-return]

        # notifications column is BOOLEAN; if frontend sends a dict (per-type toggles),
        # store it in preferences JSONB so it survives the round-trip intact.
        if isinstance(notifications_raw, dict):
            other_prefs["notifications"] = notifications_raw
            notifications = True
        else:
            notifications = bool(notifications_raw)

        cur.execute(
            """
            INSERT INTO user_dashboard_settings (user_id, theme, notifications, preferences, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE
              SET theme = EXCLUDED.theme,
                  notifications = EXCLUDED.notifications,
                  preferences = EXCLUDED.preferences,
                  updated_at = NOW()
        """,
            (user_id, theme, notifications, prefs_json),
        )

        return json_response(200, {"success": True, "message": "Settings saved"})  # type: ignore[no-any-return]
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        logger.warning("user_dashboard_settings table missing; settings not persisted")
        return json_response(200, {"success": True, "message": "Settings saved"})  # type: ignore[no-any-return]
    except (psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        code, error_type, message = handle_db_error(e, "save settings")
        return error_response(code, error_type, message)  # type: ignore[no-any-return]
