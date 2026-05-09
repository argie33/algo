"""
Stock Analytics Platform - API Lambda Handler

Serves HTTP API endpoints for the frontend dashboard.
Connects to RDS PostgreSQL database and returns JSON.

Endpoints:
- /api/algo/* — algo orchestrator status, positions, trades, performance
- /api/portfolio/* — portfolio data
- /api/sectors/* — sector analysis
- /api/market/* — market data
- /api/economic/* — economic indicators
- /api/sentiment/* — market sentiment
- /api/commodities/* — commodity data
- /api/health — API health check
"""

import os
import json
import logging
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional, List

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_db_connection():
    """Get database connection from environment or Secrets Manager."""
    try:
        # Try Secrets Manager first (Lambda)
        db_secret_arn = os.getenv('DB_SECRET_ARN')
        if db_secret_arn:
            import boto3
            secrets = boto3.client('secretsmanager', region_name='us-east-1')
            response = secrets.get_secret_value(SecretId=db_secret_arn)
            creds = json.loads(response['SecretString'])
            host = creds.get('host')
            port = creds.get('port', 5432)
            user = creds.get('username')
            password = creds.get('password')
            database = creds.get('dbname')
        else:
            # Fall back to environment variables (local/docker)
            host = os.getenv('DB_HOST', 'localhost')
            port = int(os.getenv('DB_PORT', 5432))
            user = os.getenv('DB_USER', 'stocks')
            password = os.getenv('DB_PASSWORD', '')
            database = os.getenv('DB_NAME', 'stocks')

        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise


def json_response(status_code: int, body: Dict[str, Any], headers: Optional[Dict] = None) -> Dict:
    """Return properly formatted API Gateway response."""
    default_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
    }
    if headers:
        default_headers.update(headers)

    return {
        'statusCode': status_code,
        'headers': default_headers,
        'body': json.dumps(body, default=str),
    }


def error_response(status_code: int, error: str, message: str = '') -> Dict:
    """Return error response."""
    return json_response(status_code, {'error': error, 'message': message})


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
        """Close database connection."""
        try:
            if self.cur:
                self.cur.close()
            if self.conn:
                self.conn.close()
        except Exception as e:
            logger.warning(f"Failed to close connection: {e}")

    def route(self, path: str, method: str = 'GET', query_params: Dict = None) -> Dict:
        """Route request to appropriate handler."""
        query_params = query_params or {}

        try:
            # Health check
            if path == '/api/health':
                return json_response(200, {'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})

            # Algo endpoints
            if path.startswith('/api/algo/'):
                return self._handle_algo(path, method, query_params)

            # Portfolio endpoints
            if path.startswith('/api/portfolio/'):
                return self._handle_portfolio(path, method, query_params)

            # Sector endpoints
            if path.startswith('/api/sectors/'):
                return self._handle_sectors(path, method, query_params)

            # Market endpoints
            if path.startswith('/api/market/'):
                return self._handle_market(path, method, query_params)

            # Economic endpoints
            if path.startswith('/api/economic/'):
                return self._handle_economic(path, method, query_params)

            # Sentiment endpoints
            if path.startswith('/api/sentiment/'):
                return self._handle_sentiment(path, method, query_params)

            # Commodities endpoints
            if path.startswith('/api/commodities/'):
                return self._handle_commodities(path, method, query_params)

            # Scores endpoints
            if path.startswith('/api/scores/'):
                return self._handle_scores(path, method, query_params)

            return error_response(404, 'not_found', f'No handler for {path}')

        except Exception as e:
            logger.error(f"Request failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', str(e))

    def _handle_algo(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/algo/* endpoints."""
        if path == '/api/algo/status':
            return self._get_algo_status()
        elif path == '/api/algo/trades':
            limit = int(params.get('limit', [200])[0])
            return self._get_algo_trades(limit)
        elif path == '/api/algo/positions':
            return self._get_algo_positions()
        elif path == '/api/algo/performance':
            return self._get_algo_performance()
        elif path == '/api/algo/circuit-breakers':
            return self._get_circuit_breakers()
        elif path == '/api/algo/equity-curve':
            days = int(params.get('limit', [180])[0])
            return self._get_equity_curve(days)
        elif path == '/api/algo/data-status':
            return self._get_data_status()
        elif path == '/api/algo/notifications':
            return self._get_notifications()
        elif path == '/api/algo/patrol-log':
            limit = int(params.get('limit', [50])[0])
            return self._get_patrol_log(limit)
        elif path == '/api/algo/sector-rotation':
            days = int(params.get('limit', [180])[0])
            return self._get_sector_rotation(days)
        elif path == '/api/algo/sector-breadth':
            return self._get_sector_breadth()
        elif path == '/api/algo/swing-scores':
            limit = int(params.get('limit', [100])[0])
            return self._get_swing_scores(limit)
        elif path == '/api/algo/swing-scores-history':
            days = int(params.get('days', [30])[0])
            return self._get_swing_scores_history(days)
        elif path == '/api/algo/rejection-funnel':
            return self._get_rejection_funnel()
        elif path == '/api/algo/markets':
            return self._get_markets()
        else:
            return error_response(404, 'not_found', f'No algo handler for {path}')

    def _get_algo_status(self) -> Dict:
        """Get latest algo execution status."""
        try:
            self.cur.execute("""
                SELECT run_id, created_at, phase, status, message
                FROM algo_audit_log
                ORDER BY created_at DESC
                LIMIT 1
            """)
            row = self.cur.fetchone()
            if not row:
                return json_response(200, {'status': 'no_runs_yet', 'last_run': None})

            return json_response(200, {
                'run_id': row['run_id'],
                'last_run': row['created_at'].isoformat() if row['created_at'] else None,
                'current_phase': row['phase'],
                'status': row['status'],
                'message': row['message'],
            })
        except Exception as e:
            logger.error(f"get_algo_status failed: {e}")
            return error_response(500, 'database_error', str(e))

    def _get_algo_trades(self, limit: int = 200) -> Dict:
        """Get recent trades."""
        try:
            self.cur.execute("""
                SELECT trade_id, symbol, signal_date, trade_date, entry_price, entry_quantity,
                       exit_price, exit_quantity, entry_reason, status, created_at
                FROM algo_trades
                ORDER BY trade_date DESC, trade_id DESC
                LIMIT %s
            """, (limit,))
            trades = self.cur.fetchall()
            return json_response(200, {
                'trades': [dict(t) for t in trades],
                'count': len(trades),
            })
        except Exception as e:
            logger.error(f"get_algo_trades failed: {e}")
            return error_response(500, 'database_error', str(e))

    def _get_algo_positions(self) -> Dict:
        """Get current open positions."""
        try:
            self.cur.execute("""
                SELECT position_id, symbol, quantity, avg_entry_price, current_price,
                       position_value, unrealized_pnl, unrealized_pnl_pct, status
                FROM algo_positions
                WHERE status IN ('open', 'OPEN')
                ORDER BY position_value DESC
            """)
            positions = self.cur.fetchall()
            total_value = sum(p['position_value'] or 0 for p in positions)
            return json_response(200, {
                'positions': [dict(p) for p in positions],
                'count': len(positions),
                'total_value': total_value,
            })
        except Exception as e:
            logger.error(f"get_algo_positions failed: {e}")
            return error_response(500, 'database_error', str(e))

    def _get_algo_performance(self) -> Dict:
        """Get algo performance metrics."""
        try:
            self.cur.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN exit_price > entry_price THEN 1 ELSE 0 END) as winning_trades,
                    COALESCE(AVG(CASE WHEN entry_price > 0 THEN (exit_price - entry_price) / entry_price * 100 END), 0) as avg_return_pct,
                    COALESCE(MAX(CASE WHEN exit_price > 0 THEN (exit_price - entry_price) / entry_price * 100 END), 0) as best_trade_pct,
                    COALESCE(MIN(CASE WHEN exit_price > 0 THEN (exit_price - entry_price) / entry_price * 100 END), 0) as worst_trade_pct
                FROM algo_trades
                WHERE status IN ('closed', 'CLOSED')
            """)
            row = self.cur.fetchone()
            if not row:
                return json_response(200, {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'win_rate': 0.0,
                    'avg_return_pct': 0.0,
                })

            total = row['total_trades'] or 0
            wins = row['winning_trades'] or 0
            return json_response(200, {
                'total_trades': total,
                'winning_trades': wins,
                'win_rate': (wins / total * 100) if total > 0 else 0.0,
                'avg_return_pct': float(row['avg_return_pct'] or 0),
                'best_trade_pct': float(row['best_trade_pct'] or 0),
                'worst_trade_pct': float(row['worst_trade_pct'] or 0),
            })
        except Exception as e:
            logger.error(f"get_algo_performance failed: {e}")
            return error_response(500, 'database_error', str(e))

    def _get_circuit_breakers(self) -> Dict:
        """Get circuit breaker status."""
        return json_response(200, {'circuit_breakers': [], 'active': False})

    def _get_equity_curve(self, days: int = 180) -> Dict:
        """Get equity curve for last N days."""
        return json_response(200, {'equity_curve': [], 'days': days})

    def _get_data_status(self) -> Dict:
        """Get data freshness status."""
        try:
            self.cur.execute("""
                SELECT symbol, MAX(date) as latest_date
                FROM price_daily
                GROUP BY symbol
                ORDER BY latest_date DESC
                LIMIT 10
            """)
            rows = self.cur.fetchall()
            return json_response(200, {
                'latest_data': [dict(r) for r in rows],
                'as_of': datetime.utcnow().isoformat(),
            })
        except Exception as e:
            return error_response(500, 'database_error', str(e))

    def _get_notifications(self) -> Dict:
        """Get recent notifications."""
        return json_response(200, {'notifications': []})

    def _get_patrol_log(self, limit: int = 50) -> Dict:
        """Get data patrol findings."""
        return json_response(200, {'patrol_log': [], 'limit': limit})

    def _get_sector_rotation(self, days: int = 180) -> Dict:
        """Get sector rotation data."""
        return json_response(200, {'sector_rotation': [], 'days': days})

    def _get_sector_breadth(self) -> Dict:
        """Get sector breadth indicators."""
        return json_response(200, {'sectors': []})

    def _get_swing_scores(self, limit: int = 100) -> Dict:
        """Get swing trade candidates."""
        return json_response(200, {'swing_scores': [], 'limit': limit})

    def _get_swing_scores_history(self, days: int = 30) -> Dict:
        """Get swing scores historical data."""
        return json_response(200, {'history': [], 'days': days})

    def _get_rejection_funnel(self) -> Dict:
        """Get signal rejection funnel."""
        return json_response(200, {'funnel': {}})

    def _get_markets(self) -> Dict:
        """Get market data."""
        return json_response(200, {'markets': []})

    def _handle_portfolio(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/portfolio/* endpoints."""
        return json_response(200, {'portfolio': {}})

    def _handle_sectors(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/sectors/* endpoints."""
        return json_response(200, {'sectors': []})

    def _handle_market(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/market/* endpoints."""
        return json_response(200, {'market': {}})

    def _handle_economic(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/economic/* endpoints."""
        return json_response(200, {'economic': {}})

    def _handle_sentiment(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/sentiment/* endpoints."""
        return json_response(200, {'sentiment': {}})

    def _handle_commodities(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/commodities/* endpoints."""
        return json_response(200, {'commodities': {}})

    def _handle_scores(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/scores/* endpoints."""
        return json_response(200, {'scores': []})


def lambda_handler(event, context):
    """AWS Lambda handler for HTTP API Gateway proxy integration."""
    try:
        # Parse request
        path = event.get('rawPath', event.get('path', '/'))
        method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
        query_params = event.get('queryStringParameters') or {}

        logger.info(f"{method} {path}")

        # Route to handler
        handler = APIHandler()
        handler.connect()
        try:
            response = handler.route(path, method, query_params)
        finally:
            handler.disconnect()

        return response

    except Exception as e:
        logger.error(f"Lambda handler error: {e}", exc_info=True)
        return error_response(500, 'internal_error', str(e))
