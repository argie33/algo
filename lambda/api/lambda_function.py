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
except Exception as e:
    IMPORT_ERROR = f"{type(e).__name__}: {str(e)[:200]}"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_db_conn = None

# Rate limiting state (in-memory for this Lambda instance) - only if imports succeeded
if not IMPORT_ERROR:
    _request_history = defaultdict(list)
else:
    _request_history = {}
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 1
MAX_REQUEST_BODY_SIZE = 1024 * 100


def get_db_connection():
    """Get or create database connection."""
    global _db_conn
    if _db_conn and not _db_conn.closed:
        return _db_conn

    try:
        db_secret_arn = os.getenv('DB_SECRET_ARN')
        db_host = os.getenv('DB_HOST')
        db_port = int(os.getenv('DB_PORT', '5432'))
        db_name = os.getenv('DB_NAME', 'stocks')
        db_user = os.getenv('DB_USER', 'stocks')
        db_password = os.getenv('DB_PASSWORD')

        logger.info(f'[DB CONNECT 1] Config read: secret_arn={bool(db_secret_arn)}, host={db_host}, port={db_port}, db={db_name}, user={db_user}')

        if not db_host:
            logger.error('[DB CONNECT ERROR] DB_HOST environment variable is required - CHECK LAMBDA CONFIG')
            return None

        if db_secret_arn and not db_password:
            import boto3
            try:
                logger.info(f'[DB CONNECT 2] Fetching password from Secrets Manager: {db_secret_arn}')
                secrets = boto3.client('secretsmanager', region_name='us-east-1')
                response = secrets.get_secret_value(SecretId=db_secret_arn)
                secret = json.loads(response['SecretString'])
                db_password = secret.get('password')
                db_user = secret.get('username', db_user)
                logger.info(f'[DB CONNECT 2] Secret fetched OK, password length={len(db_password) if db_password else 0}')
            except Exception as e:
                logger.error(f'[DB CONNECT ERROR] Failed to fetch secret from {db_secret_arn}: {type(e).__name__}: {e}', exc_info=True)
                return None

        if not db_password:
            logger.error('[DB CONNECT ERROR] No database password available - CHECK SECRETS MANAGER')
            return None

        # RDS Proxy requires SSL/TLS connections (but localhost dev doesn't need it)
        db_ssl_env = os.getenv('DB_SSL', 'require').lower()
        # Convert string "false"/"true" to "disable"/"require" for psycopg2
        sslmode = 'disable' if db_ssl_env in ('false', '0', 'no', 'off') else db_ssl_env

        logger.info(f'[DB CONNECT 3] Attempting connection: host={db_host}:{db_port}, db={db_name}, user={db_user}, ssl={sslmode}')
        _db_conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password,
            sslmode=sslmode,
            cursor_factory=RealDictCursor,
            connect_timeout=10
        )
        logger.info('[DB CONNECT 4] Connection successful - RDS ready')
        return _db_conn
    except psycopg2.OperationalError as e:
        error_str = str(e)
        if 'could not translate host name' in error_str.lower():
            logger.error(f'[DB CONNECT ERROR] DNS RESOLUTION FAILED for {db_host} - CHECK: RDS endpoint is correct, VPC has DNS enabled')
        elif 'connection refused' in error_str.lower():
            logger.error(f'[DB CONNECT ERROR] CONNECTION REFUSED to {db_host}:{db_port} - CHECK: RDS is running, security groups allow connection')
        elif 'timeout' in error_str.lower():
            logger.error(f'[DB CONNECT ERROR] CONNECTION TIMEOUT to {db_host}:{db_port} - CHECK: Network reachability, RDS responsiveness')
        else:
            logger.error(f'[DB CONNECT ERROR] OperationalError: {e}')
        return None
    except psycopg2.ProgrammingError as e:
        logger.error(f'[DB CONNECT ERROR] ProgrammingError: {e}')
        return None
    except Exception as e:
        logger.error(f'[DB CONNECT ERROR] Unexpected error to {db_host}:{db_port}: {type(e).__name__}: {str(e)}', exc_info=True)
        return None


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

    # Check if origin is in whitelist
    allowed_origins = _build_allowed_origins()
    if origin in allowed_origins:
        return {
            'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Credentials': 'true',
        }

    # In dev mode, accept any localhost origin
    if origin and (origin.startswith('http://localhost:') or origin.startswith('http://127.0.0.1:')):
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
    allowed_origins_list = ' '.join(_build_allowed_origins())
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
        # Decode header to get key ID without verification first
        parts = token.split('.')

        # Check if this is a dev token (starts with 'devToken')
        if parts[0].startswith('devToken'):
            logger.info("Dev token detected, validating without Cognito")
            # Handle dev token format (not URL-safe base64)
            try:
                payload = json.loads(base64.b64decode(parts[1]))
                if 'exp' in payload and payload['exp'] < int(time()):
                    return (False, None, "Token expired")
                logger.info(f"Dev token valid for user: {payload.get('sub')}")
                return (True, payload, None)
            except Exception as e:
                logger.warning(f"Dev token decode failed: {e}")
                return (False, None, f"Invalid dev token: {str(e)}")

        # Get Cognito public keys
        cognito_region = os.getenv('COGNITO_REGION', 'us-east-1')
        cognito_user_pool_id = os.getenv('COGNITO_USER_POOL_ID')

        # If Cognito not configured, do format-only validation (dev mode)
        # Dev tokens use format: devToken.{standard_base64_payload}.sig
        if not cognito_user_pool_id:
            logger.warning("Dev mode: COGNITO_USER_POOL_ID not set, skipping signature verification")
            # Handle dev token format (not URL-safe base64)
            try:
                payload = json.loads(base64.b64decode(parts[1]))
                if 'exp' in payload and payload['exp'] < int(time()):
                    return (False, None, "Token expired")
                return (True, payload, None)
            except Exception as e:
                logger.warning(f"Dev token decode failed, trying standard JWT: {e}")
                # Fall through to standard JWT handling for fallback

        # Production mode: decode header to get key ID
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


def log_api_request(event: Dict, status_code: int, user_id: Optional[str] = None, error_msg: Optional[str] = None):
    """Log API request for audit trail (security incident investigation).

    Format: JSON structured log with timestamp, request ID, IP, method, path, status, user
    """
    try:
        client_ip = event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown')
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
    # Public endpoints (no auth required) - use path.startswith() for prefix matching
    PUBLIC_PREFIXES = {
        '/health',
        '/api/health',
        '/api/contact',
        '/api/signals',  # /api/signals/stocks, /api/signals/etf, etc.
        '/api/scores',
        '/api/market',
        '/api/economic',
        '/api/algo',  # Algo trading endpoints - data is public (no user-specific data)
        '/api/sectors',  # Sector analysis pages
        '/api/sentiment',  # Market sentiment dashboard
        '/api/industries',  # Industry analysis
        '/api/prices',  # Historical prices
        '/api/stocks',  # Stock data
        '/api/trades',  # Trade history
        '/api/financials',  # Company financials
        '/api/earnings',  # Earnings data
        '/api/research',  # Research endpoints
        '/api/audit',  # Audit viewer
    }

    # Check if path matches any public prefix
    is_public = any(path == prefix or path.startswith(prefix + '/') or path.startswith(prefix + '?') for prefix in PUBLIC_PREFIXES)
    if is_public:
        logger.info(f"Public endpoint allowed: {path}")
        return (False, True, None, None)  # No auth required, so authorized
    else:
        logger.info(f"Protected endpoint (not in public list): {path}")

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
    if IMPORT_ERROR:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'import_error', 'message': f'Failed to import dependencies: {IMPORT_ERROR}'})
        }

    logger.info(f'[HANDLER_INVOKED] Event received: {event.get("rawPath", "?")} {event.get("requestContext", {}).get("http", {}).get("method", "?")}')
    try:
        # API Gateway v2 (HTTP API) uses rawPath and requestContext.http.method
        path = event.get('rawPath', event.get('path', '/'))
        method = event.get('requestContext', {}).get('http', {}).get('method', event.get('httpMethod', 'GET'))
        logger.info(f'Request: {method} {path}')

        # CORS preflight must be handled before auth check so browsers can complete handshake
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

        # Check rate limiting (per client IP)
        client_ip = event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown')
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

        # Health check
        if path in ['/health', '/api/health']:
            cors_headers = get_cors_headers(event)
            return {
                'statusCode': 200,
                'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                'body': json.dumps({'status': 'healthy', 'version': 'v2-2026-05-21'})
            }

        # Detailed health check
        if path in ['/health/detailed', '/api/health/detailed']:
            try:
                conn = get_db_connection()
                if not conn:
                    cors_headers = get_cors_headers(event)
                    return {
                        'statusCode': 503,
                        'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                        'body': json.dumps({'status': 'unhealthy', 'dbStatus': 'disconnected'})
                    }

                cur = conn.cursor()
                # Get table counts (whitelist + SQL identifier quoting prevents SQL injection)
                ALLOWED_TABLES = {'price_daily', 'signals', 'stock_scores', 'technical_data_daily'}
                table_counts = {}
                for table in ALLOWED_TABLES:
                    try:
                        query = psycopg2.sql.SQL('SELECT COUNT(*) FROM {}').format(
                            psycopg2.sql.Identifier(table)
                        )
                        cur.execute(query)
                        table_counts[table] = cur.fetchone()[0]
                    except Exception:
                        table_counts[table] = 0
                cur.close()

                cors_headers = get_cors_headers(event)
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                    'body': json.dumps({'status': 'healthy', 'dbStatus': 'connected', 'tables': table_counts})
                }
            except Exception as e:
                cors_headers = get_cors_headers(event)
                return {
                    'statusCode': 503,
                    'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                    'body': json.dumps({'status': 'unhealthy', 'error': 'internal_error'})
                }

        # Pipeline health — queries data_loader_status for all table freshness
        if path in ['/health/pipeline', '/api/health/pipeline']:
            try:
                conn = get_db_connection()
                if not conn:
                    cors_headers = get_cors_headers(event)
                    return {
                        'statusCode': 503,
                        'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                        'body': json.dumps({'status': 'unhealthy', 'error': 'db_unavailable'})
                    }
                cur = conn.cursor()
                try:
                    cur.execute("""
                        SELECT table_name, row_count, last_updated,
                               EXTRACT(EPOCH FROM (NOW() - last_updated)) / 86400 AS age_days
                        FROM data_loader_status ORDER BY table_name
                    """)
                    rows = cur.fetchall()
                except Exception:
                    rows = []
                tables = []
                for row in rows:
                    age = float(row['age_days']) if row.get('age_days') is not None else 999
                    status = 'HEALTHY' if age <= 2 and (row.get('row_count') or 0) > 0 else ('STALE' if age <= 7 else 'CRITICAL')
                    tables.append({'table_name': row['table_name'], 'row_count': row.get('row_count', 0), 'age_days': round(age, 1), 'status': status})
                healthy = sum(1 for t in tables if t['status'] == 'HEALTHY')
                cur.close()
                cors_headers = get_cors_headers(event)
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                    'body': json.dumps({'status': 'HEALTHY' if healthy == len(tables) and tables else 'DEGRADED', 'healthy_count': healthy, 'total_count': len(tables), 'tables': tables})
                }
            except Exception as e:
                cors_headers = get_cors_headers(event)
                return {
                    'statusCode': 500,
                    'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                    'body': json.dumps({'status': 'error', 'error': 'internal_error'})
                }

        conn = get_db_connection()
        if not conn:
            cors_headers = get_cors_headers(event)
            # Log diagnostic details server-side only; never expose internal config to callers
            logger.error('[DB UNAVAILABLE] host=%s port=%s db=%s secret_arn_set=%s',
                         os.getenv('DB_HOST', 'NOT_SET'),
                         os.getenv('DB_PORT', 'NOT_SET'),
                         os.getenv('DB_NAME', 'NOT_SET'),
                         bool(os.getenv('DB_SECRET_ARN')))
            return {
                'statusCode': 503,
                'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                'body': json.dumps({
                    'error': 'database_unavailable',
                    'message': 'Service temporarily unavailable. Check CloudWatch Logs for details.'
                })
            }

        # Reset any failed transaction state from a previous Lambda invocation
        try:
            conn.rollback()
        except Exception:
            _db_conn = None
            conn = get_db_connection()
            if not conn:
                cors_headers = get_cors_headers(event)
                return {
                    'statusCode': 503,
                    'headers': {'Content-Type': get_json_content_type(), **cors_headers, **get_security_headers()},
                    'body': json.dumps({'error': 'database_unavailable'})
                }

        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

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
            except Exception:
                pass

        # Route request to appropriate handler
        response = api_router.route_request(cur, path, method, params, body, jwt_claims=jwt_claims)
        cur.close()

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
