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
# Utils are packaged in the same directory as lambda_function.py in /var/task

IMPORT_ERROR = None

try:
    import psycopg2
    import psycopg2.sql
    from psycopg2.extras import RealDictCursor
    from collections import defaultdict
    from time import time
    import base64
    from datetime import datetime
    from functools import lru_cache
    import jwt
    import requests
    import api_router
    from utils.database_context import DatabaseContext
    from utils.db_connection import get_db_connection
except Exception as e:
    IMPORT_ERROR = f"{type(e).__name__}: {str(e)[:200]}"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def validate_environment():
    """Validate critical environment variables at cold start.

    Returns: (valid: bool, errors: List[str])
    """
    errors = []
    required_vars = {
        'DB_HOST': 'Database host (RDS endpoint or proxy)',
        'DB_PASSWORD': 'Database password (from env var or Secrets Manager via DB_SECRET_ARN)',
        'DB_NAME': 'Database name',
        'DB_USER': 'Database username',
    }

    missing_secret_arn = not os.getenv('DB_SECRET_ARN')
    missing_password = not os.getenv('DB_PASSWORD')

    for var, description in required_vars.items():
        if var == 'DB_PASSWORD':
            if missing_secret_arn and missing_password:
                errors.append(f"{var}: Neither DB_SECRET_ARN nor DB_PASSWORD provided")
        elif var in ['DB_NAME', 'DB_USER']:
            if not os.getenv(var) and var == 'DB_NAME':
                logger.info(f"{var}: using default 'stocks'")
            elif not os.getenv(var) and var == 'DB_USER':
                logger.info(f"{var}: using default 'stocks'")
        else:
            if not os.getenv(var):
                errors.append(f"{var}: required for {description}")

    # FIXED Issue #15: Validate DB_HOST points to proxy (now required, not optional)
    db_host = os.getenv('DB_HOST', '')
    # RDS Proxy endpoints contain both 'proxy' and 'rds.amazonaws.com'
    # Direct RDS endpoints have 'db-' and 'rds.amazonaws.com' but NOT 'proxy'
    is_likely_direct_rds = ('db-' in db_host and 'rds.amazonaws.com' in db_host and 'proxy' not in db_host.lower())
    is_localhost = db_host.startswith('localhost') or db_host.startswith('127.')

    if is_likely_direct_rds and not is_localhost:
        logger.error(f"FATAL: DB_HOST appears to be direct RDS ({db_host}), not proxy. Connection pooling REQUIRED. Use RDS Proxy endpoint.")
        errors.append(f"DB_HOST: Must point to RDS Proxy, not direct RDS endpoint")

    return len(errors) == 0, errors

def test_db_connection():
    """FIXED Issue #17: Test database connection at Lambda cold-start.

    Validates that the database is reachable and responsive.
    Fails fast if connection cannot be established, preventing silent failures later.

    Returns: (success: bool, error_msg: Optional[str])
    """
    try:
        with DatabaseContext('read') as cur:
            cur.execute("SELECT 1 as connection_test")
            result = cur.fetchone()
            if result and result.get('connection_test') == 1:
                logger.info("[DB_TEST_SUCCESS] Database connection verified at cold start")
                return True, None
            else:
                return False, "Connection test query returned unexpected result"
    except Exception as e:
        error_msg = f"Database connection test failed at cold start: {type(e).__name__}: {str(e)}"
        logger.error(f"[DB_TEST_FAILED] {error_msg}")
        return False, error_msg

# FIXED Issue #16: API Rate Limiting via API Gateway
# Global rate limiting is enforced at the API Gateway level (100 req/sec burst, 50 req/sec sustained)
# This supersedes the in-memory per-Lambda tracking below, which is kept as a secondary safeguard
# API Gateway throttling is GLOBAL across all Lambda instances (not per-instance like in-memory tracking)
if not IMPORT_ERROR:
    _request_history = defaultdict(list)
else:
    _request_history = {}
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 1
MAX_REQUEST_BODY_SIZE = 1024 * 100

# Health check endpoints exempt from rate limiting (required for uptime monitoring)
RATE_LIMIT_EXEMPT_PATHS = {
    '/health',
    '/api/health',
    '/health/detailed',
    '/api/health/detailed',
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
    """Build allowed origins from ALLOWED_ORIGINS env var (comma-separated) plus localhost defaults."""
    origins = {'http://localhost:5173', 'http://localhost:3000'}
    env_origins = os.getenv('ALLOWED_ORIGINS', '')
    if env_origins:
        for o in env_origins.split(','):
            o = o.strip()
            if o:
                origins.add(o)
    return origins

def get_cors_headers(event: Dict) -> Dict[str, str]:
    """Get CORS headers based on request origin (whitelist only)."""
    origin = event.get('headers', {}).get('origin', '') or event.get('headers', {}).get('Origin', '')

    # Production CloudFront domain (configurable via FRONTEND_URL env var)
    PROD_CLOUDFRONT = os.getenv('FRONTEND_URL', '')

    # Check if origin is in whitelist or matches production CloudFront
    allowed_origins = _build_allowed_origins()
    if PROD_CLOUDFRONT:  # Only add if actually set (no hardcoded fallback)
        allowed_origins.add(PROD_CLOUDFRONT)

    if origin in allowed_origins:
        return {
            'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Credentials': 'true',
        }

    # In dev mode, only accept whitelisted localhost ports (3000, 5173)
    if origin:
        allowed_localhost_ports = {'3000', '5173'}
        if origin.startswith('http://localhost:'):
            port = origin.split(':')[-1]
            if port in allowed_localhost_ports:
                return {
                    'Access-Control-Allow-Origin': origin,
                    'Access-Control-Allow-Credentials': 'true',
                }
        elif origin.startswith('http://127.0.0.1:'):
            port = origin.split(':')[-1]
            if port in allowed_localhost_ports:
                return {
                    'Access-Control-Allow-Origin': origin,
                    'Access-Control-Allow-Credentials': 'true',
                }

    # Reject cross-origin requests from unknown sources
    return {
        'Access-Control-Allow-Origin': 'null',
    }

def get_json_content_type() -> str:
    """Return JSON content-type with proper UTF-8 charset declaration."""
    return 'application/json; charset=utf-8'

def get_security_headers() -> Dict[str, str]:
    """Return security headers for all responses."""
    origins = _build_allowed_origins()
    # Also include production CloudFront domain if configured
    frontend_url = os.getenv('FRONTEND_URL', '')
    if frontend_url:
        origins.add(frontend_url)
    allowed_origins_list = ' '.join(sorted(origins))
    return {
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains; preload',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
        'Content-Security-Policy': f"default-src 'self'; img-src 'self' data: https:; connect-src 'self' {allowed_origins_list}; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
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

@lru_cache(maxsize=1)
def _get_cognito_jwks():
    """Fetch and cache Cognito JWKS (JSON Web Key Set) - cached for 1 hour."""
    cognito_region = os.getenv('COGNITO_REGION', 'us-east-1')
    cognito_user_pool_id = os.getenv('COGNITO_USER_POOL_ID')

    if not cognito_user_pool_id:
        logger.warning("COGNITO_USER_POOL_ID not set - JWT signature verification disabled")
        return None

    try:
        url = f"https://cognito-idp.{cognito_region}.amazonaws.com/{cognito_user_pool_id}/.well-known/jwks.json"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch Cognito JWKS: {e}")
        return None

def validate_bearer_token(token: Optional[str]) -> tuple:
    """Validate JWT token: format, signature, expiration, audience.

    Returns: (is_valid: bool, claims: dict or None, error: str or None)
    """
    if not token:
        return (False, None, "No token provided")

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
        cognito_client_id = os.getenv('COGNITO_CLIENT_ID')
        payload = jwt.decode(
            token,
            jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data)),
            algorithms=['RS256'],
            audience=cognito_client_id,
            issuer=f"https://cognito-idp.{cognito_region}.amazonaws.com/{cognito_user_pool_id}",
            options={'verify_exp': True}
        )

        logger.info(f"JWT validated: user={payload.get('sub')}, valid until {payload.get('exp')}")
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

def is_rate_limited(client_ip: str, rate_limit_requests: int = RATE_LIMIT_REQUESTS, window_seconds: int = RATE_LIMIT_WINDOW) -> bool:
    """
    Check if client IP has exceeded rate limit.
    Returns True if rate limit exceeded (should block request).
    """
    now = time()

    # Initialize empty list if client IP not seen before
    if client_ip not in _request_history:
        _request_history[client_ip] = []

    # Clean old entries outside the window
    _request_history[client_ip] = [
        req_time for req_time in _request_history[client_ip]
        if now - req_time < window_seconds
    ]

    # Check if limit exceeded
    if len(_request_history[client_ip]) >= rate_limit_requests:
        return True

    # Record this request
    _request_history[client_ip].append(now)
    return False

def get_client_ip(event: Dict) -> str:
    """Extract real client IP, accounting for CloudFront reverse proxy.

    When behind CloudFront, all requests appear to come from CloudFront's IP.
    Use CF-Connecting-IP header (CloudFront's real client IP) instead of sourceIp.
    """
    headers = event.get('headers', {})

    # Check CloudFront's real client IP header first
    if 'cf-connecting-ip' in headers:
        return headers['cf-connecting-ip']
    if 'CF-Connecting-IP' in headers:
        return headers['CF-Connecting-IP']

    # Fallback to X-Forwarded-For (standard proxy header)
    if 'x-forwarded-for' in headers:
        return headers['x-forwarded-for'].split(',')[-1].strip()
    if 'X-Forwarded-For' in headers:
        return headers['X-Forwarded-For'].split(',')[-1].strip()

    # Last resort: API Gateway sourceIp
    return event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown')

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
    # Public endpoints (no auth required) - market data and informational endpoints only
    PUBLIC_PREFIXES = {
        '/health',
        '/api/health',
        '/api/contact',
        '/api/signals',  # Market signal data (public)
        '/api/scores',  # Market scores (public)
        '/api/market',  # Market health, breadth, distribution (public)
        '/api/economic',  # Economic indicators (public)
        '/api/algo',  # Algo strategy data (public, no user-specific data)
        '/api/sectors',  # Sector analysis (public)
        '/api/sentiment',  # Market sentiment (public)
        '/api/industries',  # Industry analysis (public)
        '/api/prices',  # Historical prices (public)
        '/api/stocks',  # Stock data (public)
        '/api/financials',  # Company financials (public)
        '/api/earnings',  # Earnings data (public)
        '/api/research',  # Research endpoints (public)
        '/api/data-coverage',  # Data freshness status (public)
    }

    # Protected endpoints (requires authentication)
    # /api/trades - user-specific trade history
    # /api/audit - system audit logs (sensitive)
    # /api/admin - administrative functions
    # /api/settings - user-specific settings

    # Check if path matches any public prefix
    # Match: exact, /path/subpath, ?query, -hyphenated (e.g., /api/market-health), or no separator
    def matches_prefix(p, prefix):
        if p == prefix:
            return True
        if p.startswith(prefix + '/'):
            return True
        if p.startswith(prefix + '?'):
            return True
        if p.startswith(prefix + '-'):  # Handle hyphenated endpoints like /api/market-health
            return True
        return False

    is_public = any(matches_prefix(path, prefix) for prefix in PUBLIC_PREFIXES)
    if is_public:
        return (False, True, None, None)  # No auth required, so authorized

    if not path.startswith('/api/'):
        return (False, True, None, None)  # Non-API paths don't need auth

    # This is an /api path that requires auth
    token = get_bearer_token(event)

    if not token:
        return (True, False, "Missing Authorization: Bearer token", None)

    is_valid, claims, error = validate_bearer_token(token)
    if not is_valid:
        return (True, False, error or "Invalid token", None)

    # Token is valid - return claims for routing
    return (True, True, None, claims)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle API Gateway v2 (HTTP API) requests by routing to extracted handler modules."""
    # Clear credential cache on invocation to ensure fresh creds for rotated secrets
    try:
        from config.credential_manager import clear_credential_cache
        clear_credential_cache()
    except Exception:
        pass  # If we can't clear cache, continue anyway (non-fatal)

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

    # Health check returns immediately — even if imports failed (uptime monitors must always succeed)
    if path in ['/health', '/api/health']:
        cors_headers = get_cors_headers(event)
        return {
            'statusCode': 200,
            'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
            'body': json.dumps({'status': 'healthy', 'version': 'v2-2026-05-21'})
        }

    # Import error check (after health so health always works despite missing modules)
    if IMPORT_ERROR:
        cors_headers = get_cors_headers(event)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': get_json_content_type(), **cors_headers},
            'body': json.dumps({'error': 'import_error', 'message': f'Failed to import dependencies: {IMPORT_ERROR}'})
        }

    # Validate critical environment variables (non-health requests only)
    env_valid, env_errors = validate_environment()
    if not env_valid:
        error_msg = '; '.join(env_errors)
        logger.error(f'[ENV_VALIDATION_FAILED] {error_msg}')
        cors_headers = get_cors_headers(event)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
            'body': json.dumps({'error': 'configuration_error', 'message': f'Missing required environment variables: {error_msg}'})
        }

    # Test database connection (non-health requests only)
    db_test_ok, db_test_error = test_db_connection()
    if not db_test_ok:
        logger.error(f'[DB_VALIDATION_FAILED] {db_test_error}')
        cors_headers = get_cors_headers(event)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
            'body': json.dumps({'error': 'database_error', 'message': db_test_error})
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

        # Detailed health check
        if path in ['/health/detailed', '/api/health/detailed']:
            try:
                with DatabaseContext('read') as cur:
                    ALLOWED_TABLES = {'price_daily', 'signals', 'stock_scores', 'technical_data_daily'}
                    table_counts = {}
                    for table in ALLOWED_TABLES:
                        try:
                            query = psycopg2.sql.SQL('SELECT COUNT(*) FROM {}').format(
                                psycopg2.sql.Identifier(table)
                            )
                            cur.execute(query)
                            table_counts[table] = cur.fetchone()[0]
                        except Exception as e:
                            logger.warning(f"API exception: {e}")
                            table_counts[table] = 0

                    cors_headers = get_cors_headers(event)
                    return {
                        'statusCode': 200,
                        'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                        'body': json.dumps({'status': 'healthy', 'dbStatus': 'connected', 'tables': table_counts})
                    }
            except Exception as e:
                cors_headers = get_cors_headers(event)
                logger.error(f'[HEALTH_DETAILED_ERROR] {e}', exc_info=True)
                return {
                    'statusCode': 503,
                    'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                    'body': json.dumps({'status': 'unhealthy', 'error': 'internal_error'})
                }

        # Pipeline health — queries data_loader_status for all table freshness
        if path in ['/health/pipeline', '/api/health/pipeline']:
            try:
                with DatabaseContext('read') as cur:
                    try:
                        cur.execute("""
                            SELECT table_name, row_count, last_updated,
                                   EXTRACT(EPOCH FROM (NOW() - last_updated)) / 86400 AS age_days
                            FROM data_loader_status ORDER BY table_name
                        """)
                        rows = cur.fetchall()
                    except Exception as e:
                        logger.warning(f"API exception: {e}")
                        rows = []
                    tables = []
                    for row in rows:
                        age = float(row['age_days']) if row.get('age_days') is not None else 999
                        status = 'HEALTHY' if age <= 2 and (row.get('row_count') or 0) > 0 else ('STALE' if age <= 7 else 'CRITICAL')
                        tables.append({'table_name': row['table_name'], 'row_count': row.get('row_count', 0), 'age_days': round(age, 1), 'status': status})
                    healthy = sum(1 for t in tables if t['status'] == 'HEALTHY')
                    cors_headers = get_cors_headers(event)
                    return {
                        'statusCode': 200,
                        'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                        'body': json.dumps({'status': 'HEALTHY' if healthy == len(tables) and tables else 'DEGRADED', 'healthy_count': healthy, 'total_count': len(tables), 'tables': tables})
                    }
            except Exception as e:
                cors_headers = get_cors_headers(event)
                logger.error(f'[HEALTH_PIPELINE_ERROR] {e}', exc_info=True)
                return {
                    'statusCode': 500,
                    'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                    'body': json.dumps({'status': 'error', 'error': 'internal_error'})
                }

        # Check rate limiting (per client IP) — health endpoints are exempt
        if not is_health_check:
            client_ip = get_client_ip(event)
            if is_rate_limited(client_ip):
                cors_headers = get_cors_headers(event)
                logger.warning(f'Rate limit exceeded for IP {client_ip}')
                log_api_request(event, 429, error_msg='rate_limit_exceeded')
                return {
                    'statusCode': 429,
                    'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers(),
                               'Retry-After': '60'},
                    'body': json.dumps({'error': 'rate_limit_exceeded', 'message': 'Too many requests. Please try again later.'})
                }

        try:
            with DatabaseContext('write') as cur:
                # Set query timeout to prevent long-running queries from blocking API responses
                cur.execute("SET statement_timeout TO '10s'")

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
                    except json.JSONDecodeError as e:
                        cors_headers = get_cors_headers(event)
                        logger.warning(f'Failed to parse JSON body: {e}')
                        log_api_request(event, 400, error_msg='invalid_json')
                        return {
                            'statusCode': 400,
                            'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                            'body': json.dumps({'error': 'invalid_json', 'message': 'Request body must be valid JSON'})
                        }
                    except Exception as e:
                        logger.warning(f"Exception caught: {e}")
                        pass

                # Route request to appropriate handler
                response = api_router.route_request(cur, path, method, params, body, jwt_claims=jwt_claims)
        except Exception as e:
            cors_headers = get_cors_headers(event)
            logger.error(f'[DB_ERROR] Failed to get database connection: {e}', exc_info=True)
            return {
                'statusCode': 503,
                'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                'body': json.dumps({
                    'error': 'database_unavailable',
                    'message': 'Service temporarily unavailable. Check CloudWatch Logs for details.'
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
                # Route handlers return data dicts directly (no body key) — wrap them
                body = json.dumps({k: v for k, v in response.items() if k != 'statusCode'}, default=_json_default)

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
