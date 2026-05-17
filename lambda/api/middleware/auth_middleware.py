"""
API Authentication Middleware
Validates API keys and enforces rate limiting on all API requests.
"""

import os
import hashlib
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta
from functools import wraps


class APIKeyValidator:
    """Validate API keys and track usage."""

    def __init__(self, db_connection):
        """Initialize with database connection."""
        self.conn = db_connection
        self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def hash_key(self, api_key):
        """Hash API key for secure storage."""
        return hashlib.sha256(api_key.encode()).hexdigest()

    def validate_key(self, api_key):
        """
        Validate API key and return app info if valid.
        Returns (is_valid, app_info, error_message)
        """
        if not api_key:
            return (False, None, "Missing API key")

        # Ensure proper format (sk_XXXXXXXX... or similar)
        if not isinstance(api_key, str) or len(api_key) < 20:
            return (False, None, "Invalid API key format")

        try:
            key_hash = self.hash_key(api_key)

            # Lookup key in database
            self.cur.execute("""
                SELECT id, app_name, permissions, rate_limit_per_hour,
                       last_used_at, expires_at, is_active
                FROM api_keys
                WHERE key_hash = %s
            """, (key_hash,))

            result = self.cur.fetchone()

            if not result:
                return (False, None, "Invalid API key")

            # Check if key is active
            if not result['is_active']:
                return (False, None, "API key is disabled")

            # Check if key has expired
            if result['expires_at']:
                if datetime.now(timezone.utc) > result['expires_at']:
                    return (False, None, "API key has expired")

            # Check rate limit
            is_rate_limited = self._check_rate_limit(
                result['id'],
                result['rate_limit_per_hour']
            )

            if is_rate_limited:
                return (False, None, "Rate limit exceeded")

            # Update last_used_at
            self._update_last_used(result['id'])

            return (True, result, None)

        except Exception as e:
            return (False, None, f"Validation error: {str(e)}")

    def _check_rate_limit(self, api_key_id, limit_per_hour):
        """Check if API key has exceeded rate limit."""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=1)

            self.cur.execute("""
                SELECT COUNT(*) as request_count
                FROM api_requests_log
                WHERE api_key_id = %s
                AND created_at >= %s
            """, (api_key_id, cutoff_time))

            result = self.cur.fetchone()
            request_count = result['request_count'] if result else 0

            return request_count >= limit_per_hour

        except Exception:
            # If check fails, allow the request (fail open)
            return False

    def _update_last_used(self, api_key_id):
        """Update last_used_at timestamp for the key."""
        try:
            self.cur.execute("""
                UPDATE api_keys
                SET last_used_at = %s
                WHERE id = %s
            """, (datetime.now(timezone.utc), api_key_id))
            self.conn.commit()
        except Exception:
            pass  # Non-critical update failure

    def log_request(self, api_key_id, endpoint, method, status_code,
                    response_time_ms, source_ip, error_message=None):
        """Log API request for auditing and rate limiting."""
        try:
            self.cur.execute("""
                INSERT INTO api_requests_log
                (api_key_id, endpoint, method, status_code, response_time_ms,
                 source_ip, error_message, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                api_key_id, endpoint, method, status_code,
                response_time_ms, source_ip, error_message,
                datetime.now(timezone.utc)
            ))
            self.conn.commit()
        except Exception:
            pass  # Non-critical logging failure


def require_api_key(db_connection):
    """
    Decorator to require valid API key authentication.

    Usage in Lambda handler:
        @require_api_key(db_connection)
        def handle_request(event, context, api_key_info):
            # api_key_info contains {'id', 'app_name', 'permissions'}
            pass
    """
    def decorator(handler):
        @wraps(handler)
        def wrapper(event, context):
            # Extract API key from header or query parameter
            headers = event.get('headers', {})
            api_key = (
                headers.get('Authorization', '').replace('Bearer ', '') or
                headers.get('X-API-Key', '') or
                event.get('queryStringParameters', {}).get('api_key', '')
            )

            # Validate key
            validator = APIKeyValidator(db_connection)
            is_valid, key_info, error_msg = validator.validate_key(api_key)

            if not is_valid:
                return {
                    'statusCode': 401,
                    'headers': {'Content-Type': 'application/json'},
                    'body': f'{{"error": "{error_msg}"}}'
                }

            # Call handler with key info
            try:
                result = handler(event, context, key_info)

                # Log successful request
                source_ip = (
                    headers.get('CloudFront-Viewer-Address') or
                    headers.get('X-Forwarded-For', '').split(',')[0] or
                    'unknown'
                )
                path = event.get('path', '/')
                method = event.get('httpMethod', 'GET')

                validator.log_request(
                    key_info['id'], path, method,
                    result.get('statusCode', 200),
                    0, source_ip.strip()
                )

                return result

            except Exception as e:
                # Log failed request
                validator.log_request(
                    key_info['id'],
                    event.get('path', '/'),
                    event.get('httpMethod', 'GET'),
                    500, 0, 'unknown',
                    str(e)[:200]
                )
                raise

        return wrapper
    return decorator
