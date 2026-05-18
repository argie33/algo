"""Route: notifications"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone

logger = logging.getLogger(__name__)

def error_response(code, typ, msg):
    return {"statusCode": code, "errorType": typ, "message": msg}

def success_response(data):
    return {"statusCode": 200, "data": data}

def list_response(items, total=None):
    return {"statusCode": 200, "items": items, "total": total or len(items)}

def _safe_limit(limit_str, max_val=50000, default=500):
    if not limit_str:
        return default
    try:
        return min(int(limit_str), max_val)
    except:
        return default

def _handle_notifications(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/notifications/* endpoints."""
        try:
            if path == '/api/notifications' or path == '/api/notifications/':
                return json_response(200, {'items': [], 'status': 'no_notifications'})
            return error_response(404, 'not_found', f'No notifications handler for {path}')
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'handle notifications'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'handle notifications'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'handle notifications'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'handle notifications', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'handle notifications', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Notifications handler error')
