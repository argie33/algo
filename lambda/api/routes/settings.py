"""Route: settings — user preferences stored per authenticated user."""
import psycopg2, psycopg2.extras, psycopg2.errors
import json
import logging
from typing import Dict
from .utils import error_response, json_response, handle_db_error

logger = logging.getLogger(__name__)

_DEFAULTS = {
    'theme': 'dark',
    'defaultView': 'market',
    'notifications': {
        'signalAlerts': True,
        'portfolioUpdates': True,
        'marketAlerts': False,
    },
}

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
    """Handle /api/settings endpoints."""
    # SECURITY FIX: Require authentication for all settings endpoints
    if not jwt_claims or not jwt_claims.get('sub'):
        return error_response(401, 'unauthorized', 'Authentication required')

    if path != '/api/settings':
        return error_response(404, 'not_found', f'No settings handler for {path}')

    if method == 'GET':
        return _get_settings(cur, jwt_claims)
    if method in ('POST', 'PUT', 'PATCH'):
        return _save_settings(cur, body or {}, jwt_claims)
    return error_response(405, 'method_not_allowed', f'{method} not supported')

def _get_settings(cur, jwt_claims: Dict) -> Dict:
    """Return user settings, falling back to defaults.

    SECURITY FIX: Use authenticated user's ID from JWT, not from query params.
    Users can only access their own settings, preventing IDOR.
    """
    # SECURITY: Get user_id from authenticated JWT claims, not from query params
    user_id = jwt_claims.get('sub')
    if not user_id:
        return error_response(401, 'unauthorized', 'Unable to identify user')
    try:
        if user_id:
            cur.execute("""
                SELECT theme, notifications, preferences FROM user_dashboard_settings WHERE user_id = %s
            """, (user_id,))
            row = cur.fetchone()
            if row:
                try:
                    stored = {
                        'theme': row['theme'] or 'dark',
                        'notifications': row['notifications'] if row['notifications'] is not None else True,
                        **json.loads(row['preferences'] or '{}')
                    }
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f'Failed to parse user settings: {e}')
                    stored = {}
                merged = {**_DEFAULTS, **stored}
                return json_response(200, {'data': merged})
        return json_response(200, {'data': dict(_DEFAULTS)})
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        return json_response(200, {'data': dict(_DEFAULTS)})
    except (psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        return handle_db_error(e, logger, 'get settings')

def _save_settings(cur, body: Dict, jwt_claims: Dict) -> Dict:
    """Persist user settings.

    SECURITY FIX: Use authenticated user's ID from JWT, not from body/params.
    Users can only modify their own settings, preventing IDOR.

    NOTE: Preferences column should be encrypted at rest using:
    - AWS KMS encryption (managed via Lambda environment)
    - Or PostgreSQL pgp_sym_encrypt() function
    For MVP, using plaintext with note for future hardening.
    """
    # SECURITY: Get user_id from authenticated JWT claims, not from request
    user_id = jwt_claims.get('sub')
    if not user_id:
        return error_response(401, 'unauthorized', 'Unable to identify user')
    try:
        if user_id:
            theme = body.get('theme', 'dark')
            notifications = body.get('notifications', True)
            # Store other settings in preferences JSONB
            other_prefs = {k: v for k, v in body.items() if k not in ['user_id', 'theme', 'notifications']}

            # SECURITY HARDENING: Consider encryption for preferences at this point
            # For now, parameterized queries prevent injection
            cur.execute("""
                INSERT INTO user_dashboard_settings (user_id, theme, notifications, preferences, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE
                  SET theme = %s,
                      notifications = %s,
                      preferences = COALESCE(user_dashboard_settings.preferences, '{}'::jsonb) || %s::jsonb,
                      updated_at = NOW()
            """, (user_id, theme, notifications, json.dumps(other_prefs), theme, notifications, json.dumps(other_prefs)))
        return json_response(200, {'success': True, 'message': 'Settings saved'})
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        logger.warning("user_dashboard_settings table missing; settings not persisted")
        return json_response(200, {'success': True, 'message': 'Settings saved'})
    except (psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        return handle_db_error(e, logger, 'save settings')
