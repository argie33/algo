"""
Stock Analytics Platform - API Lambda Handler

Serves HTTP API endpoints for the frontend dashboard.
Connects to RDS PostgreSQL database and returns JSON.

Endpoints:
- /api/algo/* â€” algo orchestrator status, positions, trades, performance
- /api/signals/* â€” trading signals (stocks, etfs)
- /api/prices/* â€” price history
- /api/stocks/* â€” stock screeners
- /api/portfolio/* â€” portfolio data
- /api/sectors/* â€” sector analysis
- /api/market/* â€” market data
- /api/economic/* â€” economic indicators
- /api/sentiment/* â€” market sentiment
- /api/health â€” API health check
"""

import os
import json
import logging
import psycopg2
import psycopg2.extras
import psycopg2.errors
import psycopg2.pool
import psycopg2.sql
import re
import time
from datetime import datetime, timedelta, date, timezone
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, Field, field_validator, ValidationError
from middleware.auth_middleware import APIKeyValidator
from validation_schema import (
    SymbolRequest, PaginationParams, DateRangeParams,
    PriceData, TradeRequest, ScoreData
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class ContactRequest(BaseModel):
    """Contact form submission — validated via Pydantic before DB insert."""
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., max_length=255)
    subject: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=10, max_length=5000)

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        if '@' not in v or '.' not in v.split('@')[-1]:
            raise ValueError('Invalid email format')
        return v.lower()


# Module-level connection pool: Lambda containers are reused across warm invocations.
# ThreadedConnectionPool allows multiple sequential connections within a single Lambda container.
# minconn=2 (at least 2 idle connections), maxconn=10 (max 10 concurrent, plenty for 128MB Lambda)
_db_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_db_conn: Optional[psycopg2.extensions.connection] = None
_db_creds: Optional[Dict] = None  # cache Secrets Manager response to avoid per-call latency

# Rate limiting: track requests per IP
# Format: {ip: [timestamp1, timestamp2, ...]}
# Clean up old entries every 100 requests to prevent unbounded growth
_rate_limit_tracker: Dict[str, list] = {}
_rate_limit_check_count = 0


def _load_creds() -> Dict:
    global _db_creds
    if _db_creds:
        return _db_creds
    db_secret_arn = os.getenv('DB_SECRET_ARN') or os.getenv('DATABASE_SECRET_ARN')
    if db_secret_arn:
        import boto3
        from botocore.exceptions import ClientError
        try:
            secrets = boto3.client('secretsmanager', region_name=os.getenv('AWS_REGION', 'us-east-1'))
            response = secrets.get_secret_value(SecretId=db_secret_arn)
            _db_creds = json.loads(response['SecretString'])
        except ClientError as e:
            logger.error(f"Failed to load database credentials from Secrets Manager: {e.response['Error']['Code']}")
            raise RuntimeError("Unable to load database credentials")
    else:
        _db_creds = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'username': os.getenv('DB_USER', 'stocks'),
            'password': os.getenv('DB_PASSWORD', ''),
            'dbname': os.getenv('DB_NAME', 'stocks'),
        }
    return _db_creds


def get_db_connection():
    """Return a live DB connection, reusing the cached one on warm Lambda invocations."""
    global _db_conn
    if _db_conn is not None and not _db_conn.closed:
        try:
            _db_conn.isolation_level  # lightweight liveness probe
            return _db_conn
        except Exception as e:
            logger.warning(f"Cached connection dead, reconnecting: {e}")
    try:
        creds = _load_creds()
        # Handle both 'username' and 'user' keys (Secrets Manager vs env vars)
        username = creds.get('username') or creds.get('user')
        database = creds.get('dbname') or creds.get('database')
        _db_conn = psycopg2.connect(
            host=creds.get('host'),
            port=int(creds.get('port', 5432)),
            user=username,
            password=creds.get('password'),
            database=database,
            connect_timeout=5,
            options='-c statement_timeout=25000',  # 25s query timeout
        )
        return _db_conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise


def json_response(status_code: int, body: Dict[str, Any], headers: Optional[Dict] = None) -> Dict:
    """Return properly formatted API Gateway response with security headers."""
    # CORS: Require FRONTEND_ORIGIN to be explicitly set. Don't allow wildcard '*'
    frontend_origin = os.environ.get('FRONTEND_ORIGIN', '')
    if not frontend_origin:
        # Fail-closed: If FRONTEND_ORIGIN not set, use empty string (no CORS allowed)
        frontend_origin = ''

    # Security headers: Defense-in-depth against XSS, clickjacking, MIME sniffing
    default_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': frontend_origin,
        'Access-Control-Allow-Methods': 'GET, POST, PATCH, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Max-Age': '86400',
        # Prevent clickjacking attacks
        'X-Frame-Options': 'DENY',
        # Prevent MIME type sniffing
        'X-Content-Type-Options': 'nosniff',
        # Browser XSS protection (legacy, but defense-in-depth)
        'X-XSS-Protection': '1; mode=block',
        # Referrer policy: Don't leak referer to external sites
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        # Content Security Policy: Strict, inline scripts disabled
        'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'",
        # Enforce HTTPS for all future requests (if in production)
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains' if os.environ.get('ENVIRONMENT') == 'production' else '',
    }
    # Remove empty HSTS header in non-production
    if not default_headers['Strict-Transport-Security']:
        del default_headers['Strict-Transport-Security']

    if headers:
        default_headers.update(headers)

    # Ensure consistent response structure: always include success and timestamp for standardization
    if 'success' not in body:
        body['success'] = True
    if 'timestamp' not in body:
        body['timestamp'] = datetime.now(timezone.utc).isoformat()

    return {
        'statusCode': status_code,
        'headers': default_headers,
        'body': json.dumps(body, default=str),
    }


def error_response(status_code: int, error_code: str, message: str = '') -> Dict:
    """Return standardized error response.
    Format: {success: false, error: code, message: details, timestamp}
    Internal errors are logged but not exposed to clients.
    """
    if message:
        logger.error(f"API error [{status_code}] {error_code}: {message}")

    # Sanitize message: never expose internal details in production
    safe_message = message if status_code < 500 else 'An internal error occurred'

    # Map HTTP status to error code if provided code is generic
    if error_code == 'internal_error' and status_code == 500:
        error_code = 'internal_error'
    elif error_code == 'error' or not error_code:
        if status_code == 400:
            error_code = 'bad_request'
        elif status_code == 401:
            error_code = 'unauthorized'
        elif status_code == 403:
            error_code = 'forbidden'
        elif status_code == 404:
            error_code = 'not_found'
        elif status_code == 409:
            error_code = 'conflict'
        elif status_code == 429:
            error_code = 'rate_limited'
        elif status_code == 503:
            error_code = 'service_unavailable'
        else:
            error_code = 'error'

    return json_response(status_code, {
        'success': False,
        'error': error_code,
        'message': safe_message
    })


def list_response(items: list, total: int = None, page: int = 1, limit: int = None, offset: int = 0) -> Dict:
    """Consistent list response: {success, items, total, pagination, timestamp}."""
    n = total if total is not None else len(items)
    lim = limit or len(items) or 1
    total_pages = max(1, -(-n // lim))  # ceiling division
    return json_response(200, {
        'success': True,
        'items': items,
        'total': n,
        'pagination': {
            'limit': lim,
            'offset': offset,
            'total': n,
            'page': page,
            'totalPages': total_pages,
            'hasNext': (offset + lim) < n,
            'hasPrev': offset > 0,
        }
    })


def check_rate_limit(ip: str, max_requests: int = 100, window_seconds: int = 60) -> bool:
    """Check if IP has exceeded rate limit. Returns True if request is allowed."""
    global _rate_limit_tracker, _rate_limit_check_count

    current_time = time.time()

    # Clean up old entries periodically
    _rate_limit_check_count += 1
    if _rate_limit_check_count % 100 == 0:
        for tracked_ip in list(_rate_limit_tracker.keys()):
            _rate_limit_tracker[tracked_ip] = [
                t for t in _rate_limit_tracker[tracked_ip]
                if current_time - t < window_seconds
            ]
            if not _rate_limit_tracker[tracked_ip]:
                del _rate_limit_tracker[tracked_ip]

    # Check current IP
    if ip not in _rate_limit_tracker:
        _rate_limit_tracker[ip] = []

    # Remove old requests outside the window
    _rate_limit_tracker[ip] = [
        t for t in _rate_limit_tracker[ip]
        if current_time - t < window_seconds
    ]

    # Check if limit exceeded
    if len(_rate_limit_tracker[ip]) >= max_requests:
        return False

    # Record this request
    _rate_limit_tracker[ip].append(current_time)
    return True


def validate_request(model_class: type, data: Dict[str, Any]) -> Tuple[bool, Any, Optional[str]]:
    """Validate request data against Pydantic model. Returns (valid, data_or_error, error_message)."""
    try:
        validated = model_class(**data)
        return True, validated, None
    except ValidationError as e:
        # Extract first error for clarity
        first_error = e.errors()[0]
        field = first_error.get('loc', ['unknown'])[0]
        msg = first_error.get('msg', 'Validation error')
        error_message = f"Invalid {field}: {msg}"
        return False, None, error_message
    except Exception as e:
        return False, None, f"Validation failed: {str(e)}"


def _safe_limit(limit_str: Any, min_val: int = 1, max_val: int = 500, default: int = 100) -> int:
    """Safely extract and clamp limit parameter to prevent DoS attacks via large result sets."""
    try:
        if limit_str is None:
            return default
        limit = int(limit_str)
        return max(min_val, min(limit, max_val))
    except (ValueError, TypeError):
        return default


def _safe_offset(offset_str: Any, max_offset: int = 1000000, default: int = 0) -> int:
    """Safely extract and clamp offset parameter."""
    try:
        if offset_str is None:
            return default
        offset = int(offset_str)
        return max(0, min(offset, max_offset))
    except (ValueError, TypeError):
        return default


def _safe_days(days_str: Any, min_val: int = 1, max_val: int = 730, default: int = 30) -> int:
    """Safely extract and clamp days parameter (max 2 years) to prevent DoS attacks."""
    try:
        if days_str is None:
            return default
        days = int(days_str)
        return max(min_val, min(days, max_val))
    except (ValueError, TypeError):
        return default


def _safe_page(page_str: Any, min_val: int = 1, max_val: int = 100000, default: int = 1) -> int:
    """Safely extract and clamp page parameter to prevent DoS attacks via deep pagination."""
    try:
        if page_str is None:
            return default
        page = int(page_str)
        return max(min_val, min(page, max_val))
    except (ValueError, TypeError):
        return default


def _validate_symbol(symbol: str) -> bool:
    """Validate stock symbol format: 1-20 chars, uppercase letters, numbers, dash, dot only."""
    if not symbol:
        return False
    return bool(re.match(r'^[A-Z0-9.\-]{1,20}$', symbol))


class APIHandler:
    """Main API request handler."""

    def __init__(self):
        self.conn = None
        self.cur = None

    def connect(self):
        """Establish database connection."""
        self.conn = get_db_connection()
        self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def disconnect(self):
        """Release cursor; keep connection alive for Lambda container reuse."""
        try:
            if self.cur:
                self.cur.close()
            # Roll back any uncommitted transaction so next request starts clean
            if self.conn:
                self.conn.rollback()
        except Exception as e:
            logger.debug(f"Error during disconnect: {e}")
        # Do NOT close self.conn â€” it's the module-level cached connection for reuse

    def _safe_limit(self, limit_val, default=200, max_limit=10000) -> int:
        """Safely extract and validate limit parameter (prevents DoS)."""
        try:
            limit = int(limit_val) if limit_val else default
            return max(1, min(limit, max_limit))
        except (ValueError, TypeError):
            return default

    def _safe_offset(self, offset_val, max_offset=1000000) -> int:
        """Safely extract and validate offset parameter (prevents DoS)."""
        try:
            offset = int(offset_val) if offset_val else 0
            return max(0, min(offset, max_offset))
        except (ValueError, TypeError):
            return 0

    def _sanitize_error(self, exc: Exception) -> str:
        """Sanitize exception messages to prevent information leakage."""
        error_str = str(exc)
        # Hide database-specific details
        if 'relation' in error_str or 'column' in error_str or 'syntax error' in error_str:
            return 'internal_error'
        if 'authentication' in error_str or 'permission' in error_str:
            return 'permission_denied'
        if 'connection' in error_str or 'timeout' in error_str:
            return 'connection_error'
        # Generic error for anything else
        return 'operation_failed'

    def _parse_range_param(self, params: Dict) -> int:
        """Parse range parameter safely. Format: '30d', '1y', etc. Default: 30 days."""
        if not params:
            return 30
        range_str = params.get('range', ['30d'])[0] if params else '30d'
        try:
            # Validate format: must be digits followed by 'd'
            if not range_str.endswith('d'):
                return 30
            days_str = range_str[:-1]
            if not days_str.isdigit():
                return 30
            days = int(days_str)
            # Clamp to reasonable range (1-365 days)
            return max(1, min(days, 365))
        except (ValueError, AttributeError):
            return 30

    def _health_check(self) -> Dict:
        """Health check: verify API and database are operational."""
        try:
            # Test database connectivity with simple query
            self.cur.execute("SELECT 1 as connectivity_check")
            self.cur.fetchone()
            db_status = 'ok'
        except Exception as e:
            logger.error(f"Health check: database unavailable - {e}")
            db_status = 'error'
            return error_response(503, 'service_unavailable', 'Database connection failed')

        return json_response(200, {
            'status': 'healthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'database': db_status,
            'checks': {
                'api': 'ok',
                'database': db_status
            }
        })

    def route(self, path: str, method: str = 'GET', query_params: Dict = None, body: Dict = None) -> Dict:
        """Route request to appropriate handler."""
        query_params = query_params or {}
        body = body or {}

        try:
            # Health check
            if path == '/api/health':
                return self._health_check()

            # Algo endpoints
            if path.startswith('/api/algo/'):
                return self._handle_algo(path, method, query_params)

            # Signals endpoints
            if path.startswith('/api/signals/'):
                return self._handle_signals(path, method, query_params)

            # Prices endpoints
            if path.startswith('/api/prices/'):
                return self._handle_prices(path, method, query_params)

            # Stocks endpoints
            if path == '/api/stocks' or path.startswith('/api/stocks/'):
                return self._handle_stocks(path, method, query_params)

            # Financials endpoints
            if path.startswith('/api/financials/'):
                return self._handle_financials(path, method, query_params)

            # Portfolio endpoints
            if path.startswith('/api/portfolio/'):
                return self._handle_portfolio(path, method, query_params)

            # Sector endpoints
            if path == '/api/sectors' or path.startswith('/api/sectors/'):
                return self._handle_sectors(path, method, query_params)

            # Industries endpoints
            if path == '/api/industries' or path.startswith('/api/industries/'):
                return self._handle_industries(path, method, query_params)

            # Market endpoints
            if path.startswith('/api/market/'):
                return self._handle_market(path, method, query_params)

            # Economic endpoints
            if path == '/api/economic' or path.startswith('/api/economic/'):
                return self._handle_economic(path, method, query_params)

            # Sentiment endpoints
            if path.startswith('/api/sentiment/'):
                return self._handle_sentiment(path, method, query_params)

            # Research endpoints
            if path.startswith('/api/research/'):
                return self._handle_research(path, method, query_params)

            # Audit endpoints
            if path.startswith('/api/audit/'):
                return self._handle_audit(path, method, query_params)

            # Trade endpoints
            if path == '/api/trades' or path.startswith('/api/trades/'):
                return self._handle_trades(path, method, query_params)

            # Scores endpoints
            if path.startswith('/api/scores/'):
                return self._handle_scores(path, method, query_params)

            # Earnings endpoints
            if path.startswith('/api/earnings/'):
                return self._handle_earnings(path, method, query_params)

            # Contact endpoints
            if path == '/api/contact' or path.startswith('/api/contact/'):
                return self._handle_contact(path, method, query_params, body)

            # Admin endpoints
            if path.startswith('/api/admin/'):
                return self._handle_admin(path, method, query_params)

            # Settings endpoints
            if path == '/api/settings' or path.startswith('/api/settings/'):
                return self._handle_settings(path, method, query_params, body)

            # Test endpoint
            if path == '/api/test':
                return json_response(200, {'status': 'ok', 'message': 'API connection successful'})

            return error_response(404, 'not_found', f'No handler for {path}')

        except Exception as e:
            logger.error(f"Request failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Internal server error')

    def _handle_algo(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/algo/* endpoints."""
        # Handle PATCH /api/algo/notifications/{id}/read
        if method == 'PATCH' and path.endswith('/read') and '/notifications/' in path:
            notif_id = path.split('/notifications/')[-1].replace('/read', '')
            try:
                try:
                    notif_id_int = int(notif_id)
                except ValueError:
                    return error_response(400, 'bad_request', 'ID must be numeric')
                self.cur.execute(
                    "UPDATE algo_notifications SET seen=TRUE, seen_at=NOW() WHERE id=%s",
                    (notif_id_int,)
                )
                self.conn.commit()
                return json_response(200, {'status': 'updated'})
            except Exception as e:
                logger.error(f"notification mark-read error: {e}")
                return error_response(500, 'internal_error', 'Failed to update notification')
        # Handle DELETE /api/algo/notifications/{id}
        if method == 'DELETE' and '/notifications/' in path:
            notif_id = path.split('/notifications/')[-1]
            try:
                self.cur.execute("DELETE FROM algo_notifications WHERE id=%s", (int(notif_id),))
                self.conn.commit()
                return json_response(200, {'status': 'deleted'})
            except Exception as e:
                logger.error(f"notification delete error: {e}")
                return error_response(500, 'internal_error', 'Failed to delete notification')
        # Handle POST /api/algo/patrol
        if method == 'POST' and path == '/api/algo/patrol':
            logger.info("Manual patrol triggered via API")
            return json_response(200, {'status': 'triggered', 'message': 'Patrol triggered'})
        # Handle POST /api/algo/pre-trade-impact
        if method == 'POST' and path == '/api/algo/pre-trade-impact':
            return self._analyze_pre_trade_impact(body)
        if path == '/api/algo/status':
            return self._get_algo_status()
        elif path == '/api/algo/trades':
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=500, default=200)
            return self._get_algo_trades(limit)
        elif path == '/api/algo/positions':
            return self._get_algo_positions()
        elif path == '/api/algo/performance':
            return self._get_algo_performance()
        elif path == '/api/algo/circuit-breakers':
            return self._get_circuit_breakers()
        elif path == '/api/algo/equity-curve':
            days_str = params.get('limit', [None])[0] if params else None
            days = _safe_days(days_str, max_val=365, default=180)
            return self._get_equity_curve(days)
        elif path == '/api/algo/data-status':
            return self._get_data_status()
        elif path == '/api/algo/notifications':
            return self._get_notifications(params)
        elif path == '/api/algo/patrol-log':
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=200, default=50)
            offset_str = params.get('offset', [None])[0] if params else None
            offset = _safe_offset(offset_str)
            return self._get_patrol_log(limit, offset)
        elif path == '/api/algo/sector-rotation':
            days_str = params.get('limit', [None])[0] if params else None
            days = _safe_days(days_str, max_val=365, default=180)
            return self._get_sector_rotation(days)
        elif path == '/api/algo/sector-breadth':
            return self._get_sector_breadth()
        elif path == '/api/algo/swing-scores':
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=200, default=100)
            return self._get_swing_scores(limit)
        elif path == '/api/algo/swing-scores-history':
            days_str = params.get('days', [None])[0] if params else None
            days = _safe_days(days_str, max_val=365, default=30)
            return self._get_swing_scores_history(days)
        elif path == '/api/algo/rejection-funnel':
            return self._get_rejection_funnel()
        elif path == '/api/algo/markets':
            return self._get_markets()
        elif path == '/api/algo/evaluate':
            return self._get_algo_evaluate()
        elif path == '/api/algo/data-quality':
            return self._get_data_quality()
        elif path == '/api/algo/exposure-policy':
            return self._get_exposure_policy()
        elif path == '/api/algo/sector-stage2':
            return self._get_sector_stage2()
        elif path == '/api/algo/config':
            return self._get_algo_config()
        elif path.startswith('/api/algo/config/'):
            key = path[len('/api/algo/config/'):]
            return self._get_algo_config_key(key)
        elif path == '/api/algo/audit-log':
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=200, default=100)
            offset_str = params.get('offset', [None])[0] if params else None
            offset = _safe_offset(offset_str)
            action_type = params.get('action_type', [None])[0] if params else None
            return self._get_algo_audit_log(limit, offset, action_type)
        else:
            return error_response(404, 'not_found', f'No algo handler for {path}')

    def _get_algo_status(self) -> Dict:
        """Get latest algo execution status."""
        try:
            self.cur.execute("""
                SELECT
                    details->>'run_id' AS run_id,
                    action_type,
                    action_date,
                    details->>'summary' AS message,
                    status,
                    created_at
                FROM algo_audit_log
                ORDER BY created_at DESC
                LIMIT 1
            """)
            row = self.cur.fetchone()
            if not row:
                return json_response(200, {'status': 'no_runs_yet', 'last_run': None})

            return json_response(200, {
                'run_id': row['run_id'],
                'last_run': row['action_date'].isoformat() if row['action_date'] else None,
                'current_phase': row['action_type'],
                'status': row['status'],
                'message': row['message'],
            })
        except Exception as e:
            logger.error(f"get_algo_status failed: {e}")
            return error_response(500, 'internal_error', 'Failed to fetch algo status')

    def _get_algo_trades(self, limit: int = 200) -> Dict:
        """Get recent trades with all fields for frontend."""
        try:
            self.cur.execute("""
                SELECT trade_id, symbol, signal_date, trade_date, entry_price, entry_time,
                       entry_quantity, entry_reason, exit_price, exit_date, exit_time,
                       exit_reason, exit_r_multiple, profit_loss_dollars, profit_loss_pct,
                       status, swing_score, swing_grade, base_type, stage_phase,
                       trade_duration_days, mfe_pct, mae_pct, created_at
                FROM algo_trades
                ORDER BY trade_date DESC, trade_id DESC
                LIMIT %s
            """, (limit,))
            trades = self.cur.fetchall()
            items = [dict(t) for t in trades]
            return json_response(200, {
                'items': items,
                'pagination': {'total': len(items), 'limit': limit, 'offset': 0}
            })
        except Exception as e:
            logger.error(f"get_algo_trades failed: {e}")
            return error_response(500, 'internal_error', 'Failed to fetch trades')

    def _get_algo_positions(self) -> Dict:
        """Get current open positions with all tracking fields."""
        try:
            self.cur.execute("""
                SELECT position_id, symbol, quantity, avg_entry_price, current_price,
                       position_value, unrealized_pnl, unrealized_pnl_pct, status,
                       days_since_entry, distribution_day_count, target_levels_hit,
                       current_stop_price, stage_in_exit_plan, created_at, updated_at
                FROM algo_positions
                WHERE status IN ('open', 'OPEN')
                ORDER BY position_value DESC
            """)
            positions = self.cur.fetchall()
            items = [dict(p) for p in positions]
            return json_response(200, {
                'items': items,
                'pagination': {'total': len(items), 'limit': 10000, 'offset': 0}
            })
        except Exception as e:
            logger.error(f"get_algo_positions failed: {e}")
            return error_response(500, 'internal_error', 'Failed to fetch positions')

    def _get_algo_performance(self) -> Dict:
        """Get comprehensive algo performance metrics including Sharpe, Sortino, max drawdown."""
        try:
            import numpy as np
            self.cur.execute("""
                SELECT trade_id, symbol, trade_date, exit_date, entry_price, exit_price,
                       entry_quantity, profit_loss_dollars, profit_loss_pct,
                       exit_r_multiple,
                       EXTRACT(DAY FROM COALESCE(exit_date, CURRENT_DATE) - trade_date) as holding_days
                FROM algo_trades WHERE status IN ('closed', 'CLOSED') ORDER BY exit_date DESC LIMIT 1000
            """)
            trades = [dict(row) for row in self.cur.fetchall()]
            if not trades:
                return json_response(200, {'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0,
                    'win_rate': 0.0, 'profit_factor': 0.0, 'total_pnl_dollars': 0.0, 'total_pnl_pct': 0.0,
                    'avg_trade_pct': 0.0, 'best_trade_pct': 0.0, 'worst_trade_pct': 0.0,
                    'sharpe_ratio': 0.0, 'sortino_ratio': 0.0, 'max_drawdown_pct': 0.0, 'avg_holding_days': 0.0})
            pnls_dollars = [float(t['profit_loss_dollars'] or 0) for t in trades]
            pnls_pcts = [float(t['profit_loss_pct'] or 0) for t in trades]
            holding_days = [float(t['holding_days'] or 0) for t in trades if t['holding_days']]
            r_multiples = [float(t['exit_r_multiple']) for t in trades if t.get('exit_r_multiple') is not None]
            winning, losing = sum(1 for p in pnls_dollars if p > 0), sum(1 for p in pnls_dollars if p < 0)
            total = len(trades)
            wins_sum, losses_sum = sum(p for p in pnls_dollars if p > 0), abs(sum(p for p in pnls_dollars if p < 0))
            profit_factor = (wins_sum / losses_sum) if losses_sum > 0 else 0.0

            # Compute Sharpe and Sortino from daily portfolio returns (not per-trade returns)
            sharpe, sortino, max_dd = 0.0, 0.0, 0.0
            try:
                self.cur.execute("""
                    SELECT snapshot_date, total_portfolio_value
                    FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date ASC
                """)
                snapshots = [dict(row) for row in self.cur.fetchall()]
                if len(snapshots) > 1:
                    portfolio_values = np.array([float(s['total_portfolio_value'] or 0) for s in snapshots])
                    portfolio_returns = np.diff(portfolio_values) / portfolio_values[:-1]
                    if len(portfolio_returns) > 0:
                        mean_ret = float(np.mean(portfolio_returns))
                        std_ret = float(np.std(portfolio_returns))
                        sharpe = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0
                        downside = np.array([r for r in portfolio_returns if r < 0])
                        downside_vol = float(np.std(downside)) if len(downside) > 0 else 0.0
                        sortino = (mean_ret / downside_vol * np.sqrt(252)) if downside_vol > 0 else 0.0
                        cumulative = np.cumprod(1 + portfolio_returns)
                        running_max = np.maximum.accumulate(cumulative)
                        max_dd = float(np.min((cumulative - running_max) / running_max)) if len(cumulative) > 0 else 0.0
            except Exception as e:
                logger.debug(f"Could not compute Sharpe/Sortino from snapshots: {e}")

            # Fallback max_dd from cumulative trade returns if snapshots unavailable
            if max_dd == 0.0 and len(pnls_pcts) > 0:
                daily_returns = np.array(pnls_pcts) / 100.0
                cumulative = np.cumprod(1 + daily_returns)
                running_max = np.maximum.accumulate(cumulative)
                max_dd = float(np.min((cumulative - running_max) / running_max)) if len(cumulative) > 0 else 0.0
            else:
                daily_returns = np.array(pnls_pcts) / 100.0
            win_rate_pct = round((winning / total * 100) if total > 0 else 0.0, 2)
            return json_response(200, {
                'total_trades': total,
                'winning_trades': winning,
                'losing_trades': losing,
                'win_rate': win_rate_pct,
                'win_rate_pct': win_rate_pct,
                'profit_factor': round(profit_factor, 2),
                'total_pnl_dollars': round(sum(pnls_dollars), 2),
                'total_pnl_pct': round(sum(pnls_pcts), 2),
                'total_return_pct': round(sum(pnls_pcts), 2),
                'avg_trade_pct': round(float(np.mean(pnls_pcts)) if pnls_pcts else 0.0, 2),
                'avg_win_pct': round(float(np.mean([p for p in pnls_pcts if p > 0])) if any(p > 0 for p in pnls_pcts) else 0.0, 2),
                'avg_loss_pct': round(float(np.mean([p for p in pnls_pcts if p < 0])) if any(p < 0 for p in pnls_pcts) else 0.0, 2),
                'best_trade_pct': round(float(np.max(pnls_pcts)) if pnls_pcts else 0.0, 2),
                'worst_trade_pct': round(float(np.min(pnls_pcts)) if pnls_pcts else 0.0, 2),
                'sharpe_annualized': round(sharpe, 2),
                'sharpe_ratio': round(sharpe, 2),
                'sortino_annualized': round(sortino, 2),
                'sortino_ratio': round(sortino, 2),
                'max_drawdown_pct': round(max_dd * 100, 2),
                'calmar_ratio': round(sum(pnls_pcts) / 100 / abs(max_dd) if max_dd < 0 else 0.0, 2),
                'expectancy_r': round((wins_sum - losses_sum) / total if total > 0 else 0.0, 2),
                'avg_hold_days': round(float(np.mean(holding_days)) if holding_days else 0.0, 1),
                'avg_holding_days': round(float(np.mean(holding_days)) if holding_days else 0.0, 1),
                'avg_r_multiple': round(float(np.mean(r_multiples)) if r_multiples else 0.0, 2),
                'avg_win_r': round(float(np.mean([r for r in r_multiples if r > 0])) if any(r > 0 for r in r_multiples) else 0.0, 2),
                'avg_loss_r': round(float(np.mean([r for r in r_multiples if r < 0])) if any(r < 0 for r in r_multiples) else 0.0, 2),
                'portfolio_snapshots': 0
            })
        except Exception as e:
            logger.error(f"get_algo_performance failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to calculate performance metrics')

    def _get_circuit_breakers(self) -> Dict:
        """Get circuit breaker status from most recent orchestrator run."""
        try:
            # Most recent circuit breaker check (halt or all-clear)
            self.cur.execute("""
                SELECT details, action_date, status
                FROM algo_audit_log
                WHERE action_type = 'circuit_breaker_halt'
                ORDER BY created_at DESC
                LIMIT 1
            """)
            row = self.cur.fetchone()

            # Also get last successful (non-halted) orchestrator run details
            self.cur.execute("""
                SELECT details, action_date
                FROM algo_audit_log
                WHERE action_type IN ('phase_2_complete', 'orchestrator_run')
                ORDER BY created_at DESC
                LIMIT 1
            """)
            last_run = self.cur.fetchone()

            breakers = []
            if row and row['details']:
                try:
                    details = json.loads(row['details']) if isinstance(row['details'], str) else row['details']
                    # Validate that details is a dict before calling .get()
                    if not isinstance(details, dict):
                        details = {}
                    checks = details.get('checks', {})
                    # Validate that checks is a dict and contains dicts
                    if not isinstance(checks, dict):
                        checks = {}
                    for name, state in checks.items():
                        if not isinstance(state, dict):
                            continue  # Skip malformed entries
                        breakers.append({
                            'name': name,
                            'halted': bool(state.get('halted', False)),
                            'reason': state.get('reason', ''),
                            'as_of': str(row['action_date']),
                        })
                except (json.JSONDecodeError, AttributeError):
                    pass

            return json_response(200, {
                'breakers': breakers,
                'last_check': str(row['action_date']) if row else None,
                'last_run': str(last_run['action_date']) if last_run else None,
                'system_halted': any(b['halted'] for b in breakers),
            })
        except Exception as e:
            logger.error(f"get_circuit_breakers failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch circuit breaker status')

    def _get_equity_curve(self, days: int = 180) -> Dict:
        """Get equity curve for last N days."""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            self.cur.execute("""
                SELECT snapshot_date, total_portfolio_value, total_cash,
                       unrealized_pnl_total, position_count, daily_return_pct
                FROM algo_portfolio_snapshots
                WHERE snapshot_date >= %s
                ORDER BY snapshot_date DESC
                LIMIT 1000
            """, (cutoff_date,))
            curve = self.cur.fetchall()
            return list_response([dict(c) for c in reversed(curve) if c])
        except Exception as e:
            logger.error(f"Error fetching equity curve: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch equity curve')

    def _get_data_status(self) -> Dict:
        """Get data freshness status."""
        try:
            self.cur.execute("""
                SELECT symbol, latest_date
                FROM data_loader_status
                ORDER BY latest_date DESC
                LIMIT 10
            """)
            rows = self.cur.fetchall()
            return json_response(200, {
                'latest_data': [dict(r) for r in rows],
                'as_of': datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.error(f"get_equity_curve failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch equity curve')

    def _get_notifications(self, params: Dict = None) -> Dict:
        """Get recent notifications with optional filtering."""
        try:
            params = params or {}
            kind = params.get('kind', [None])[0] if params.get('kind') else None
            severity = params.get('severity', [None])[0] if params.get('severity') else None
            unread = params.get('unread', [None])[0] if params.get('unread') else None
            limit_str = params.get('limit', [None])[0] if params.get('limit') else None
            limit = _safe_limit(limit_str, max_val=200, default=50)

            where_clauses = []
            where_params = []

            if kind:
                where_clauses.append("kind = %s")
                where_params.append(kind)
            if severity:
                where_clauses.append("severity = %s")
                where_params.append(severity)
            if unread and unread.lower() in ('true', '1', 'yes'):
                where_clauses.append("seen = FALSE")

            where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

            query = f"""
                SELECT id, created_at, kind, severity, title, message, seen, seen_at, symbol, details
                FROM algo_notifications
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT %s
            """
            where_params.append(limit)

            self.cur.execute(query, tuple(where_params))
            notifs = self.cur.fetchall()
            return list_response([dict(n) for n in notifs])
        except Exception as e:
            logger.error(f"Error fetching notifications: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch notifications')

    def _analyze_pre_trade_impact(self, body: Dict) -> Dict:
        """Analyze impact of a potential trade on portfolio constraints."""
        try:
            symbol = body.get('symbol', '').upper()
            entry_price = float(body.get('entry_price', 0)) if body.get('entry_price') else None
            position_dollars = body.get('position_dollars')
            position_pct = body.get('position_pct')

            if not symbol:
                return error_response(400, 'bad_request', 'symbol is required')

            # Get current portfolio state
            self.cur.execute("""
                SELECT COUNT(*) AS position_count,
                       SUM(CASE WHEN pd.quantity > 0 THEN pd.market_value ELSE 0 END) AS invested
                FROM algo_positions pd
            """)
            portfolio_row = self.cur.fetchone()
            current_positions = portfolio_row[0] if portfolio_row else 0
            invested = float(portfolio_row[1]) if portfolio_row and portfolio_row[1] else 0.0

            # Get portfolio value
            self.cur.execute("""
                SELECT equity FROM algo_portfolio_snapshot
                ORDER BY created_at DESC LIMIT 1
            """)
            snap = self.cur.fetchone()
            portfolio_value = float(snap[0]) if snap and snap[0] else 100000.0

            # Get sector and industry
            self.cur.execute("""
                SELECT sector, industry FROM company_profile WHERE symbol = %s
            """, (symbol,))
            profile = self.cur.fetchone()
            sector = dict(profile)['sector'] if profile else 'Unknown'
            industry = dict(profile)['industry'] if profile else 'Unknown'

            # Determine position size
            if position_dollars:
                position_size_dollars = float(position_dollars)
            elif position_pct:
                position_size_dollars = portfolio_value * (float(position_pct) / 100)
            else:
                position_size_dollars = portfolio_value * 0.01  # default 1%

            if not entry_price:
                entry_price = position_size_dollars / 100  # assume 100 shares

            shares = int(position_size_dollars / entry_price) if entry_price > 0 else 0
            position_pct_calc = (position_size_dollars / portfolio_value * 100) if portfolio_value > 0 else 0

            # Check constraints
            max_positions = 12
            max_position_pct = 8.0
            max_sector_pct = 30.0

            position_limit_ok = current_positions < max_positions
            position_size_ok = position_pct_calc <= max_position_pct
            cash_available = portfolio_value - invested
            cash_ok = cash_available >= position_size_dollars

            # Get current sector exposure
            self.cur.execute("""
                SELECT SUM(CASE WHEN cp.sector = %s THEN pd.market_value ELSE 0 END) /
                       NULLIF((SELECT SUM(market_value) FROM algo_positions), 0) * 100 AS sector_pct
                FROM algo_positions pd
                JOIN company_profile cp ON pd.symbol = cp.symbol
            """, (sector,))
            sector_row = self.cur.fetchone()
            current_sector_pct = float(sector_row[0]) if sector_row and sector_row[0] else 0.0
            new_sector_pct = current_sector_pct + position_pct_calc
            sector_limit_ok = new_sector_pct <= max_sector_pct

            # Worst-case drawdown impact (simplified)
            max_acceptable_impact = 2.0
            worst_case_impact = (position_pct_calc / 100) * 0.20  # assume 20% loss on new position
            drawdown_risk_ok = (worst_case_impact * 100) <= max_acceptable_impact

            all_ok = (position_limit_ok and position_size_ok and cash_ok and
                     sector_limit_ok and drawdown_risk_ok)

            return json_response(200, {
                'symbol': symbol,
                'entry_price': entry_price,
                'position_size_dollars': position_size_dollars,
                'position_size_percent': position_pct_calc,
                'sector': sector,
                'risk_score': min(100, sum([
                    0 if position_limit_ok else 25,
                    0 if position_size_ok else 25,
                    0 if cash_ok else 25,
                    0 if sector_limit_ok else 15,
                    0 if drawdown_risk_ok else 10
                ])) / 100,
                'all_constraints_met': all_ok,
                'recommendation': 'APPROVED' if all_ok else 'REJECTED',
                'portfolio_impact': {
                    'new_total_positions': current_positions + 1,
                    'position_limit': max_positions,
                    'position_limit_ok': position_limit_ok,
                    'new_position_percent': position_pct_calc,
                    'max_position_percent': max_position_pct,
                    'position_size_ok': position_size_ok,
                    'new_sector_percent': new_sector_pct,
                    'max_sector_percent': max_sector_pct,
                    'sector_limit_ok': sector_limit_ok,
                    'worst_case_drawdown_impact': worst_case_impact,
                    'max_acceptable_impact': max_acceptable_impact,
                    'drawdown_risk_ok': drawdown_risk_ok,
                    'cash_available': cash_available,
                    'cash_required': position_size_dollars,
                    'cash_ok': cash_ok
                }
            })
        except Exception as e:
            logger.error(f"Error in pre-trade analysis: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to analyze trade impact')

    def _trigger_data_patrol(self) -> Dict:
        """Trigger async data patrol ECS task."""
        try:
            import boto3
            from botocore.exceptions import ClientError
            ecs = boto3.client('ecs')

            cluster_arn = os.getenv('ECS_CLUSTER_ARN', '')
            task_def_arn = os.getenv('PATROL_TASK_DEFINITION_ARN', '')
            container_name = os.getenv('PATROL_CONTAINER_NAME', 'algo-data-patrol')
            subnet_ids = os.getenv('PATROL_SUBNET_IDS', '').split(',') if os.getenv('PATROL_SUBNET_IDS') else []
            sg_id = os.getenv('PATROL_SECURITY_GROUP_ID', '')

            if not cluster_arn or not task_def_arn:
                logger.warning("Patrol task not configured (missing ECS_CLUSTER_ARN or PATROL_TASK_DEFINITION_ARN)")
                return error_response(503, 'service_unavailable', 'Patrol task not available')

            response = ecs.run_task(
                cluster=cluster_arn,
                taskDefinition=task_def_arn,
                launchType='FARGATE',
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': subnet_ids,
                        'securityGroups': [sg_id] if sg_id else [],
                        'assignPublicIp': 'DISABLED'
                    }
                } if subnet_ids and sg_id else None
            )

            if response['tasks']:
                task_arn = response['tasks'][0]['taskArn']
                logger.info(f"Triggered data patrol ECS task: {task_arn}")
                return json_response(202, {
                    'status': 'triggered',
                    'message': 'Data patrol triggered',
                    'task_arn': task_arn,
                    'task_id': task_arn.split('/')[-1]
                })
            else:
                logger.error(f"Failed to run patrol task: {response.get('failures', [])}")
                return error_response(500, 'internal_error', 'Failed to trigger patrol task')
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ClusterNotFoundException':
                logger.error(f"ECS cluster not found: {error_code}")
                return error_response(503, 'service_unavailable', 'Patrol service not configured')
            elif error_code == 'InvalidParameterException':
                logger.error(f"Invalid ECS parameters: {error_code}")
                return error_response(503, 'service_unavailable', 'Patrol service configuration invalid')
            else:
                logger.error(f"AWS error triggering patrol: {error_code}", exc_info=True)
                return error_response(503, 'service_unavailable', 'Unable to trigger patrol service')
        except Exception as e:
            logger.error(f"Error triggering data patrol: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to trigger data patrol')

    def _get_patrol_log(self, limit: int = 50, offset: int = 0) -> Dict:
        """Get data patrol findings with pagination."""
        try:
            # Get total count for pagination metadata
            self.cur.execute("SELECT COUNT(*) as total FROM data_patrol_log")
            total = self.cur.fetchone()['total']

            self.cur.execute("""
                SELECT created_at, check_name, severity, target_table, message, patrol_run_id
                FROM data_patrol_log
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            findings = self.cur.fetchall()
            return list_response([dict(f) for f in findings], total=total, limit=limit, offset=offset)
        except Exception as e:
            logger.error(f"Error fetching patrol log: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch patrol log')

    def _get_sector_rotation(self, days: int = 180) -> Dict:
        """Get sector rotation data."""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            self.cur.execute("""
                SELECT date, sector, strength AS performance_pct, signal, rank
                FROM sector_rotation_signal
                WHERE date >= %s
                ORDER BY date DESC, rank ASC
            """, (cutoff_date,))
            rotation = self.cur.fetchall()
            return list_response([dict(r) for r in rotation])
        except Exception as e:
            logger.error(f"Error fetching sector rotation: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch sector rotation')

    def _get_sector_breadth(self) -> Dict:
        """Get sector breadth indicators (derived from price_daily by sector)."""
        try:
            self.cur.execute("""
                SELECT
                    cp.sector,
                    COUNT(CASE WHEN pd.close > pd.open THEN 1 END) AS up_count,
                    COUNT(CASE WHEN pd.close < pd.open THEN 1 END) AS down_count,
                    COUNT(CASE WHEN pd.close = pd.open THEN 1 END) AS unchanged_count
                FROM price_daily pd
                JOIN company_profile cp ON pd.symbol = cp.ticker
                WHERE pd.date = (SELECT MAX(date) FROM price_daily)
                  AND cp.sector IS NOT NULL
                GROUP BY cp.sector
                ORDER BY up_count DESC
            """)
            breadth = self.cur.fetchall()
            return list_response([dict(b) for b in breadth])
        except Exception as e:
            logger.error(f"Error fetching sector breadth: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch sector breadth')

    def _get_swing_scores(self, limit: int = 100) -> Dict:
        """Get swing trade candidates with scoring."""
        try:
            self.cur.execute("""
                SELECT
                    s.symbol, s.date, s.score AS swing_score,
                    s.components->>'grade' AS grade,
                    cp.sector, cp.industry
                FROM swing_trader_scores s
                LEFT JOIN company_profile cp ON s.symbol = cp.ticker
                WHERE s.date >= CURRENT_DATE - INTERVAL '1 day'
                ORDER BY s.date DESC, s.score DESC
                LIMIT %s
            """, (limit,))
            scores = self.cur.fetchall()
            return list_response([dict(s) for s in scores])
        except Exception as e:
            logger.error(f"get_swing_scores failed: {e}")
            return error_response(500, 'internal_error', 'Failed to fetch swing scores')

    def _get_swing_scores_history(self, days: int = 30) -> Dict:
        """Get swing scores historical data."""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            self.cur.execute("""
                SELECT date AS eval_date,
                    COUNT(*) AS total_candidates,
                    AVG(score) AS avg_score
                FROM swing_trader_scores
                WHERE date >= %s
                GROUP BY date
                ORDER BY date DESC
            """, (cutoff_date,))
            history = self.cur.fetchall()
            return list_response([dict(h) for h in history])
        except Exception as e:
            logger.error(f"get_swing_scores_history failed: {e}")
            return error_response(500, 'internal_error', 'Failed to fetch swing scores history')

    def _get_rejection_funnel(self) -> Dict:
        """Get signal rejection funnel."""
        try:
            self.cur.execute("""
                SELECT
                    'Initial Signals' AS stage,
                    COUNT(DISTINCT symbol) AS count
                FROM buy_sell_daily
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                UNION ALL
                SELECT
                    'Scored Candidates' AS stage,
                    COUNT(DISTINCT symbol) AS count
                FROM swing_trader_scores
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY count DESC
            """)
            funnel = self.cur.fetchall()
            return list_response([dict(f) for f in funnel])
        except Exception as e:
            logger.error(f"Error fetching rejection funnel: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch rejection funnel')

    def _get_markets(self) -> Dict:
        """Get current market regime data."""
        try:
            self.cur.execute("""
                SELECT
                    symbol, date, close, volume
                FROM price_daily
                WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                AND symbol IN ('SPY', 'QQQ', 'IWM', 'VIX')
                ORDER BY symbol, date DESC
                LIMIT 120
            """)
            markets = self.cur.fetchall()
            return list_response([dict(m) for m in markets])
        except Exception as e:
            logger.error(f"Error fetching markets data: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch markets data')

    def _get_algo_evaluate(self) -> Dict:
        """Get latest signal evaluation summary from swing_trader_scores."""
        try:
            self.cur.execute("""
                SELECT
                    COUNT(DISTINCT symbol) AS candidates_screened,
                    COUNT(DISTINCT CASE WHEN score >= 60 THEN symbol END) AS candidates_passing,
                    MAX(score) AS top_score,
                    AVG(score) AS avg_score
                FROM swing_trader_scores
                WHERE date >= CURRENT_DATE - INTERVAL '1 day'
            """)
            row = self.cur.fetchone()
            if not row or not row['candidates_screened']:
                return json_response(200, {'stage': 'no_data', 'candidates_screened': 0, 'candidates_passing': 0})
            return json_response(200, {
                'stage': 'evaluated',
                'candidates_screened': row['candidates_screened'] or 0,
                'candidates_passing': row['candidates_passing'] or 0,
                'top_score': float(row['top_score'] or 0),
                'avg_score': float(row['avg_score'] or 0),
            })
        except Exception as e:
            logger.error(f"get_algo_evaluate failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to evaluate algorithm')

    def _get_data_quality(self) -> Dict:
        """Get data quality summary from latest data_patrol_log run."""
        try:
            self.cur.execute("""
                SELECT
                    MAX(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) AS has_critical,
                    COUNT(CASE WHEN severity = 'error' THEN 1 END) AS error_count,
                    COUNT(CASE WHEN severity = 'warn' THEN 1 END) AS warn_count,
                    MAX(created_at) AS last_check
                FROM data_patrol_log
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            """)
            row = self.cur.fetchone()
            if not row or not row['last_check']:
                return json_response(200, {'accuracy_check': 'no_data', 'last_check': None})
            has_critical = row['has_critical'] or 0
            error_count = row['error_count'] or 0
            warn_count = row['warn_count'] or 0
            accuracy = 'failed' if has_critical else ('warning' if error_count > 0 else 'passed')
            return json_response(200, {
                'accuracy_check': accuracy,
                'critical_count': has_critical,
                'error_count': error_count,
                'warn_count': warn_count,
                'last_check': row['last_check'].isoformat() if row['last_check'] else None,
            })
        except Exception as e:
            logger.error(f"get_data_quality failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to check data quality')

    def _get_exposure_policy(self) -> Dict:
        """Get latest market exposure from market_exposure_daily."""
        try:
            self.cur.execute("""
                SELECT date, exposure_pct, raw_score, regime, distribution_days, factors, halt_reasons
                FROM market_exposure_daily
                ORDER BY date DESC
                LIMIT 1
            """)
            row = self.cur.fetchone()
            if not row:
                return json_response(200, {'current_exposure': None, 'regime': None})
            return json_response(200, {
                'current_exposure': float(row['exposure_pct'] or 0),
                'raw_score': float(row['raw_score'] or 0),
                'regime': row.get('regime', 'unknown'),
                'distribution_days': int(row.get('distribution_days', 0)),
                'factors': row.get('factors'),
                'halt_reasons': row.get('halt_reasons'),
                'as_of': row['date'].isoformat() if row['date'] else None,
            })
        except Exception as e:
            logger.error(f"get_exposure_policy failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch exposure policy')

    def _get_sector_stage2(self) -> Dict:
        """Get Stage 2 stocks by sector from trend_template_data."""
        try:
            self.cur.execute("""
                SELECT t.symbol, t.minervini_trend_score AS strength, cp.sector
                FROM trend_template_data t
                LEFT JOIN company_profile cp ON t.symbol = cp.ticker
                WHERE t.date = (SELECT MAX(date) FROM trend_template_data)
                  AND t.weinstein_stage = 2
                ORDER BY t.minervini_trend_score DESC
                LIMIT 50
            """)
            rows = self.cur.fetchall()
            return list_response([dict(r) for r in rows])
        except Exception as e:
            logger.error(f"get_sector_stage2 failed: {e}")
            return error_response(500, 'internal_error', 'Failed to fetch sector stage 2')

    def _get_algo_config(self) -> Dict:
        """Return all algo configuration rows."""
        try:
            self.cur.execute("SELECT key, value, value_type, description, updated_at FROM algo_config ORDER BY key")
            rows = self.cur.fetchall()
            return list_response([dict(r) for r in rows])
        except Exception as e:
            logger.error(f"algo_config error: {e}")
            return error_response(500, 'internal_error', 'Failed to fetch algo config')

    def _get_algo_config_key(self, key: str) -> Dict:
        """Return a single algo config key."""
        try:
            self.cur.execute("SELECT key, value, value_type, description, updated_at FROM algo_config WHERE key = %s", (key,))
            row = self.cur.fetchone()
            return json_response(200, dict(row) if row else {})
        except Exception as e:
            logger.error(f"algo_config_key error: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch config key')

    def _get_algo_audit_log(self, limit: int = 100, offset: int = 0, action_type: str = None) -> Dict:
        """Return algo audit log entries with pagination."""
        try:
            # Get total count
            if action_type:
                self.cur.execute("SELECT COUNT(*) as total FROM algo_audit_log WHERE action_type = %s", (action_type,))
            else:
                self.cur.execute("SELECT COUNT(*) as total FROM algo_audit_log")
            total = self.cur.fetchone()['total']

            # Get paginated results
            if action_type:
                self.cur.execute("""
                    SELECT id, action_type, symbol, action_date, details, actor, status, error_message
                    FROM algo_audit_log
                    WHERE action_type = %s
                    ORDER BY action_date DESC
                    LIMIT %s OFFSET %s
                """, (action_type, limit, offset))
            else:
                self.cur.execute("""
                    SELECT id, action_type, symbol, action_date, details, actor, status, error_message
                    FROM algo_audit_log
                    ORDER BY action_date DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
            rows = self.cur.fetchall()
            return json_response(200, {'data': [dict(r) for r in rows], 'total': total, 'limit': limit, 'offset': offset})
        except Exception as e:
            logger.error(f"algo_audit_log error: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch audit log')

    def _handle_financials(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/financials/{symbol}/* endpoints."""
        try:
            parts = path.split('/')
            if len(parts) < 4:
                return error_response(400, 'bad_request', 'Path must include symbol: /api/financials/{symbol}/{endpoint}')
            symbol = parts[3].upper()
            endpoint = parts[4] if len(parts) > 4 else None
            if not endpoint:
                return error_response(400, 'bad_request', 'Path must include endpoint (income-statement, balance-sheet, cash-flow, key-metrics)')
            period = params.get('period', ['annual'])[0] if params else 'annual'

            if endpoint == 'income-statement':
                if period == 'quarterly':
                    self.cur.execute("""
                        SELECT fiscal_year, fiscal_quarter, revenue, net_income, earnings_per_share
                        FROM quarterly_income_statement WHERE symbol = %s
                        ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT 12
                    """, (symbol,))
                else:
                    self.cur.execute("""
                        SELECT fiscal_year, revenue, cost_of_revenue, gross_profit,
                               operating_income, net_income, earnings_per_share
                        FROM annual_income_statement WHERE symbol = %s
                        ORDER BY fiscal_year DESC LIMIT 5
                    """, (symbol,))
                rows = self.cur.fetchall()
                return list_response([dict(r) for r in rows])

            elif endpoint == 'balance-sheet':
                if period == 'quarterly':
                    self.cur.execute("""
                        SELECT fiscal_year, fiscal_quarter, total_assets,
                               total_liabilities, stockholders_equity
                        FROM quarterly_balance_sheet WHERE symbol = %s
                        ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT 12
                    """, (symbol,))
                else:
                    self.cur.execute("""
                        SELECT fiscal_year, total_assets, current_assets,
                               total_liabilities, stockholders_equity
                        FROM annual_balance_sheet WHERE symbol = %s
                        ORDER BY fiscal_year DESC LIMIT 5
                    """, (symbol,))
                rows = self.cur.fetchall()
                return list_response([dict(r) for r in rows])

            elif endpoint == 'cash-flow':
                if period == 'quarterly':
                    self.cur.execute("""
                        SELECT fiscal_year, fiscal_quarter, operating_cash_flow, free_cash_flow
                        FROM quarterly_cash_flow WHERE symbol = %s
                        ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT 12
                    """, (symbol,))
                else:
                    self.cur.execute("""
                        SELECT fiscal_year, operating_cash_flow, investing_cash_flow,
                               financing_cash_flow, free_cash_flow
                        FROM annual_cash_flow WHERE symbol = %s
                        ORDER BY fiscal_year DESC LIMIT 5
                    """, (symbol,))
                rows = self.cur.fetchall()
                return list_response([dict(r) for r in rows])

            elif endpoint == 'key-metrics':
                self.cur.execute("""
                    SELECT km.market_cap, km.held_percent_insiders, km.held_percent_institutions,
                           cp.sector, cp.industry
                    FROM key_metrics km
                    LEFT JOIN company_profile cp ON cp.ticker = km.ticker
                    WHERE km.ticker = %s
                """, (symbol,))
                row = self.cur.fetchone()
                if not row:
                    return json_response(200, {})
                return json_response(200, dict(row))

            return error_response(400, 'bad_request', f'Unknown financial endpoint: {endpoint}. Valid: income-statement, balance-sheet, cash-flow, key-metrics')
        except psycopg2.errors.UndefinedTable as e:
            logger.warning(f"financials: table not found - {str(e)[:100]}")
            return error_response(503, 'service_unavailable', 'Financial data not yet loaded. Check data pipeline status.')
        except psycopg2.errors.UndefinedColumn as e:
            logger.warning(f"financials: column not found - {str(e)[:100]}")
            return error_response(503, 'service_unavailable', 'Financial data schema outdated. Contact administrator.')
        except psycopg2.DatabaseError as e:
            logger.error(f"financials handler database error: {e}", exc_info=True)
            return error_response(503, 'service_unavailable', 'Temporary database issue. Please retry.')
        except Exception as e:
            logger.error(f"financials handler error: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Financials handler error')

    def _handle_earnings(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/earnings/* endpoints. Returns upcoming/past earnings dates."""
        try:
            period = params.get('period', ['upcoming'])[0] if params else 'upcoming'
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=100, default=25)
            symbol = params.get('symbol', [None])[0] if params else None

            if period == 'upcoming':
                sql = """
                    SELECT symbol, quarter, earnings_date, eps_estimate, eps_actual, eps_surprise_pct
                    FROM earnings_history
                    WHERE earnings_date >= CURRENT_DATE
                    ORDER BY earnings_date ASC
                    LIMIT %s
                """
                params_tuple = (limit,)
            elif period == 'past':
                sql = """
                    SELECT symbol, quarter, earnings_date, eps_estimate, eps_actual, eps_surprise_pct
                    FROM earnings_history
                    WHERE earnings_date < CURRENT_DATE
                    ORDER BY earnings_date DESC
                    LIMIT %s
                """
                params_tuple = (limit,)
            else:
                return error_response(400, 'bad_request', f'Period must be "upcoming" or "past", got "{period}"')

            if symbol:
                sql = sql.replace('WHERE earnings_date', 'WHERE symbol = %s AND earnings_date')
                params_tuple = (symbol,) + params_tuple

            self.cur.execute(sql, params_tuple)
            rows = self.cur.fetchall()
            return list_response([dict(r) for r in rows], total=len(rows))
        except Exception as e:
            logger.error(f"earnings handler error: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Earnings handler error')

    def _handle_signals(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/signals/* endpoints."""
        if path == '/api/signals/stocks':
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=500, default=200)
            timeframe = params.get('timeframe', ['daily'])[0] if params else 'daily'
            return self._get_signals_stocks(limit, timeframe)
        elif path == '/api/signals/etf':
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=500, default=200)
            return self._get_signals_etf(limit)
        else:
            return error_response(404, 'not_found', f'No signals handler for {path}')

    def _get_signals_stocks(self, limit: int = 500, timeframe: str = 'daily') -> Dict:
        """Get stock trading signals with technical enrichment from normalized tables."""
        try:
            self.cur.execute("""
                SELECT
                    bsd.id, bsd.symbol, bsd.signal, bsd.date,
                    bsd.strength, bsd.reason,
                    COALESCE(td.close, 0) as close,
                    COALESCE(td.rsi, 0) as rsi,
                    COALESCE(td.adx, 0) as adx,
                    COALESCE(td.atr, 0) as atr,
                    COALESCE(td.sma_50, 0) as sma_50,
                    COALESCE(td.sma_200, 0) as sma_200,
                    COALESCE(td.ema_12, 0) as ema_12,
                    COALESCE(td.ema_26, 0) as ema_26,
                    COALESCE(tt.weinstein_stage, 'unknown') as market_stage,
                    COALESCE(tt.trend_direction, 'unknown') as trend,
                    ss.security_name, cp.sector, cp.industry,
                    COALESCE(swg.score, 0) AS swing_score,
                    swg.components->>'grade' AS grade
                FROM buy_sell_daily bsd
                LEFT JOIN technical_data_daily td ON bsd.symbol = td.symbol
                    AND bsd.date = td.date
                LEFT JOIN trend_template_data tt ON bsd.symbol = tt.symbol
                    AND bsd.date = tt.date
                LEFT JOIN stock_symbols ss ON bsd.symbol = ss.symbol
                LEFT JOIN company_profile cp ON bsd.symbol = cp.ticker
                LEFT JOIN swing_trader_scores swg ON bsd.symbol = swg.symbol
                    AND swg.date >= CURRENT_DATE - INTERVAL '1 day'
                WHERE bsd.date >= CURRENT_DATE - INTERVAL '90 days'
                  AND bsd.signal IN ('BUY', 'SELL')
                ORDER BY bsd.date DESC, bsd.symbol ASC
                LIMIT %s
            """, (limit,))
            signals = self.cur.fetchall()
            return list_response([dict(s) for s in signals])
        except Exception as e:
            logger.error(f"get_signals_stocks failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch signals')

    def _get_signals_etf(self, limit: int = 500) -> Dict:
        """Get ETF trading signals."""
        try:
            self.cur.execute("""
                SELECT
                    bsd.id, bsd.symbol, bsd.signal, bsd.date,
                    bsd.strength, bsd.reason,
                    COALESCE(td.close, 0) as close,
                    COALESCE(td.rsi, 0) as rsi,
                    COALESCE(td.sma_50, 0) as sma_50,
                    COALESCE(td.sma_200, 0) as sma_200,
                    COALESCE(tt.weinstein_stage, 'unknown') as market_stage,
                    COALESCE(cp.short_name, cp.long_name, bsd.symbol) as company_name
                FROM buy_sell_daily_etf bsd
                LEFT JOIN technical_data_daily td ON bsd.symbol = td.symbol
                    AND bsd.date = td.date
                LEFT JOIN trend_template_data tt ON bsd.symbol = tt.symbol
                    AND bsd.date = tt.date
                LEFT JOIN company_profile cp ON bsd.symbol = cp.ticker
                WHERE bsd.date >= CURRENT_DATE - INTERVAL '90 days'
                AND bsd.symbol IN ('SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EFA')
                ORDER BY bsd.date DESC
                LIMIT %s
            """, (limit,))
            signals = self.cur.fetchall()
            return list_response([dict(s) for s in signals])
        except Exception as e:
            logger.error(f"get_signals_etf failed: {e}")
            return error_response(500, 'internal_error', 'Failed to fetch ETF signals')

    def _handle_prices(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/prices/* endpoints."""
        match = re.match(r'/api/prices/history/([A-Z0-9.]+)', path)
        if match:
            symbol = match.group(1)
            timeframe = params.get('timeframe', ['daily'])[0] if params else 'daily'
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=500, default=60)
            return self._get_price_history(symbol, timeframe, limit)
        else:
            return error_response(404, 'not_found', f'Invalid prices endpoint: {path}')

    def _get_price_history(self, symbol: str, timeframe: str = 'daily', limit: int = 60) -> Dict:
        """Get price history for a symbol."""
        if not _validate_symbol(symbol):
            return error_response(400, 'bad_request', 'Symbol format invalid (1-20 chars, letters/numbers/dash/dot)')
        try:
            self.cur.execute("""
                SELECT date, open, high, low, close, volume
                FROM price_daily
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT %s
            """, (symbol.upper(), limit))
            prices = self.cur.fetchall()
            return list_response([dict(p) for p in reversed(prices)])
        except Exception as e:
            logger.error(f"get_price_history failed: {e}")
            return error_response(500, 'internal_error', 'Failed to fetch price history')

    def _handle_stocks(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/stocks and /api/stocks/* endpoints."""
        if path == '/api/stocks/deep-value':
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=500, default=100)
            return self._get_deep_value_stocks(limit)
        elif path == '/api/stocks' or path == '/api/stocks/list':
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=500, default=100)
            symbol_filter = params.get('symbol', [None])[0] if params else None
            industry_filter = params.get('industry', [None])[0] if params else None
            try:
                query = """
                    SELECT ss.symbol, ss.security_name as company_name,
                           cp.sector, cp.industry, ss.is_sp500
                    FROM stock_symbols ss
                    LEFT JOIN company_profile cp ON cp.ticker = ss.symbol
                    WHERE 1=1
                """
                args = []
                if symbol_filter:
                    query += " AND ss.symbol ILIKE %s"
                    args.append(f'%{symbol_filter}%')
                if industry_filter:
                    query += " AND cp.industry = %s"
                    args.append(industry_filter)
                query += " ORDER BY ss.symbol LIMIT %s"
                args.append(limit)
                self.cur.execute(query, args)
                stocks = self.cur.fetchall()
                return list_response([dict(s) for s in stocks])
            except Exception as e:
                logger.error(f"stocks list error: {e}")
                return error_response(500, 'internal_error', 'Failed to fetch stocks')
        elif path.startswith('/api/stocks/'):
            symbol = path.split('/api/stocks/')[-1]
            if not _validate_symbol(symbol):
                return error_response(400, 'bad_request', 'Symbol format invalid (1-20 chars, letters/numbers/dash/dot)')
            try:
                self.cur.execute("""
                    SELECT ss.symbol, ss.security_name as company_name,
                           cp.sector, cp.industry, cp.website, cp.employees,
                           km.market_cap
                    FROM stock_symbols ss
                    LEFT JOIN company_profile cp ON cp.ticker = ss.symbol
                    LEFT JOIN key_metrics km ON km.ticker = ss.symbol
                    WHERE ss.symbol = %s
                """, (symbol.upper(),))
                row = self.cur.fetchone()
                return json_response(200, dict(row) if row else {})
            except Exception as e:
                logger.error(f"stock detail error: {e}")
                return error_response(500, 'internal_error', 'Failed to fetch stock details')
        else:
            return error_response(404, 'not_found', f'No stocks handler for {path}')

    def _get_deep_value_stocks(self, limit: int = 600) -> Dict:
        """Get deep value stock screener data from normalized metric tables."""
        try:
            self.cur.execute("""
                SELECT
                    sc.symbol,
                    ss.security_name AS company_name,
                    cp.sector, cp.industry,
                    pd_latest.close AS current_price,
                    vm.pe_ratio AS trailing_pe,
                    vm.pb_ratio AS price_to_book,
                    vm.ps_ratio AS price_to_sales,
                    vm.peg_ratio,
                    vm.dividend_yield,
                    vm.fcf_yield,
                    qm.roe AS roe_pct,
                    qm.net_margin AS net_margin_pct,
                    qm.roa AS roa_pct,
                    qm.debt_to_equity,
                    qm.current_ratio,
                    gm.revenue_growth_1y AS revenue_growth_yoy_pct,
                    gm.eps_growth_1y AS eps_growth_yoy_pct,
                    gm.revenue_growth_3y AS revenue_growth_3y_pct,
                    gm.eps_growth_3y AS eps_growth_3y_pct,
                    sc.composite_score,
                    sc.value_score,
                    sc.value_score AS generational_score
                FROM stock_scores sc
                JOIN stock_symbols ss ON ss.symbol = sc.symbol
                LEFT JOIN company_profile cp ON cp.ticker = sc.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
                LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
                LEFT JOIN (
                    SELECT DISTINCT ON (symbol) symbol, close
                    FROM price_daily
                    ORDER BY symbol, date DESC
                ) pd_latest ON pd_latest.symbol = sc.symbol
                WHERE sc.value_score > 0
                ORDER BY sc.value_score DESC
                LIMIT %s
            """, (limit,))
            stocks = self.cur.fetchall()
            return list_response([dict(s) for s in stocks])
        except Exception as e:
            logger.error(f"get_deep_value_stocks failed: {e}")
            return error_response(500, 'internal_error', 'Failed to fetch value stocks')

    def _handle_portfolio(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/portfolio/* endpoints."""
        try:
            if path == '/api/portfolio/summary':
                self.cur.execute("""
                    SELECT
                        COALESCE(SUM(position_value), 0) as total_invested,
                        COUNT(*) as position_count
                    FROM algo_positions WHERE status='open'
                """)
                row = self.cur.fetchone()
                total_invested = float(row['total_invested'] or 0) if row else 0
                position_count = int(row['position_count'] or 0) if row else 0
                # Get latest account value from snapshots for real exposure calc
                self.cur.execute("""
                    SELECT total_portfolio_value FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date DESC LIMIT 1
                """)
                snap = self.cur.fetchone()
                portfolio_value = float(snap['total_portfolio_value'] or 0) if snap else 0
                exposure = round(total_invested / portfolio_value, 4) if portfolio_value > 0 else 0.0
                return json_response(200, {
                    'total_value': total_invested,
                    'portfolio_value': portfolio_value,
                    'position_count': position_count,
                    'cash': max(0, portfolio_value - total_invested),
                    'exposure': exposure,
                })
            elif path == '/api/portfolio/allocation':
                self.cur.execute("""
                    SELECT
                        COALESCE(cp.sector, 'Unknown') as sector,
                        COUNT(*) as count,
                        SUM(ap.position_value) as value
                    FROM algo_positions ap
                    LEFT JOIN company_profile cp ON ap.symbol = cp.ticker
                    WHERE ap.status = 'open'
                    GROUP BY COALESCE(cp.sector, 'Unknown')
                    ORDER BY value DESC
                """)
                alloc = self.cur.fetchall()
                return list_response([dict(a) for a in alloc])
            return error_response(404, 'not_found', f'Unknown portfolio endpoint: {path}')
        except Exception as e:
            logger.error(f"Error in portfolio allocation handler: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch portfolio allocation')

    def _handle_sectors(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/sectors and /api/sectors/* endpoints - return full ranking data."""
        try:
            # Handle /api/sectors/trends-batch?sectors=X,Y,Z&days=90
            if path == '/api/sectors/trends-batch' or path.startswith('/api/sectors/trends-batch?'):
                sectors_str = params.get('sectors', [None])[0] if params else None
                days_str = params.get('days', [None])[0] if params else None
                days = _safe_days(days_str, max_val=365, default=90)

                if not sectors_str:
                    return error_response(400, 'bad_request', 'sectors parameter required (comma-separated)')

                sectors = [s.strip() for s in sectors_str.split(',')]
                result = {}

                for sector in sectors:
                    if not sector:
                        continue
                    self.cur.execute("""
                        SELECT date, AVG(close) AS avgPrice
                        FROM price_daily pd
                        JOIN company_profile cp ON pd.symbol = cp.symbol
                        WHERE cp.sector = %s AND pd.date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                        GROUP BY pd.date
                        ORDER BY pd.date ASC
                    """, (sector, days))
                    rows = self.cur.fetchall()
                    result[sector] = [dict(r) for r in rows] if rows else []

                return json_response(200, {'data': result})

            # Extract sector name if provided: /api/sectors/Technology
            parts = path.split('/')
            sector_name = parts[3] if len(parts) > 3 else None

            if sector_name and sector_name not in ('performance', 'trends-batch'):
                # Return data for specific sector
                days_str = params.get('days', [None])[0] if params else None
                days = _safe_days(days_str, max_val=365, default=90)
                self.cur.execute("""
                    SELECT date, sector, return_pct
                    FROM sector_performance
                    WHERE sector = %s AND date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                    ORDER BY date DESC
                """, (sector_name, days))
                rows = self.cur.fetchall()
                return list_response([dict(r) for r in rows])
            elif path in ('/api/sectors', '/api/sectors/performance'):
                limit_str = params.get('limit', [None])[0] if params else None
                limit = _safe_limit(limit_str, max_val=100, default=20)
                page_str = params.get('page', [None])[0] if params else None
                page = _safe_page(page_str, default=1)
                offset = (page - 1) * limit

                self.cur.execute("""
                    WITH sector_perf AS (
                        SELECT sector,
                               ROUND(SUM(CASE WHEN return_pct > 0 THEN return_pct ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as perf_20d
                        FROM sector_performance
                        WHERE date >= CURRENT_DATE - INTERVAL '20 days'
                        GROUP BY sector
                    ),
                    sector_scores AS (
                        SELECT
                            cp.sector as sector_name,
                            COUNT(DISTINCT cp.symbol) as stock_count,
                            AVG(ss.composite_score) as composite_score,
                            AVG(ss.momentum_score) as momentum_score,
                            AVG(ss.value_score) as value_score,
                            AVG(ss.quality_score) as quality_score,
                            AVG(ss.growth_score) as growth_score,
                            AVG(ss.stability_score) as stability_score,
                            COALESCE(sp.perf_20d, 0) as perf_20d
                        FROM company_profile cp
                        LEFT JOIN stock_scores ss ON cp.symbol = ss.symbol
                        LEFT JOIN sector_perf sp ON sp.sector = cp.sector
                        WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) != ''
                        GROUP BY cp.sector, sp.perf_20d
                    ),
                    ranked AS (
                        SELECT *,
                            RANK() OVER (ORDER BY composite_score DESC NULLS LAST) as current_rank
                        FROM sector_scores
                    ),
                    sector_pe AS (
                        SELECT
                            cp.sector,
                            AVG(vm.pe_ratio) FILTER (WHERE vm.pe_ratio > 0 AND vm.pe_ratio < 200) AS avg_trailing_pe,
                            0::float AS avg_forward_pe
                        FROM value_metrics vm
                        JOIN company_profile cp ON vm.symbol = cp.ticker
                        WHERE cp.sector IS NOT NULL
                        GROUP BY cp.sector
                    ),
                    sector_pe_ranked AS (
                        SELECT *,
                            PERCENT_RANK() OVER (ORDER BY avg_trailing_pe ASC NULLS LAST) * 100 AS pe_percentile
                        FROM sector_pe
                    )
                    SELECT r.*, spe.avg_trailing_pe, spe.avg_forward_pe, spe.pe_percentile
                    FROM ranked r
                    LEFT JOIN sector_pe_ranked spe ON spe.sector = r.sector_name
                    ORDER BY r.current_rank, r.stock_count DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))

                sectors_data = self.cur.fetchall()
                self.cur.execute("""SELECT COUNT(DISTINCT sector) FROM company_profile WHERE sector IS NOT NULL""")
                total = self.cur.fetchone()[0]

                sectors = []
                for row in sectors_data:
                    s = dict(row)
                    composite = float(s.get('composite_score') or 0)
                    perf20d = float(s.get('perf_20d') or 0)
                    momentum_label = 'Strong' if composite >= 60 else 'Moderate' if composite >= 45 else 'Weak'
                    trend_label = 'Uptrend' if perf20d > 2 else 'Downtrend' if perf20d < -2 else 'Sideways'

                    sectors.append({
                        'sector_name': s.get('sector_name'),
                        'current_rank': int(s.get('current_rank') or 0),
                        'stock_count': int(s.get('stock_count') or 0),
                        'composite_score': float(s.get('composite_score') or 0),
                        'momentum_score': float(s.get('momentum_score') or 0),
                        'value_score': float(s.get('value_score') or 0),
                        'quality_score': float(s.get('quality_score') or 0),
                        'growth_score': float(s.get('growth_score') or 0),
                        'stability_score': float(s.get('stability_score') or 0),
                        'current_momentum': momentum_label,
                        'current_trend': trend_label,
                        'pe': {
                            'trailing': float(s.get('avg_trailing_pe') or 0),
                            'forward': float(s.get('avg_forward_pe') or 0),
                            'percentile': float(s.get('pe_percentile') or 0)
                        }
                    })

                return json_response(200, {
                    'data': sectors,
                    'total': total,
                    'page': page,
                    'limit': limit,
                })
            elif '/trend' in path:
                parts = path.split('/')
                sector_name = parts[3] if len(parts) > 3 else None
                days_str = params.get('days', [None])[0] if params else None
                days = _safe_days(days_str, max_val=365, default=90)
                if not sector_name:
                    return error_response(400, 'bad_request', 'Sector name required')
                self.cur.execute("""
                    SELECT date, sector, return_pct, relative_strength
                    FROM sector_performance
                    WHERE sector = %s AND date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                    ORDER BY date DESC
                """, (sector_name, days))
                rows = self.cur.fetchall()
                return list_response([dict(r) for r in rows])
            return json_response(200, {'data': [], 'total': 0, 'page': 1, 'limit': 20})
        except Exception as e:
            logger.error(f"Error in sectors handler: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch sectors')

    def _handle_industries(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/industries and /api/industries/{name} - return ranking data."""
        try:
            # Extract industry name if provided: /api/industries/Software
            parts = path.split('/')
            industry_name = parts[3] if len(parts) > 3 else None

            if industry_name and industry_name != 'trend':
                # Return data for specific industry
                days_str = params.get('days', [None])[0] if params else None
                days = _safe_days(days_str, max_val=365, default=90)
                self.cur.execute("""
                    SELECT date, industry, return_pct
                    FROM industry_performance
                    WHERE industry = %s AND date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                    ORDER BY date DESC
                """, (industry_name, days))
                rows = self.cur.fetchall()
                return list_response([dict(r) for r in rows])
            else:
                limit_str = params.get('limit', [None])[0] if params else None
                limit = _safe_limit(limit_str, max_val=500, default=100)
                page_str = params.get('page', [None])[0] if params else None
                page = _safe_page(page_str, default=1)
                offset = (page - 1) * limit

                self.cur.execute("""
                    WITH industry_perf AS (
                        SELECT industry,
                               ROUND(SUM(CASE WHEN return_pct > 0 THEN return_pct ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as perf_20d
                        FROM industry_performance
                        WHERE date >= CURRENT_DATE - INTERVAL '20 days'
                        GROUP BY industry
                    ),
                    industry_scores AS (
                        SELECT
                            cp.industry,
                            cp.sector,
                            COUNT(DISTINCT cp.symbol) as stock_count,
                            AVG(ss.composite_score) as composite_score,
                            AVG(ss.momentum_score) as momentum_score,
                            AVG(ss.value_score) as value_score,
                            AVG(ss.quality_score) as quality_score,
                            AVG(ss.growth_score) as growth_score,
                            AVG(ss.stability_score) as stability_score,
                            COALESCE(ip.perf_20d, 0) as perf_20d
                        FROM company_profile cp
                        LEFT JOIN stock_scores ss ON cp.symbol = ss.symbol
                        LEFT JOIN industry_perf ip ON ip.industry = cp.industry
                        WHERE cp.industry IS NOT NULL AND TRIM(cp.industry) != ''
                        GROUP BY cp.industry, cp.sector, ip.perf_20d
                    ),
                    ranked AS (
                        SELECT *,
                            RANK() OVER (ORDER BY composite_score DESC NULLS LAST) as current_rank
                        FROM industry_scores
                    ),
                    industry_pe AS (
                        SELECT
                            cp.industry,
                            AVG(vm.pe_ratio) FILTER (WHERE vm.pe_ratio > 0 AND vm.pe_ratio < 200) AS avg_trailing_pe,
                            0::float AS avg_forward_pe
                        FROM value_metrics vm
                        JOIN company_profile cp ON vm.symbol = cp.ticker
                        WHERE cp.industry IS NOT NULL
                        GROUP BY cp.industry
                    ),
                    industry_pe_ranked AS (
                        SELECT *,
                            PERCENT_RANK() OVER (ORDER BY avg_trailing_pe ASC NULLS LAST) * 100 AS pe_percentile
                        FROM industry_pe
                    )
                    SELECT r.*, ipe.avg_trailing_pe, ipe.avg_forward_pe, ipe.pe_percentile
                    FROM ranked r
                    LEFT JOIN industry_pe_ranked ipe ON ipe.industry = r.industry
                    ORDER BY r.current_rank, r.stock_count DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))

                industries_data = self.cur.fetchall()
                self.cur.execute("""SELECT COUNT(DISTINCT industry) FROM company_profile WHERE industry IS NOT NULL""")
                total = self.cur.fetchone()[0]

                industries = []
                for row in industries_data:
                    ind = dict(row)
                    composite = float(ind.get('composite_score') or 0)
                    perf20d = float(ind.get('perf_20d') or 0)
                    momentum_label = 'Strong' if composite >= 60 else 'Moderate' if composite >= 45 else 'Weak'
                    trend_label = 'Uptrend' if perf20d > 2 else 'Downtrend' if perf20d < -2 else 'Sideways'

                    industries.append({
                        'industry': ind.get('industry'),
                        'sector': ind.get('sector'),
                        'current_rank': int(ind.get('current_rank') or 0),
                        'stock_count': int(ind.get('stock_count') or 0),
                        'composite_score': float(ind.get('composite_score') or 0),
                        'momentum_score': float(ind.get('momentum_score') or 0),
                        'value_score': float(ind.get('value_score') or 0),
                        'quality_score': float(ind.get('quality_score') or 0),
                        'growth_score': float(ind.get('growth_score') or 0),
                        'stability_score': float(ind.get('stability_score') or 0),
                        'current_momentum': momentum_label,
                        'current_trend': trend_label,
                        'pe': {
                            'trailing': float(ind.get('avg_trailing_pe') or 0),
                            'forward': float(ind.get('avg_forward_pe') or 0),
                            'percentile': float(ind.get('pe_percentile') or 0)
                        }
                    })

                return json_response(200, {
                    'data': industries,
                    'total': total,
                    'page': page,
                    'limit': limit,
                })
        except Exception as e:
            logger.error(f"Error in industries handler: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch industries')

    def _handle_market(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/market/* endpoints."""
        try:
            if path == '/api/market/indices':
                return self._get_markets()
            elif path == '/api/market/breadth':
                self.cur.execute("""
                    SELECT date,
                        COUNT(*) as total,
                        SUM(CASE WHEN close > open THEN 1 ELSE 0 END) as advances
                    FROM price_daily
                    WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                    GROUP BY date
                    ORDER BY date DESC
                """)
                breadth = self.cur.fetchall()
                return list_response([dict(b) for b in breadth])
            elif path == '/api/market/technicals':
                self.cur.execute("""
                    SELECT date, advance_decline_ratio, new_highs_count, new_lows_count,
                           up_volume_percent, distribution_days_4w, breadth_momentum_10d,
                           vix_level, put_call_ratio, market_trend, market_stage
                    FROM market_health_daily
                    ORDER BY date DESC
                    LIMIT 1
                """)
                row = self.cur.fetchone()
                return json_response(200, dict(row) if row else {})
            elif path == '/api/market/top-movers':
                self.cur.execute("""
                    WITH today AS (
                        SELECT symbol, close
                        FROM price_daily
                        WHERE date = (SELECT MAX(date) FROM price_daily)
                    ),
                    yesterday AS (
                        SELECT symbol, close
                        FROM price_daily
                        WHERE date = (
                            SELECT MAX(date) FROM price_daily
                            WHERE date < (SELECT MAX(date) FROM price_daily)
                        )
                    )
                    SELECT t.symbol, ss.security_name,
                           ROUND(((t.close - y.close) / NULLIF(y.close, 0) * 100)::numeric, 2) as pct_change
                    FROM today t
                    JOIN yesterday y ON t.symbol = y.symbol
                    LEFT JOIN stock_symbols ss ON t.symbol = ss.symbol
                    WHERE y.close > 0
                    ORDER BY ABS(t.close - y.close) / y.close DESC
                    LIMIT 20
                """)
                movers = self.cur.fetchall()
                return list_response([dict(m) for m in movers] if movers else [])
            elif path == '/api/market/distribution-days':
                self.cur.execute("""
                    SELECT symbol, date, distribution_count
                    FROM distribution_days
                    ORDER BY date DESC
                    LIMIT 50
                """)
                dist = self.cur.fetchall()
                return list_response([dict(d) for d in dist] if dist else [])
            elif path == '/api/market/seasonality':
                # Seasonality tables are market-wide aggregates (SPY-based), no per-symbol filtering
                self.cur.execute("""
                    SELECT month, month_name, avg_return, best_return, worst_return,
                           winning_years, losing_years, years_counted
                    FROM seasonality_monthly_stats
                    ORDER BY month
                """)
                monthly = self.cur.fetchall()
                self.cur.execute("""
                    SELECT day, day_num, avg_return, win_rate, days_counted
                    FROM seasonality_day_of_week
                    ORDER BY day_num
                """)
                dow = self.cur.fetchall()
                return json_response(200, {
                    'monthly': [dict(r) for r in monthly],
                    'day_of_week': [dict(r) for r in dow],
                })
            elif path == '/api/market/sentiment':
                range_days = self._parse_range_param(params) if params else 30
                self.cur.execute("""
                    SELECT date, fear_greed_value as value
                    FROM fear_greed_index
                    WHERE date >= CURRENT_DATE - INTERVAL '%s days'
                    ORDER BY date DESC
                """, (range_days,))
                sentiment = self.cur.fetchall()
                return list_response([dict(s) for s in sentiment] if sentiment else [])
            elif path == '/api/market/fear-greed':
                range_days = self._parse_range_param(params) if params else 30
                return self._get_fear_greed_history(range_days)
            elif path == '/api/market/status':
                self.cur.execute("""
                    SELECT date, market_trend, market_stage, advance_decline_ratio,
                           new_highs_count, new_lows_count, vix_level, put_call_ratio,
                           distribution_days_4w
                    FROM market_health_daily
                    ORDER BY date DESC
                    LIMIT 1
                """)
                row = self.cur.fetchone()
                return json_response(200, dict(row) if row else {})
            elif path == '/api/market/naaim':
                self.cur.execute("""
                    SELECT date, naaim_number_mean, bullish, bearish
                    FROM naaim
                    ORDER BY date DESC
                    LIMIT 52
                """)
                rows = self.cur.fetchall()
                return list_response([dict(r) for r in rows] if rows else [])
            elif path == '/api/market/latest':
                return self._get_market_latest()
            elif path == '/api/market/cap-distribution':
                return json_response(501, {'status': 'not_implemented', 'message': 'Market cap distribution requires data aggregation'})
            elif path == '/api/market/correlation':
                return json_response(501, {'status': 'not_implemented', 'message': 'Correlation matrix requires additional computation'})
            return error_response(404, 'not_found', f'No market handler for {path}')
        except Exception as e:
            logger.error(f"market handler error: {e}")
            return error_response(500, 'internal_error', 'Failed to fetch market data')

    def _get_fear_greed_history(self, days: int = 30) -> Dict:
        """Get fear/greed index history."""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            self.cur.execute("""
                SELECT date, fear_greed_value as value, fear_greed_label as label
                FROM fear_greed_index
                WHERE date >= %s
                ORDER BY date DESC
            """, (cutoff_date,))
            history = self.cur.fetchall()
            return list_response([dict(h) for h in history] if history else [])
        except Exception as e:
            logger.error(f"Error fetching sentiment history: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch sentiment history')

    def _get_market_latest(self) -> Dict:
        """Get latest market data including indices, breadth, and sentiment."""
        try:
            self.cur.execute("""
                SELECT date, market_trend, market_stage, advance_decline_ratio,
                       new_highs_count, new_lows_count, vix_level, put_call_ratio,
                       distribution_days_4w, up_volume_percent, breadth_momentum_10d
                FROM market_health_daily
                ORDER BY date DESC
                LIMIT 1
            """)
            market_row = self.cur.fetchone()

            self.cur.execute("""
                SELECT date, fear_greed_value, fear_greed_label
                FROM fear_greed_index
                ORDER BY date DESC
                LIMIT 1
            """)
            sentiment_row = self.cur.fetchone()

            self.cur.execute("""
                SELECT symbol, close
                FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
                ORDER BY symbol
                LIMIT 10
            """)
            recent_prices = self.cur.fetchall()

            result = {}
            if market_row:
                result['market'] = dict(market_row)
            if sentiment_row:
                result['sentiment'] = dict(sentiment_row)
            if recent_prices:
                result['prices'] = [dict(p) for p in recent_prices]

            return json_response(200, result if result else {})
        except Exception as e:
            logger.error(f"Error fetching market latest: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch market latest')

    def _handle_economic(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/economic and /api/economic/* endpoints."""
        try:
            if path == '/api/economic/VIX':
                # Return VIX data from market_health_daily
                self.cur.execute("""
                    SELECT date, vix_level as vix
                    FROM market_health_daily
                    WHERE vix_level IS NOT NULL
                    ORDER BY date DESC
                    LIMIT 100
                """)
                rows = self.cur.fetchall()
                return list_response([dict(r) for r in rows] if rows else [])
            elif path == '/api/economic/leading-indicators':
                return self._get_leading_indicators()
            elif path == '/api/economic/indicators':
                return self._get_leading_indicators()
            elif path == '/api/economic/yield-curve-full':
                return self._get_yield_curve_full()
            elif path == '/api/economic/calendar':
                self.cur.execute("""
                    SELECT event_date AS date, event_name, country, importance,
                           category, event_time,
                           forecast_value, actual_value, previous_value
                    FROM economic_calendar
                    ORDER BY event_date DESC
                    LIMIT 100
                """)
                events = self.cur.fetchall()
                return list_response([dict(e) for e in events] if events else [])
            elif path == '/api/economic':
                # Combine all economic data
                return self._get_leading_indicators()
            return error_response(404, 'not_found', f'No economic handler for {path}')
        except Exception as e:
            logger.error(f"Error in economic handler: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch economic data')

    def _get_leading_indicators(self) -> Dict:
        """Get leading economic indicators formatted for EconomicDashboard."""
        # Maps FRED series IDs to indicator names
        indicator_map = {
            'UNRATE': 'Unemployment Rate',
            'PAYEMS': 'Total Nonfarm Payroll',
            'ICSA': 'Initial Claims',
            'CIVPART': 'Labor Force Participation',
            'INDPRO': 'Industrial Production',
            'RSXFS': 'Retail Sales',
            'CPIAUCSL': 'CPI - All Urban Consumers',
            'FEDFUNDS': 'Federal Funds Rate',
            'M2SL': 'M2 Money Supply',
            'T10Y2Y': 'Yield Curve (10Y-2Y)',
            'GDPC1': 'GDP Growth',
            'UMCSENT': 'Consumer Sentiment',
            'HOUST': 'Housing Starts',
        }
        # Series that report absolute levels but should be shown as YoY % change
        yoy_pct_series = {'GDPC1', 'INDPRO', 'RSXFS', 'PAYEMS', 'HOUST'}

        try:
            # Get latest values for all indicators
            self.cur.execute("""
                WITH latest AS (
                    SELECT series_id, date, value,
                           ROW_NUMBER() OVER (PARTITION BY series_id ORDER BY date DESC) as rn
                    FROM economic_data
                )
                SELECT series_id, date, value
                FROM latest
                WHERE rn = 1
            """)
            latest_rows = {row['series_id']: (float(row['value']) if row['value'] else None, row['date'])
                          for row in self.cur.fetchall()}

            # Get history for each indicator (last 12-24 months)
            self.cur.execute("""
                SELECT series_id, date, value
                FROM economic_data
                WHERE date >= CURRENT_DATE - INTERVAL '24 months'
                ORDER BY series_id, date DESC
            """)
            all_history = self.cur.fetchall()

            # Group by series_id
            history_by_series = {}
            for row in all_history:
                sid = row['series_id']
                if sid not in history_by_series:
                    history_by_series[sid] = []
                history_by_series[sid].append({
                    'date': str(row['date']),
                    'value': float(row['value']) if row['value'] else None
                })

            # Build indicator objects
            indicators = []
            for series_id, name in indicator_map.items():
                if series_id not in latest_rows:
                    continue

                value, date = latest_rows[series_id]
                history = sorted(history_by_series.get(series_id, []), key=lambda x: x['date'])

                # For level series, compute YoY % change so the frontend gets a meaningful rate
                display_value = value
                if series_id in yoy_pct_series and len(history) >= 12:
                    # history is sorted ascending; last = most recent, -13 â‰ˆ 1 year ago
                    cur_h  = history[-1] if history else None
                    yr_ago = history[-13] if len(history) >= 13 else history[0]
                    if cur_h and yr_ago and yr_ago.get('value') and cur_h.get('value'):
                        prior = float(yr_ago['value'])
                        if prior != 0:
                            display_value = round((float(cur_h['value']) - prior) / abs(prior) * 100, 2)
                    # Replace history values with rolling YoY % change too
                    yoy_history = []
                    for idx in range(12, len(history)):
                        cur_v  = history[idx].get('value')
                        yr_v   = history[idx - 12].get('value')
                        if cur_v is not None and yr_v and float(yr_v) != 0:
                            yoy_history.append({
                                'date': history[idx]['date'],
                                'value': round((float(cur_v) - float(yr_v)) / abs(float(yr_v)) * 100, 2)
                            })
                    if yoy_history:
                        history = yoy_history

                # Calculate trend (up/down/flat) on the (possibly transformed) history
                if len(history) >= 2:
                    recent_avg = sum([h['value'] for h in history[-3:] if h['value'] is not None] or [0]) / max(1, len([h for h in history[-3:] if h['value'] is not None]))
                    older_avg  = sum([h['value'] for h in history[:3]  if h['value'] is not None] or [0]) / max(1, len([h for h in history[:3]  if h['value'] is not None]))
                    if older_avg and recent_avg:
                        trend = 'up' if recent_avg > older_avg * 1.01 else 'down' if recent_avg < older_avg * 0.99 else 'flat'
                    else:
                        trend = 'flat'
                else:
                    trend = 'flat'

                indicators.append({
                    'name': name,
                    'series_id': series_id,
                    'rawValue': display_value,
                    'date': str(date),
                    'history': history,
                    'trend': trend
                })

            return json_response(200, {'indicators': indicators})

        except Exception as e:
            logger.error(f"get_leading_indicators error: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch leading indicators')

    def _get_yield_curve_full(self) -> Dict:
        """Get yield curve and credit spread data formatted for EconomicDashboard."""
        try:
            # Get latest yield curve data
            self.cur.execute("""
                WITH latest AS (
                    SELECT series_id, date, value,
                           ROW_NUMBER() OVER (PARTITION BY series_id ORDER BY date DESC) as rn
                    FROM economic_data
                    WHERE series_id IN ('DGS2', 'DGS5', 'DGS10', 'DGS30', 'T10Y3M', 'T10Y2Y',
                                       'BAMLH0A0HYM2', 'BAMLC0A0CM', 'VIXCLS')
                )
                SELECT series_id, date, value
                FROM latest
                WHERE rn = 1
            """)
            latest_rows = self.cur.fetchall()

            # Get history for spreads and VIX
            self.cur.execute("""
                SELECT series_id, date, value
                FROM economic_data
                WHERE date >= CURRENT_DATE - INTERVAL '12 months'
                AND series_id IN ('BAMLH0A0HYM2', 'BAMLC0A0CM', 'VIXCLS')
                ORDER BY series_id, date
            """)
            history_rows = self.cur.fetchall()

            # Build response
            spreads = {}
            credit = {'history': {}}

            for row in latest_rows:
                sid = row['series_id']
                val = float(row['value']) if row['value'] else None

                if sid == 'T10Y3M':
                    spreads['T10Y3M'] = val / 100 if val else None  # Convert to decimal
                elif sid == 'T10Y2Y':
                    spreads['T10Y2Y'] = val / 100 if val else None
                elif sid in ('BAMLH0A0HYM2', 'BAMLC0A0CM', 'VIXCLS'):
                    if sid not in credit['history']:
                        credit['history'][sid] = []

            # Add history for credit series
            history_by_series = {}
            for row in history_rows:
                sid = row['series_id']
                if sid not in history_by_series:
                    history_by_series[sid] = []
                history_by_series[sid].append({
                    'date': str(row['date']),
                    'value': float(row['value']) if row['value'] else None
                })

            for sid, hist in history_by_series.items():
                credit['history'][sid] = sorted(hist, key=lambda x: x['date'])

            return json_response(200, {'spreads': spreads, 'credit': credit})

        except Exception as e:
            logger.error(f"get_yield_curve_full error: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch yield curve')

    def _handle_sentiment(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/sentiment/* endpoints."""
        try:
            if path == '/api/sentiment/summary':
                self.cur.execute("""
                    SELECT fg.fear_greed_value, fg.fear_greed_label, fg.date,
                           mh.put_call_ratio, mh.vix_level
                    FROM fear_greed_index fg
                    LEFT JOIN market_health_daily mh ON mh.date = fg.date
                    ORDER BY fg.date DESC
                    LIMIT 1
                """)
                row = self.cur.fetchone()
                if row:
                    return json_response(200, {
                        'fear_greed': float(row['fear_greed_value']) if row['fear_greed_value'] else None,
                        'label': row['fear_greed_label'],
                        'put_call_ratio': float(row['put_call_ratio']) if row['put_call_ratio'] else None,
                        'vix_level': float(row['vix_level']) if row['vix_level'] else None,
                        'date': str(row['date']),
                    })
                return json_response(200, {})
            elif path == '/api/sentiment/data' or path.startswith('/api/sentiment/data?'):
                limit_str = params.get('limit', [None])[0] if params else None
                limit = _safe_limit(limit_str, max_val=500, default=100)
                page_str = params.get('page', [None])[0] if params else None
                page = _safe_page(page_str, default=1)
                offset = (page - 1) * limit
                self.cur.execute("""
                    SELECT symbol, date, analyst_count, bullish_count, bearish_count, neutral_count,
                           target_price, current_price, upside_downside_percent
                    FROM analyst_sentiment_analysis
                    ORDER BY date DESC, symbol ASC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                sentiment = self.cur.fetchall()
                return list_response([dict(s) for s in sentiment] if sentiment else [])
            elif path == '/api/sentiment/divergence':
                self.cur.execute("""
                    SELECT asa.symbol, asa.date,
                           asa.bullish_count, asa.bearish_count,
                           asa.upside_downside_percent,
                           ss.composite_score
                    FROM analyst_sentiment_analysis asa
                    JOIN stock_scores ss ON ss.symbol = asa.symbol
                    WHERE asa.date = (SELECT MAX(date) FROM analyst_sentiment_analysis)
                      AND asa.upside_downside_percent IS NOT NULL
                    ORDER BY asa.upside_downside_percent DESC
                    LIMIT 100
                """)
                rows = self.cur.fetchall()
                return list_response([dict(r) for r in rows] if rows else [])
            elif path.startswith('/api/sentiment/analyst/insights/'):
                symbol = path.split('/api/sentiment/analyst/insights/')[-1].upper()
                self.cur.execute("""
                    SELECT date, analyst_count, bullish_count, bearish_count, neutral_count,
                           target_price, current_price, upside_downside_percent
                    FROM analyst_sentiment_analysis
                    WHERE symbol = %s
                    ORDER BY date DESC
                    LIMIT 12
                """, (symbol,))
                rows = self.cur.fetchall()
                return list_response([dict(r) for r in rows] if rows else [])
            elif path.startswith('/api/sentiment/social/insights/'):
                return json_response(501, {'status': 'not_implemented', 'message': 'Social sentiment requires external API integration (not yet configured)'})
            elif path == '/api/sentiment/vix':
                return self._get_vix_data()
            return error_response(404, 'not_found', f'No sentiment handler for {path}')
        except Exception as e:
            logger.error(f"Error in sentiment handler: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch sentiment data')


    def _get_vix_data(self) -> Dict:
        """Get latest VIX data and historical trend."""
        try:
            self.cur.execute("""
                SELECT date, vix_level, put_call_ratio, market_trend, market_stage
                FROM market_health_daily
                WHERE vix_level IS NOT NULL
                ORDER BY date DESC
                LIMIT 60
            """)
            rows = self.cur.fetchall()

            if not rows:
                return json_response(200, {'data': [], 'latest': None})

            latest = dict(rows[0]) if rows else None
            history = [dict(r) for r in rows]

            return json_response(200, {
                'latest': latest,
                'history': history,
                'signal': 'fear' if latest and latest.get('vix_level', 0) > 25 else 'neutral' if latest and latest.get('vix_level', 0) > 15 else 'greed'
            })
        except Exception as e:
            logger.error(f"Error fetching VIX data: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch VIX data')
    def _handle_scores(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/scores/* endpoints."""
        if path == '/api/scores/stockscores' or path.startswith('/api/scores/stockscores?'):
            limit_str = params.get('limit', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=500, default=100)
            offset_str = params.get('offset', [None])[0] if params else None
            offset = _safe_offset(offset_str)
            sort_by = params.get('sortBy', ['composite_score'])[0] if params else 'composite_score'
            sort_order = params.get('sortOrder', ['desc'])[0] if params else 'desc'
            sp500_only = params.get('sp500Only', ['false'])[0] if params else 'false'
            symbol = params.get('symbol', [None])[0] if params else None

            allowed_sorts = ['composite_score', 'momentum_score', 'quality_score', 'value_score',
                           'growth_score', 'positioning_score', 'stability_score', 'symbol']
            if sort_by not in allowed_sorts:
                return error_response(400, 'bad_request', f'Sort must be one of: {", ".join(allowed_sorts)}')
            if sort_order not in ['asc', 'desc']:
                return error_response(400, 'bad_request', 'Sort order must be "asc" or "desc"')

            return self._get_stock_scores(limit, offset, sort_by, sort_order, sp500_only == 'true', symbol)
        else:
            return error_response(404, 'not_found', f'No scores handler for {path}')

    def _get_stock_scores(self, limit: int = 5000, offset: int = 0, sort_by: str = 'composite_score',
                         sort_order: str = 'desc', sp500_only: bool = False, symbol: str = None) -> Dict:
        """Get stock scores with multi-factor ranking."""
        try:
            allowed_sorts = {
                'composite_score': 'sc.composite_score',
                'momentum_score': 'sc.momentum_score',
                'quality_score': 'sc.quality_score',
                'value_score': 'sc.value_score',
                'growth_score': 'sc.growth_score',
                'positioning_score': 'sc.positioning_score',
                'stability_score': 'sc.stability_score',
                'symbol': 'sc.symbol'
            }
            sort_col = allowed_sorts.get(sort_by, 'sc.composite_score')
            sort_direction = 'DESC' if sort_order == 'desc' else 'ASC'

            where_clause = "WHERE sc.composite_score > 0"
            params_list = []

            if sp500_only:
                where_clause += " AND ss.is_sp500 = TRUE"
            if symbol:
                where_clause += " AND sc.symbol = %s"
                params_list.append(symbol.upper())

            query = f"""
                SELECT
                    sc.symbol,
                    ss.security_name AS company_name,
                    cp.sector, cp.industry,
                    sc.composite_score, sc.momentum_score, sc.quality_score,
                    sc.value_score, sc.growth_score, sc.positioning_score, sc.stability_score,
                    pd.close AS current_price,
                    pd.close AS price,
                    ROUND(CASE
                        WHEN pd_prev.close IS NOT NULL THEN ((pd.close - pd_prev.close) / NULLIF(pd_prev.close, 0)) * 100
                        ELSE NULL
                    END, 2) AS change_percent,
                    km.market_cap,
                    vm.pe_ratio AS trailing_pe,
                    vm.pb_ratio AS price_to_book,
                    qm.roe AS roe_pct,
                    qm.debt_to_equity,
                    vm.dividend_yield,
                    gm.revenue_growth_1y AS revenue_growth_yoy_pct,
                    gm.eps_growth_1y AS eps_growth_yoy_pct
                FROM stock_scores sc
                JOIN stock_symbols ss ON ss.symbol = sc.symbol
                LEFT JOIN company_profile cp ON cp.ticker = sc.symbol
                LEFT JOIN key_metrics km ON km.ticker = sc.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
                LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
                LEFT JOIN (
                    SELECT DISTINCT ON (symbol) symbol, close
                    FROM price_daily
                    ORDER BY symbol, date DESC
                ) pd ON pd.symbol = sc.symbol
                LEFT JOIN (
                    SELECT symbol, close FROM (
                        SELECT symbol, close,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                        FROM price_daily
                    ) ranked WHERE rn = 2
                ) pd_prev ON pd_prev.symbol = sc.symbol
                {where_clause}
                ORDER BY {sort_col} {sort_direction}
                LIMIT %s OFFSET %s
            """
            params_list.extend([limit, offset])
            self.cur.execute(query, params_list)
            scores = self.cur.fetchall()
            return list_response([dict(s) for s in scores])
        except Exception as e:
            logger.error(f"get_stock_scores failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch stock scores')



    def _handle_research(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/research/* endpoints."""
        try:
            if path == '/api/research/backtests' or path.startswith('/api/research/backtests?'):
                limit_str = params.get('limit', [None])[0] if params else None
                limit = _safe_limit(limit_str, max_val=200, default=50)
                self.cur.execute("""
                    SELECT run_id AS id, strategy_name, date_start AS start_date, date_end AS end_date, total_return_pct AS total_return,
                           sharpe_annualized AS sharpe_ratio, max_drawdown_pct AS max_drawdown, win_rate, total_trades
                    FROM backtest_runs
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                backtests = self.cur.fetchall()
                return list_response([dict(b) for b in backtests] if backtests else [])
            elif path.startswith('/api/research/backtests/'):
                run_id = path.split('/api/research/backtests/')[-1]
                try:
                    run_id_int = int(run_id)
                except ValueError:
                    return error_response(400, 'bad_request', 'Run ID must be numeric')

                # Get backtest run details
                self.cur.execute("""
                    SELECT run_id, strategy_name, date_start, date_end,
                           total_return_pct, sharpe_annualized, max_drawdown_pct, win_rate,
                           total_trades, best_trade_pct, worst_trade_pct, avg_trade_pct,
                           consecutive_wins, consecutive_losses, created_at, notes
                    FROM backtest_runs
                    WHERE run_id = %s
                """, (run_id_int,))
                backtest = self.cur.fetchone()
                if not backtest:
                    return error_response(404, 'not_found', f'Backtest run {run_id} not found')

                # Get trades for this backtest
                limit_str = params.get('limit', [None])[0] if params else None
                offset_str = params.get('offset', [None])[0] if params else None
                limit = _safe_limit(limit_str, max_val=500, default=100)
                offset = _safe_offset(offset_str)

                self.cur.execute("""
                    SELECT trade_id, symbol, signal_date, entry_date, entry_price, entry_quantity,
                           exit_date, exit_price, profit_loss_pct, mfe_pct, mae_pct
                    FROM backtest_trades
                    WHERE run_id = %s
                    ORDER BY entry_date DESC
                    LIMIT %s OFFSET %s
                """, (run_id_int, limit, offset))
                trades = self.cur.fetchall()

                self.cur.execute("""
                    SELECT COUNT(*) FROM backtest_trades WHERE run_id = %s
                """, (run_id_int,))
                total_trades_count = self.cur.fetchone()[0]

                # Build response
                run_dict = dict(backtest)
                return json_response(200, {
                    'run': run_dict,
                    'trades': [dict(t) for t in trades] if trades else [],
                    'trade_pagination': {'total': total_trades_count}
                })
            return error_response(404, 'not_found', f'No research handler for {path}')
        except Exception as e:
            logger.error(f"get_backtests failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch backtest results')


    def _handle_audit(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/audit/* endpoints."""
        try:
            limit_str = params.get('limit', [None])[0] if params else None
            offset_str = params.get('offset', [None])[0] if params else None
            limit = _safe_limit(limit_str, max_val=200, default=100)
            offset = _safe_offset(offset_str)

            if path == '/api/audit/trail' or path.startswith('/api/audit/trail?'):
                self.cur.execute("""
                    SELECT id, created_at AS timestamp, action_type AS action,
                           actor AS user_id, status, details
                    FROM algo_audit_log
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                audits = self.cur.fetchall()
                self.cur.execute("SELECT COUNT(*) FROM algo_audit_log")
                total = self.cur.fetchone()[0]
                return json_response(200, {
                    'data': [dict(a) for a in audits] if audits else [],
                    'pagination': {'total': total}
                })

            elif path == '/api/audit/trades' or path.startswith('/api/audit/trades?'):
                self.cur.execute("""
                    SELECT id, created_at AS timestamp, action_type,
                           symbol, actor, status, error_message, details
                    FROM algo_audit_log
                    WHERE action_type IN ('entry', 'exit', 'partial_exit', 'pyramid')
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                audits = self.cur.fetchall()
                self.cur.execute("""
                    SELECT COUNT(*) FROM algo_audit_log
                    WHERE action_type IN ('entry', 'exit', 'partial_exit', 'pyramid')
                """)
                total = self.cur.fetchone()[0]
                return json_response(200, {
                    'data': [dict(a) for a in audits] if audits else [],
                    'pagination': {'total': total}
                })

            elif path == '/api/audit/config' or path.startswith('/api/audit/config?'):
                self.cur.execute("""
                    SELECT id, created_at AS timestamp, action_type,
                           actor, status, error_message, details
                    FROM algo_audit_log
                    WHERE action_type LIKE 'config%' OR action_type = 'settings_change'
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                audits = self.cur.fetchall()
                self.cur.execute("""
                    SELECT COUNT(*) FROM algo_audit_log
                    WHERE action_type LIKE 'config%' OR action_type = 'settings_change'
                """)
                total = self.cur.fetchone()[0]
                return json_response(200, {
                    'data': [dict(a) for a in audits] if audits else [],
                    'pagination': {'total': total}
                })

            elif path == '/api/audit/safeguards' or path.startswith('/api/audit/safeguards?'):
                self.cur.execute("""
                    SELECT id, created_at AS timestamp, action_type,
                           actor, status, error_message, details
                    FROM algo_audit_log
                    WHERE action_type IN ('circuit_breaker', 'safeguard', 'halt', 'exposure_policy')
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                audits = self.cur.fetchall()
                self.cur.execute("""
                    SELECT COUNT(*) FROM algo_audit_log
                    WHERE action_type IN ('circuit_breaker', 'safeguard', 'halt', 'exposure_policy')
                """)
                total = self.cur.fetchone()[0]
                return json_response(200, {
                    'data': [dict(a) for a in audits] if audits else [],
                    'pagination': {'total': total}
                })

            return error_response(404, 'not_found', f'No audit handler for {path}')
        except Exception as e:
            logger.error(f"Error in audit handler: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch audit data')

    def _handle_trades(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/trades and /api/trades/* endpoints."""
        try:
            if path == '/api/trades':
                limit_str = params.get('limit', [None])[0] if params else None
                limit = _safe_limit(limit_str, max_val=500, default=100)
                offset_str = params.get('offset', [None])[0] if params else None
                offset = _safe_offset(offset_str)
                status_filter = params.get('status', [None])[0] if params else None
                query = """
                    SELECT trade_id, symbol, signal_date, trade_date, entry_time,
                           entry_price, entry_quantity, entry_reason,
                           exit_price, exit_date, exit_reason,
                           stop_loss_price, status, profit_loss_dollars, profit_loss_pct,
                           execution_mode, created_at
                    FROM algo_trades
                    WHERE 1=1
                """
                args = []
                if status_filter:
                    query += " AND status = %s"
                    args.append(status_filter)
                query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                args.extend([limit, offset])
                self.cur.execute(query, args)
                trades = self.cur.fetchall()
                # Count total trades
                count_query = "SELECT COUNT(*) FROM algo_trades WHERE 1=1"
                count_args = []
                if status_filter:
                    count_query += " AND status = %s"
                    count_args.append(status_filter)
                self.cur.execute(count_query, count_args)
                total = self.cur.fetchone()[0]
                return json_response(200, {'data': [dict(t) for t in trades], 'total': total})
            elif path == '/api/trades/summary':
                self.cur.execute("""
                    SELECT
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN exit_price > entry_price THEN 1 ELSE 0 END) as winning_trades,
                        COUNT(DISTINCT symbol) as unique_symbols,
                        SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_trades
                    FROM algo_trades
                """)
                summary = self.cur.fetchone()
                return json_response(200, dict(summary) if summary else {})
            return error_response(404, 'not_found', f'Unknown trade endpoint: {path}')
        except Exception as e:
            logger.error(f"Error in trades handler: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch trades')


    def _handle_contact(self, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
        """Handle /api/contact and /api/contact/submissions."""
        try:
            if path == '/api/contact/submissions':
                self.cur.execute("""
                    SELECT id, name, email, subject, message, status, submitted_at
                    FROM contact_submissions
                    ORDER BY submitted_at DESC
                    LIMIT 100
                """)
                rows = self.cur.fetchall()
                return list_response([dict(r) for r in rows])
            elif path == '/api/contact' and method == 'POST':
                # Validate contact request against schema
                data = body or {}
                valid, result, error_msg = validate_request(ContactRequest, data)
                if not valid:
                    return error_response(400, 'bad_request', error_msg)

                contact = result  # ContactRequest instance
                self.cur.execute("""
                    INSERT INTO contact_submissions (name, email, subject, message, status, submitted_at)
                    VALUES (%s, %s, %s, %s, 'new', NOW())
                """, (contact.name, contact.email, contact.subject, contact.message))
                self.conn.commit()
                return json_response(200, {'status': 'submitted', 'message': 'Contact form submission received'})
            return error_response(404, 'not_found', f'No handler for {path}')
        except Exception as e:
            logger.error(f"contact handler error: {e}")
            return error_response(500, 'internal_error', 'Contact handler error')

    def _handle_admin(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/admin/* endpoints for operational visibility."""
        try:
            if path == '/api/admin/loader-status':
                return self._get_loader_status()
            elif path == '/api/admin/system-health':
                return self._get_system_health()
            elif path == '/api/admin/database-stats':
                return self._get_database_stats()
            elif path == '/api/admin/data-quality':
                return self._get_data_quality()
            return error_response(404, 'not_found', f'No admin handler for {path}')
        except Exception as e:
            logger.error(f"admin handler error: {e}")
            return error_response(500, 'internal_error', 'Admin handler error')

    def _get_loader_status(self) -> Dict:
        """Get status of all data loaders from data_loader_runs table."""
        try:
            self.cur.execute("""
                SELECT
                    loader_name,
                    run_date,
                    rows_processed,
                    duration_seconds,
                    status,
                    error_message,
                    checksum
                FROM data_loader_runs
                WHERE (loader_name, run_date) IN (
                    SELECT loader_name, MAX(run_date)
                    FROM data_loader_runs
                    GROUP BY loader_name
                )
                ORDER BY run_date DESC, loader_name
            """)
            rows = self.cur.fetchall()

            if not rows:
                return json_response(200, {
                    'status': 'no_runs',
                    'message': 'No loader runs recorded yet',
                    'loaders': []
                })

            loaders = []
            for row in rows:
                run_date = row[1]
                age_hours = (datetime.now(timezone.utc) - run_date.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                health = 'stale' if age_hours > 24 else 'fresh'

                loaders.append({
                    'name': row[0],
                    'last_run': run_date.isoformat() if run_date else None,
                    'rows_processed': row[2],
                    'duration_seconds': row[3],
                    'status': row[4],
                    'error': row[5],
                    'checksum': row[6],
                    'age_hours': round(age_hours, 1),
                    'health': health,
                })

            return json_response(200, {
                'status': 'ok',
                'loaders': loaders,
                'summary': {
                    'total': len(loaders),
                    'healthy': len([l for l in loaders if l['health'] == 'fresh']),
                    'stale': len([l for l in loaders if l['health'] == 'stale']),
                    'failed': len([l for l in loaders if l['status'] != 'success']),
                }
            })
        except Exception as e:
            logger.error(f"loader status query failed: {e}")
            return error_response(500, 'internal_error', 'Failed to fetch loader status')

    def _get_system_health(self) -> Dict:
        """Get overall system health status."""
        try:
            health_data = {'status': 'healthy', 'components': {}}

            # Check database connectivity
            try:
                self.cur.execute("SELECT 1")
                health_data['components']['database'] = 'ok'
            except Exception as e:
                logger.error(f"Database health check failed: {e}")
                health_data['components']['database'] = 'error'
                health_data['status'] = 'degraded'

            # Check data freshness
            self.cur.execute("SELECT MAX(date) FROM price_daily")
            last_price_date = self.cur.fetchone()[0]
            if last_price_date:
                age_days = (datetime.now(timezone.utc).date() - last_price_date).days
                health_data['components']['data_freshness'] = 'ok' if age_days <= 3 else 'stale'
                health_data['last_data_update'] = last_price_date.isoformat()
                if age_days > 3:
                    health_data['status'] = 'degraded'
            else:
                health_data['components']['data_freshness'] = 'no_data'
                health_data['status'] = 'unhealthy'

            # Check table counts
            table_counts = {}
            for table in ['stock_symbols', 'price_daily', 'algo_trades', 'algo_positions']:
                try:
                    query = psycopg2.sql.SQL("SELECT COUNT(*) FROM {}").format(
                        psycopg2.sql.Identifier(table)
                    )
                    self.cur.execute(query)
                    count = self.cur.fetchone()[0]
                    table_counts[table] = count
                except:
                    table_counts[table] = 0

            health_data['tables'] = table_counts
            health_data['timestamp'] = datetime.now(timezone.utc).isoformat()
            return json_response(200, health_data)
        except Exception as e:
            logger.error(f"system health check failed: {e}")
            return error_response(500, 'internal_error', 'Failed to get system health')

    def _get_database_stats(self) -> Dict:
        """Get database statistics."""
        try:
            stats = {}

            # Get table sizes
            self.cur.execute("""
                SELECT
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                FROM pg_tables
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                LIMIT 20
            """)

            tables = []
            for row in self.cur.fetchall():
                tables.append({'name': row[1], 'size': row[2]})

            stats['largest_tables'] = tables

            # Get connection info
            self.cur.execute("SELECT count(*) FROM pg_stat_activity WHERE state != 'idle'")
            stats['active_connections'] = self.cur.fetchone()[0]

            # Get index usage
            self.cur.execute("""
                SELECT COUNT(*) FROM pg_stat_user_indexes WHERE idx_scan = 0
            """)
            stats['unused_indexes'] = self.cur.fetchone()[0]

            stats['timestamp'] = datetime.now(timezone.utc).isoformat()
            return json_response(200, stats)
        except Exception as e:
            logger.error(f"database stats query failed: {e}")
            return error_response(500, 'internal_error', 'Failed to get database stats')

    def _get_data_quality(self) -> Dict:
        """Get data quality metrics."""
        try:
            quality = {'timestamp': datetime.now(timezone.utc).isoformat(), 'checks': {}}

            # Check for null prices
            self.cur.execute("""
                SELECT COUNT(*) FROM price_daily
                WHERE close IS NULL OR open IS NULL OR high IS NULL OR low IS NULL
            """)
            null_prices = self.cur.fetchone()[0]
            quality['checks']['null_prices'] = {'count': null_prices, 'status': 'ok' if null_prices == 0 else 'warning'}

            # Check for duplicate prices
            self.cur.execute("""
                SELECT COUNT(*) FROM (
                    SELECT symbol, date, COUNT(*)
                    FROM price_daily
                    GROUP BY symbol, date HAVING COUNT(*) > 1
                ) t
            """)
            duplicate_prices = self.cur.fetchone()[0]
            quality['checks']['duplicate_prices'] = {'count': duplicate_prices, 'status': 'ok' if duplicate_prices == 0 else 'warning'}

            # Check price logical consistency (high >= low >= close)
            self.cur.execute("""
                SELECT COUNT(*) FROM price_daily
                WHERE high < low OR close > high OR close < low
            """)
            invalid_prices = self.cur.fetchone()[0]
            quality['checks']['invalid_price_ranges'] = {'count': invalid_prices, 'status': 'ok' if invalid_prices == 0 else 'error'}

            # Overall status
            quality['status'] = 'healthy' if invalid_prices == 0 else 'degraded'

            return json_response(200, quality)
        except Exception as e:
            logger.error(f"data quality check failed: {e}")
            return error_response(500, 'internal_error', 'Failed to get data quality metrics')

    def _handle_notifications(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/notifications/* endpoints."""
        try:
            if path == '/api/notifications' or path == '/api/notifications/':
                return json_response(200, {'items': [], 'status': 'no_notifications'})
            return error_response(404, 'not_found', f'No notifications handler for {path}')
        except Exception as e:
            logger.error(f"notifications handler error: {e}")
            return error_response(500, 'internal_error', 'Notifications handler error')

    def _handle_metrics(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/metrics/* endpoints."""
        try:
            return json_response(501, {'status': 'not_implemented', 'message': 'Metrics feature requires additional setup'})
        except Exception as e:
            logger.error(f"metrics handler error: {e}")
            return error_response(500, 'internal_error', 'Metrics handler error')

    def _handle_articles(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/articles/* endpoints."""
        try:
            return json_response(501, {'status': 'not_implemented', 'message': 'Articles feature requires additional setup'})
        except Exception as e:
            logger.error(f"articles handler error: {e}")
            return error_response(500, 'internal_error', 'Articles handler error')

    def _handle_simulator(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/simulator/* endpoints."""
        try:
            return json_response(501, {'status': 'not_implemented', 'message': 'Simulator feature requires additional setup'})
        except Exception as e:
            logger.error(f"simulator handler error: {e}")
            return error_response(500, 'internal_error', 'Simulator handler error')

    def _handle_settings(self, path: str, method: str, params: Dict, body: Dict) -> Dict:
        """Handle /api/settings endpoints for user preferences."""
        try:
            if method == 'GET':
                return json_response(200, {'theme': 'light', 'notifications_enabled': True, 'auto_refresh': True})
            elif method == 'POST':
                return json_response(200, {'status': 'ok', 'message': 'Settings saved'})
            return error_response(405, 'method_not_allowed', f'Method {method} not allowed for {path}')
        except Exception as e:
            logger.error(f"settings handler error: {e}")
            return error_response(500, 'internal_error', 'Settings handler error')


def lambda_handler(event, context):
    """AWS Lambda handler for HTTP API Gateway proxy integration."""
    try:
        # Validate required configuration before processing requests
        environment = os.environ.get('ENVIRONMENT', 'production')

        # Check FRONTEND_ORIGIN for CORS
        frontend_origin = os.environ.get('FRONTEND_ORIGIN')
        if not frontend_origin:
            if environment == 'production':
                # CRITICAL: CORS is disabled in production if FRONTEND_ORIGIN not set
                logger.critical("FRONTEND_ORIGIN env var not set — API requests from browser will be blocked by CORS policy")
                return error_response(503, 'service_unavailable', 'API not configured. Contact administrator.')
            else:
                # Dev/test: Allow localhost
                logger.warning("FRONTEND_ORIGIN not set in development — allowing localhost")

        # Check other critical env vars (except for /api/health which doesn't need DB)
        path = event.get('rawPath', event.get('path', '/'))
        if path != '/api/health':
            required_envs = ['DB_SECRET_ARN', 'DATABASE_SECRET_ARN', 'ECS_CLUSTER_ARN']
            missing_envs = [e for e in required_envs if e not in ('DATABASE_SECRET_ARN',) and not os.getenv(e)]
            # Allow either DB_SECRET_ARN or DATABASE_SECRET_ARN
            has_db_secret = os.getenv('DB_SECRET_ARN') or os.getenv('DATABASE_SECRET_ARN')
            if not has_db_secret:
                logger.critical("Database secret ARN not set (DB_SECRET_ARN or DATABASE_SECRET_ARN)")
                return error_response(503, 'service_unavailable', 'Database credentials not configured')
            if environment == 'production' and not os.getenv('ECS_CLUSTER_ARN'):
                logger.warning("ECS_CLUSTER_ARN not set - data patrol trigger will fail")

        # Parse request (path already extracted above for env var checks)
        method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
        # Get client IP for rate limiting
        client_ip = event.get('requestContext', {}).get('http', {}).get('sourceIp', 'unknown')

        # Rate limiting: Apply stricter limits to trading/action endpoints, standard to others
        # Trading endpoints (prevent accidental rapid-fire trades): 5 req/min
        if path.startswith('/api/trades') or path == '/api/algo/patrol':
            max_requests, window_seconds = 5, 60
            limit_desc = 'Max 5 requests per minute for trading endpoints'
        # Admin/sensitive endpoints: 10 req/min
        elif path.startswith('/api/admin') or path.startswith('/api/audit'):
            max_requests, window_seconds = 10, 60
            limit_desc = 'Max 10 requests per minute for admin endpoints'
        # Standard endpoints: 100 req/min
        else:
            max_requests, window_seconds = 100, 60
            limit_desc = 'Max 100 requests per minute'

        if not check_rate_limit(client_ip, max_requests=max_requests, window_seconds=window_seconds):
            logger.warning(f"Rate limit exceeded for {client_ip} on {path} (limit: {limit_desc})")
            return error_response(429, 'rate_limited', limit_desc)

        # API GW v2 HTTP API passes query params as plain strings, but all handlers
        # do params.get('key', [default])[0]. Normalize each value to a single-item list
        # so [0] indexing works uniformly regardless of whether a param was sent.
        raw_params = event.get('queryStringParameters') or {}
        query_params = {k: [v] if not isinstance(v, list) else v for k, v in raw_params.items()}

        logger.info(f"{method} {path}")

        # Parse request body for POST/PATCH/PUT methods
        raw_body = event.get('body', '{}') or '{}'
        try:
            body = json.loads(raw_body) if raw_body else {}
        except (json.JSONDecodeError, ValueError):
            body = {}

        # API Authentication: Validate API key for all endpoints except /api/health
        api_key_info = None
        if path != '/api/health':
            # Extract API key from headers or query parameters
            headers = event.get('headers', {})
            api_key = (
                headers.get('authorization', '').replace('Bearer ', '').replace('bearer ', '') or
                headers.get('Authorization', '').replace('Bearer ', '').replace('bearer ', '') or
                headers.get('x-api-key', '') or
                headers.get('X-API-Key', '') or
                query_params.get('api_key', [None])[0]
            )

            # Validate API key
            if not api_key:
                logger.warning(f"Missing API key for {method} {path} from {client_ip}")
                return error_response(401, 'unauthorized', 'API key is required')

            # Connect to database to validate key
            temp_conn = None
            try:
                temp_conn = get_db_connection()
                validator = APIKeyValidator(temp_conn)
                is_valid, app_info, error_msg = validator.validate_key(api_key)

                if not is_valid:
                    logger.warning(f"Invalid API key for {method} {path} from {client_ip}: {error_msg}")
                    return error_response(401, 'unauthorized', error_msg)

                api_key_info = app_info
            except Exception as e:
                logger.error(f"API key validation error: {e}")
                return error_response(500, 'unauthorized', 'Authentication check failed')

        # Route to handler
        handler = APIHandler()
        handler.connect()
        try:
            response = handler.route(path, method, query_params, body)
        finally:
            handler.disconnect()

        return response

    except Exception as e:
        logger.error(f"Lambda handler error: {e}", exc_info=True)
        return error_response(500, 'internal_error', 'Internal server error')

