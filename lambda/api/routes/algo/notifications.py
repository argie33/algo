"""Notification handlers - get, mark read, delete."""
import logging
import sys
from pathlib import Path
from typing import Dict
import psycopg2, psycopg2.errors

_routes_dir = str(Path(__file__).parent.parent)
if _routes_dir not in sys.path:
    sys.path.insert(0, _routes_dir)

from routes.utils import error_response, json_response, handle_db_error
from algo_original import _get_notifications

logger = logging.getLogger(__name__)

handle_get_notifications = _get_notifications


def handle_mark_read(cur, path: str, jwt_claims: Dict) -> Dict:
    """Mark notification as read."""
    try:
        from routes.utils import error_response, json_response, handle_db_error
        notif_id = path.split('/notifications/')[-1].replace('/read', '')
        try:
            notif_id_int = int(notif_id)
        except ValueError:
            return error_response(400, 'bad_request', 'ID must be numeric')

        cur.execute("SELECT id FROM algo_notifications WHERE id=%s LIMIT 1", (notif_id_int,))
        if not cur.fetchone():
            return error_response(404, 'not_found', 'Notification not found')

        cur.execute("UPDATE algo_notifications SET seen=TRUE, seen_at=NOW() WHERE id=%s", (notif_id_int,))
        return json_response(200, {'status': 'updated'})
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        code, error_type, message = handle_db_error(e, 'mark notification as read')
        logger.error(f'Failed to mark notification as read: {error_type} - {message}')
        return json_response(code, {'errorType': error_type, 'message': message})


def handle_delete(cur, path: str, jwt_claims: Dict) -> Dict:
    """Delete notification."""
    try:
        from routes.utils import error_response, json_response, handle_db_error
        notif_id = path.split('/notifications/')[-1]
        try:
            notif_id_int = int(notif_id)
        except ValueError:
            return error_response(400, 'bad_request', 'ID must be numeric')

        cur.execute("SELECT id FROM algo_notifications WHERE id=%s LIMIT 1", (notif_id_int,))
        if not cur.fetchone():
            return error_response(404, 'not_found', 'Notification not found')

        cur.execute("DELETE FROM algo_notifications WHERE id=%s", (notif_id_int,))
        return json_response(200, {'status': 'deleted'})
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        code, error_type, message = handle_db_error(e, 'delete notification')
        logger.error(f'Failed to delete notification: {error_type} - {message}')
        return json_response(code, {'errorType': error_type, 'message': message})


__all__ = ['handle_get_notifications', 'handle_mark_read', 'handle_delete']
