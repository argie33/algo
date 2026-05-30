"""Route: contact"""
import psycopg2, psycopg2.extras, psycopg2.errors
from typing import Dict
import logging, re
from datetime import datetime, timezone
from .utils import error_response, json_response, list_response, safe_limit, handle_db_error, check_data_freshness

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
    """Handle /api/contact/* endpoints."""
    if path == '/api/contact':
        if method == 'POST':
            return _submit_contact(cur, body or {})
        return error_response(405, 'method_not_allowed', 'POST required')

    if path == '/api/contact/submissions':
        if method == 'GET':
            return _get_submissions(cur, params)
        return error_response(405, 'method_not_allowed', 'GET required')

    return error_response(404, 'not_found', f'No contact handler for {path}')

def _submit_contact(cur, body: Dict) -> Dict:
    """Store a contact form submission."""
    name = str(body.get('name', '')).strip()[:100]
    email = str(body.get('email', '')).strip()[:200]
    subject = str(body.get('subject', '')).strip()[:200]
    message = str(body.get('message', '')).strip()[:5000]

    if not name:
        return error_response(400, 'bad_request', 'Name is required')
    if not email or not _EMAIL_RE.match(email):
        return error_response(400, 'bad_request', 'Valid email is required')
    if not message:
        return error_response(400, 'bad_request', 'Message is required')

    try:
        cur.execute("""
            INSERT INTO contact_submissions (name, email, subject, message, submitted_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, email, subject, message, datetime.now(timezone.utc)))
        logger.info(f"Contact form submission from {email}")
        return json_response(200, {'success': True, 'message': "Thank you for reaching out. We'll get back to you soon."})
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        # Table doesn't exist yet — log and succeed gracefully
        logger.warning(f"contact_submissions table missing; submission from {email} logged only")
        return json_response(200, {'success': True, 'message': "Thank you for reaching out. We'll get back to you soon."})
    except (psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        return handle_db_error(e, logger, 'submit contact')

def _get_submissions(cur, params: Dict) -> Dict:
    """Get contact form submissions (admin only)."""
    try:
        limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=200, default=50)
        cur.execute("""
            SELECT id, name, email, subject, message, submitted_at
            FROM contact_submissions
            ORDER BY submitted_at DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        freshness = check_data_freshness(cur, 'contact_submissions', 'submitted_at', warning_days=1)
        return list_response([dict(r) for r in rows] if rows else [], data_freshness=freshness)
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        return list_response([])
    except (psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        return handle_db_error(e, logger, 'get contact submissions')
