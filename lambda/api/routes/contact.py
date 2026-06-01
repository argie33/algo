"""Route: contact"""
import psycopg2, psycopg2.extras, psycopg2.errors
from typing import Dict
import logging, re
from datetime import datetime, timezone
from .utils import error_response, json_response, list_response, safe_limit, handle_db_error, check_data_freshness
from collections import defaultdict
from time import time

logger = logging.getLogger(__name__)

# SECURITY FIX: More strict email validation (RFC 5322 simplified)
_EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~\-]+@[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
)

# Rate limiting for contact form submissions
# Prevent spam abuse by limiting submissions per email per time window
_CONTACT_SUBMISSION_HISTORY = defaultdict(list)
CONTACT_RATE_LIMIT_REQUESTS = 5  # Max 5 submissions per email
CONTACT_RATE_LIMIT_WINDOW = 3600  # Per hour

def _is_contact_spam(email: str) -> bool:
    """Check if email has exceeded contact form submission rate limit."""
    now = time()

    # Clean old entries outside the window
    _CONTACT_SUBMISSION_HISTORY[email] = [
        req_time for req_time in _CONTACT_SUBMISSION_HISTORY[email]
        if now - req_time < CONTACT_RATE_LIMIT_WINDOW
    ]

    # Check if limit exceeded
    if len(_CONTACT_SUBMISSION_HISTORY[email]) >= CONTACT_RATE_LIMIT_REQUESTS:
        logger.warning(f"Contact form rate limit exceeded for {email}")
        return True

    # Record this submission
    _CONTACT_SUBMISSION_HISTORY[email].append(now)
    return False

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
    """Handle /api/contact/* endpoints. Submissions require auth."""
    try:
        if path == '/api/contact/submissions':
            if not jwt_claims or not jwt_claims.get('sub'):
                return error_response(401, 'unauthorized', 'Authentication required')
            if method == 'GET':
                return _get_submissions(cur, params)
            return error_response(405, 'method_not_allowed', 'GET required')

        if path == '/api/contact':
            if method == 'POST':
                return _submit_contact(cur, body or {})
            return error_response(405, 'method_not_allowed', 'POST required')

        return error_response(404, 'not_found', f'No contact handler for {path}')
    except Exception as e:
        logger.error(f'[CONTACT] unhandled {type(e).__name__}: {e}', exc_info=True)
        return error_response(500, 'internal_error', f'Contact handler error: {type(e).__name__}')

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

    # Rate limit contact form submissions per email
    if _is_contact_spam(email):
        return error_response(429, 'rate_limit_exceeded', 'Too many contact submissions. Please try again later.')

    try:
        cur.execute("""
            INSERT INTO contact_submissions (name, email, subject, message, submitted_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, email, subject, message, datetime.now(timezone.utc)))
        logger.info(f"Contact form submission from {email}")
        return json_response(200, {'success': True, 'message': "Thank you for reaching out. We'll get back to you soon."})
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        logger.warning(f"contact_submissions table missing; submission from {email} logged only")
        return json_response(200, {'success': True, 'message': "Thank you for reaching out. We'll get back to you soon."})
    except Exception as e:
        return handle_db_error(e, logger, 'submit_contact')

def _get_submissions(cur, params: Dict) -> Dict:
    """Get contact submissions."""
    try:
        limit = safe_limit(params.get('limit', [100])[0] if params else 100)
        cur.execute("SELECT * FROM contact_submissions ORDER BY submitted_at DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
        return list_response(rows, total=len(rows))
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        logger.warning("contact_submissions table missing")
        return list_response([])
    except Exception as e:
        return handle_db_error(e, logger, 'get_submissions')
