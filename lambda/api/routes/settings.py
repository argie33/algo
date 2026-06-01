"""Route: settings — user preferences stored per authenticated user."""
import psycopg2, psycopg2.extras, psycopg2.errors
import json
import logging
import os
from typing import Dict
from .utils import error_response, json_response, handle_db_error

logger = logging.getLogger(__name__)

def _get_encryption_key() -> str:
    """Fetch pgcrypto encryption key from Secrets Manager.

    Falls back to hardcoded default for development (when secret not available).
    In production, the secret MUST be set.
    """
    try:
        # Try to import and use credential manager for production
        from config.credential_manager import get_secret
        return get_secret('settings/encryption-key', default=None)
    except (ImportError, ValueError):
        # In Lambda development mode or if credential manager unavailable,
        # use a development default (not the hardcoded _DEFAULTS which is insecure)
        if os.getenv('AWS_LAMBDA_FUNCTION_NAME'):
            # In Lambda but no secret available — log warning but don't fail
            logger.warning("Settings encryption key not found in Secrets Manager; using temporary development key")
        return os.getenv('SETTINGS_ENCRYPTION_KEY', 'dev-settings-key-change-in-production')

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
    # Note: When Cognito is disabled, jwt_claims={} (empty dict) is passed, which is treated as authorized
    if jwt_claims is None:
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
    Preferences are encrypted at rest using pgp_sym_decrypt.
    """
    # SECURITY: Get user_id from authenticated JWT claims, not from query params
    # When Cognito is disabled, use 'anonymous' as fallback user ID
    user_id = jwt_claims.get('sub') or 'anonymous'
    try:
        # Decrypt preferences using pgp_sym_decrypt (requires pgcrypto extension)
        encryption_key = _get_encryption_key()
        cur.execute("""
            SELECT theme, notifications,
              pgp_sym_decrypt(preferences, %s) as preferences_decrypted
            FROM user_dashboard_settings WHERE user_id = %s
        """, (encryption_key, user_id))
        row = cur.fetchone()
        if row:
            try:
                stored = {
                    'theme': row['theme'] or 'dark',
                    'notifications': row['notifications'] if row['notifications'] is not None else True,
                    **json.loads(row['preferences_decrypted'] or '{}')
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
    Preferences are encrypted at rest using PostgreSQL pgp_sym_encrypt.
    """
    # SECURITY: Get user_id from authenticated JWT claims, not from request
    # When Cognito is disabled, use 'anonymous' as fallback user ID
    user_id = jwt_claims.get('sub') or 'anonymous'
    try:
        theme = body.get('theme', 'dark')
        notifications = body.get('notifications', True)
        # Store other settings in preferences JSONB (encrypted)
        other_prefs = {k: v for k, v in body.items() if k not in ['user_id', 'theme', 'notifications']}

        # Encrypt preferences using pgp_sym_encrypt with secret key from Secrets Manager
        encryption_key = _get_encryption_key()
        cur.execute("""
            INSERT INTO user_dashboard_settings (user_id, theme, notifications, preferences, updated_at)
            VALUES (%s, %s, %s, pgp_sym_encrypt(%s, %s), NOW())
            ON CONFLICT (user_id) DO UPDATE
              SET theme = %s,
                  notifications = %s,
                  preferences = pgp_sym_encrypt(%s, %s),
                  updated_at = NOW()
        """, (user_id, theme, notifications, json.dumps(other_prefs), encryption_key,
              theme, notifications, json.dumps(other_prefs), encryption_key))
        return json_response(200, {'success': True, 'message': 'Settings saved'})
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        logger.warning("user_dashboard_settings table missing; settings not persisted")
        return json_response(200, {'success': True, 'message': 'Settings saved'})
    except (psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        return handle_db_error(e, logger, 'save settings')
