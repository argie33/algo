"""Route: contact"""
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

def _handle_contact(self, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
        """Handle /api/contact and /api/contact/submissions."""
        try:
            if path == '/api/contact/submissions':
                cur.execute("""
                    SELECT id, name, email, subject, message, status, submitted_at
                    FROM contact_submissions
                    ORDER BY submitted_at DESC
                    LIMIT 100
                """)
                rows = cur.fetchall()
                return list_response([dict(r) for r in rows])
            elif path == '/api/contact' and method == 'POST':
                # Validate contact request against schema
                data = body or {}
                valid, result, error_msg = validate_request(ContactRequest, data)
                if not valid:
                    return error_response(400, 'bad_request', error_msg)

                contact = result  # ContactRequest instance
                cur.execute("""
                    INSERT INTO contact_submissions (name, email, subject, message, status, submitted_at)
                    VALUES (%s, %s, %s, %s, 'new', NOW())
                """, (contact.name, contact.email, contact.subject, contact.message))
                cur.connection.commit()
                return json_response(200, {'status': 'submitted', 'message': 'Contact form submission received'})
            return error_response(404, 'not_found', f'No handler for {path}')
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'handle contact'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'handle contact'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'handle contact'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'handle contact', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'handle contact', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Contact handler error')
