"""
Stock Analytics Platform - API Lambda Handler

Serves HTTP API endpoints for the frontend dashboard.
Connects to RDS PostgreSQL database and returns JSON.

Endpoints:
- /api/algo/* — algo orchestrator status, positions, trades, performance
- /api/signals/* — trading signals (stocks, etfs)
- /api/prices/* — price history
- /api/stocks/* — stock screeners
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
import re
from datetime import datetime, timedelta, date, timezone
from typing import Dict, Any, Optional, List

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Module-level connection cache: Lambda containers are reused across warm invocations.
# Reusing the connection avoids ~100ms connection overhead and prevents exhausting
# the RDS connection limit under concurrent Lambda scaling.
_db_conn: Optional[Any] = None
_db_creds: Optional[Dict] = None  # cache Secrets Manager response to avoid per-call latency


def _load_creds() -> Dict:
    global _db_creds
    if _db_creds:
        return _db_creds
    db_secret_arn = os.getenv('DB_SECRET_ARN') or os.getenv('DATABASE_SECRET_ARN')
    if db_secret_arn:
        import boto3
        secrets = boto3.client('secretsmanager', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        response = secrets.get_secret_value(SecretId=db_secret_arn)
        _db_creds = json.loads(response['SecretString'])
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
        """Release cursor; keep connection alive for Lambda container reuse."""
        try:
            if self.cur:
                self.cur.close()
            # Do NOT close self.conn — it's the module-level cached connection.
            # Roll back any uncommitted transaction so next request starts clean.
            if self.conn and not self.conn.closed:
                self.conn.rollback()
        except Exception as e:
            logger.warning(f"Failed to release cursor: {e}")

    def route(self, path: str, method: str = 'GET', query_params: Dict = None, body: Dict = None) -> Dict:
        """Route request to appropriate handler."""
        query_params = query_params or {}
        body = body or {}

        try:
            # Health check
            if path == '/api/health':
                return json_response(200, {'status': 'healthy', 'timestamp': datetime.now(timezone.utc).isoformat()})

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
                return self._handle_industries(path, query_params)

            # Market endpoints
            if path.startswith('/api/market/'):
                return self._handle_market(path, method, query_params)

            # Economic endpoints
            if path == '/api/economic' or path.startswith('/api/economic/'):
                return self._handle_economic(path, method, query_params)

            # Sentiment endpoints
            if path.startswith('/api/sentiment/'):
                return self._handle_sentiment(path, method, query_params)

            # Commodities endpoints
            if path.startswith('/api/commodities/'):
                return self._handle_commodities(path, method, query_params)

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

            # Earnings endpoints (no real data source — return graceful empty)
            if path.startswith('/api/earnings/'):
                return json_response(200, {'data': [], 'total': 0, 'message': 'No earnings data available'})

            # Contact endpoints
            if path == '/api/contact' or path.startswith('/api/contact/'):
                return self._handle_contact(path, method, query_params)

            return error_response(404, 'not_found', f'No handler for {path}')

        except Exception as e:
            logger.error(f"Request failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', str(e))

    def _handle_algo(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/algo/* endpoints."""
        # Handle PATCH /api/algo/notifications/{id}/read
        if method == 'PATCH' and path.endswith('/read') and '/notifications/' in path:
            notif_id = path.split('/notifications/')[-1].replace('/read', '')
            try:
                self.cur.execute(
                    "UPDATE algo_notifications SET seen=TRUE, seen_at=NOW() WHERE id=%s",
                    (int(notif_id),)
                )
                self.conn.commit()
                return json_response(200, {'ok': True})
            except Exception as e:
                logger.error(f"notification mark-read error: {e}")
                return json_response(500, {'ok': False, 'error': 'Failed to update notification'})
        # Handle DELETE /api/algo/notifications/{id}
        if method == 'DELETE' and '/notifications/' in path:
            notif_id = path.split('/notifications/')[-1]
            try:
                self.cur.execute("DELETE FROM algo_notifications WHERE id=%s", (int(notif_id),))
                self.conn.commit()
                return json_response(200, {'ok': True})
            except Exception as e:
                logger.error(f"notification delete error: {e}")
                return json_response(500, {'ok': False, 'error': 'Failed to delete notification'})
        # Handle POST /api/algo/patrol
        if method == 'POST' and path == '/api/algo/patrol':
            logger.info("Manual patrol triggered via API")
            return json_response(200, {'ok': True, 'message': 'Patrol triggered'})
        if path == '/api/algo/status':
            return self._get_algo_status()
        elif path == '/api/algo/trades':
            limit = int(params.get('limit', [200])[0]) if params else 200
            return self._get_algo_trades(limit)
        elif path == '/api/algo/positions':
            return self._get_algo_positions()
        elif path == '/api/algo/performance':
            return self._get_algo_performance()
        elif path == '/api/algo/circuit-breakers':
            return self._get_circuit_breakers()
        elif path == '/api/algo/equity-curve':
            days = int(params.get('limit', [180])[0]) if params else 180
            return self._get_equity_curve(days)
        elif path == '/api/algo/data-status':
            return self._get_data_status()
        elif path == '/api/algo/notifications':
            return self._get_notifications()
        elif path == '/api/algo/patrol-log':
            limit = int(params.get('limit', [50])[0]) if params else 50
            return self._get_patrol_log(limit)
        elif path == '/api/algo/sector-rotation':
            days = int(params.get('limit', [180])[0]) if params else 180
            return self._get_sector_rotation(days)
        elif path == '/api/algo/sector-breadth':
            return self._get_sector_breadth()
        elif path == '/api/algo/swing-scores':
            limit = int(params.get('limit', [100])[0]) if params else 100
            return self._get_swing_scores(limit)
        elif path == '/api/algo/swing-scores-history':
            days = int(params.get('days', [30])[0]) if params else 30
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
            limit = int(params.get('limit', [100])[0]) if params else 100
            action_type = params.get('action_type', [None])[0] if params else None
            return self._get_algo_audit_log(limit, action_type)
        elif path == '/api/algo/signal-performance':
            days = int(params.get('days', [90])[0]) if params else 90
            return self._get_signal_performance(days)
        elif path == '/api/algo/signal-performance-by-pattern':
            days = int(params.get('days', [90])[0]) if params else 90
            return self._get_signal_performance_by_pattern(days)
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
            return error_response(500, 'database_error', str(e))

    def _get_algo_trades(self, limit: int = 200) -> Dict:
        """Get recent trades."""
        try:
            self.cur.execute("""
                SELECT trade_id, symbol, signal_date, trade_date, entry_price, entry_quantity,
                       exit_price, exit_date, exit_reason, profit_loss_pct, entry_reason,
                       status, created_at
                FROM algo_trades
                ORDER BY trade_date DESC, trade_id DESC
                LIMIT %s
            """, (limit,))
            trades = self.cur.fetchall()
            return json_response(200, [dict(t) for t in trades])
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
            return json_response(200, [dict(p) for p in positions])
        except Exception as e:
            logger.error(f"get_algo_positions failed: {e}")
            return error_response(500, 'database_error', str(e))

    def _get_algo_performance(self) -> Dict:
        """Get comprehensive algo performance metrics including Sharpe, Sortino, max drawdown."""
        try:
            import numpy as np
            self.cur.execute("""
                SELECT trade_id, symbol, entry_date, exit_date, entry_price, exit_price,
                       entry_quantity, profit_loss_dollars, profit_loss_pct,
                       EXTRACT(DAY FROM COALESCE(exit_date, CURRENT_DATE) - entry_date) as holding_days
                FROM algo_trades WHERE status IN ('closed', 'CLOSED') ORDER BY exit_date ASC
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
            winning, losing = sum(1 for p in pnls_dollars if p > 0), sum(1 for p in pnls_dollars if p < 0)
            total = len(trades)
            wins_sum, losses_sum = sum(p for p in pnls_dollars if p > 0), abs(sum(p for p in pnls_dollars if p < 0))
            profit_factor = (wins_sum / losses_sum) if losses_sum > 0 else 0.0
            daily_returns = np.array(pnls_pcts) / 100.0
            mean_ret, std_ret = float(np.mean(daily_returns)), float(np.std(daily_returns))
            sharpe = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 and len(daily_returns) > 1 else 0.0
            downside = np.array([r for r in daily_returns if r < 0])
            downside_vol = float(np.std(downside)) if len(downside) > 0 else 0.0
            sortino = (mean_ret / downside_vol * np.sqrt(252)) if downside_vol > 0 else 0.0
            cumulative, running_max = np.cumprod(1 + daily_returns), np.maximum.accumulate(np.cumprod(1 + daily_returns))
            max_dd = float(np.min((cumulative - running_max) / running_max)) if len(cumulative) > 0 else 0.0
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
                'portfolio_snapshots': 0
            })
        except Exception as e:
            logger.error(f"get_algo_performance failed: {e}", exc_info=True)
            return error_response(500, 'database_error', str(e))

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
                    checks = details.get('checks', {})
                    for name, state in checks.items():
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
            return error_response(500, 'database_error', f'Circuit breakers query failed: {str(e)}')

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
            return json_response(200, [dict(c) for c in reversed(curve) if c])
        except Exception as e:
            logger.error(f"Error fetching equity curve: {e}", exc_info=True)
            return json_response(500, {'error': 'Failed to fetch equity curve'})

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
                'as_of': datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            return error_response(500, 'database_error', str(e))

    def _get_notifications(self) -> Dict:
        """Get recent notifications."""
        try:
            self.cur.execute("""
                SELECT id, created_at, kind, severity, title, message
                FROM algo_notifications
                ORDER BY created_at DESC
                LIMIT 50
            """)
            notifs = self.cur.fetchall()
            return json_response(200, [dict(n) for n in notifs])
        except Exception as e:
            logger.error(f"Error fetching notifications: {e}", exc_info=True)
            return json_response(500, {'error': 'Failed to fetch notifications'})

    def _get_patrol_log(self, limit: int = 50) -> Dict:
        """Get data patrol findings."""
        try:
            self.cur.execute("""
                SELECT created_at, check_name, severity, target_table, message, patrol_run_id
                FROM data_patrol_log
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
            findings = self.cur.fetchall()
            return json_response(200, [dict(f) for f in findings])
        except Exception as e:
            logger.error(f"Error fetching patrol log: {e}", exc_info=True)
            return json_response(500, {'error': 'Failed to fetch patrol log'})

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
            return json_response(200, [dict(r) for r in rotation])
        except Exception as e:
            logger.error(f"Error fetching sector rotation: {e}", exc_info=True)
            return error_response(500, 'database_error', str(e))

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
            return json_response(200, [dict(b) for b in breadth])
        except Exception as e:
            logger.error(f"Error fetching sector breadth: {e}", exc_info=True)
            return error_response(500, 'database_error', str(e))

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
            return json_response(200, [dict(s) for s in scores])
        except Exception as e:
            logger.error(f"get_swing_scores failed: {e}")
            return error_response(500, 'database_error', str(e))

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
            return json_response(200, [dict(h) for h in history])
        except Exception as e:
            logger.error(f"get_swing_scores_history failed: {e}")
            return error_response(500, 'database_error', str(e))

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
            return json_response(200, [dict(f) for f in funnel])
        except Exception as e:
            logger.error(f"Error fetching rejection funnel: {e}", exc_info=True)
            return error_response(500, 'database_error', str(e))

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
            return json_response(200, [dict(m) for m in markets])
        except Exception as e:
            logger.error(f"Error fetching markets data: {e}", exc_info=True)
            return error_response(500, 'database_error', str(e))

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
            return error_response(500, 'database_error', f'Algorithm evaluation query failed: {str(e)}')

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
            return error_response(500, 'database_error', f'Data quality check query failed: {str(e)}')

    def _get_exposure_policy(self) -> Dict:
        """Get latest market exposure from market_exposure_daily."""
        try:
            self.cur.execute("""
                SELECT date, exposure_pct, regime, raw_score, distribution_days, factors, halt_reasons
                FROM market_exposure_daily
                ORDER BY date DESC
                LIMIT 1
            """)
            row = self.cur.fetchone()
            if not row:
                return json_response(200, {'current_exposure': None, 'exposure_tier': None})
            regime = row.get('regime', 'caution')
            regime_tier_map = {
                'bull': 'tier_1_strong_uptrend',
                'uptrend': 'tier_1_strong_uptrend',
                'pressure': 'tier_2_pressure',
                'caution': 'tier_3_caution',
                'correction': 'tier_4_correction',
                'bear': 'tier_4_correction',
            }
            exposure_tier = regime_tier_map.get(regime, 'tier_3_caution')
            halt_reasons = json.loads(row.get('halt_reasons') or '[]') if row.get('halt_reasons') else []
            is_entry_allowed = len(halt_reasons) == 0
            return json_response(200, {
                'current_exposure': float(row['exposure_pct'] or 0),
                'exposure_tier': exposure_tier,
                'is_entry_allowed': is_entry_allowed,
                'regime': regime,
                'raw_score': float(row.get('raw_score') or 0),
                'distribution_days': row.get('distribution_days', 0),
                'halt_reasons': halt_reasons,
                'as_of': row['date'].isoformat() if row['date'] else None,
            })
        except Exception as e:
            logger.error(f"get_exposure_policy failed: {e}", exc_info=True)
            return error_response(500, 'database_error', f'Exposure policy query failed: {str(e)}')

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
            return json_response(200, [dict(r) for r in rows])
        except Exception as e:
            logger.error(f"get_sector_stage2 failed: {e}")
            return error_response(500, 'database_error', str(e))

    def _get_algo_config(self) -> Dict:
        """Return all algo configuration rows."""
        try:
            self.cur.execute("SELECT key, value, value_type, description, updated_at FROM algo_config ORDER BY key")
            rows = self.cur.fetchall()
            return json_response(200, [dict(r) for r in rows])
        except Exception as e:
            logger.error(f"algo_config error: {e}")
            return error_response(500, 'database_error', str(e))

    def _get_algo_config_key(self, key: str) -> Dict:
        """Return a single algo config key."""
        try:
            self.cur.execute("SELECT key, value, value_type, description, updated_at FROM algo_config WHERE key = %s", (key,))
            row = self.cur.fetchone()
            return json_response(200, dict(row) if row else {})
        except Exception as e:
            logger.error(f"algo_config_key error: {e}", exc_info=True)
            return error_response(500, 'internal_error', f'Config key error: {str(e)}')

    def _get_algo_audit_log(self, limit: int = 100, action_type: str = None) -> Dict:
        """Return algo audit log entries."""
        try:
            if action_type:
                self.cur.execute("""
                    SELECT id, action_type, symbol, action_date, details, actor, status, error_message
                    FROM algo_audit_log
                    WHERE action_type = %s
                    ORDER BY action_date DESC
                    LIMIT %s
                """, (action_type, limit))
            else:
                self.cur.execute("""
                    SELECT id, action_type, symbol, action_date, details, actor, status, error_message
                    FROM algo_audit_log
                    ORDER BY action_date DESC
                    LIMIT %s
                """, (limit,))
            rows = self.cur.fetchall()
            return json_response(200, {'data': [dict(r) for r in rows], 'total': len(rows)})
        except Exception as e:
            logger.error(f"algo_audit_log error: {e}", exc_info=True)
            return error_response(500, 'internal_error', f'Audit log error: {str(e)}')

    def _get_signal_performance(self, days: int = 90) -> Dict:
        """Return signal trade performance summary."""
        try:
            self.cur.execute("""
                SELECT
                    COUNT(*) as total_signals,
                    SUM(CASE WHEN win THEN 1 ELSE 0 END) as wins,
                    AVG(r_multiple) as avg_r_multiple,
                    AVG(hold_days) as avg_hold_days,
                    AVG(realized_pnl_pct) as avg_pnl_pct,
                    SUM(CASE WHEN target_1_hit THEN 1 ELSE 0 END) as target_1_hits,
                    SUM(CASE WHEN target_2_hit THEN 1 ELSE 0 END) as target_2_hits,
                    SUM(CASE WHEN exit_by_stop THEN 1 ELSE 0 END) as stop_exits
                FROM signal_trade_performance
                WHERE signal_date >= CURRENT_DATE - (%s * INTERVAL '1 day')
            """, (days,))
            summary = self.cur.fetchone()
            self.cur.execute("""
                SELECT signal_date, symbol, base_type, swing_score, entry_price,
                       exit_price, r_multiple, win, hold_days, realized_pnl_pct
                FROM signal_trade_performance
                WHERE signal_date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                ORDER BY signal_date DESC
                LIMIT 200
            """, (days,))
            trades = self.cur.fetchall()
            return json_response(200, {
                'summary': dict(summary) if summary else {},
                'trades': [dict(t) for t in trades],
            })
        except Exception as e:
            logger.error(f"signal_performance error: {e}", exc_info=True)
            return error_response(500, 'internal_error', f'Signal performance error: {str(e)}')

    def _get_signal_performance_by_pattern(self, days: int = 90) -> Dict:
        """Return signal performance grouped by base_type (pattern)."""
        try:
            self.cur.execute("""
                SELECT
                    base_type,
                    COUNT(*) as total,
                    SUM(CASE WHEN win THEN 1 ELSE 0 END) as wins,
                    ROUND(AVG(r_multiple)::numeric, 2) as avg_r,
                    ROUND(AVG(realized_pnl_pct)::numeric, 4) as avg_pnl_pct,
                    ROUND(AVG(hold_days)::numeric, 1) as avg_hold_days
                FROM signal_trade_performance
                WHERE signal_date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                  AND base_type IS NOT NULL
                GROUP BY base_type
                ORDER BY avg_r DESC
            """, (days,))
            rows = self.cur.fetchall()
            return json_response(200, [dict(r) for r in rows])
        except Exception as e:
            logger.error(f"signal_performance_by_pattern error: {e}", exc_info=True)
            return error_response(500, 'internal_error', f'Signal performance pattern error: {str(e)}')

    def _handle_financials(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/financials/{symbol}/* endpoints."""
        try:
            parts = path.split('/')
            if len(parts) < 4:
                return error_response(400, 'invalid_path', 'Path must include symbol: /api/financials/{symbol}/{endpoint}')
            symbol = parts[3].upper()
            endpoint = parts[4] if len(parts) > 4 else None
            if not endpoint:
                return error_response(400, 'invalid_path', 'Path must include endpoint (income-statement, balance-sheet, cash-flow, key-metrics)')
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
                return json_response(200, [dict(r) for r in rows])

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
                return json_response(200, [dict(r) for r in rows])

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
                return json_response(200, [dict(r) for r in rows])

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

            return error_response(400, 'invalid_endpoint', f'Unknown financial endpoint: {endpoint}. Valid: income-statement, balance-sheet, cash-flow, key-metrics')
        except Exception as e:
            logger.error(f"financials handler error: {e}", exc_info=True)
            return error_response(500, 'internal_error', f'Financials handler error: {str(e)}')

    def _handle_signals(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/signals/* endpoints."""
        if path == '/api/signals/stocks':
            limit = int(params.get('limit', [500])[0]) if params else 500
            timeframe = params.get('timeframe', ['daily'])[0] if params else 'daily'
            return self._get_signals_stocks(limit, timeframe)
        elif path == '/api/signals/etf':
            limit = int(params.get('limit', [500])[0]) if params else 500
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
                    COALESCE(td.ema_21, 0) as ema_21,
                    COALESCE(tt.stage, 'unknown') as market_stage,
                    COALESCE(tt.trend, 'unknown') as trend,
                    ss.company_name, cp.sector, cp.industry,
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
            return json_response(200, [dict(s) for s in signals])
        except Exception as e:
            logger.error(f"get_signals_stocks failed: {e}", exc_info=True)
            return json_response(500, {'error': 'Failed to fetch signals', 'detail': str(e)})

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
                    COALESCE(tt.stage, 'unknown') as market_stage,
                    COALESCE(cp.company_name, bsd.symbol) as company_name
                FROM buy_sell_daily_etf bsd
                LEFT JOIN technical_data_daily td ON bsd.symbol = td.symbol
                    AND bsd.date = td.date
                LEFT JOIN trend_template_data tt ON bsd.symbol = tt.symbol
                    AND bsd.date = tt.date
                LEFT JOIN company_profile cp ON bsd.symbol = cp.ticker
                WHERE bsd.date >= CURRENT_DATE - INTERVAL '90 days'
                AND bsd.symbol IN ('SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EFA')
                ORDER BY bsd.signal_triggered_date DESC
                LIMIT %s
            """, (limit,))
            signals = self.cur.fetchall()
            return json_response(200, [dict(s) for s in signals])
        except Exception as e:
            logger.error(f"get_signals_etf failed: {e}")
            return error_response(500, 'internal_error', f'Signals ETF error: {str(e)}')

    def _handle_prices(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/prices/* endpoints."""
        match = re.match(r'/api/prices/history/([A-Z0-9.]+)', path)
        if match:
            symbol = match.group(1)
            timeframe = params.get('timeframe', ['daily'])[0] if params else 'daily'
            limit = int(params.get('limit', [60])[0]) if params else 60
            return self._get_price_history(symbol, timeframe, limit)
        else:
            return error_response(404, 'not_found', f'Invalid prices endpoint: {path}')

    def _get_price_history(self, symbol: str, timeframe: str = 'daily', limit: int = 60) -> Dict:
        """Get price history for a symbol."""
        try:
            self.cur.execute("""
                SELECT date, open, high, low, close, volume
                FROM price_daily
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT %s
            """, (symbol.upper(), limit))
            prices = self.cur.fetchall()
            return json_response(200, [dict(p) for p in reversed(prices)])
        except Exception as e:
            logger.error(f"get_price_history failed: {e}")
            return error_response(500, 'internal_error', f'Price history error: {str(e)}')

    def _handle_stocks(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/stocks and /api/stocks/* endpoints."""
        if path == '/api/stocks/deep-value':
            limit = int(params.get('limit', [600])[0]) if params else 600
            return self._get_deep_value_stocks(limit)
        elif path == '/api/stocks' or path == '/api/stocks/list':
            limit = int(params.get('limit', [100])[0]) if params else 100
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
                return json_response(200, [dict(s) for s in stocks])
            except Exception as e:
                logger.error(f"stocks list error: {e}")
                return error_response(500, 'database_error', str(e))
        elif path.startswith('/api/stocks/'):
            symbol = path.split('/api/stocks/')[-1]
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
                return error_response(500, 'database_error', str(e))
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
                    sc.value_score
                FROM stock_scores sc
                JOIN stock_symbols ss ON ss.symbol = sc.symbol
                LEFT JOIN company_profile cp ON cp.ticker = sc.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
                LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
                LEFT JOIN LATERAL (
                    SELECT close FROM price_daily
                    WHERE symbol = sc.symbol ORDER BY date DESC LIMIT 1
                ) pd_latest ON true
                WHERE sc.value_score > 0
                ORDER BY sc.value_score DESC
                LIMIT %s
            """, (limit,))
            stocks = self.cur.fetchall()
            return json_response(200, [dict(s) for s in stocks])
        except Exception as e:
            logger.error(f"get_deep_value_stocks failed: {e}")
            return error_response(500, 'database_error', str(e))

    def _handle_portfolio(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/portfolio/* endpoints."""
        try:
            if path == '/api/portfolio/summary':
                self.cur.execute("SELECT SUM(position_value) as total FROM algo_positions WHERE status='open'")
                row = self.cur.fetchone()
                total = float(row['total'] or 0) if row else 0
                return json_response(200, {'total_value': total, 'cash': 0, 'exposure': 0.75})
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
                return json_response(200, [dict(a) for a in alloc])
            return error_response(500, 'database_error', str(e))
        except Exception as e:
            logger.error(f"Error in portfolio allocation handler: {e}", exc_info=True)
            return error_response(500, 'database_error', str(e))

    def _handle_sectors(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/sectors and /api/sectors/* endpoints."""
        try:
            if path in ('/api/sectors', '/api/sectors/performance'):
                limit = int(params.get('limit', [20])[0]) if params else 20
                page = int(params.get('page', [1])[0]) if params else 1
                offset = (page - 1) * limit
                self.cur.execute("""
                    SELECT sector,
                           AVG(return_pct) as avg_return_pct,
                           AVG(relative_strength) as avg_relative_strength
                    FROM sector_performance
                    WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                    GROUP BY sector
                    ORDER BY avg_return_pct DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                sectors = self.cur.fetchall()
                self.cur.execute("""
                    SELECT COUNT(DISTINCT sector) FROM sector_performance
                    WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                """)
                total = self.cur.fetchone()[0]
                return json_response(200, {
                    'data': [dict(s) for s in sectors],
                    'total': total,
                    'page': page,
                    'limit': limit,
                })
            elif '/trend' in path:
                # /api/sectors/{name}/trend
                parts = path.split('/')
                sector_name = parts[3] if len(parts) > 3 else None
                days = int(params.get('days', [90])[0]) if params else 90
                if not sector_name:
                    return error_response(500, 'database_error', str(e))
                self.cur.execute("""
                    SELECT date, sector, return_pct, relative_strength
                    FROM sector_performance
                    WHERE sector = %s AND date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                    ORDER BY date DESC
                """, (sector_name, days))
                rows = self.cur.fetchall()
                return json_response(200, [dict(r) for r in rows])
            return json_response(200, {'data': [], 'total': 0, 'page': 1, 'limit': 20})
        except Exception as e:
            logger.error(f"Error in sectors handler: {e}", exc_info=True)
            return error_response(500, 'database_error', f'Sectors query failed: {str(e)}')

    def _handle_industries(self, path: str, params: Dict) -> Dict:
        """Handle /api/industries and /api/industries/{name}/trend."""
        try:
            if '/trend' in path:
                parts = path.split('/')
                industry_name = parts[3] if len(parts) > 3 else None
                days = int(params.get('days', [90])[0]) if params else 90
                if not industry_name:
                    return error_response(500, 'database_error', str(e))
                self.cur.execute("""
                    SELECT date, industry, return_pct
                    FROM industry_performance
                    WHERE industry = %s AND date >= CURRENT_DATE - (%s * INTERVAL '1 day')
                    ORDER BY date DESC
                """, (industry_name, days))
                rows = self.cur.fetchall()
                return json_response(200, [dict(r) for r in rows])
            else:
                limit = int(params.get('limit', [500])[0]) if params else 500
                self.cur.execute("""
                    SELECT DISTINCT industry, sector,
                           COUNT(*) as stock_count
                    FROM company_profile
                    WHERE industry IS NOT NULL AND industry != ''
                    GROUP BY industry, sector
                    ORDER BY sector, industry
                    LIMIT %s
                """, (limit,))
                rows = self.cur.fetchall()
                return json_response(200, [dict(r) for r in rows])
        except Exception as e:
            logger.error(f"Error in industries handler: {e}", exc_info=True)
            return error_response(500, 'database_error', str(e))

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
                return json_response(200, [dict(b) for b in breadth])
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
                    SELECT t.symbol, ss.company_name,
                           ROUND(((t.close - y.close) / NULLIF(y.close, 0) * 100)::numeric, 2) as pct_change
                    FROM today t
                    JOIN yesterday y ON t.symbol = y.symbol
                    LEFT JOIN stock_symbols ss ON t.symbol = ss.symbol
                    WHERE y.close > 0
                    ORDER BY ABS(t.close - y.close) / y.close DESC
                    LIMIT 20
                """)
                movers = self.cur.fetchall()
                return json_response(200, [dict(m) for m in movers] if movers else [])
            elif path == '/api/market/distribution-days':
                self.cur.execute("""
                    SELECT symbol, date, distribution_count
                    FROM distribution_days
                    ORDER BY date DESC
                    LIMIT 50
                """)
                dist = self.cur.fetchall()
                return json_response(200, [dict(d) for d in dist] if dist else [])
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
                range_days = int(params.get('range', ['30d'])[0].replace('d', '')) if params else 30
                self.cur.execute("""
                    SELECT date, fear_greed_index as value
                    FROM market_sentiment
                    WHERE date >= CURRENT_DATE - INTERVAL '%s days'
                    ORDER BY date DESC
                """, (range_days,))
                sentiment = self.cur.fetchall()
                return json_response(200, [dict(s) for s in sentiment] if sentiment else [])
            elif path == '/api/market/fear-greed':
                range_days = int(params.get('range', ['30d'])[0].replace('d', '')) if params else 30
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
                return json_response(200, [dict(r) for r in rows] if rows else [])
            return error_response(500, 'database_error', str(e))
        except Exception as e:
            logger.error(f"market handler error: {e}")
            return error_response(500, 'database_error', str(e))

    def _get_fear_greed_history(self, days: int = 30) -> Dict:
        """Get fear/greed index history."""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            self.cur.execute("""
                SELECT date, fear_greed_index as value, label
                FROM market_sentiment
                WHERE date >= %s
                ORDER BY date DESC
            """, (cutoff_date,))
            history = self.cur.fetchall()
            return json_response(200, [dict(h) for h in history] if history else [])
        except Exception as e:
            logger.error(f"Error fetching sentiment history: {e}", exc_info=True)
            return error_response(500, 'database_error', str(e))

    def _handle_economic(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/economic and /api/economic/* endpoints."""
        try:
            if path == '/api/economic/leading-indicators':
                return self._get_leading_indicators()
            elif path == '/api/economic/yield-curve-full':
                return self._get_yield_curve_full()
            elif path == '/api/economic/calendar':
                self.cur.execute("""
                    SELECT date, event_name, country, importance, forecast, actual, previous
                    FROM economic_calendar
                    ORDER BY date DESC
                    LIMIT 100
                """)
                events = self.cur.fetchall()
                return json_response(200, [dict(e) for e in events] if events else [])
            elif path == '/api/economic':
                # Combine all economic data
                return self._get_leading_indicators()
            return error_response(404, 'not_found', f'No economic handler for {path}')
        except Exception as e:
            logger.error(f"Error in economic handler: {e}", exc_info=True)
            return error_response(500, 'database_error', str(e))

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
            'DFF': 'Federal Funds Rate',
            'MMNRNJ': 'MZM Money Stock',
            'T10Y2Y': 'Yield Curve (10Y-2Y)',
        }

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

                # Calculate trend (up/down/flat)
                if len(history) >= 2:
                    recent_avg = sum([h['value'] for h in history[:3] if h['value']] or [0]) / max(1, len([h for h in history[:3] if h['value']]))
                    older_avg = sum([h['value'] for h in history[-3:] if h['value']] or [0]) / max(1, len([h for h in history[-3:] if h['value']]))
                    if older_avg and recent_avg:
                        trend = 'up' if recent_avg > older_avg * 1.01 else 'down' if recent_avg < older_avg * 0.99 else 'flat'
                    else:
                        trend = 'flat'
                else:
                    trend = 'flat'

                indicators.append({
                    'name': name,
                    'series_id': series_id,
                    'rawValue': value,
                    'date': str(date),
                    'history': history,
                    'trend': trend
                })

            return json_response(200, {'indicators': indicators})

        except Exception as e:
            logger.error(f"get_leading_indicators error: {e}", exc_info=True)
            return error_response(500, 'database_error', f'Leading indicators query failed: {str(e)}')

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
            return error_response(500, 'database_error', f'Yield curve query failed: {str(e)}')

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
                limit = int(params.get('limit', [5000])[0]) if params else 5000
                page = int(params.get('page', [1])[0]) if params else 1
                offset = (page - 1) * limit
                self.cur.execute("""
                    SELECT date, fear_greed_index, put_call_ratio, vix, sentiment_score
                    FROM market_sentiment
                    ORDER BY date DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                sentiment = self.cur.fetchall()
                return json_response(200, [dict(s) for s in sentiment] if sentiment else [])
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
                return json_response(200, [dict(r) for r in rows] if rows else [])
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
                return json_response(200, [dict(r) for r in rows] if rows else [])
            elif path.startswith('/api/sentiment/social/insights/'):
                symbol = path.split('/api/sentiment/social/insights/')[-1].upper()
                self.cur.execute("""
                    SELECT date, twitter_sentiment_score, reddit_sentiment_score,
                           stocktwits_sentiment_score, overall_sentiment_score,
                           twitter_mention_count, reddit_mention_count,
                           stocktwits_mention_count
                    FROM sentiment_social
                    WHERE symbol = %s
                    ORDER BY date DESC
                    LIMIT 30
                """, (symbol,))
                rows = self.cur.fetchall()
                return json_response(200, [dict(r) for r in rows] if rows else [])
            return error_response(404, 'not_found', f'No sentiment handler for {path}')
        except Exception as e:
            logger.error(f"Error in sentiment handler: {e}", exc_info=True)
            return error_response(500, 'internal_error', f'Sentiment handler error: {str(e)}')

    def _handle_commodities(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/commodities/* endpoints."""
        try:
            if path == '/api/commodities/prices':
                limit = int(params.get('limit', [50])[0]) if params else 50
                self.cur.execute("""
                    SELECT symbol, name, price, date
                    FROM commodity_prices
                    ORDER BY symbol
                    LIMIT %s
                """, (limit,))
                rows = self.cur.fetchall()
                return json_response(200, [dict(r) for r in rows] if rows else [])
            elif path == '/api/commodities/categories':
                self.cur.execute("SELECT category, symbols FROM commodity_categories ORDER BY category")
                rows = self.cur.fetchall()
                return json_response(200, [dict(r) for r in rows] if rows else [])
            elif path == '/api/commodities/correlations':
                self.cur.execute("""
                    SELECT symbol1, symbol2, correlation_30d, correlation_90d, correlation_1y
                    FROM commodity_correlations
                    ORDER BY ABS(correlation_90d) DESC
                """)
                rows = self.cur.fetchall()
                return json_response(200, [dict(r) for r in rows] if rows else [])
            elif path == '/api/commodities/events':
                self.cur.execute("""
                    SELECT event_name, event_date, event_type, description, impact
                    FROM commodity_events
                    ORDER BY event_date DESC
                    LIMIT 50
                """)
                rows = self.cur.fetchall()
                return json_response(200, [dict(r) for r in rows] if rows else [])
            elif path == '/api/commodities/macro':
                self.cur.execute("""
                    SELECT DISTINCT ON (series_id) series_id, series_name, date, value
                    FROM commodity_macro_drivers
                    ORDER BY series_id, date DESC
                """)
                rows = self.cur.fetchall()
                return json_response(200, [dict(r) for r in rows] if rows else [])
            elif path == '/api/commodities/market-summary':
                self.cur.execute("""
                    SELECT cp.symbol, cp.name, cp.price, cp.date,
                           cph.open, cph.high, cph.low, cph.close, cph.volume
                    FROM commodity_prices cp
                    LEFT JOIN commodity_price_history cph
                        ON cph.symbol = cp.symbol
                        AND cph.date = cp.date
                    ORDER BY cp.symbol
                """)
                rows = self.cur.fetchall()
                return json_response(200, [dict(r) for r in rows] if rows else [])
            elif path.startswith('/api/commodities/technicals/'):
                symbol = path.split('/api/commodities/technicals/')[-1].upper()
                self.cur.execute("""
                    SELECT date, rsi, macd, macd_signal, sma_20, sma_50, sma_200,
                           bb_upper, bb_lower, atr, signal
                    FROM commodity_technicals
                    WHERE symbol = %s
                    ORDER BY date DESC
                    LIMIT 60
                """, (symbol,))
                rows = self.cur.fetchall()
                return json_response(200, [dict(r) for r in rows] if rows else [])
            elif path.startswith('/api/commodities/seasonality/'):
                symbol = path.split('/api/commodities/seasonality/')[-1].upper()
                self.cur.execute("""
                    SELECT month, avg_return, win_rate, volatility, num_years
                    FROM commodity_seasonality
                    WHERE symbol = %s
                    ORDER BY month
                """, (symbol,))
                rows = self.cur.fetchall()
                return json_response(200, [dict(r) for r in rows] if rows else [])
            elif path.startswith('/api/commodities/cot/'):
                symbol = path.split('/api/commodities/cot/')[-1].upper()
                self.cur.execute("""
                    SELECT date, commercial_long, commercial_short,
                           non_commercial_long, non_commercial_short
                    FROM cot_data
                    WHERE symbol = %s
                    ORDER BY date DESC
                    LIMIT 52
                """, (symbol,))
                rows = self.cur.fetchall()
                return json_response(200, [dict(r) for r in rows] if rows else [])
            return error_response(404, 'not_found', f'No commodities handler for {path}')
        except Exception as e:
            logger.error(f"Error in commodities handler: {e}", exc_info=True)
            return error_response(500, 'internal_error', f'Commodities handler error: {str(e)}')

    def _handle_scores(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/scores/* endpoints."""
        if path == '/api/scores/stockscores' or path.startswith('/api/scores/stockscores?'):
            limit = int(params.get('limit', [5000])[0]) if params else 5000
            offset = int(params.get('offset', [0])[0]) if params else 0
            sort_by = params.get('sortBy', ['composite_score'])[0] if params else 'composite_score'
            sort_order = params.get('sortOrder', ['desc'])[0] if params else 'desc'
            sp500_only = params.get('sp500Only', ['false'])[0] if params else 'false'
            symbol = params.get('symbol', [None])[0] if params else None
            return self._get_stock_scores(limit, offset, sort_by, sort_order, sp500_only == 'true', symbol)
        else:
            return error_response(404, 'not_found', f'No scores handler for {path}')

    def _get_stock_scores(self, limit: int = 5000, offset: int = 0, sort_by: str = 'composite_score',
                         sort_order: str = 'desc', sp500_only: bool = False, symbol: str = None) -> Dict:
        """Get stock scores with multi-factor ranking."""
        try:
            allowed_sorts = [
                'composite_score', 'momentum_score', 'quality_score', 'value_score',
                'growth_score', 'positioning_score', 'stability_score', 'symbol'
            ]
            if sort_by not in allowed_sorts:
                sort_by = 'composite_score'
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
                    cp.market_cap,
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
                LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
                LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
                LEFT JOIN LATERAL (
                    SELECT close FROM price_daily
                    WHERE symbol = sc.symbol ORDER BY date DESC LIMIT 1
                ) pd ON true
                LEFT JOIN LATERAL (
                    SELECT close FROM price_daily
                    WHERE symbol = sc.symbol AND date < (SELECT MAX(date) FROM price_daily WHERE symbol = sc.symbol)
                    ORDER BY date DESC LIMIT 1
                ) pd_prev ON true
                {where_clause}
                ORDER BY sc.{sort_by} {sort_direction}
                LIMIT %s OFFSET %s
            """
            params_list.extend([limit, offset])
            self.cur.execute(query, params_list)
            scores = self.cur.fetchall()
            return json_response(200, [dict(s) for s in scores])
        except Exception as e:
            logger.error(f"get_stock_scores failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', f'Stock scores error: {str(e)}')



    def _handle_research(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/research/* endpoints."""
        try:
            if path == '/api/research/backtests' or path.startswith('/api/research/backtests?'):
                limit = int(params.get('limit', [50])[0]) if params else 50
                self.cur.execute("""
                    SELECT run_id AS id, strategy_name, start_date, end_date, total_return,
                           sharpe_ratio, max_drawdown, win_rate, num_trades AS total_trades
                    FROM backtest_runs
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                backtests = self.cur.fetchall()
                return json_response(200, [dict(b) for b in backtests] if backtests else [])
            return error_response(404, 'not_found', f'No research handler for {path}')
        except Exception as e:
            logger.error(f"get_backtests failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', f'Research handler error: {str(e)}')


    def _handle_audit(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/audit/* endpoints."""
        try:
            if path == '/api/audit/trail' or path.startswith('/api/audit/trail?'):
                limit = int(params.get('limit', [100])[0]) if params else 100
                self.cur.execute("""
                    SELECT id, created_at AS timestamp, action_type AS action,
                           actor AS user_id, status, details
                    FROM algo_audit_log
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                audits = self.cur.fetchall()
                return json_response(200, [dict(a) for a in audits] if audits else [])
            return error_response(404, 'not_found', f'No audit handler for {path}')
        except Exception as e:
            logger.error(f"Error in audit handler: {e}", exc_info=True)
            return error_response(500, 'internal_error', f'Audit handler error: {str(e)}')

    def _handle_trades(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/trades and /api/trades/* endpoints."""
        try:
            if path == '/api/trades':
                limit = int(params.get('limit', [100])[0]) if params else 100
                offset = int(params.get('offset', [0])[0]) if params else 0
                status_filter = params.get('status', [None])[0] if params else None
                query = """
                    SELECT trade_id, symbol, signal_date, trade_date, entry_time,
                           entry_price, entry_quantity, entry_reason,
                           exit_price, exit_date, exit_reason,
                           stop_loss_price, status, realized_pnl, realized_pnl_pct,
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
                self.cur.execute("SELECT COUNT(*) FROM algo_trades" + (" WHERE status = %s" if status_filter else ""), ([status_filter] if status_filter else []))
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
            return error_response(500, 'database_error', str(e))
        except Exception as e:
            logger.error(f"Error in trades handler: {e}", exc_info=True)
            return error_response(500, 'database_error', str(e))


    def _handle_contact(self, path: str, method: str, params: Dict) -> Dict:
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
                return json_response(200, [dict(r) for r in rows])
            elif path == '/api/contact' and method == 'POST':
                return json_response(200, {'ok': True, 'message': 'Contact form submission received'})
            return error_response(500, 'database_error', str(e))
        except Exception as e:
            logger.error(f"contact handler error: {e}")
            return error_response(500, 'database_error', str(e))


def lambda_handler(event, context):
    """AWS Lambda handler for HTTP API Gateway proxy integration."""
    try:
        # Parse request
        path = event.get('rawPath', event.get('path', '/'))
        method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
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
        return error_response(500, 'internal_error', str(e))
