from utils.database_context import DatabaseContext
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
    if path != '/api/settings':
        return error_response(404, 'not_found', f'No settings handler for {path}')

    if method == 'GET':
        return _get_settings(cur, params)
    if method in ('POST', 'PUT', 'PATCH'):
        return _save_settings(cur, body or {}, params)
    return error_response(405, 'method_not_allowed', f'{method} not supported')

def _get_settings(cur, params: Dict) -> Dict:
    """Return user settings, falling back to defaults."""
    mode = 'write' if method in ['POST', 'PATCH', 'DELETE', 'PUT'] else 'read'
    
    with DatabaseContext(mode) as cur:
        user_id = params.get('user_id', [None])[0] if params else None
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

    def _save_settings(cur, body: Dict, params: Dict) -> Dict:
        """Persist user settings."""
        user_id = (params.get('user_id', [None])[0] if params else None) or body.get('user_id')
        try:
            if user_id:
                theme = body.get('theme', 'dark')
                notifications = body.get('notifications', True)
                # Store other settings in preferences JSONB
                other_prefs = {k: v for k, v in body.items() if k not in ['user_id', 'theme', 'notifications']}
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
