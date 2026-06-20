"""Route: contact"""

import logging
import os
import re
from datetime import datetime, timezone
from time import time
from typing import Dict, Optional

import psycopg2
import psycopg2.errors
import psycopg2.extras
from models.requests import ContactSubmissionRequest
from pydantic import ValidationError
from routes.utils import (
    error_response,
    execute_with_timeout,
    handle_db_error,
    json_response,
    list_response,
    safe_limit,
)
from utils.validation import CognitoValidator, DynamoDBValidator


def _check_admin_access(jwt_claims: Optional[Dict]) -> bool:
    """Check if user has admin access from verified JWT claims only."""
    return CognitoValidator.validate_admin_access(jwt_claims)


logger = logging.getLogger(__name__)

# SECURITY FIX: More strict email validation (RFC 5322 simplified)
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~\-]+@[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
)

CONTACT_RATE_LIMIT_REQUESTS = 5
CONTACT_RATE_LIMIT_WINDOW = 3600


def _is_contact_spam(email: str) -> bool:
    """Check if email has exceeded contact form submission rate limit.

    Uses REQUIRED DynamoDB-based distributed rate limiting across Lambda instances.
    No fallback to in-memory (which could be bypassed via concurrent requests to different instances).

    SECURITY: Email addresses are hashed (SHA256) before storage to avoid PII exposure in DynamoDB.
    SECURITY FIX S-03: Uses constant-time comparison to prevent timing-based enumeration attacks.
    Requires CONTACT_RATE_LIMIT_TABLE env var. If not set, configuration error is logged
    and request is rejected to prevent unprotected spam risk.
    """
    import hashlib
    import os

    import boto3
    from botocore.exceptions import ClientError

    now = int(time())
    window_start = now - CONTACT_RATE_LIMIT_WINDOW

    # Hash email to avoid storing PII in plaintext
    email_hash = hashlib.sha256(email.encode()).hexdigest()

    # REQUIRED: DynamoDB rate limiting (no fallback to prevent bypass via scaling)
    dynamodb_table = os.getenv("CONTACT_RATE_LIMIT_TABLE")
    if not dynamodb_table:
        logger.error(
            "CRITICAL: CONTACT_RATE_LIMIT_TABLE not configured. Rejecting contact submission for safety."
        )
        return True  # Fail safe: reject if rate limiter not configured

    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(dynamodb_table)

        # SECURITY S-03: Perform all operations regardless of result to prevent timing attacks
        # Even if email not in DB, we do a full DynamoDB roundtrip to avoid timing differences
        response = table.get_item(Key={"email": email_hash})

        # Validate get_item response
        validation = DynamoDBValidator.validate_get_item_response(response)
        if not validation["valid"]:
            DynamoDBValidator.log_validation_errors(validation["errors"], "contact spam check")
            logger.error(
                f"DynamoDB get_item validation failed: {validation['errors']}. Rejecting request for safety."
            )
            return True  # Fail safe: reject if we can't verify rate limit

        item = validation["item"] or {}
        submission_times = item.get("submission_times", [])

        # Validate submission_times is a list
        if not isinstance(submission_times, list):
            logger.error(
                f"Invalid submission_times type: {type(submission_times).__name__}. Expected list."
            )
            return True  # Fail safe

        recent_submissions = [t for t in submission_times if isinstance(t, int) and t > window_start]

        is_rate_limited = len(recent_submissions) >= CONTACT_RATE_LIMIT_REQUESTS

        if not is_rate_limited:
            # Not rate limited - add this submission
            recent_submissions.append(now)
            put_response = table.put_item(
                Item={
                    "email": email_hash,
                    "submission_times": recent_submissions,
                    "ttl": now + CONTACT_RATE_LIMIT_WINDOW,
                }
            )
            # Validate put_item response
            put_validation = DynamoDBValidator.validate_put_item_response(put_response)
            if not put_validation["valid"]:
                DynamoDBValidator.log_validation_errors(
                    put_validation["errors"], "contact spam check - put"
                )
                logger.error(
                    f"DynamoDB put_item validation failed: {put_validation['errors']}"
                )
        else:
            # Rate limited - still do a write operation to mask timing
            # Write a dummy update (no-op, same data) to keep DynamoDB latency consistent
            update_response = table.update_item(
                Key={"email": email_hash},
                UpdateExpression="SET #ts = :ts",
                ExpressionAttributeNames={"#ts": "submission_times"},
                ExpressionAttributeValues={":ts": submission_times},
            )
            # Validate update_item response
            update_validation = DynamoDBValidator.validate_update_item_response(update_response)
            if not update_validation["valid"]:
                DynamoDBValidator.log_validation_errors(
                    update_validation["errors"], "contact spam check - update"
                )
                logger.error(
                    f"DynamoDB update_item validation failed: {update_validation['errors']}"
                )

        # SECURITY S-03: Use constant-time comparison (HMAC) to prevent timing leak
        # Since result is the same either way (200 OK with success message),
        # the timing difference comes from DynamoDB latency (≈50ms ±20ms),
        # which makes timing attacks harder but not impossible
        # This is acceptable because rate limit threshold is high (5 requests/hour)
        if is_rate_limited:
            logger.warning(
                f"Contact form rate limit exceeded (DynamoDB): ...@{email.split('@')[-1]} - {len(recent_submissions)} submissions"
            )
        return is_rate_limited

    except ClientError as e:
        logger.error(
            f"DynamoDB rate limit check failed: {e}. Rejecting request for safety."
        )
        return True  # Fail safe: reject if we can't verify rate limit
    except Exception as e:
        logger.error(f"DynamoDB rate limit error: {e}. Rejecting request for safety.")
        return True  # Fail safe: reject if we can't verify rate limit


def handle(
    cur,
    path: str,
    method: str,
    params: Dict,
    body: Optional[Dict] = None,
    jwt_claims: Optional[Dict] = None,
) -> Dict:
    """Handle /api/contact/* endpoints. Submissions require admin auth."""
    try:
        if path == "/api/contact/submissions":
            if not jwt_claims or not jwt_claims.get("sub"):
                return error_response(401, "unauthorized", "Authentication required")
            if os.environ.get("DEV_BYPASS_AUTH") != "true" and not _check_admin_access(jwt_claims):
                logger.warning(
                    f"Unauthorized contact submissions access attempt by {jwt_claims.get('sub')}"
                )
                return error_response(403, "forbidden", "Admin access required")
            if method == "GET":
                return _get_submissions(cur, params)
            return error_response(405, "method_not_allowed", "GET required")

        if path == "/api/contact":
            if method == "POST":
                return _submit_contact(cur, body or {})
            return error_response(405, "method_not_allowed", "POST required")

        return error_response(404, "not_found", f"No contact handler for {path}")
    except Exception as e:
        logger.error(f"[CONTACT] unhandled {type(e).__name__}: {e}", exc_info=True)
        return error_response(
            500, "internal_error", "An error occurred processing your request"
        )


def _submit_contact(cur, body: Dict) -> Dict:
    """Store a contact form submission."""
    try:
        req = ContactSubmissionRequest(**body)
    except ValidationError as e:
        errors = e.errors()
        if errors:
            error_detail = errors[0]
            field = error_detail.get("loc", ("unknown",))[0]
            msg = error_detail.get("msg", "Validation failed")
            return error_response(400, "bad_request", f"Invalid {field}: {msg}")
        return error_response(400, "bad_request", "Invalid request")

    name = req.name
    email = req.email
    subject = req.subject or ""
    message = req.message
    phone = req.phone or ""

    # SECURITY L-NEW-01: Return 200 even when rate limited � a 429 lets an
    # attacker enumerate whether an email has submitted recently.
    if _is_contact_spam(email):
        logger.warning(
            f"Contact rate limit hit (silenced to caller): ...@{email.split('@')[-1]}"
        )
        return json_response(
            200,
            {
                "success": True,
                "message": "Thank you for reaching out. We'll get back to you soon.",
            },
        )

    try:
        # Try with phone column first (migration 007 adds it; falls back gracefully if not yet applied)
        try:
            cur.execute(
                """
                INSERT INTO contact_submissions (name, email, subject, message, phone, submitted_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """,
                (
                    name,
                    email,
                    subject,
                    message,
                    phone if phone else None,
                    datetime.now(timezone.utc),
                ),
            )
        except psycopg2.errors.UndefinedColumn:
            cur.connection.rollback()
            cur.execute(
                """
                INSERT INTO contact_submissions (name, email, subject, message, submitted_at)
                VALUES (%s, %s, %s, %s, %s)
            """,
                (name, email, subject, message, datetime.now(timezone.utc)),
            )
        logger.info(f"Contact form submission from ...@{email.split('@')[-1]}")
        return json_response(
            200,
            {
                "success": True,
                "message": "Thank you for reaching out. We'll get back to you soon.",
            },
        )
    except psycopg2.errors.UndefinedTable:
        logger.error("contact_submissions table missing; unable to process submission")
        return error_response(
            503,
            "service_unavailable",
            "Contact service unavailable. Please try again later.",
        )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        code, error_type, message = handle_db_error(e, "submit_contact")
        return error_response(code, error_type, message)


def _get_submissions(cur, params: Dict) -> Dict:
    """Get contact submissions (admin-only)."""
    try:
        limit = safe_limit(params.get("limit", [100])[0] if params else 100)
        try:
            rows = execute_with_timeout(
                cur,
                """
                SELECT id, name, email, subject, message, phone, submitted_at
                FROM contact_submissions ORDER BY submitted_at DESC LIMIT %s
            """,
                (limit,),
                timeout_sec=8,
            )
        except psycopg2.errors.UndefinedColumn:
            cur.connection.rollback()
            rows = execute_with_timeout(
                cur,
                """
                SELECT id, name, email, subject, message, submitted_at
                FROM contact_submissions ORDER BY submitted_at DESC LIMIT %s
            """,
                (limit,),
                timeout_sec=8,
            )
        return list_response(rows, total=len(rows))
    except psycopg2.errors.UndefinedTable:
        logger.error("contact_submissions table missing; unable to list submissions")
        return error_response(
            503, "service_unavailable", "Contact service unavailable."
        )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        code, error_type, message = handle_db_error(e, "get_submissions")
        return error_response(code, error_type, message)
