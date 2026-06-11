"""Stock Analytics Platform - API Lambda Handler.

Routes requests to extracted handler modules via api_router.
Deployment: Fixed Secrets Manager secret name for password sync.
"""

import os
import json
import logging
import sys
import traceback
from typing import Dict, Any, Optional
from pathlib import Path

# Add lambda/api to path so routes module can be imported
sys.path.insert(0, str(Path(__file__).parent))
# Utils are packaged in the same directory as lambda_function.py (/var/task)
# Explicitly add /var/task to ensure utils module can be imported
sys.path.insert(0, '/var/task')
if not __file__.startswith('/var/task'):
    # Local dev (Mac, Linux, Windows): add project root so utils/ is importable
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

IMPORT_ERROR = None
ENV_VALIDATION_ERROR = None
DB_CONNECTION_ERROR = None
_JWKS_CACHE = {}
_JWKS_CACHE_TIME = None
_ALLOWED_ORIGINS_CACHE = None
_COGNITO_ENABLED = None  # Determined at module load
_CLOUDFRONT_DOMAIN_CACHE = None  # CloudFront domain fetched from Secrets Manager

try:
    import psycopg2
    import psycopg2.sql
    from psycopg2.extras import RealDictCursor
    import base64
    from datetime import datetime, timedelta, timezone
    from functools import lru_cache
    import jwt
    import requests
    import api_router
    from utils.database_context import DatabaseContext
except Exception as e:
    IMPORT_ERROR = f"{type(e).__name__}: {str(e)[:200]}"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def fetch_cloudfront_domain_from_secrets():
    """Fetch CloudFront domain from AWS Secrets Manager.

    This eliminates hardcoding CloudFront domain in terraform.tfvars.
    If domain is not found in Secrets Manager, falls back to FRONTEND_URL env var.

    Returns: (domain: Optional[str], error: Optional[str])
    """
    global _CLOUDFRONT_DOMAIN_CACHE

    if _CLOUDFRONT_DOMAIN_CACHE is not None:
        return _CLOUDFRONT_DOMAIN_CACHE, None

    try:
        import boto3
        import json

        secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
        secret_name = 'algo/cloudfront-domain'

        try:
            response = secrets_client.get_secret_value(SecretId=secret_name)
            secret = response.get('SecretString', '')

            if isinstance(secret, str) and not secret.startswith('{'):
                # Plain string secret (just the domain)
                domain = secret.strip()
            else:
                # JSON secret with domain key
                secret_dict = json.loads(secret) if isinstance(secret, str) else secret
                domain = secret_dict.get('domain', '').strip()

            if domain:
                logger.info(f"[CloudFront] Fetched domain from Secrets Manager: {domain}")
                _CLOUDFRONT_DOMAIN_CACHE = domain
                return domain, None
            else:
                logger.warning("[CloudFront] Secret exists but domain is empty")
                return None, "Secret exists but domain is empty"

        except secrets_client.exceptions.ResourceNotFoundException:
            logger.info("[CloudFront] Secret 'algo/cloudfront-domain' not found in Secrets Manager (OK on first deploy)")
            return None, "Secret not found"
        except json.JSONDecodeError as e:
            logger.warning(f"[CloudFront] Failed to parse secret JSON: {e}")
            return None, f"Invalid secret format: {e}"

    except ImportError:
        logger.warning("[CloudFront] boto3 not available, skipping Secrets Manager fetch")
        return None, "boto3 not available"
    except Exception as e:
        logger.error(f"[CloudFront] Error fetching from Secrets Manager: {type(e).__name__}: {e}")
        return None, f"Error: {e}"

def validate_environment():
    """Validate critical environment variables at cold start.

    Returns: (valid: bool, errors: List[str])
    """
    errors = []
    required_vars = {
        'DB_HOST': 'RDS Proxy endpoint (e.g., my-proxy.proxy-abc123.us-east-1.rds.amazonaws.com)',
        'DB_PORT': 'Database port (e.g., 5432 for PostgreSQL; must be a valid integer)',
        'DB_PASSWORD': 'Database password (set via DB_PASSWORD env var or fetch from DB_SECRET_ARN)',
        'DB_NAME': 'Database name (defaults to "stocks" if not set)',
        'DB_USER': 'Database username (defaults to "stocks" if not set)',
    }

    # SECURITY FIX H-01: If Cognito authentication is enabled, ALL Cognito vars must be set
    cognito_user_pool_id = os.getenv('COGNITO_USER_POOL_ID', '').strip()
    if cognito_user_pool_id:
        # Authentication enabled - require all Cognito vars
        cognito_client_id = os.getenv('COGNITO_CLIENT_ID', '').strip()
        cognito_region = os.getenv('COGNITO_REGION', '').strip()

        if not cognito_client_id:
            errors.append('COGNITO_CLIENT_ID missing: Required when COGNITO_USER_POOL_ID is set (find in AWS Cognito console → App clients)')
        if not cognito_region:
            # Default to us-east-1, but still validate it's explicitly set in production
            is_lambda = 'AWS_LAMBDA_FUNCTION_NAME' in os.environ
            if is_lambda:
                errors.append('COGNITO_REGION missing: Required in Lambda (e.g., us-east-1)')

    # SECURITY FIX: In production, FRONTEND_URL must be explicitly set for CORS
    # IMPROVEMENT: Try to fetch CloudFront domain from Secrets Manager if not set
    is_lambda = 'AWS_LAMBDA_FUNCTION_NAME' in os.environ
    if is_lambda:
        frontend_url = os.getenv('FRONTEND_URL', '').strip()
        allow_localhost = os.getenv('ALLOW_LOCALHOST_CORS', '') == 'true'

        # If FRONTEND_URL not set, try to fetch CloudFront domain from Secrets Manager
        if not frontend_url:
            cf_domain, cf_error = fetch_cloudfront_domain_from_secrets()
            if cf_domain:
                frontend_url = f'https://{cf_domain}' if not cf_domain.startswith(('http://', 'https://')) else cf_domain
                os.environ['FRONTEND_URL'] = frontend_url
                logger.info(f"[CloudFront] Set FRONTEND_URL from Secrets Manager: {frontend_url}")
            elif cf_error != "Secret not found":
                logger.warning(f"[CloudFront] Fetch attempt returned error (may be first deploy): {cf_error}")

        # Validation: FRONTEND_URL or localhost must be available
        if not frontend_url and not allow_localhost:
            errors.append('FRONTEND_URL missing: Set to frontend domain (e.g., https://myapp.example.com) for CORS, or enable ALLOW_LOCALHOST_CORS=true for dev')

    missing_secret_arn = not os.getenv('DB_SECRET_ARN')
    missing_password = not os.getenv('DB_PASSWORD')

    for var, description in required_vars.items():
        if var == 'DB_PASSWORD':
            if missing_secret_arn and missing_password:
                errors.append(f"DB_PASSWORD missing: Provide either DB_PASSWORD directly or DB_SECRET_ARN pointing to Secrets Manager secret")
        elif var == 'DB_PORT':
            port_str = os.getenv(var, '').strip()
            if not port_str:
                errors.append(f"{var} missing: {description}")
            else:
                try:
                    int(port_str)
                except (ValueError, TypeError):
                    errors.append(f"{var} invalid: Must be a valid integer (e.g., 5432)")
        elif var in ['DB_NAME', 'DB_USER']:
            if not os.getenv(var) and var == 'DB_NAME':
                logger.info(f"{var}: using default 'stocks'")
            elif not os.getenv(var) and var == 'DB_USER':
                logger.info(f"{var}: using default 'stocks'")
        else:
            if not os.getenv(var):
                errors.append(f"{var} missing: {description}")

    # FIXED Issue #15: Validate DB_HOST points to proxy (now required, not optional)
    db_host = os.getenv('DB_HOST', '')
    # RDS Proxy endpoints contain both 'proxy' and 'rds.amazonaws.com'
    # Direct RDS endpoints have 'db-' and 'rds.amazonaws.com' but NOT 'proxy'
    is_likely_direct_rds = ('db-' in db_host and 'rds.amazonaws.com' in db_host and 'proxy' not in db_host.lower())
    is_localhost = db_host.startswith('localhost') or db_host.startswith('127.')

    if is_likely_direct_rds and not is_localhost:
        # SECURITY FIX S-12: Don't log actual DB_HOST in error messages (exposes infrastructure)
        logger.error(f"FATAL: DB_HOST appears to be direct RDS, not proxy. Connection pooling REQUIRED. Use RDS Proxy endpoint.")
        errors.append(f"DB_HOST invalid: Must use RDS Proxy endpoint (contains 'proxy'), not direct RDS. Connection pooling is required for production.")

    return len(errors) == 0, errors

def test_db_connection():
    """Test database connection at Lambda cold-start.

    Validates that the database is reachable and responsive.
    Fails fast if connection cannot be established, providing clear diagnostics.

    Uses adaptive timeouts:
    - connect_timeout=5s: abort if RDS Proxy connection fails
    - statement_timeout=3s: abort if query execution stalls
    - Total overhead stays well within API Gateway 29s limit

    Returns: (success: bool, error_msg: Optional[str])
    """
    import time
    start_time = time.time()

    try:
        from utils.db_connection import get_db_connection
        # Increased timeouts: 5s for connection, allows for slow startups
        conn = get_db_connection(max_retries=0, timeout=5)
        connect_time = time.time() - start_time

        cur = conn.cursor()
        try:
            # 3-second query timeout (up from 1s) for more reliable test on slow systems
            cur.execute("SET statement_timeout TO '3000'")
            query_start = time.time()
            cur.execute("SELECT 1 as connection_test")
            result = cur.fetchone()
            query_time = time.time() - query_start

            cur.close()
            conn.close()

            if result and result[0] == 1:
                total_time = time.time() - start_time
                logger.info(
                    f"[DB_TEST_SUCCESS] Database connection verified at cold start "
                    f"(connect={connect_time:.2f}s, query={query_time:.3f}s, total={total_time:.2f}s)"
                )
                return True, None
            else:
                return False, "Connection test query returned unexpected result"
        except Exception as qe:
            try:
                conn.close()
            except Exception:
                pass
            raise qe
    except Exception as e:
        error_msg = (
            f"Database connection test failed at cold start: {type(e).__name__}: {str(e)}. "
            f"Verify RDS Proxy is running and network connectivity is available."
        )
        logger.error(f"[DB_TEST_FAILED] {error_msg}")
        return False, error_msg

# SECURITY FIX: API Rate Limiting is enforced ONLY at API Gateway level
# In-memory per-Lambda tracking is ineffective because:
# - Each Lambda cold start resets tracking dict
# - Each Lambda instance has independent tracking
# - Concurrent instances multiply effective rate limit
# Instead, rely on API Gateway throttling (100 req/sec burst, 50 req/sec sustained)
# which is GLOBAL across all instances
MAX_REQUEST_BODY_SIZE = 1024 * 100

# Public health endpoints exempt from in-Lambda rate limiting (uptime monitors hit these).
# /health/detailed and /api/health/detailed require authentication — they are NOT exempt,
# so authenticated clients share the same per-instance throttle as other endpoints.
RATE_LIMIT_EXEMPT_PATHS = {
    '/health',
    '/api/health',
    '/health/pipeline',
    '/api/health/pipeline',
}

def redact_sensitive_headers(headers_dict):
    """Issue #42: Redact sensitive headers from logs to prevent credential leakage."""
    redacted = dict(headers_dict)
    sensitive_keys = ['authorization', 'cookie', 'x-api-key', 'x-auth-token']
    for key in sensitive_keys:
        if key.lower() in [k.lower() for k in redacted.keys()]:
            actual_key = [k for k in redacted.keys() if k.lower() == key.lower()][0]
            redacted[actual_key] = '***REDACTED***'
    return redacted

def validate_query_param_type(value: str, expected_type: str) -> tuple:
    """Validate and convert query parameter to expected type.

    Args:
        value: The string value to validate
        expected_type: 'int', 'float', 'bool', 'string'

    Returns:
        (valid: bool, converted_value: Any)
    """
    if expected_type == 'int':
        try:
            return True, int(value)
        except ValueError:
            return False, None
    elif expected_type == 'float':
        try:
            return True, float(value)
        except ValueError:
            return False, None
    elif expected_type == 'bool':
        if value.lower() in ('true', '1', 'yes', 'on'):
            return True, True
        elif value.lower() in ('false', '0', 'no', 'off'):
            return True, False
        else:
            return False, None
    else:  # string
        return True, value

def parse_query_params(event: Dict) -> Dict:
    """Parse query parameters from API Gateway v1 or v2 events."""
    params = {}
    # Try v1 format first (REST API)
    if 'queryStringParameters' in event and event['queryStringParameters']:
        for k, v in event['queryStringParameters'].items():
            params[k] = [v] if v else []
    # If no v1 params, try v2 format (HTTP API with rawQueryString)
    elif 'rawQueryString' in event and event['rawQueryString']:
        for param in event['rawQueryString'].split('&'):
            if '=' in param:
                k, v = param.split('=', 1)
                params[k] = params.get(k, []) + [v]
            else:
                params[param] = ['']
    return params

def _build_allowed_origins() -> set:
    """Build allowed origins from environment variables (cached at module load).

    SECURITY FIX: Explicitly configure all allowed origins; no wildcard matching.
    Dev mode origins (localhost) only allowed if ALLOW_LOCALHOST_CORS=true
    """
    global _ALLOWED_ORIGINS_CACHE

    if _ALLOWED_ORIGINS_CACHE is not None:
        return _ALLOWED_ORIGINS_CACHE

    origins = set()

    # FRONTEND_URL is required in production (must be set explicitly)
    frontend_url = os.getenv('FRONTEND_URL', '').strip()
    if frontend_url:
        origins.add(frontend_url)

    # Additional origins from ALLOWED_ORIGINS env var (comma-separated)
    env_origins = os.getenv('ALLOWED_ORIGINS', '')
    if env_origins:
        for o in env_origins.split(','):
            o = o.strip()
            if o:
                origins.add(o)

    # In development ONLY, allow localhost origins (if explicitly enabled)
    # This is gated behind ALLOW_LOCALHOST_CORS=true to prevent accidental exposure
    if os.getenv('ALLOW_LOCALHOST_CORS') == 'true':
        origins.add('http://localhost:5173')  # Vite default
        origins.add('http://localhost:3000')  # React dev default

    _ALLOWED_ORIGINS_CACHE = origins
    return origins

def get_cors_headers(event: Dict) -> Dict[str, str]:
    """Get CORS headers based on request origin (strict whitelist only).

    SECURITY FIX: Rejects any origin not explicitly whitelisted.
    No wildcard localhost matching - all origins must be configured.
    """
    origin = event.get('headers', {}).get('origin', '') or event.get('headers', {}).get('Origin', '')

    allowed_origins = _build_allowed_origins()

    # Only allow origin if explicitly whitelisted
    if origin in allowed_origins:
        return {
            'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Credentials': 'true',
            'Vary': 'Origin',
        }

    # Reject cross-origin requests from unknown sources
    # Return null origin so browser blocks the response
    return {
        'Vary': 'Origin',
    }

def get_json_content_type() -> str:
    """Return JSON content-type with proper UTF-8 charset declaration."""
    return 'application/json; charset=utf-8'

def get_security_headers() -> Dict[str, str]:
    """Return security headers for all responses."""
    return {
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains; preload',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
        'Content-Security-Policy': "default-src 'self'; img-src 'self' data: https:; frame-ancestors 'none'; base-uri 'self'",
    }

def get_cache_headers(cache_type: str = 'no-cache') -> Dict[str, str]:
    """Return cache control headers based on content type.

    Args:
        cache_type: 'no-cache' (revalidate each time), 'public' (cacheable),
                    'private' (user-specific), or 'none' (never cache)
    """
    if cache_type == 'no-cache':
        # Sensitive data - always revalidate with server
        return {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
        }
    elif cache_type == 'public':
        # Public market data - cache for 5 minutes
        return {
            'Cache-Control': 'public, max-age=300, s-maxage=300',
        }
    elif cache_type == 'private':
        # User-specific data - cache only on client, not CDN
        return {
            'Cache-Control': 'private, max-age=300',
        }
    elif cache_type == 'none':
        # Never cache
        return {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
        }
    else:
        return {'Cache-Control': 'no-cache'}

def get_bearer_token(event: Dict) -> Optional[str]:
    """Extract Bearer token from Authorization header."""
    headers = event.get('headers', {})
    auth_header = (
        headers.get('Authorization') or
        headers.get('authorization') or
        ''
    )

    if not auth_header.startswith('Bearer '):
        return None

    return auth_header[7:]  # Remove 'Bearer ' prefix

def _get_cognito_jwks():
    """Fetch and cache Cognito JWKS (JSON Web Key Set) - cached for 10 minutes.

    Short TTL allows rapid key rotation in emergencies (max 10min delay).
    """
    global _JWKS_CACHE, _JWKS_CACHE_TIME

    cognito_region = os.getenv('COGNITO_REGION', 'us-east-1')
    cognito_user_pool_id = os.getenv('COGNITO_USER_POOL_ID')

    if not cognito_user_pool_id:
        logger.warning("COGNITO_USER_POOL_ID not set - JWT signature verification disabled")
        return None

    now = datetime.now(timezone.utc)
    cache_ttl = timedelta(minutes=10)

    if _JWKS_CACHE and _JWKS_CACHE_TIME and (now - _JWKS_CACHE_TIME) < cache_ttl:
        return _JWKS_CACHE

    try:
        from requests.adapters import HTTPAdapter
        url = f"https://cognito-idp.{cognito_region}.amazonaws.com/{cognito_user_pool_id}/.well-known/jwks.json"
        session = requests.Session()
        session.mount('https://', HTTPAdapter(max_retries=0))
        response = session.get(url, timeout=3)
        response.raise_for_status()
        _JWKS_CACHE = response.json()
        _JWKS_CACHE_TIME = now
        return _JWKS_CACHE
    except Exception as e:
        logger.error(f"Failed to fetch Cognito JWKS: {e}")
        return None

def validate_bearer_token(token: Optional[str]) -> tuple:
    """Validate JWT token: format, signature, expiration, audience.

    Returns: (is_valid: bool, claims: dict or None, error: str or None)
    """
    if not token:
        return (False, None, "No token provided")

    # Development mode: allow simple dev tokens (e.g., "dev-admin")
    # This supports frontend dev authentication without Cognito JWT
    is_dev_mode = os.getenv('DEV_BYPASS_AUTH', '').lower() == 'true' or \
                  os.getenv('ENVIRONMENT', '').lower() == 'development'
    if is_dev_mode and token.startswith('dev-'):
        # Create minimal claims for dev token
        logger.info(f"[DEV_MODE] Accepting development token: {token}")
        dev_claims = {
            'sub': 'dev-user',
            'cognito:groups': ['admin', 'user'],  # Grant admin access for testing
            'email': 'dev@localhost',
        }
        return (True, dev_claims, None)

    if len(token) < 50:
        return (False, None, "Token too short")
    if token.count('.') != 2:
        return (False, None, "Invalid token structure")

    try:
        parts = token.split('.')

        # Verify Cognito is configured - fail hard if not (no dev fallback)
        cognito_region = os.getenv('COGNITO_REGION', 'us-east-1')
        cognito_user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
        if not cognito_user_pool_id:
            logger.error("FATAL: COGNITO_USER_POOL_ID not configured in Lambda environment")
            return (False, None, "Authentication system not configured - contact administrator")

        # Decode header to get key ID
        header = json.loads(base64.urlsafe_b64decode(parts[0] + '=='))

        # Production: verify signature with Cognito public keys
        jwks = _get_cognito_jwks()
        if not jwks:
            return (False, None, "Unable to fetch Cognito keys")

        kid = header.get('kid')
        if not kid:
            return (False, None, "Token has no key ID")

        # Find matching key
        key_data = None
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                key_data = key
                break

        if not key_data:
            logger.warning(f"Key {kid} not found in Cognito JWKS")
            return (False, None, "Key not found")

        # Verify signature and claims
        cognito_client_id = os.getenv('COGNITO_CLIENT_ID', '').strip()
        if not cognito_client_id:
            logger.error("FATAL: COGNITO_CLIENT_ID not configured - JWT audience validation will be skipped (SECURITY H-01)")
            return (False, None, "Authentication system misconfigured - COGNITO_CLIENT_ID missing")

        # Cognito access tokens use `client_id` claim (not `aud`).
        # ID tokens use `aud` = client_id. Skip PyJWT audience validation
        # and check whichever claim is present to support both token types.
        payload = jwt.decode(
            token,
            jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data)),
            algorithms=['RS256'],
            issuer=f"https://cognito-idp.{cognito_region}.amazonaws.com/{cognito_user_pool_id}",
            options={'verify_exp': True, 'verify_aud': False}
        )

        # Manually verify client identity from either claim
        actual_client = payload.get('client_id') or payload.get('aud', '')
        if isinstance(actual_client, list):
            actual_client = actual_client[0] if actual_client else ''
        if actual_client != cognito_client_id:
            logger.warning(f"JWT client_id/aud mismatch: expected {cognito_client_id}, got {actual_client}")
            return (False, None, "Token client mismatch")

        # O-1: Check server-side revocation (user called POST /api/logout)
        jti = payload.get('jti')
        if jti:
            try:
                from utils.token_blocklist import is_revoked
                if is_revoked(jti):
                    return (False, None, "Token has been revoked")
            except Exception as e:
                logger.warning(f"Blocklist check failed (non-fatal): {e}")

        logger.info(f"JWT validated: user={payload.get('sub')}, valid until {payload.get('exp')}")

        # SECURITY FIX S-08: Validate JWT scope claim (if present)
        # Scope is optional, but if Cognito is configured to issue scopes, validate them
        token_scope = payload.get('scope', '').split()
        if token_scope:
            # Example: if a user has read-only scope, they shouldn't be able to modify data
            # For now, just log it. In future: reject write operations for read-only users
            logger.debug(f"JWT scopes: {token_scope}")

        return (True, payload, None)

    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        return (False, None, "Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return (False, None, f"Token invalid: {str(e)}")
    except json.JSONDecodeError as e:
        return (False, None, f"Invalid token format: {str(e)}")
    except Exception as e:
        logger.error(f"Token validation error: {e}", exc_info=True)
        return (False, None, "Token validation failed")


def categorize_error(e: Exception) -> str:
    """Categorize exception to return specific error_type for better debugging.

    Returns error_type string: 'database_error', 'auth_error', 'validation_error', 'import_error', or 'unknown_error'
    """
    error_class_name = type(e).__name__
    error_module = type(e).__module__ if hasattr(type(e), '__module__') else ''

    # Database errors
    if 'psycopg2' in error_module or error_class_name in ('OperationalError', 'DatabaseError'):
        return 'database_error'

    # Auth/JWT errors
    if 'jwt' in error_module or error_class_name in ('ExpiredSignatureError', 'InvalidTokenError'):
        return 'auth_error'

    # Validation errors
    if error_class_name == 'ValueError':
        return 'validation_error'

    # Import/initialization errors
    if error_class_name in ('ImportError', 'ModuleNotFoundError', 'AttributeError'):
        return 'import_error'

    return 'unknown_error'


def get_client_ip(event: Dict) -> str:
    """Extract client IP for audit logging.

    Uses API Gateway's requestContext.identity.sourceIp as the authoritative source —
    this is filled by API Gateway itself and cannot be forged by a client.

    NOTE: When behind CloudFront, sourceIp is the CloudFront edge IP, not the user's IP.
    To log real user IPs, configure CloudFront to add a shared-secret custom header
    (e.g. x-origin-verify) and verify it here before trusting CF-Connecting-IP.
    """
    # API GW fills sourceIp from the TCP connection — not client-spoofable
    source_ip = event.get('requestContext', {}).get('identity', {}).get('sourceIp', '')
    if source_ip:
        return source_ip

    # Fallback for local/test invocations without requestContext
    headers = event.get('headers', {})
    xff = headers.get('x-forwarded-for') or headers.get('X-Forwarded-For', '')
    if xff:
        return xff.split(',')[0].strip()

    return 'unknown'

def log_api_request(event: Dict, status_code: int, user_id: Optional[str] = None, error_msg: Optional[str] = None):
    """Log API request for audit trail (security incident investigation).

    Format: JSON structured log with timestamp, request ID, IP, method, path, status, user
    """
    try:
        client_ip = get_client_ip(event)
        path = event.get('rawPath', event.get('path', '/'))
        method = event.get('requestContext', {}).get('http', {}).get('method', 'UNKNOWN')
        request_id = event.get('requestContext', {}).get('requestId', 'unknown')

        audit_log = {
            'event': 'API_REQUEST',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'request_id': request_id,
            'client_ip': client_ip,
            'method': method,
            'path': path,
            'status_code': status_code,
            'user_id': user_id or 'anonymous',
            'error': error_msg or ''
        }

        logger.info(json.dumps(audit_log))
    except Exception as e:
        logger.error(f"Failed to log API request: {str(e)}")

def require_auth(event: Dict, path: str) -> tuple:
    """
    Check if path requires authentication.
    Returns: (requires_auth: bool, is_authorized: bool, error_msg: str or None, jwt_claims: dict or None)
    """
    # Public endpoints (no auth required) - only aggregate market data (no strategy/trading info)
    # SECURITY FIX: Strategy and trading endpoints require authentication
    PUBLIC_PREFIXES = {
        '/api/health',  # Basic health check (no auth required for uptime monitoring)
        # /api/health/detailed and /api/health/pipeline intentionally require authentication
        # (they expose DB table names, loader names, row counts, freshness ages).
        '/api/market',  # Market breadth, distribution (aggregate only - no strategy)
        '/api/algo/markets',  # Market regime data (public market conditions)
        '/api/algo/swing-scores',  # Swing trader scores (used by TradingSignals page for all users)
        '/api/algo/notifications',  # Notifications visible in dev mode
        '/api/algo/sector-rotation',  # Sector rotation analysis (public market analysis)
        '/api/algo/sector-breadth',   # Sector breadth analysis (public market data)
        '/api/algo/sector-stage2',    # Stage 2 sector stocks (public market analysis)
        '/api/economic',  # Economic indicators (public data)
        '/api/sectors',  # Sector analysis (aggregate market data only)
        '/api/sentiment',  # Market sentiment (aggregate only)
        '/api/industries',  # Industry analysis (aggregate market data)
        '/api/prices',  # Historical prices (public market data)
        '/api/stocks',  # Stock metadata/list (public data)
        '/api/scores',  # Stock scores/analysis (public market analysis, used by Sentiment and SectorAnalysis)
        '/api/financials',  # Company financials (public data)
        '/api/earnings',  # Earnings data (public data)
        # /api/research intentionally NOT public: exposes backtest strategy names, returns, trade history
        '/api/data-coverage',  # Data freshness status (public metadata)
        '/api/contact',  # Public contact form (no auth required)
    }

    # Protected endpoints requiring authentication (strategy/trading data)
    # These endpoints are NOT in PUBLIC_PREFIXES:
    # - /api/algo/* - algo performance, signals, positions, trades, notifications
    # - /api/signals/* - trading signals (strategy intelligence)
    # - /api/scores/* - trading scores (strategy intelligence)
    # - /api/audit/* - audit logs (sensitive)
    # - /api/trades/* - trade history (user-specific)
    # - /api/admin/* - admin functions (sensitive)
    # - /api/settings/* - user settings (user-specific)

    # Protected endpoints (requires authentication)
    # /api/trades - user-specific trade history
    # /api/audit - system audit logs (sensitive)
    # /api/admin - administrative functions
    # /api/settings - user-specific settings

    # Check if path matches any public prefix
    # Match: exact route or /path/subpath (strict matching to prevent auth bypass)
    def matches_prefix(p, prefix):
        if p == prefix:
            return True
        if p.startswith(prefix + '/'):
            return True
        if p.startswith(prefix + '?'):
            return True
        return False

    is_public = any(matches_prefix(path, prefix) for prefix in PUBLIC_PREFIXES)
    if is_public:
        return (False, True, None, None)  # No auth required, so authorized

    if not path.startswith('/api/'):
        return (False, True, None, None)  # Non-API paths don't need auth

    # This is an /api path that requires authentication
    # SECURITY FIX: Authentication must be enforced for protected endpoints
    # In production, Cognito MUST be configured (COGNITO_USER_POOL_ID set)
    if not _COGNITO_ENABLED:
        # Allow development bypass with DEV_BYPASS_AUTH environment variable
        if os.getenv('DEV_BYPASS_AUTH', '').lower() == 'true':
            logger.warning(f"[DEV_MODE] Dev mode enabled, checking for dev token...")
            token = get_bearer_token(event)
            if token and token.startswith('dev-'):
                is_valid, claims, error = validate_bearer_token(token)
                if is_valid:
                    logger.info(f"[DEV_MODE] Dev token validated with groups: {claims.get('cognito:groups')}")
                    return (True, True, None, claims)
            # If no valid dev token, grant admin access for development
            logger.info(f"[DEV_MODE] No token or invalid token; granting dev admin access")
            return (False, True, None, {'cognito:groups': ['admin', 'user'], 'sub': 'dev-user'})
        logger.error(f"[AUTH_FAILURE] Protected endpoint {path} accessed but Cognito not configured")
        return (True, False, "Authentication system not configured. Contact administrator.", None)

    token = get_bearer_token(event)

    if not token:
        return (True, False, "Missing Authorization: Bearer token", None)

    is_valid, claims, error = validate_bearer_token(token)
    if not is_valid:
        return (True, False, error or "Invalid token", None)

    # Token is valid - return claims for routing
    return (True, True, None, claims)

# Module-level initialization: Run validation, DB test, and pre-cache values once at cold start
if not IMPORT_ERROR:
    env_valid, env_errors = validate_environment()
    if not env_valid:
        ENV_VALIDATION_ERROR = '; '.join(env_errors)
        logger.error(f'[MODULE_INIT_ENV_VALIDATION_FAILED] {ENV_VALIDATION_ERROR}')

    db_test_ok, db_test_error = test_db_connection()
    if not db_test_ok:
        # Log the error but do NOT set DB_CONNECTION_ERROR as a permanent flag.
        # A transient DB blip during cold-start should not brick this instance for its lifetime.
        # Each request will attempt its own connection via DatabaseContext and fail gracefully if needed.
        logger.error(f'[MODULE_INIT_DB_TEST_FAILED] {db_test_error}')

    # Determine if Cognito authentication is enabled
    _COGNITO_ENABLED = bool(os.getenv('COGNITO_USER_POOL_ID'))
    if not _COGNITO_ENABLED:
        logger.warning("[COGNITO] COGNITO_USER_POOL_ID not set - Cognito authentication is disabled")

    # Pre-cache allowed origins at module load to avoid building on every request
    _build_allowed_origins()

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle API Gateway v2 (HTTP API) requests by routing to extracted handler modules."""
    # Credential cache uses 5-minute TTL to balance freshness with API costs
    # No need to clear on every invocation — expired entries are automatically skipped
    try:
        from config.credential_manager import clear_expired_credentials
        clear_expired_credentials()
    except Exception:
        pass  # If we can't clear expired creds, continue anyway (non-fatal)

    # Extract path and method before ANY checks so health/CORS always work
    path = event.get('rawPath', event.get('path', '/'))
    method = event.get('requestContext', {}).get('http', {}).get('method', event.get('httpMethod', 'GET'))

    # CORS preflight: must succeed even during import failures (browsers need this)
    if method == 'OPTIONS':
        cors_headers = get_cors_headers(event)
        return {
            'statusCode': 200,
            'headers': {
                **cors_headers,
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, PATCH, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
                **get_security_headers()
            }
        }

    # EventBridge warmup ping — return immediately without touching DB or Cognito.
    # Keeps one Lambda container alive to eliminate VPC cold-start 502s for real users.
    if event.get('source') == 'warmup':
        return {'statusCode': 200, 'body': 'warm'}

    # Health checks are handled via api_router (routes/health.py) for consistent response format
    # All health endpoints (basic, detailed, pipeline) now route through normal flow
    # This ensures all API responses use the same {statusCode, data/items/error} structure

    # Import error check (after health so health always works despite missing modules)
    if IMPORT_ERROR:
        cors_headers = get_cors_headers(event)
        # SECURITY FIX: Don't expose internal error details to clients; log server-side
        logger.error(f'[IMPORT_ERROR] {IMPORT_ERROR}')
        return {
            'statusCode': 500,
            'headers': {'Content-Type': get_json_content_type(), **cors_headers},
            'body': json.dumps({'error': 'service_unavailable', 'message': 'Service temporarily unavailable'})
        }

    # Environment validation and DB test are now run once at module load (not on every request)
    # This check ensures that if there were initialization errors, we return them
    if ENV_VALIDATION_ERROR:
        cors_headers = get_cors_headers(event)
        logger.error(f'[ENV_VALIDATION_FAILED] {ENV_VALIDATION_ERROR}')

        # Parse error message to extract individual errors for clearer diagnostics
        error_list = [e.strip() for e in ENV_VALIDATION_ERROR.split(';') if e.strip()]

        # Determine specific config error type for better client diagnostics
        error_type = 'configuration_error'
        if any('COGNITO' in e for e in error_list):
            error_type = 'cognito_config_error'
        elif any('DB_' in e or 'database' in e.lower() for e in error_list):
            error_type = 'database_config_error'
        elif any('FRONTEND_URL' in e for e in error_list):
            error_type = 'cors_config_error'

        return {
            'statusCode': 500,
            'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
            'body': json.dumps({
                'error': error_type,
                'message': 'Service configuration incomplete',
                'missing_config': error_list,
                'details': 'Ensure all required environment variables are set in Lambda configuration'
            })
        }

    logger.info(f'[HANDLER_INVOKED] Event received: {path} {method}')
    try:
        logger.info(f'Request: {method} {path}')

        # Check authorization for protected endpoints
        requires_auth, is_authorized, auth_error, jwt_claims = require_auth(event, path)

        if requires_auth and not is_authorized:
            cors_headers = get_cors_headers(event)
            logger.warning(f'Unauthorized access attempt to {path}: {auth_error}')
            log_api_request(event, 401, error_msg=auth_error)
            return {
                'statusCode': 401,
                'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                'body': json.dumps({'error': 'unauthorized', 'message': auth_error})
            }

        # Skip rate limiting for health check endpoints (required for uptime monitoring)
        is_health_check = path in RATE_LIMIT_EXEMPT_PATHS

        # Detailed and pipeline health checks are handled via api_router (routes/health.py)
        # They verify authentication through the normal flow and provide consistent response format

        # Rate limiting enforced at API Gateway level (not per-Lambda)
        # All rate limiting is handled by API Gateway throttling, which is global across instances

        try:
            # Use read-only mode for GET/HEAD, write mode for POST/PUT/PATCH/DELETE
            http_method = method.upper() if method else 'GET'
            db_mode = 'write' if http_method in ('POST', 'PUT', 'PATCH', 'DELETE') else 'read'
            with DatabaseContext(db_mode) as cur:
                # statement_timeout is now set at RDS parameter group level (30s) — no per-request SET needed.

                params = parse_query_params(event)
                body = None
                if event.get('body'):
                    body_str = event['body']
                    if len(body_str) > MAX_REQUEST_BODY_SIZE:
                        cors_headers = get_cors_headers(event)
                        logger.warning(f'Request body exceeds max size: {len(body_str)} > {MAX_REQUEST_BODY_SIZE}')
                        log_api_request(event, 413, error_msg='request_entity_too_large')
                        return {
                            'statusCode': 413,
                            'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                            'body': json.dumps({'error': 'request_entity_too_large', 'message': 'Request body too large'})
                        }
                    try:
                        body = json.loads(body_str)
                    except (json.JSONDecodeError, Exception) as e:
                        cors_headers = get_cors_headers(event)
                        logger.warning(f'Failed to parse JSON body: {e}')
                        log_api_request(event, 400, error_msg='invalid_json')
                        return {
                            'statusCode': 400,
                            'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                            'body': json.dumps({'error': 'invalid_json', 'message': 'Request body must be valid JSON'})
                        }

                # O-1: POST /api/logout — revoke current token server-side
                if method == 'POST' and path == '/api/logout':
                    cors_headers = get_cors_headers(event)
                    if not is_authorized or not jwt_claims:
                        log_api_request(event, 401, error_msg='unauthorized')
                        return {
                            'statusCode': 401,
                            'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                            'body': json.dumps({'error': 'unauthorized', 'message': 'Authentication required'})
                        }
                    jti = jwt_claims.get('jti')
                    exp = jwt_claims.get('exp')
                    if jti and exp:
                        try:
                            from utils.token_blocklist import revoke_token
                            revoke_token(jti, int(exp))
                        except Exception as e:
                            logger.error(f"[LOGOUT] Blocklist write failed: {e}")
                    logger.info(f"[LOGOUT] User {jwt_claims.get('sub')} logged out")
                    log_api_request(event, 200)
                    return {
                        'statusCode': 200,
                        'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                        'body': json.dumps({'status': 'logged_out'})
                    }

                # Route request to appropriate handler
                response = api_router.route_request(cur, path, method, params, body, jwt_claims=jwt_claims)
        except Exception as e:
            cors_headers = get_cors_headers(event)

            # SECURITY FIX: Don't leak error details to client; log full details server-side only
            error_detail = f'{type(e).__name__}: {str(e)[:300]}'
            error_type = categorize_error(e)
            logger.error(f'[HANDLER_ERROR] path={path} error_type={error_type} {error_detail}', exc_info=True)
            # Never expose error details to client (prevents info disclosure)
            return {
                'statusCode': 503,
                'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                'body': json.dumps({
                    'error': 'service_unavailable',
                    'error_type': error_type,
                    'message': 'Service temporarily unavailable. Please try again later.'
                })
            }

        # Ensure response has proper format
        def _json_default(obj):
            import datetime
            from decimal import Decimal
            if isinstance(obj, (datetime.date, datetime.datetime)):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return float(obj)
            if hasattr(obj, '__float__'):
                return float(obj)
            return str(obj)

        if isinstance(response, dict):
            status = response.get('statusCode', 200)
            cors_headers = get_cors_headers(event)
            headers = {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()}
            if 'body' in response:
                body = response['body'] if isinstance(response['body'], str) else json.dumps(response['body'], default=_json_default)
            else:
                # Route handlers return data dicts directly (no body key) — include statusCode in body
                body = json.dumps(response, default=_json_default)

            # Log successful requests (2xx, 3xx)
            if status < 400:
                log_api_request(event, status)
            # Log errors (4xx, 5xx)
            elif status >= 400:
                error_msg = response.get('message', response.get('error', 'unknown_error'))
                log_api_request(event, status, error_msg=str(error_msg))

            return {'statusCode': status, 'headers': headers, 'body': body}

        cors_headers = get_cors_headers(event)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
            'body': json.dumps({'error': 'invalid_response'})
        }

    except Exception as e:
        error_msg = f'{type(e).__name__}: {str(e)}'
        logger.error(f'[UNHANDLED_ERROR] {error_msg}', exc_info=True)
        cors_headers = get_cors_headers(event)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
            'body': json.dumps({
                'error': 'internal_server_error',
                'message': 'An unexpected error occurred'
            })
        }
