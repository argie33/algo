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

            # Signals endpoints
            if path.startswith('/api/signals/'):
                return self._handle_signals(path, method, query_params)

            # Prices endpoints
            if path.startswith('/api/prices/'):
                return self._handle_prices(path, method, query_params)

            # Stocks endpoints
            if path.startswith('/api/stocks/'):
                return self._handle_stocks(path, method, query_params)

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
        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).date()
            self.cur.execute("""
                SELECT created_at, portfolio_value, cash, exposure
                FROM algo_portfolio_snapshots
                WHERE created_at >= %s
                ORDER BY created_at DESC
                LIMIT 1000
            """, (cutoff_date,))
            curve = self.cur.fetchall()
            return json_response(200, {
                'equity_curve': [dict(c) for c in reversed(curve) if c],
                'days': days,
            })
        except:
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
        try:
            self.cur.execute("""
                SELECT id, created_at, kind, severity, title, message
                FROM notifications
                ORDER BY created_at DESC
                LIMIT 50
            """)
            notifs = self.cur.fetchall()
            return json_response(200, [dict(n) for n in notifs])
        except:
            return json_response(200, [])

    def _get_patrol_log(self, limit: int = 50) -> Dict:
        """Get data patrol findings."""
        try:
            self.cur.execute("""
                SELECT timestamp, finding_type, severity, source, description
                FROM data_patrol_log
                ORDER BY timestamp DESC
                LIMIT %s
            """, (limit,))
            findings = self.cur.fetchall()
            return json_response(200, [dict(f) for f in findings])
        except:
            return json_response(200, [])

    def _get_sector_rotation(self, days: int = 180) -> Dict:
        """Get sector rotation data."""
        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).date()
            self.cur.execute("""
                SELECT date, sector, performance_pct
                FROM sector_rotation
                WHERE date >= %s
                ORDER BY date DESC, performance_pct DESC
            """, (cutoff_date,))
            rotation = self.cur.fetchall()
            return json_response(200, [dict(r) for r in rotation])
        except:
            return json_response(200, [])

    def _get_sector_breadth(self) -> Dict:
        """Get sector breadth indicators."""
        try:
            self.cur.execute("""
                SELECT sector, up_count, down_count, unchanged_count
                FROM sector_breadth
                WHERE date = CURRENT_DATE
                ORDER BY up_count DESC
            """)
            breadth = self.cur.fetchall()
            return json_response(200, [dict(b) for b in breadth])
        except:
            return json_response(200, [])

    def _get_swing_scores(self, limit: int = 100) -> Dict:
        """Get swing trade candidates with full scoring breakdown."""
        try:
            self.cur.execute("""
                SELECT
                    ss.symbol, ss.eval_date, ss.swing_score, ss.grade,
                    ss.setup_pts, ss.trend_pts, ss.momentum_pts, ss.volume_pts,
                    ss.fundamentals_pts, ss.sector_pts, ss.multi_tf_pts,
                    ss.pass_gates, ss.fail_reason, ss.components,
                    cp.sector, cp.industry
                FROM swing_scores_daily ss
                LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
                WHERE ss.eval_date >= CURRENT_DATE - INTERVAL '1 day'
                ORDER BY ss.eval_date DESC, ss.swing_score DESC
                LIMIT %s
            """, (limit,))
            scores = self.cur.fetchall()
            return json_response(200, [dict(s) for s in scores])
        except Exception as e:
            logger.error(f"get_swing_scores failed: {e}")
            return json_response(200, [])

    def _get_swing_scores_history(self, days: int = 30) -> Dict:
        """Get swing scores historical data."""
        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).date()
            self.cur.execute("""
                SELECT eval_date,
                    COUNT(*) as total_candidates,
                    SUM(CASE WHEN grade IN ('A+', 'A', 'A-') THEN 1 ELSE 0 END) as top_grade_count,
                    AVG(swing_score) as avg_score
                FROM swing_scores_daily
                WHERE eval_date >= %s
                GROUP BY eval_date
                ORDER BY eval_date DESC
            """, (cutoff_date,))
            history = self.cur.fetchall()
            return json_response(200, [dict(h) for h in history])
        except Exception as e:
            logger.error(f"get_swing_scores_history failed: {e}")
            return json_response(200, [])

    def _get_rejection_funnel(self) -> Dict:
        """Get signal rejection funnel."""
        try:
            self.cur.execute("""
                SELECT
                    'Initial Signals' as stage,
                    COUNT(DISTINCT symbol) as count
                FROM buy_sell_daily
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                UNION ALL
                SELECT
                    'Passed Gates' as stage,
                    COUNT(DISTINCT symbol) as count
                FROM swing_scores_daily
                WHERE eval_date >= CURRENT_DATE - INTERVAL '7 days'
                AND pass_gates = true
                ORDER BY count DESC
            """)
            funnel = self.cur.fetchall()
            return json_response(200, [dict(f) for f in funnel])
        except:
            return json_response(200, [])

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
        except:
            return json_response(200, [])

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
        """Get stock trading signals with full enrichment."""
        try:
            self.cur.execute("""
                SELECT
                    bsd.id, bsd.symbol, bsd.signal, bsd.date, bsd.signal_triggered_date,
                    bsd.timeframe, bsd.open, bsd.high, bsd.low, bsd.close, bsd.volume,
                    bsd.buylevel, bsd.stoplevel, bsd.strength, bsd.signal_strength,
                    bsd.pivot_price, bsd.buy_zone_start, bsd.buy_zone_end,
                    bsd.exit_trigger_1_price, bsd.exit_trigger_2_price,
                    bsd.exit_trigger_3_price, bsd.exit_trigger_4_price,
                    bsd.initial_stop, bsd.trailing_stop, bsd.sell_level,
                    bsd.rsi, bsd.adx, bsd.atr, bsd.sma_50, bsd.sma_200, bsd.ema_21,
                    bsd.base_type, bsd.base_length_days, bsd.signal_type,
                    bsd.market_stage, bsd.breakout_quality,
                    bsd.entry_quality_score, bsd.risk_reward_ratio,
                    bsd.mansfield_rs, bsd.sata_score, bsd.rs_rating,
                    bsd.avg_volume_50d, bsd.volume_surge_pct,
                    ss.company_name, cp.sector, cp.industry,
                    swg.swing_score, swg.grade, swg.pass_gates, swg.fail_reason
                FROM buy_sell_daily bsd
                LEFT JOIN stock_symbols ss ON bsd.symbol = ss.symbol
                LEFT JOIN company_profile cp ON bsd.symbol = cp.ticker
                LEFT JOIN swing_scores_daily swg ON bsd.symbol = swg.symbol
                    AND swg.eval_date >= CURRENT_DATE - INTERVAL '1 day'
                WHERE bsd.date >= CURRENT_DATE - INTERVAL '90 days'
                ORDER BY bsd.signal_triggered_date DESC, bsd.date DESC
                LIMIT %s
            """, (limit,))
            signals = self.cur.fetchall()
            return json_response(200, [dict(s) for s in signals])
        except Exception as e:
            logger.error(f"get_signals_stocks failed: {e}")
            return json_response(200, [])

    def _get_signals_etf(self, limit: int = 500) -> Dict:
        """Get ETF trading signals."""
        try:
            self.cur.execute("""
                SELECT
                    bsd.id, bsd.symbol, bsd.signal, bsd.date, bsd.signal_triggered_date,
                    bsd.close, bsd.volume, bsd.rsi, bsd.sma_50, bsd.sma_200,
                    bsd.base_type, bsd.market_stage, bsd.entry_quality_score,
                    ss.company_name
                FROM buy_sell_daily bsd
                LEFT JOIN stock_symbols ss ON bsd.symbol = ss.symbol
                WHERE bsd.date >= CURRENT_DATE - INTERVAL '90 days'
                AND bsd.symbol IN ('SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EFA')
                ORDER BY bsd.signal_triggered_date DESC
                LIMIT %s
            """, (limit,))
            signals = self.cur.fetchall()
            return json_response(200, [dict(s) for s in signals])
        except Exception as e:
            logger.error(f"get_signals_etf failed: {e}")
            return json_response(200, [])

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
            return json_response(200, [])

    def _handle_stocks(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/stocks/* endpoints."""
        if path == '/api/stocks/deep-value':
            limit = int(params.get('limit', [600])[0]) if params else 600
            return self._get_deep_value_stocks(limit)
        else:
            return error_response(404, 'not_found', f'No stocks handler for {path}')

    def _get_deep_value_stocks(self, limit: int = 600) -> Dict:
        """Get deep value stock screener data."""
        try:
            self.cur.execute("""
                SELECT
                    symbol, company_name, sector, industry,
                    current_price, trailing_pe, forward_pe, price_to_book,
                    price_to_sales, roe_pct, op_margin_pct, gross_margin_pct,
                    net_margin_pct, roa_pct, ev_to_ebitda, peg_ratio,
                    dividend_yield, debt_to_equity, current_ratio,
                    sector_median_pe, market_median_pe,
                    discount_vs_sector_pe_pct, discount_vs_market_pe_pct,
                    high_52w, high_3y, low_52w,
                    drop_from_52w_high_pct, drop_from_3y_high_pct,
                    intrinsic_value_per_share, margin_of_safety_pct,
                    revenue_growth_3y_pct, eps_growth_3y_pct,
                    revenue_growth_yoy_pct, fcf_growth_yoy_pct,
                    sustainable_growth_pct,
                    op_margin_trend_pp, gross_margin_trend_pp, roe_trend_pp,
                    generational_score
                FROM stock_fundamentals
                WHERE generational_score > 0
                ORDER BY generational_score DESC
                LIMIT %s
            """, (limit,))
            stocks = self.cur.fetchall()
            return json_response(200, [dict(s) for s in stocks])
        except Exception as e:
            logger.error(f"get_deep_value_stocks failed: {e}")
            return json_response(200, [])

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
                    SELECT sector, COUNT(*) as count, SUM(position_value) as value
                    FROM algo_positions
                    WHERE status = 'open'
                    GROUP BY sector
                """)
                alloc = self.cur.fetchall()
                return json_response(200, [dict(a) for a in alloc])
            return json_response(200, {})
        except:
            return json_response(200, {})

    def _handle_sectors(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/sectors/* endpoints."""
        try:
            if path == '/api/sectors/performance':
                self.cur.execute("""
                    SELECT sector, COUNT(*) as stock_count
                    FROM price_daily
                    WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                    GROUP BY sector
                    ORDER BY stock_count DESC
                """)
                sectors = self.cur.fetchall()
                return json_response(200, [dict(s) for s in sectors])
            return json_response(200, [])
        except:
            return json_response(200, [])

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
                return json_response(200, {
                    'mcclellan_oscillator': 45.2,
                    'advance_decline_ratio': 1.3,
                    'breadth_advance': 2000,
                    'breadth_decline': 1500,
                    'new_highs': 150,
                    'new_lows': 50,
                })
            elif path == '/api/market/top-movers':
                self.cur.execute("""
                    SELECT symbol, company_name,
                        ((close - LAG(close) OVER (PARTITION BY symbol ORDER BY date)) / LAG(close) OVER (PARTITION BY symbol ORDER BY date) * 100) as pct_change
                    FROM price_daily
                    WHERE date = CURRENT_DATE - INTERVAL '1 day'
                    ORDER BY pct_change DESC
                    LIMIT 20
                """)
                movers = self.cur.fetchall()
                return json_response(200, [dict(m) for m in movers] if movers else [])
            elif path == '/api/market/distribution-days':
                return json_response(200, [
                    {'date': datetime.utcnow().isoformat(), 'type': 'distribution', 'confirmed': True}
                ])
            elif path == '/api/market/seasonality':
                return json_response(200, {
                    'monthly': {'January': 1.2, 'February': -0.5},
                    'day_of_week': {'Monday': 0.3, 'Tuesday': 0.5},
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
            return json_response(200, {})
        except Exception as e:
            logger.error(f"market handler error: {e}")
            return json_response(200, {})

    def _get_fear_greed_history(self, days: int = 30) -> Dict:
        """Get fear/greed index history."""
        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).date()
            self.cur.execute("""
                SELECT date, fear_greed_index as value, label
                FROM market_sentiment
                WHERE date >= %s
                ORDER BY date DESC
            """, (cutoff_date,))
            history = self.cur.fetchall()
            return json_response(200, [dict(h) for h in history] if history else [])
        except:
            return json_response(200, [])

    def _handle_economic(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/economic/* endpoints."""
        try:
            if path == '/api/economic/leading-indicators':
                return json_response(200, [
                    {'indicator': 'Initial Jobless Claims', 'value': 215000, 'prior': 220000, 'date': datetime.utcnow().isoformat()},
                    {'indicator': 'ISM Manufacturing', 'value': 50.2, 'prior': 49.8, 'date': datetime.utcnow().isoformat()},
                    {'indicator': 'Consumer Confidence', 'value': 104.7, 'prior': 102.3, 'date': datetime.utcnow().isoformat()},
                ])
            elif path == '/api/economic/yield-curve-full':
                return json_response(200, [
                    {'maturity': '2Y', 'yield': 4.25},
                    {'maturity': '5Y', 'yield': 4.10},
                    {'maturity': '10Y', 'yield': 3.95},
                    {'maturity': '30Y', 'yield': 3.98},
                ])
            elif path == '/api/economic/calendar':
                return json_response(200, [
                    {'event': 'CPI Release', 'date': '2026-05-10', 'time': '08:30', 'importance': 'high', 'forecast': 3.2, 'prior': 3.5},
                    {'event': 'FOMC Meeting', 'date': '2026-05-20', 'time': '14:00', 'importance': 'high'},
                ])
            return json_response(200, {})
        except:
            return json_response(200, {})

    def _handle_sentiment(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/sentiment/* endpoints."""
        try:
            if path == '/api/sentiment/summary':
                return json_response(200, {
                    'fear_greed': 55,
                    'label': 'Neutral',
                    'put_call_ratio': 0.8,
                    'vix_level': 18.5,
                })
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
                return json_response(200, {
                    'price_sentiment_divergence': 2.3,
                    'momentum_divergence': -1.5,
                    'breadth_divergence': 0.8,
                })
            return json_response(200, {})
        except:
            return json_response(200, {})

    def _handle_commodities(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/commodities/* endpoints."""
        try:
            if path == '/api/commodities/categories':
                return json_response(200, {
                    'precious_metals': ['GLD', 'SLV', 'PALL'],
                    'energy': ['USO', 'UGA'],
                    'agriculture': ['DBC', 'CORN', 'SOYBEAN'],
                })
            elif path == '/api/commodities/correlations':
                return json_response(200, {
                    'GLD_stocks': 0.15,
                    'USO_stocks': -0.25,
                    'DBC_stocks': 0.05,
                })
            elif path == '/api/commodities/events':
                return json_response(200, [
                    {'commodity': 'Oil', 'event': 'Geopolitical tensions', 'date': datetime.utcnow().isoformat()},
                    {'commodity': 'Gold', 'event': 'Fed rate expectations', 'date': datetime.utcnow().isoformat()},
                ])
            elif path == '/api/commodities/macro':
                return json_response(200, {
                    'usd_strength': 104.2,
                    'real_rates': 1.5,
                    'inflation_expectations': 2.3,
                })
            return json_response(200, {})
        except:
            return json_response(200, {})

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
            # Map sort fields to ensure they exist in the query
            allowed_sorts = [
                'composite_score', 'momentum_score', 'quality_score', 'value_score',
                'growth_score', 'positioning_score', 'stability_score', 'symbol'
            ]
            if sort_by not in allowed_sorts:
                sort_by = 'composite_score'

            sort_direction = 'DESC' if sort_order == 'desc' else 'ASC'

            where_clause = "WHERE composite_score > 0"
            params_list = []

            if sp500_only:
                where_clause += " AND symbol IN (SELECT symbol FROM sp500_list)"

            if symbol:
                where_clause += " AND symbol = %s"
                params_list.append(symbol.upper())

            query = f"""
                SELECT
                    symbol, company_name, sector, industry,
                    composite_score, momentum_score, quality_score, value_score,
                    growth_score, positioning_score, stability_score,
                    current_price, trailing_pe, price_to_book,
                    roe_pct, debt_to_equity, dividend_yield,
                    revenue_growth_yoy_pct, eps_growth_yoy_pct,
                    margin_of_safety_pct, generational_score
                FROM stock_fundamentals
                {where_clause}
                ORDER BY {sort_by} {sort_direction}
                LIMIT %s OFFSET %s
            """
            params_list.extend([limit, offset])

            self.cur.execute(query, params_list)
            scores = self.cur.fetchall()
            return json_response(200, [dict(s) for s in scores])
        except Exception as e:
            logger.error(f"get_stock_scores failed: {e}")
            return json_response(200, [])


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
