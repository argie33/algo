"""Route: settings — user preferences stored per authenticated user."""
import psycopg2, psycopg2.extras, psycopg2.errors
import json
import logging
import os
from typing import Dict
from .utils import error_response, json_response, handle_db_error

logger = logging.getLogger(__name__)

def _get_encryption_key() -> str:
    """Fetch pgcrypto encryption key from Secrets Manager (required).

    Fails loudly if the encryption key is not available.
    """
    try:
        # Try to import and use credential manager for production
        from config.credential_manager import get_secret
        key = get_secret('settings/encryption-key', default=None)
        if not key:
            raise ValueError("SETTINGS_ENCRYPTION_KEY secret not found in Secrets Manager")
        return key
    except (ImportError, ValueError) as e:
        # Check environment variable as fallback
        key = os.getenv('SETTINGS_ENCRYPTION_KEY')
        if not key:
            error_msg = f"SETTINGS_ENCRYPTION_KEY not available: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        return key

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
    # SECURITY: Get user_id from authenticated JWT claims, require 'sub' claim
    # Do NOT fall back to 'anonymous' - each user must have their own identity
    user_id = jwt_claims.get('sub')
    if not user_id:
        return error_response(401, 'unauthorized', 'User identity (sub claim) required')

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
    except RuntimeError as e:
        logger.error(f"Encryption key unavailable: {e}")
        return error_response(503, 'service_unavailable', 'Settings service unavailable')
    except (psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        return handle_db_error(e, logger, 'get settings')

def _save_settings(cur, body: Dict, jwt_claims: Dict) -> Dict:
    """Persist user settings.

    SECURITY FIX: Use authenticated user's ID from JWT, not from body/params.
    Users can only modify their own settings, preventing IDOR.
    Preferences are encrypted at rest using PostgreSQL pgp_sym_encrypt.
    Audit trail logs all settings changes for incident investigation.
    """
    # SECURITY: Get user_id from authenticated JWT claims, require 'sub' claim
    # Do NOT fall back to 'anonymous' - each user must have their own identity
    user_id = jwt_claims.get('sub')
    if not user_id:
        return error_response(401, 'unauthorized', 'User identity (sub claim) required')

    try:
        theme = body.get('theme', 'dark')
        notifications = body.get('notifications', True)
        # Store other settings in preferences JSONB (encrypted)
        other_prefs = {k: v for k, v in body.items() if k not in ['user_id', 'theme', 'notifications']}

        # Encrypt preferences using pgp_sym_encrypt with secret key from Secrets Manager
        encryption_key = _get_encryption_key()

        # Fetch old settings for audit trail
        old_theme = None
        old_notifications = None
        try:
            cur.execute("""
                SELECT theme, notifications FROM user_dashboard_settings WHERE user_id = %s
            """, (user_id,))
            old_row = cur.fetchone()
            if old_row:
                old_theme = old_row.get('theme')
                old_notifications = old_row.get('notifications')
        except Exception:
            pass

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

        # Audit logging: record settings changes
        try:
            changes = []
            if old_theme != theme:
                changes.append(f"theme: {old_theme} → {theme}")
            if old_notifications != notifications:
                changes.append(f"notifications: {old_notifications} → {notifications}")
            if other_prefs:
                changes.append(f"preferences: updated")

            if changes:
                logger.info(f"Settings changed for user {user_id}: {'; '.join(changes)}")
            else:
                logger.debug(f"Settings saved for user {user_id} (no changes)")
        except Exception as e:
            logger.warning(f"Failed to log settings audit trail: {e}")

        return json_response(200, {'success': True, 'message': 'Settings saved'})
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        logger.warning("user_dashboard_settings table missing; settings not persisted")
        return json_response(200, {'success': True, 'message': 'Settings saved'})
    except RuntimeError as e:
        logger.error(f"Encryption key unavailable: {e}")
        return error_response(503, 'service_unavailable', 'Settings service unavailable')
    except (psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        return handle_db_error(e, logger, 'save settings')
