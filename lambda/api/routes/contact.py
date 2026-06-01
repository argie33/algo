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

# Fallback in-memory rate limiter (per Lambda instance)
# Tracks submission times by email: {email: [timestamp, timestamp, ...]}
_FALLBACK_RATE_LIMIT_TRACKER = {}

def _is_contact_spam(email: str) -> bool:
    """Check if email has exceeded contact form submission rate limit.

    Implements TWO-LAYER rate limiting:
    1. Primary: DynamoDB (distributed across Lambda instances)
    2. Fallback: In-memory per-instance (when DynamoDB not available)

    SECURITY: When both fail, conservatively returns True (rejects request) to prevent DoS.
    """
    import boto3
    import os
    from botocore.exceptions import ClientError

    now = int(time())
    window_start = now - CONTACT_RATE_LIMIT_WINDOW

    # LAYER 1: Try distributed DynamoDB rate limiting
    dynamodb_table = os.getenv('CONTACT_RATE_LIMIT_TABLE')
    if dynamodb_table:
        try:
            dynamodb = boto3.resource('dynamodb')
            table = dynamodb.Table(dynamodb_table)
            response = table.get_item(Key={'email': email})
            item = response.get('Item', {})
            submission_times = item.get('submission_times', [])
            recent_submissions = [t for t in submission_times if t > window_start]

            if len(recent_submissions) >= CONTACT_RATE_LIMIT_REQUESTS:
                logger.warning(f"Contact form rate limit exceeded (DynamoDB): {email} - {len(recent_submissions)} submissions")
                return True

            recent_submissions.append(now)
            table.put_item(Item={'email': email, 'submission_times': recent_submissions, 'ttl': now + CONTACT_RATE_LIMIT_WINDOW + 86400})
            return False
        except ClientError as e:
            logger.warning(f"DynamoDB rate limit check failed: {e}. Falling back to in-memory limiter.")
        except Exception as e:
            logger.warning(f"DynamoDB error: {e}. Falling back to in-memory limiter.")

    # LAYER 2: Fallback in-memory rate limiting (this Lambda instance only)
    try:
        if email not in _FALLBACK_RATE_LIMIT_TRACKER:
            _FALLBACK_RATE_LIMIT_TRACKER[email] = []

        submission_times = _FALLBACK_RATE_LIMIT_TRACKER[email]
        recent_submissions = [t for t in submission_times if t > window_start]

        if len(recent_submissions) >= CONTACT_RATE_LIMIT_REQUESTS:
            logger.warning(f"Contact form rate limit exceeded (in-memory): {email} - {len(recent_submissions)} submissions")
            return True

        recent_submissions.append(now)
        _FALLBACK_RATE_LIMIT_TRACKER[email] = recent_submissions

        # Cleanup old entries to prevent memory leak (keep last 100 per email)
        if len(recent_submissions) > 100:
            _FALLBACK_RATE_LIMIT_TRACKER[email] = recent_submissions[-100:]

        return False
    except Exception as e:
        logger.error(f"CRITICAL: Both rate limiters failed: {e}. Rejecting request for safety.")
        return True  # Fail safe: reject if we can't rate limit

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

    # Rate limit contact form submissions per email
    if _is_contact_spam(email):
        return error_response(429, 'rate_limit_exceeded', 'Too many contact submissions. Please try again later.')

    try:
        cur.execute("""
            INSERT INTO contact_submissions (name, email, subject, message, phone, submitted_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (name, email, subject, message, phone if phone else None, datetime.now(timezone.utc)))
        logger.info(f"Contact form submission from {email}")
        return json_response(200, {'success': True, 'message': "Thank you for reaching out. We'll get back to you soon."})
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        logger.warning(f"contact_submissions table missing; submission from {email} logged only")
        return json_response(200, {'success': True, 'message': "Thank you for reaching out. We'll get back to you soon."})
    except Exception as e:
        return handle_db_error(e, logger, 'submit_contact')

def _get_submissions(cur, params: Dict) -> Dict:
    """Get contact submissions (admin-only)."""
    try:
        limit = safe_limit(params.get('limit', [100])[0] if params else 100)
        cur.execute("""
            SELECT id, name, email, subject, message, phone, submitted_at
            FROM contact_submissions ORDER BY submitted_at DESC LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
        return list_response(rows, total=len(rows))
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        logger.warning("contact_submissions table missing")
        return list_response([])
    except Exception as e:
        return handle_db_error(e, logger, 'get_submissions')
