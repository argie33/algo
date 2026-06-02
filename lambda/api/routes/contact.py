"""Route: contact"""
import psycopg2, psycopg2.extras, psycopg2.errors
from typing import Dict
import logging, re
from datetime import datetime, timezone
from .utils import error_response, json_response, list_response, safe_limit, handle_db_error, check_data_freshness
from collections import defaultdict
from time import time

def _check_admin_access(jwt_claims: Dict) -> bool:
    """Check if user has admin access from verified JWT claims only."""
    if not jwt_claims:
        return False
    groups = jwt_claims.get('cognito:groups', [])
    return 'admin' in groups

logger = logging.getLogger(__name__)

# SECURITY FIX: More strict email validation (RFC 5322 simplified)
_EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~\-]+@[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
)

CONTACT_RATE_LIMIT_REQUESTS = 5
CONTACT_RATE_LIMIT_WINDOW = 3600

def _is_contact_spam(email: str) -> bool:
    """Check if email has exceeded contact form submission rate limit.

    Uses REQUIRED DynamoDB-based distributed rate limiting across Lambda instances.
    No fallback to in-memory (which could be bypassed via concurrent requests to different instances).

    SECURITY: Email addresses are hashed (SHA256) before storage to avoid PII exposure in DynamoDB.
    Requires CONTACT_RATE_LIMIT_TABLE env var. If not set, configuration error is logged
    and request is rejected to prevent unprotected spam risk.
    """
    import boto3
    import os
    import hashlib
    from botocore.exceptions import ClientError

    now = int(time())
    window_start = now - CONTACT_RATE_LIMIT_WINDOW

    # Hash email to avoid storing PII in plaintext
    email_hash = hashlib.sha256(email.encode()).hexdigest()

    # REQUIRED: DynamoDB rate limiting (no fallback to prevent bypass via scaling)
    dynamodb_table = os.getenv('CONTACT_RATE_LIMIT_TABLE')
    if not dynamodb_table:
        logger.error(f"CRITICAL: CONTACT_RATE_LIMIT_TABLE not configured. Rejecting contact submission for safety.")
        return True  # Fail safe: reject if rate limiter not configured

    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(dynamodb_table)
        response = table.get_item(Key={'email_hash': email_hash})
        item = response.get('Item', {})
        submission_times = item.get('submission_times', [])
        recent_submissions = [t for t in submission_times if t > window_start]

        if len(recent_submissions) >= CONTACT_RATE_LIMIT_REQUESTS:
            logger.warning(f"Contact form rate limit exceeded (DynamoDB): ...@{email.split('@')[-1]} - {len(recent_submissions)} submissions")
            return True

        recent_submissions.append(now)
        table.put_item(Item={'email_hash': email_hash, 'submission_times': recent_submissions, 'ttl': now + CONTACT_RATE_LIMIT_WINDOW})
        return False
    except ClientError as e:
        logger.error(f"DynamoDB rate limit check failed: {e}. Rejecting request for safety.")
        return True  # Fail safe: reject if we can't verify rate limit
    except Exception as e:
        logger.error(f"DynamoDB rate limit error: {e}. Rejecting request for safety.")
        return True  # Fail safe: reject if we can't verify rate limit

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
    """Handle /api/contact/* endpoints. Submissions require admin auth."""
    try:
        if path == '/api/contact/submissions':
            if not jwt_claims or not jwt_claims.get('sub'):
                return error_response(401, 'unauthorized', 'Authentication required')
            if not _check_admin_access(jwt_claims):
                logger.warning(f"Unauthorized contact submissions access attempt by {jwt_claims.get('sub')}")
                return error_response(403, 'forbidden', 'Admin access required')
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
        return error_response(500, 'internal_error', 'An error occurred processing your request')

def _submit_contact(cur, body: Dict) -> Dict:
    """Store a contact form submission."""
    name = str(body.get('name', '')).strip()[:100]
    email = str(body.get('email', '')).strip()[:200]
    subject = str(body.get('subject', '')).strip()[:200]
    message = str(body.get('message', '')).strip()[:5000]
    phone = str(body.get('phone', '')).strip()[:20] if body.get('phone') else ''

    if not name:
        return error_response(400, 'bad_request', 'Name is required')
    if not email or not _EMAIL_RE.match(email):
        return error_response(400, 'bad_request', 'Valid email is required')
    if not message:
        return error_response(400, 'bad_request', 'Message is required')

    # SECURITY FIX: Validate phone number format (if provided)
    if phone and not re.match(r'^\+?[\d\s\-\(\)]{10,15}$', phone):
        return error_response(400, 'bad_request', 'Phone number format invalid')

    # SECURITY FIX: Reject messages with suspicious patterns (script tags, SQL keywords, etc.)
    # This is defense-in-depth; fields are parameterized so no injection risk, but reject anyway
    dangerous_patterns = [
        r'<script',
        r'javascript:',
        r'on\w+\s*=',  # onclick=, onload=, etc.
        r'union\s+select',  # SQL injection pattern
        r'drop\s+table',  # SQL attack pattern
        r'update\s+\w+\s+set',  # SQL attack pattern
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            return error_response(400, 'bad_request', 'Message contains invalid content')
        if re.search(pattern, name, re.IGNORECASE):
            return error_response(400, 'bad_request', 'Name contains invalid content')
        if re.search(pattern, subject, re.IGNORECASE):
            return error_response(400, 'bad_request', 'Subject contains invalid content')

    # SECURITY L-NEW-01: Return 200 even when rate limited � a 429 lets an
    # attacker enumerate whether an email has submitted recently.
    if _is_contact_spam(email):
        logger.warning(f"Contact rate limit hit (silenced to caller): ...@{email.split('@')[-1]}")
        return json_response(200, {'success': True, 'message': "Thank you for reaching out. We'll get back to you soon."})

    try:
        # Try with phone column first (migration 007 adds it; falls back gracefully if not yet applied)
        try:
            cur.execute("""
                INSERT INTO contact_submissions (name, email, subject, message, phone, submitted_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (name, email, subject, message, phone if phone else None, datetime.now(timezone.utc)))
        except psycopg2.errors.UndefinedColumn:
            cur.connection.rollback()
            cur.execute("""
                INSERT INTO contact_submissions (name, email, subject, message, submitted_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (name, email, subject, message, datetime.now(timezone.utc)))
        logger.info(f"Contact form submission from ...@{email.split('@')[-1]}")
        return json_response(200, {'success': True, 'message': "Thank you for reaching out. We'll get back to you soon."})
    except psycopg2.errors.UndefinedTable:
        logger.error(f"contact_submissions table missing; unable to process submission")
        return error_response(503, 'service_unavailable', 'Contact service unavailable. Please try again later.')
    except Exception as e:
        return handle_db_error(e, logger, 'submit_contact')

def _get_submissions(cur, params: Dict) -> Dict:
    """Get contact submissions (admin-only)."""
    try:
        limit = safe_limit(params.get('limit', [100])[0] if params else 100)
        try:
            cur.execute("""
                SELECT id, name, email, subject, message, phone, submitted_at
                FROM contact_submissions ORDER BY submitted_at DESC LIMIT %s
            """, (limit,))
        except psycopg2.errors.UndefinedColumn:
            cur.connection.rollback()
            cur.execute("""
                SELECT id, name, email, subject, message, submitted_at
                FROM contact_submissions ORDER BY submitted_at DESC LIMIT %s
            """, (limit,))
        rows = cur.fetchall()
        return list_response(rows, total=len(rows))
    except psycopg2.errors.UndefinedTable:
        logger.error("contact_submissions table missing; unable to list submissions")
        return error_response(503, 'service_unavailable', 'Contact service unavailable.')
    except Exception as e:
        return handle_db_error(e, logger, 'get_submissions')
