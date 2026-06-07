"""Route: algo"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re, json, os
from datetime import datetime, timedelta, date, timezone
import boto3
from botocore.exceptions import ClientError
from .utils import error_response, success_response, list_response, json_response, safe_limit, safe_days, safe_offset, handle_db_error, check_data_freshness
from utils.admin_rate_limiter import check_admin_rate_limit, ADMIN_RATE_LIMITS

logger = logging.getLogger(__name__)

def _check_admin_access(jwt_claims: Dict) -> bool:
    """Check if user has admin access from verified JWT claims only."""
    if not jwt_claims:
        # In dev mode (DEV_BYPASS_AUTH=true), allow access to admin endpoints
        if os.environ.get('DEV_BYPASS_AUTH') == 'true':
            return True
        return False
    groups = jwt_claims.get('cognito:groups') or []
    return 'admin' in groups

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
        """Handle /api/algo/* endpoints."""
        try:
            return _dispatch(cur, path, method, params, body, jwt_claims)
        except Exception as e:
            logger.error(f'[ALGO] unhandled {type(e).__name__}: {e}', exc_info=True)
            return error_response(500, 'internal_error', 'An error occurred while processing your request')

def _dispatch(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
        # User identity from verified JWT claims (sub is the Cognito user ID)
        user_id = (jwt_claims or {}).get('sub', '')

        if method == 'PATCH' and path.endswith('/read') and '/notifications/' in path:
            notif_id = path.split('/notifications/')[-1].replace('/read', '')
            if not _check_admin_access(jwt_claims):
                logger.warning(f"Unauthorized notification mark-read attempt by {(jwt_claims or {}).get('sub')}")
                return error_response(403, 'forbidden', 'Admin access required')
            try:
                try:
                    notif_id_int = int(notif_id)
                except ValueError:
                    return error_response(400, 'bad_request', 'ID must be numeric')

                # algo_notifications are system-wide; user_id is NULL for system events (migration 008).
                # Access is gated at the Lambda level (JWT required). Verify record exists.
                cur.execute("SELECT id FROM algo_notifications WHERE id=%s LIMIT 1", (notif_id_int,))
                if not cur.fetchone():
                    return error_response(404, 'not_found', 'Notification not found')

                cur.execute("UPDATE algo_notifications SET seen=TRUE, seen_at=NOW() WHERE id=%s", (notif_id_int,))
                return json_response(200, {'status': 'updated'})
            except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                    psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
                code, error_type, message = handle_db_error(e, 'mark notification as read')
                logger.error(f'Failed to mark notification as read: {error_type} - {message}')
                return json_response(200, {'status': 'error', 'message': message})
        if method == 'DELETE' and '/notifications/' in path:
            notif_id = path.split('/notifications/')[-1]
            if not _check_admin_access(jwt_claims):
                logger.warning(f"Unauthorized notification delete attempt by {(jwt_claims or {}).get('sub')}")
                return error_response(403, 'forbidden', 'Admin access required')
            try:
                try:
                    notif_id_int = int(notif_id)
                except ValueError:
                    return error_response(400, 'bad_request', 'ID must be numeric')

                cur.execute("SELECT id FROM algo_notifications WHERE id=%s LIMIT 1", (notif_id_int,))
                if not cur.fetchone():
                    return error_response(404, 'not_found', 'Notification not found')

                cur.execute("DELETE FROM algo_notifications WHERE id=%s", (notif_id_int,))
                return json_response(200, {'status': 'deleted'})
            except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                    psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
                code, error_type, message = handle_db_error(e, 'delete notification')
                logger.error(f'Failed to delete notification: {error_type} - {message}')
                return json_response(200, {'status': 'error', 'message': message})
        if method == 'POST' and path == '/api/algo/patrol':
            if not _check_admin_access(jwt_claims):
                logger.warning(f"Unauthorized algo patrol access attempt by {(jwt_claims or {}).get('sub')}")
                return error_response(403, 'forbidden', 'Admin access required')
            # SECURITY FIX S-09: Rate limit expensive operations
            if path in ADMIN_RATE_LIMITS:
                limits = ADMIN_RATE_LIMITS[path]
                is_allowed, error_msg = check_admin_rate_limit(user_id, path, max_requests=limits['max_requests'], window_seconds=limits['window'])
                if not is_allowed:
                    return error_response(429, 'too_many_requests', error_msg)
            return _trigger_data_patrol()
        if method == 'POST' and path == '/api/algo/pre-trade-impact':
            if not _check_admin_access(jwt_claims):
                logger.warning(f"Unauthorized algo pre-trade-impact access attempt by {(jwt_claims or {}).get('sub')}")
                return error_response(403, 'forbidden', 'Admin access required')
            if path in ADMIN_RATE_LIMITS:
                limits = ADMIN_RATE_LIMITS[path]
                is_allowed, error_msg = check_admin_rate_limit(user_id, path, max_requests=limits['max_requests'], window_seconds=limits['window'])
                if not is_allowed:
                    return error_response(429, 'too_many_requests', error_msg)
            return _analyze_pre_trade_impact(cur, body)
        if path == '/api/algo/status':
            # Status is accessible to authenticated users (Portfolio Dashboard)
            return _get_algo_status(cur)
        elif path == '/api/algo/trades':
            # Trades accessible to authenticated users (Portfolio Dashboard)
            limit_str = params.get('limit', [None])[0] if params else None
            limit = safe_limit(limit_str, max_val=10000, default=100)
            return _get_algo_trades(cur, limit, user_id=user_id)
        elif path == '/api/algo/positions':
            # Positions accessible to authenticated users (Portfolio Dashboard)
            return _get_algo_positions(cur, user_id=user_id)
        elif path == '/api/algo/performance':
            # Performance accessible to authenticated users (Portfolio Dashboard)
            return _get_algo_performance(cur)
        elif path == '/api/algo/circuit-breakers':
            # Circuit breakers accessible to authenticated users (Portfolio Dashboard)
            return _get_circuit_breakers(cur)
        elif path == '/api/algo/equity-curve':
            # Equity curve accessible to authenticated users (Portfolio Dashboard)
            days_str = params.get('limit', [None])[0] if params else None
            days = safe_days(days_str, max_val=365, default=180)
            return _get_equity_curve(cur, days)
        elif path == '/api/algo/data-status':
            # Data status accessible to authenticated users
            return _get_data_status(cur)
        elif path == '/api/algo/notifications':
            # Admin-only: GET returns circuit breaker alerts, halt flags, position alerts, trade execution failures
            # Dev mode: Allow access for testing
            if os.environ.get('DEV_BYPASS_AUTH') != 'true' and not _check_admin_access(jwt_claims):
                logger.warning(f"Unauthorized notifications access attempt by {(jwt_claims or {}).get('sub')}")
                return error_response(403, 'forbidden', 'Admin access required')
            return _get_notifications(cur, params, jwt_claims)
        elif path == '/api/algo/patrol-log':
            if not _check_admin_access(jwt_claims):
                logger.warning(f"Unauthorized algo patrol-log access attempt by {(jwt_claims or {}).get('sub')}")
                return error_response(403, 'forbidden', 'Admin access required')
            limit_str = params.get('limit', [None])[0] if params else None
            limit = safe_limit(limit_str, max_val=10000, default=100)
            offset_str = params.get('offset', [None])[0] if params else None
            offset = safe_offset(offset_str)
            return _get_patrol_log(cur, limit, offset)
        elif path == '/api/algo/sector-rotation':
            days_str = params.get('limit', [None])[0] if params else None
            days = safe_days(days_str, max_val=365, default=180)
            return _get_sector_rotation(cur, days)
        elif path == '/api/algo/sector-breadth':
            return _get_sector_breadth(cur)
        elif path == '/api/algo/swing-scores':
            # Swing scores accessible to authenticated users (AlgoTradingDashboard)
            limit_str = params.get('limit', [None])[0] if params else None
            limit = safe_limit(limit_str, max_val=10000, default=100)
            min_score_str = params.get('min_score', [None])[0] if params else None
            try:
                min_score = float(min_score_str) if min_score_str else None
            except (ValueError, TypeError):
                return error_response(400, 'bad_request', 'min_score must be numeric')
            symbol_filter = params.get('symbol', [None])[0] if params else None
            # SECURITY M-03: Validate symbol parameter format
            if symbol_filter:
                if not re.match(r'^[A-Z0-9\-\^]{1,10}$', symbol_filter.upper()):
                    return error_response(400, 'bad_request', 'Invalid symbol format')
            return _get_swing_scores(cur, limit, min_score, symbol_filter)
        elif path == '/api/algo/swing-scores-history':
            days_str = params.get('days', [None])[0] if params else None
            days = safe_days(days_str, max_val=365, default=30)
            return _get_swing_scores_history(cur, days)
        elif path == '/api/algo/rejection-funnel':
            # Rejection funnel accessible to authenticated users
            return _get_rejection_funnel(cur)
        elif path == '/api/algo/markets':
            # Market regime data is public - no auth required (market conditions are not sensitive)
            return _get_markets(cur)
        elif path == '/api/algo/evaluate':
            # Evaluate accessible to authenticated users (AlgoTradingDashboard)
            return _get_algo_evaluate(cur)
        elif path == '/api/algo/data-quality':
            # Data quality accessible to authenticated users
            return _get_data_quality(cur)
        elif path == '/api/algo/exposure-policy':
            # Exposure policy accessible to authenticated users
            return _get_exposure_policy(cur)
        elif path == '/api/algo/sector-stage2':
            return _get_sector_stage2(cur)
        elif path == '/api/algo/config':
            # Config accessible to authenticated users
            return _get_algo_config(cur)
        elif path.startswith('/api/algo/config/'):
            if not _check_admin_access(jwt_claims):
                logger.warning(f"Unauthorized algo config access attempt by {(jwt_claims or {}).get('sub')}")
                return error_response(403, 'forbidden', 'Admin access required')
            key = path[len('/api/algo/config/'):]
            return _get_algo_config_key(cur, key)
        elif path == '/api/algo/last-run':
            # Last run accessible to authenticated users
            return _get_last_run(cur)
        elif path == '/api/algo/audit-log':
            if not _check_admin_access(jwt_claims):
                logger.warning(f"Unauthorized algo audit-log access attempt by {(jwt_claims or {}).get('sub')}")
                return error_response(403, 'forbidden', 'Admin access required')
            limit_str = params.get('limit', [None])[0] if params else None
            limit = safe_limit(limit_str, max_val=10000, default=100)
            offset_str = params.get('offset', [None])[0] if params else None
            offset = safe_offset(offset_str)
            action_type = params.get('action_type', [None])[0] if params else None
            # Validate action_type parameter (normalize to lowercase for case-insensitive matching)
            if action_type:
                action_type = action_type.lower()
                VALID_ACTION_TYPES = {'entry', 'exit', 'alert', 'halt', 'reconciliation', 'error',
                                      'stop', 'pyramid', 'skip', 'pass',
                                      'phase_0_halt_flag_detected', 'phase_0_oom_prevention',
                                      'phase_0_table_validation',
                                      'phase_1_data_freshness', 'phase_1_data_patrol',
                                      'phase_1_pipeline_health', 'phase_1_signal_quality_scores',
                                      'phase_2_circuit_breakers', 'phase_2_market_circuit_breaker',
                                      'phase_3_position_monitor', 'phase_3_single_stock_halts',
                                      'phase_3_halt_check_error',
                                      'phase_3a_reconciliation',
                                      'phase_3b_exposure_policy', 'phase_4_exit_execution',
                                      'phase_4b_pyramid_adds', 'phase_5_signal_generation',
                                      'phase_6_entry_execution',
                                      'phase_7_reconciliation', 'phase_7_daily_report',
                                      'phase_7_ic_computation', 'phase_7_performance',
                                      'phase_7_risk_metrics', 'phase_7_signal_attribution',
                                      'phase_7_weight_optimization',
                                      'halt_flag_detected', 'position_review', 'position_monitor',
                                      'pipeline_health', 'single_stock_halts', 'halt_check_error'}
                if action_type not in VALID_ACTION_TYPES:
                    return error_response(400, 'bad_request', f'Invalid action_type: {action_type}')
            return _get_algo_audit_log(cur, limit, offset, action_type)
        else:
            return error_response(404, 'not_found', f'No algo handler for {path}')

def _get_last_run(cur) -> Dict:
    """Get the most recent orchestrator run with per-phase status."""
    try:
        cur.execute("""
            SELECT details->>'run_id' AS run_id, MAX(created_at) AS run_at
            FROM algo_audit_log
            WHERE details->>'run_id' IS NOT NULL
            GROUP BY details->>'run_id'
            ORDER BY MAX(created_at) DESC
            LIMIT 1
        """)
        latest = cur.fetchone()
        if not latest or not latest['run_id']:
            return json_response(200, {'run_id': None, 'run_at': None, 'success': False, 'halted': False, 'phases': []})

        run_id = latest['run_id']
        run_at = latest['run_at']

        cur.execute("""
            SELECT action_type, status, action_date, created_at,
                   details->>'summary' AS summary,
                   error_message AS error
            FROM algo_audit_log
            WHERE details->>'run_id' = %s
            ORDER BY created_at ASC
        """, (run_id,))
        phases = [dict(r) for r in cur.fetchall()]

        halted = any(p.get('status') == 'halt' for p in phases)
        errored = any(p.get('status') == 'error' for p in phases)
        success = len(phases) > 0 and not errored

        return json_response(200, {
            'run_id': run_id,
            'run_at': run_at.isoformat() if run_at else None,
            'success': success,
            'halted': halted,
            'phases': phases,
        })
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        code, error_type, message = handle_db_error(e, 'get last run')
        logger.error(f'Failed to fetch last run: {error_type} - {message}')
        return json_response(200, {'run_id': None, 'run_at': None, 'success': False, 'halted': False, 'phases': []})

def _get_algo_status(cur) -> Dict:
        """Get latest algo execution status plus latest portfolio snapshot."""
        try:
            cur.execute("SET LOCAL statement_timeout = '5000ms'")
            cur.execute("""
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
            row = cur.fetchone()
            if not row:
                return json_response(200, {'status': 'no_runs_yet', 'last_run': None, 'portfolio': {}})

            portfolio = {}
            try:
                cur.execute("SET LOCAL statement_timeout = '3000ms'")
                cur.execute("""
                    SELECT total_portfolio_value, daily_return_pct,
                           unrealized_pnl_total, position_count
                    FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date DESC LIMIT 1
                """)
                snap = cur.fetchone()
                if snap:
                    pv = float(snap[0] or 0)
                    portfolio = {
                        'total_value': round(pv, 2),
                        'daily_return_pct': round(float(snap[1] or 0), 2),
                        'unrealized_pnl_pct': round((float(snap[2] or 0) / pv * 100) if pv > 0 else 0, 2),
                        'open_positions': int(snap[3] or 0),
                    }
            except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                    psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
                logger.warning(f"[STATUS] Portfolio snapshot unavailable: {type(e).__name__}: {e}")

            freshness = check_data_freshness(cur, 'algo_audit_log', 'created_at', warning_days=1)
            return json_response(200, {
                'run_id': row['run_id'],
                'last_run': row['action_date'].isoformat() if row['action_date'] else None,
                'current_phase': row['action_type'],
                'status': row['status'],
                'message': row['message'],
                'portfolio': portfolio,
                'data_freshness': freshness,
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            code, error_type, message = handle_db_error(e, 'fetch algo status')
            logger.error(f'Failed to fetch algo status: {error_type} - {message}')
            return json_response(200, {'status': 'unavailable', 'last_run': None, 'portfolio': {}, 'data_freshness': {'data_age_days': None, 'is_stale': True, 'warning': 'Data unavailable'}})

def _get_algo_trades(cur, limit: int = 200, user_id: str = None) -> Dict:
        """Get recent trades with all fields for frontend (scoped to user if user_id provided)."""
        try:
            if user_id:
                where_clause = "WHERE cognito_sub = %s"
                params = (user_id, limit)
            else:
                where_clause = ""
                params = (limit,)

            cur.execute(f"""
                SELECT trade_id, symbol, signal_date, trade_date, entry_price, entry_time,
                       entry_quantity, entry_reason, exit_price, exit_date, exit_time,
                       exit_reason, exit_r_multiple, profit_loss_dollars, profit_loss_pct,
                       status, swing_score, swing_grade, base_type, stage_phase,
                       trade_duration_days, mfe_pct, mae_pct, created_at
                FROM algo_trades
                {where_clause}
                ORDER BY trade_date DESC, trade_id DESC
                LIMIT %s
            """, params)
            trades = cur.fetchall()
            items = [dict(t) for t in trades]
            freshness = check_data_freshness(cur, 'algo_trades', 'created_at', warning_days=1)
            return json_response(200, {
                'items': items,
                'pagination': {'total': len(items), 'limit': limit, 'offset': 0},
                'data_freshness': freshness
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            code, error_type, message = handle_db_error(e, 'fetch algo trades')
            logger.error(f'Failed to fetch algo trades: {error_type} - {message}')
            return json_response(200, {
                'items': [],
                'pagination': {'total': 0, 'limit': limit, 'offset': 0},
                'data_freshness': {'data_age_days': None, 'is_stale': True, 'warning': 'Data unavailable'}
            })

def _get_algo_positions(cur, user_id: str = None) -> Dict:
        """Get current open positions enriched with targets, sector, stage, and computed risk fields (scoped to user if user_id provided)."""
        try:
            # Ensure cognito_sub column exists (migration)
            try:
                # Check if column exists first
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name='algo_positions' AND column_name='cognito_sub'
                """)
                if not cur.fetchone():
                    # Column doesn't exist, create it
                    cur.execute("ALTER TABLE algo_positions ADD COLUMN cognito_sub VARCHAR(255)")
                    logger.info("Created cognito_sub column in algo_positions")
            except Exception as e:
                logger.warning(f"Migration check failed: {e} - continuing anyway")

            # Build WHERE clause with optional user scoping
            # If cognito_sub column doesn't exist yet, skip user filtering
            user_filter = f"AND p.cognito_sub = %s" if user_id else ""
            params = (user_id,) if user_id else ()

            cur.execute("SET LOCAL statement_timeout = '30000ms'")

            try:
                # Try query with user_id filter
                cur.execute(f"""
                WITH latest_trend AS (
                    SELECT DISTINCT ON (symbol)
                        symbol, weinstein_stage, minervini_trend_score, percent_from_52w_low
                    FROM trend_template_data
                    WHERE date >= CURRENT_DATE - INTERVAL '14 days'
                    ORDER BY symbol, date DESC
                )
                SELECT
                    p.position_id, p.symbol, p.quantity, p.avg_entry_price, p.current_price,
                    p.position_value, p.unrealized_pnl, p.unrealized_pnl_pct, p.status,
                    p.days_since_entry, p.distribution_day_count, p.target_levels_hit,
                    p.current_stop_price,
                    p.current_stop_price AS stop_loss_price,
                    p.stage_in_exit_plan, p.created_at, p.updated_at,
                    -- Original entry trade: stop and targets
                    ot.stop_loss_price AS trade_stop_price,
                    ot.target_1_price, ot.target_2_price, ot.target_3_price,
                    -- Sector from company_profile (with fallback to Unknown)
                    COALESCE(cp.sector, 'Unknown') as sector,
                    -- Stage / trend from trend_template_data
                    lt.weinstein_stage,
                    lt.minervini_trend_score,
                    lt.percent_from_52w_low AS pct_from_52w_low,
                    -- Computed: r_multiple = (current - entry) / (entry - stop)
                    CASE
                        WHEN p.avg_entry_price IS NOT NULL
                             AND p.current_stop_price IS NOT NULL
                             AND (p.avg_entry_price - p.current_stop_price) > 0
                        THEN ROUND(
                            ((p.current_price - p.avg_entry_price) /
                             (p.avg_entry_price - p.current_stop_price))::NUMERIC, 2)
                    END AS r_multiple,
                    -- open_risk_dollars = quantity * (entry_price - stop_price)
                    CASE
                        WHEN p.current_stop_price IS NOT NULL AND p.avg_entry_price > p.current_stop_price
                        THEN ROUND((p.quantity * (p.avg_entry_price - p.current_stop_price))::NUMERIC, 2)
                    END AS open_risk_dollars,
                    -- distance_to_stop_pct: positive = above stop, negative = stop already broken
                    CASE
                        WHEN p.current_stop_price IS NOT NULL AND p.current_price > 0
                        THEN ROUND(
                            ((p.current_price - p.current_stop_price) / p.current_price * 100)::NUMERIC, 2)
                    END AS distance_to_stop_pct,
                    -- distance_to_t1/t2/t3_pct: positive = target above current price
                    CASE
                        WHEN ot.target_1_price IS NOT NULL AND p.current_price > 0
                        THEN ROUND(
                            ((ot.target_1_price - p.current_price) / p.current_price * 100)::NUMERIC, 2)
                    END AS distance_to_t1_pct,
                    CASE
                        WHEN ot.target_2_price IS NOT NULL AND p.current_price > 0
                        THEN ROUND(
                            ((ot.target_2_price - p.current_price) / p.current_price * 100)::NUMERIC, 2)
                    END AS distance_to_t2_pct,
                    CASE
                        WHEN ot.target_3_price IS NOT NULL AND p.current_price > 0
                        THEN ROUND(
                            ((ot.target_3_price - p.current_price) / p.current_price * 100)::NUMERIC, 2)
                    END AS distance_to_t3_pct
                FROM algo_positions p
                LEFT JOIN LATERAL (
                    SELECT stop_loss_price, target_1_price, target_2_price, target_3_price
                    FROM algo_trades at
                    WHERE p.trade_ids_arr IS NOT NULL AND at.trade_id = ANY(p.trade_ids_arr)
                    ORDER BY at.id ASC
                    LIMIT 1
                ) ot ON true
                LEFT JOIN company_profile cp ON cp.ticker = p.symbol
                LEFT JOIN latest_trend lt ON lt.symbol = p.symbol
                WHERE LOWER(p.status) = 'open' {user_filter}
                ORDER BY p.position_value DESC
            """, params)
                positions = cur.fetchall()
            except psycopg2.errors.UndefinedColumn as e:
                # cognito_sub column doesn't exist yet - retry without user filtering
                if user_id and 'cognito_sub' in str(e):
                    logger.warning(f"cognito_sub column missing, returning all positions (not filtered by user)")
                    cur.execute(f"""
                WITH latest_trend AS (
                    SELECT DISTINCT ON (symbol)
                        symbol, weinstein_stage, minervini_trend_score, percent_from_52w_low
                    FROM trend_template_data
                    WHERE date >= CURRENT_DATE - INTERVAL '14 days'
                    ORDER BY symbol, date DESC
                )
                SELECT
                    p.position_id, p.symbol, p.quantity, p.avg_entry_price, p.current_price,
                    p.position_value, p.unrealized_pnl, p.unrealized_pnl_pct, p.status,
                    p.days_since_entry, p.distribution_day_count, p.target_levels_hit,
                    p.current_stop_price,
                    p.current_stop_price AS stop_loss_price,
                    p.stage_in_exit_plan, p.created_at, p.updated_at,
                    ot.stop_loss_price AS trade_stop_price,
                    ot.target_1_price, ot.target_2_price, ot.target_3_price,
                    COALESCE(cp.sector, 'Unknown') as sector,
                    lt.weinstein_stage,
                    lt.minervini_trend_score,
                    lt.percent_from_52w_low AS pct_from_52w_low,
                    CASE
                        WHEN p.avg_entry_price IS NOT NULL
                             AND p.current_stop_price IS NOT NULL
                             AND (p.avg_entry_price - p.current_stop_price) > 0
                        THEN ROUND(
                            ((p.current_price - p.avg_entry_price) /
                             (p.avg_entry_price - p.current_stop_price))::NUMERIC, 2)
                    END AS r_multiple,
                    CASE
                        WHEN p.current_stop_price IS NOT NULL AND p.avg_entry_price > p.current_stop_price
                        THEN ROUND((p.quantity * (p.avg_entry_price - p.current_stop_price))::NUMERIC, 2)
                    END AS open_risk_dollars,
                    CASE
                        WHEN p.current_stop_price IS NOT NULL AND p.current_price > 0
                        THEN ROUND(
                            ((p.current_price - p.current_stop_price) / p.current_price * 100)::NUMERIC, 2)
                    END AS distance_to_stop_pct
                FROM algo_positions p
                LEFT JOIN LATERAL (
                    SELECT stop_loss_price, target_1_price, target_2_price, target_3_price
                    FROM algo_trades at
                    WHERE p.trade_ids_arr IS NOT NULL AND at.trade_id = ANY(p.trade_ids_arr)
                    ORDER BY at.id ASC
                    LIMIT 1
                ) ot ON true
                LEFT JOIN company_profile cp ON cp.ticker = p.symbol
                LEFT JOIN latest_trend lt ON lt.symbol = p.symbol
                WHERE LOWER(p.status) = 'open'
                ORDER BY p.position_value DESC
            """)
                    positions = cur.fetchall()
                else:
                    raise

            items = []
            for p in positions:
                d = dict(p)
                # Prefer current_stop_price (updated by monitor) over original trade stop
                if d.get('current_stop_price') is None and d.get('trade_stop_price') is not None:
                    d['current_stop_price'] = d['trade_stop_price']
                    d['stop_loss_price'] = d['trade_stop_price']
                items.append(d)
            freshness = check_data_freshness(cur, 'algo_positions', 'updated_at', warning_days=1)
            return json_response(200, {
                'items': items,
                'pagination': {'total': len(items), 'limit': 10000, 'offset': 0},
                'data_freshness': freshness
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            code, error_type, message = handle_db_error(e, 'fetch algo positions')
            logger.error(f'Failed to fetch algo positions: {error_type} - {message}')
            return json_response(200, {
                'items': [],
                'pagination': {'total': 0, 'limit': 10000, 'offset': 0},
                'data_freshness': {'data_age_days': None, 'is_stale': True, 'warning': 'Data unavailable'}
            })

def _get_algo_performance(cur) -> Dict:
        """Get comprehensive algo performance metrics including Sharpe, Sortino, max drawdown."""
        import math

        def _mean(xs): return sum(xs) / len(xs) if xs else 0.0
        def _std(xs):
            if len(xs) < 2: return 0.0
            m = _mean(xs); return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))
        def _cumprod_max_dd(returns):
            cum, peak, max_dd = 1.0, 1.0, 0.0
            for r in returns:
                cum *= (1 + r)
                if cum > peak: peak = cum
                dd = (cum - peak) / peak
                if dd < max_dd: max_dd = dd
            return max_dd

        try:
            cur.execute("""
                SELECT trade_id, symbol, trade_date, exit_date, entry_price, exit_price,
                       entry_quantity, profit_loss_dollars, profit_loss_pct,
                       exit_r_multiple,
                       (COALESCE(exit_date, CURRENT_DATE) - trade_date) as holding_days
                FROM algo_trades WHERE exit_date IS NOT NULL ORDER BY exit_date DESC LIMIT 1000
            """)
            trades = [dict(row) for row in cur.fetchall()]
            if not trades:
                return json_response(200, {'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0,
                    'win_rate': 0.0, 'profit_factor': 0.0, 'total_pnl_dollars': 0.0, 'total_pnl_pct': 0.0,
                    'avg_trade_pct': 0.0, 'best_trade_pct': 0.0, 'worst_trade_pct': 0.0,
                    'sharpe_ratio': 0.0, 'sortino_ratio': 0.0, 'max_drawdown_pct': 0.0, 'avg_holding_days': 0.0})
            pnls_dollars = [float(t['profit_loss_dollars'] or 0) for t in trades]
            pnls_pcts = [float(t['profit_loss_pct'] or 0) for t in trades]
            holding_days = [float(t['holding_days'] or 0) for t in trades if t['holding_days']]
            r_multiples = [float(t['exit_r_multiple']) for t in trades if t.get('exit_r_multiple') is not None]
            winning = sum(1 for p in pnls_dollars if p > 0)
            losing = sum(1 for p in pnls_dollars if p < 0)
            total = len(trades)
            wins_sum = sum(p for p in pnls_dollars if p > 0)
            losses_sum = abs(sum(p for p in pnls_dollars if p < 0))
            profit_factor = (wins_sum / losses_sum) if losses_sum > 0 else 0.0

            sharpe, sortino, max_dd = 0.0, 0.0, 0.0
            snapshot_count = 0
            total_return_pct = None  # True compounded return from snapshots (preferred)
            calmar_ratio = 0.0
            try:
                cur.execute("""
                    SELECT snapshot_date, total_portfolio_value
                    FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date ASC
                """)
                snapshots = [dict(row) for row in cur.fetchall()]
                snapshot_count = len(snapshots)
                if snapshot_count > 1:
                    vals = [float(s['total_portfolio_value'] or 0) for s in snapshots]
                    dates = [s['snapshot_date'] for s in snapshots]
                    returns = [(vals[i] - vals[i-1]) / vals[i-1] for i in range(1, len(vals)) if vals[i-1] != 0]
                    if returns:
                        mean_r = _mean(returns)
                        std_r = _std(returns)
                        sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0
                        downside = [r for r in returns if r < 0]
                        dv = _std(downside) if downside else 0.0
                        sortino = (mean_r / dv * math.sqrt(252)) if dv > 0 else 0.0
                        max_dd = _cumprod_max_dd(returns)
                    # True compounded portfolio return: (end / start - 1) * 100
                    if len(vals) > 0 and vals[0] > 0 and vals[-1] > 0:
                        total_return_pct = round((vals[-1] / vals[0] - 1) * 100, 2)
                        # CAGR for Calmar: (end/start)^(365/calendar_days) - 1
                        n_days = (dates[-1] - dates[0]).days if len(dates) > 1 else 0
                        if n_days > 0 and max_dd < 0:
                            cagr = (vals[-1] / vals[0]) ** (365.25 / n_days) - 1
                            calmar_ratio = round(cagr / abs(max_dd), 2)
            except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                    psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
                logger.warning(f'Portfolio snapshots unavailable: {e}')
            if max_dd == 0.0 and pnls_pcts:
                max_dd = _cumprod_max_dd([p / 100.0 for p in pnls_pcts])
            win_rate_pct = round((winning / total * 100) if total > 0 else 0.0, 2)
            wins_p = [p for p in pnls_pcts if p > 0]
            losses_p = [p for p in pnls_pcts if p < 0]
            # sum_of_trade_pnls_pct: sum of per-trade P&L percentages (not compounded portfolio return)
            sum_of_trade_pnls_pct = round(sum(pnls_pcts), 2)
            # total_return_pct: true compounded portfolio return from snapshots when available
            if total_return_pct is None:
                total_return_pct = sum_of_trade_pnls_pct
            # Calmar fallback when no snapshots: use sum_of_trade_pnls_pct as numerator (imprecise)
            if calmar_ratio == 0.0 and max_dd < 0:
                calmar_ratio = round(sum_of_trade_pnls_pct / 100 / abs(max_dd), 2)
            # Compute streak metrics from ordered trade P&Ls
            best_win_streak = worst_loss_streak = current_streak = 0
            if pnls_dollars:
                cur_run = 0
                best_w = best_l = 0
                for p in reversed(pnls_dollars):
                    if p > 0:
                        cur_run = max(0, cur_run) + 1
                    elif p < 0:
                        cur_run = min(0, cur_run) - 1
                    best_w = max(best_w, cur_run)
                    best_l = min(best_l, cur_run)
                current_streak = cur_run
                best_win_streak = best_w
                worst_loss_streak = abs(best_l)

            # Compute advanced metrics
            # Ulcer Index = sqrt(sum(drawdowns^2) / n)
            ulcer_index = 0.0
            if total_return_pct and max_dd < 0:
                # Approximate Ulcer Index from max drawdown
                ulcer_index = round(abs(max_dd) * 100, 2)

            # Recovery Factor = total profit / max_drawdown
            recovery_factor = 0.0
            if max_dd < 0 and (wins_sum > 0 or sum_of_trade_pnls_pct > 0):
                recovery_factor = round(sum_of_trade_pnls_pct / abs(max_dd * 100), 2)

            # Tail ratio (ratio of largest wins to largest losses)
            tail_ratio = 0.0
            if pnls_pcts and len(wins_p) > 0 and len(losses_p) > 0:
                max_win = max(wins_p) if wins_p else 0
                max_loss = abs(min(losses_p)) if losses_p else 0
                if max_loss > 0:
                    tail_ratio = round(max_win / max_loss, 2)

            freshness = check_data_freshness(cur, 'algo_trades', 'exit_date', warning_days=1)
            result = {
                'total_trades': total,
                'winning_trades': winning,
                'losing_trades': losing,
                'win_rate': win_rate_pct,
                'win_rate_pct': win_rate_pct,
                'profit_factor': round(profit_factor, 2),
                'total_pnl_dollars': round(sum(pnls_dollars), 2),
                'total_pnl_pct': sum_of_trade_pnls_pct,
                'total_return_pct': total_return_pct,
                'avg_trade_pct': round(_mean(pnls_pcts), 2),
                'avg_win_pct': round(_mean(wins_p), 2),
                'avg_loss_pct': round(_mean(losses_p), 2),
                'best_trade_pct': round(max(pnls_pcts), 2) if pnls_pcts else 0.0,
                'worst_trade_pct': round(min(pnls_pcts), 2) if pnls_pcts else 0.0,
                'sharpe_annualized': round(sharpe, 2),
                'sharpe_ratio': round(sharpe, 2),
                'sortino_annualized': round(sortino, 2),
                'sortino_ratio': round(sortino, 2),
                'max_drawdown_pct': round(abs(max_dd) * 100, 2),
                'calmar_ratio': calmar_ratio,
                'ulcer_index': ulcer_index,
                'recovery_factor': recovery_factor,
                'tail_ratio': tail_ratio,
                'expectancy_r': round(_mean(r_multiples), 2) if r_multiples else 0.0,
                'avg_hold_days': round(_mean(holding_days), 1),
                'avg_holding_days': round(_mean(holding_days), 1),
                'avg_r_multiple': round(_mean(r_multiples), 2),
                'avg_win_r': round(_mean([r for r in r_multiples if r > 0]), 2),
                'avg_loss_r': round(_mean([r for r in r_multiples if r < 0]), 2),
                'portfolio_snapshots': snapshot_count,
                'best_win_streak': best_win_streak,
                'worst_loss_streak': worst_loss_streak,
                'current_streak': current_streak,
                'gross_win_dollars': round(wins_sum, 2),
                'gross_loss_dollars': round(losses_sum, 2),
                'data_freshness': freshness,
            }
            return json_response(200, result)
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            code, error_type, message = handle_db_error(e, 'calculate performance')
            logger.error(f'Failed to calculate performance: {error_type} - {message}')
            return json_response(200, {
                'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0,
                'win_rate': 0.0, 'profit_factor': 0.0, 'total_pnl_dollars': 0.0, 'total_pnl_pct': 0.0,
                'total_return_pct': 0.0, 'avg_trade_pct': 0.0, 'best_trade_pct': 0.0, 'worst_trade_pct': 0.0,
                'sharpe_ratio': 0.0, 'sortino_ratio': 0.0, 'max_drawdown_pct': 0.0, 'avg_holding_days': 0.0,
                'data_freshness': {'data_age_days': None, 'is_stale': True, 'warning': 'Data unavailable'}
            })

def _get_circuit_breakers(cur) -> Dict:
        """Get real-time circuit breaker state with current values vs thresholds."""
        try:
            today = date.today()
            breakers = []

            # CB1: Portfolio drawdown
            try:
                cur.execute("""
                    SELECT MAX(total_portfolio_value) AS peak,
                           (SELECT total_portfolio_value FROM algo_portfolio_snapshots
                            ORDER BY snapshot_date DESC LIMIT 1) AS current
                    FROM algo_portfolio_snapshots
                """)
                row = cur.fetchone()
                peak = float(row[0] or 0) if row else 0
                current_val = float(row[1] or 0) if row else 0
                dd = round(((peak - current_val) / peak * 100) if peak > 0 else 0, 2)
                threshold_dd = 20.0
                breakers.append({
                    'id': 'drawdown', 'label': 'Portfolio Drawdown',
                    'triggered': dd >= threshold_dd,
                    'current': dd, 'threshold': threshold_dd, 'unit': '%',
                    'description': f'Halt when drawdown from peak ≥ {threshold_dd:.0f}%',
                })
            except Exception as e:
                logger.warning(f"API exception: {e}")
                breakers.append({'id': 'drawdown', 'label': 'Portfolio Drawdown',
                    'triggered': False, 'current': 0, 'threshold': 20, 'unit': '%',
                    'description': 'No portfolio data yet'})

            # CB2: Daily loss
            try:
                cur.execute("""
                    SELECT daily_return_pct FROM algo_portfolio_snapshots
                    WHERE snapshot_date = %s
                """, (today,))
                row = cur.fetchone()
                daily = round(float(row[0] or 0), 2) if row else 0.0
                daily_loss = abs(min(0, daily))
                threshold_dl = 2.0
                breakers.append({
                    'id': 'daily_loss', 'label': 'Daily Loss',
                    'triggered': daily <= -threshold_dl,
                    'current': daily_loss, 'threshold': threshold_dl, 'unit': '%',
                    'description': f'Halt when today\'s loss ≥ {threshold_dl:.0f}%',
                })
            except Exception as e:
                logger.warning(f"API exception: {e}")
                breakers.append({'id': 'daily_loss', 'label': 'Daily Loss',
                    'triggered': False, 'current': 0, 'threshold': 2, 'unit': '%',
                    'description': 'No today snapshot yet'})

            # CB3: Consecutive losses
            try:
                cur.execute("""
                    SELECT profit_loss_pct FROM algo_trades
                    WHERE status = 'closed' AND exit_date IS NOT NULL
                    ORDER BY exit_date DESC, trade_id DESC
                    LIMIT 10
                """)
                rows = cur.fetchall()
                streak = 0
                for r in rows:
                    if float(r[0] or 0) < 0:
                        streak += 1
                    else:
                        break
                threshold_cl = 3
                breakers.append({
                    'id': 'consecutive_losses', 'label': 'Consecutive Losses',
                    'triggered': streak >= threshold_cl,
                    'current': streak, 'threshold': threshold_cl, 'unit': '',
                    'description': f'Halt after {threshold_cl} consecutive losing trades',
                })
            except Exception as e:
                logger.warning(f"API exception: {e}")
                breakers.append({'id': 'consecutive_losses', 'label': 'Consecutive Losses',
                    'triggered': False, 'current': 0, 'threshold': 3, 'unit': '',
                    'description': 'No closed trades yet'})

            # CB4: VIX spike
            try:
                cur.execute("SELECT vix_level FROM market_health_daily ORDER BY date DESC LIMIT 1")
                row = cur.fetchone()
                vix = round(float(row[0] or 0), 1) if row else 0.0
                threshold_vix = 35.0
                breakers.append({
                    'id': 'vix_spike', 'label': 'VIX Spike',
                    'triggered': vix >= threshold_vix,
                    'current': vix, 'threshold': threshold_vix, 'unit': '',
                    'description': f'Halt when VIX ≥ {threshold_vix:.0f} (extreme fear)',
                })
            except Exception as e:
                logger.warning(f"API exception: {e}")
                breakers.append({'id': 'vix_spike', 'label': 'VIX Spike',
                    'triggered': False, 'current': 0, 'threshold': 35, 'unit': '',
                    'description': 'No market data yet'})

            # CB5: Weekly portfolio loss
            try:
                cur.execute("""
                    SELECT total_portfolio_value FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= %s
                    ORDER BY snapshot_date ASC
                    LIMIT 1
                """, (today - timedelta(days=7),))
                week_start = cur.fetchone()
                cur.execute("""
                    SELECT total_portfolio_value FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date DESC LIMIT 1
                """)
                week_end = cur.fetchone()
                if week_start and week_end:
                    sv = float(week_start[0] or 0)
                    ev = float(week_end[0] or 0)
                    weekly_ret = round(((ev - sv) / sv * 100) if sv > 0 else 0, 2)
                else:
                    weekly_ret = 0.0
                weekly_loss = abs(min(0, weekly_ret))
                threshold_wl = 5.0
                breakers.append({
                    'id': 'weekly_loss', 'label': 'Weekly Loss',
                    'triggered': weekly_ret <= -threshold_wl,
                    'current': weekly_loss, 'threshold': threshold_wl, 'unit': '%',
                    'description': f'Halt when 7-day loss ≥ {threshold_wl:.0f}%',
                })
            except Exception as e:
                logger.warning(f"API exception: {e}")
                breakers.append({'id': 'weekly_loss', 'label': 'Weekly Loss',
                    'triggered': False, 'current': 0, 'threshold': 5, 'unit': '%',
                    'description': 'No weekly data yet'})

            # CB6: Market stage break (Stage 4 = downtrend)
            try:
                cur.execute("SELECT market_stage FROM market_health_daily ORDER BY date DESC LIMIT 1")
                row = cur.fetchone()
                stage = int(row[0] or 0) if row else 0
                breakers.append({
                    'id': 'market_stage', 'label': 'Market Stage',
                    'triggered': stage == 4,
                    'current': stage, 'threshold': 4, 'unit': '',
                    'description': 'Halt when market enters Stage 4 (confirmed downtrend)',
                })
            except Exception as e:
                logger.warning(f"API exception: {e}")
                breakers.append({'id': 'market_stage', 'label': 'Market Stage',
                    'triggered': False, 'current': 0, 'threshold': 4, 'unit': '',
                    'description': 'No market data yet'})

            # CB7: Total open risk
            try:
                cur.execute("""
                    SELECT COALESCE(SUM(GREATEST(0, (t.entry_price - COALESCE(p.current_stop_price, t.stop_loss_price)) * p.quantity)), 0)
                    FROM algo_positions p
                    JOIN algo_trades t ON t.trade_id = ANY(p.trade_ids_arr)
                    WHERE LOWER(p.status) = 'open'
                """)
                risk_result = cur.fetchone()
                total_risk = float(risk_result[0] or 0) if risk_result else 0

                cur.execute("SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1")
                port_result = cur.fetchone()
                port_val = float(port_result[0] or 1) if port_result else 1
                risk_pct = (total_risk / port_val * 100) if port_val > 0 else 0
                threshold_risk = 4.0
                breakers.append({
                    'id': 'total_risk', 'label': 'Total Open Risk',
                    'triggered': risk_pct >= threshold_risk,
                    'current': round(risk_pct, 2), 'threshold': threshold_risk, 'unit': '%',
                    'description': f'Halt when total open risk ≥ {threshold_risk:.0f}% of portfolio',
                })
            except Exception as e:
                logger.warning(f"API exception: {e}")
                breakers.append({'id': 'total_risk', 'label': 'Total Open Risk',
                    'triggered': False, 'current': 0, 'threshold': 4, 'unit': '%',
                    'description': 'No positions data yet'})

            # CB8: Intraday market health (SPY down >2% yesterday)
            try:
                cur.execute("""
                    SELECT close FROM price_daily
                    WHERE symbol = 'SPY' AND date <= %s
                    ORDER BY date DESC LIMIT 2
                """, (today,))
                prices = cur.fetchall()
                if len(prices) >= 2:
                    latest = float(prices[0][0] or 0)
                    prior = float(prices[1][0] or 0)
                    if latest > 0 and prior > 0:
                        market_change = ((latest - prior) / prior * 100)
                        threshold_mc = -2.0
                        breakers.append({
                            'id': 'intraday_health', 'label': 'Prior-Day Market Health',
                            'triggered': market_change <= threshold_mc,
                            'current': round(market_change, 2), 'threshold': threshold_mc, 'unit': '%',
                            'description': f'Halt if SPY dropped >{abs(threshold_mc):.0f}% yesterday (await stability)',
                        })
                    else:
                        raise ValueError("Invalid price data")
                else:
                    raise ValueError("Insufficient price history")
            except Exception as e:
                logger.warning(f"API exception: {e}")
                breakers.append({'id': 'intraday_health', 'label': 'Prior-Day Market Health',
                    'triggered': False, 'current': 0, 'threshold': -2.0, 'unit': '%',
                    'description': 'No price history yet'})

            # CB9: Win rate floor
            try:
                cur.execute("""
                    SELECT COUNT(*) FILTER (WHERE profit_loss_pct > 0) as wins,
                           COUNT(*) FILTER (WHERE profit_loss_pct < 0) as losses,
                           COUNT(*) as total
                    FROM (
                        SELECT profit_loss_pct
                        FROM algo_trades
                        WHERE status = 'closed' AND exit_date IS NOT NULL
                        ORDER BY exit_date DESC LIMIT 30
                    ) recent_trades
                """)
                wr_result = cur.fetchone()
                if wr_result:
                    wins = int(wr_result[0] or 0)
                    losses = int(wr_result[1] or 0)
                    decisive = wins + losses
                    win_rate = (wins / decisive * 100) if decisive > 0 else 0
                    threshold_wr = 40.0
                    breakers.append({
                        'id': 'win_rate', 'label': 'Win Rate Floor',
                        'triggered': win_rate < threshold_wr and decisive >= 10,
                        'current': round(win_rate, 1), 'threshold': threshold_wr, 'unit': '%',
                        'description': f'Halt if win rate drops below {threshold_wr:.0f}% (last 30 closed)',
                    })
                else:
                    raise ValueError("No trade data")
            except Exception as e:
                logger.warning(f"API exception: {e}")
                breakers.append({'id': 'win_rate', 'label': 'Win Rate Floor',
                    'triggered': False, 'current': 0, 'threshold': 40, 'unit': '%',
                    'description': 'Insufficient closed trades (need 10+)'})

            any_halted = any(b['triggered'] for b in breakers)
            triggered_count = sum(1 for b in breakers if b['triggered'])
            freshness = check_data_freshness(cur, 'algo_portfolio_snapshots', 'snapshot_date', warning_days=1)
            return json_response(200, {'breakers': breakers, 'any_triggered': any_halted, 'triggered_count': triggered_count, 'data_freshness': freshness})
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            code, error_type, message = handle_db_error(e, 'fetch circuit breakers')
            logger.error(f'Failed to fetch circuit breakers: {error_type} - {message}')
            return json_response(200, {'breakers': [], 'any_triggered': False, 'triggered_count': 0, 'data_freshness': {'data_age_days': None, 'is_stale': True, 'warning': 'Data unavailable'}})

def _get_equity_curve(cur, days: int = 180) -> Dict:
        """Get equity curve for last N days."""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            cur.execute("SET LOCAL statement_timeout = '8000ms'")
            cur.execute("""
                SELECT snapshot_date, total_portfolio_value, total_cash,
                       unrealized_pnl_total, position_count, daily_return_pct
                FROM algo_portfolio_snapshots
                WHERE snapshot_date >= %s
                ORDER BY snapshot_date DESC
                LIMIT 1000
            """, (cutoff_date,))
            curve = cur.fetchall()
            freshness = check_data_freshness(cur, 'algo_portfolio_snapshots', 'snapshot_date', warning_days=1)
            return list_response([dict(c) for c in reversed(curve) if c], data_freshness=freshness)
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            logger.error(f'Data unavailable (equity curve): {e}', extra={'operation': 'fetch equity curve'})
            return error_response(503, 'service_unavailable', 'Data unavailable')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error (equity curve): {e}', extra={'operation': 'fetch equity curve'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error (equity curve): {e}', extra={'operation': 'fetch equity curve', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error (equity curve): {e}', extra={'operation': 'fetch equity curve', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch equity curve')

def _get_data_status(cur) -> Dict:
        """Get data freshness status with summary for ServiceHealth/AlgoTradingDashboard.

        Uses same trading-day-aware freshness logic as Phase 1 orchestrator to avoid
        false stale warnings on Monday holidays or 3-day weekends.
        """
        try:
            from algo.algo_market_calendar import MarketCalendar

            cur.execute("""
                SELECT table_name, row_count, last_updated
                FROM data_loader_status
                ORDER BY table_name
            """)
            rows = cur.fetchall()

            # Critical tables that must be fresh for live trading (same as Phase 1)
            CRITICAL_TABLES = {'price_daily', 'market_health_daily', 'trend_template_data'}

            # Compute expected data date using trading-day-aware logic (match Phase 1)
            today = date.today()
            expected_date = today - timedelta(days=1)
            try:
                for _ in range(10):
                    if MarketCalendar.is_trading_day(expected_date):
                        break
                    expected_date -= timedelta(days=1)
            except Exception:
                # Fallback: weekday check if MarketCalendar unavailable
                while expected_date.weekday() >= 5:
                    expected_date -= timedelta(days=1)

            sources = []
            summary = {'ok': 0, 'stale': 0, 'empty': 0, 'error': 0}
            critical_stale = []

            for row in rows:
                last_updated = row['last_updated']
                row_count = row['row_count'] or 0

                if row_count == 0:
                    status = 'empty'
                elif last_updated is None:
                    status = 'empty'
                else:
                    # Convert to date if datetime
                    data_date = last_updated.date() if hasattr(last_updated, 'date') else last_updated

                    # Use Phase 1 logic: stale if data_date < expected_date
                    if data_date < expected_date:
                        status = 'stale'
                    else:
                        status = 'ok'

                # Calculate age in hours for reference
                if last_updated:
                    age_h = (datetime.now(timezone.utc) - (last_updated if isinstance(last_updated, datetime) else datetime.combine(last_updated, datetime.min.time()))).total_seconds() / 3600
                else:
                    age_h = 999

                summary[status] = summary.get(status, 0) + 1
                if status in ('stale', 'empty') and row['table_name'] in CRITICAL_TABLES:
                    critical_stale.append(row['table_name'])
                sources.append({
                    'name': row['table_name'],
                    'status': status,
                    'last_updated': last_updated.isoformat() if last_updated else None,
                    'age_hours': round(age_h, 1),
                    'row_count': row_count,
                })

            ready_to_trade = len(critical_stale) == 0 and summary.get('ok', 0) > 0

            return json_response(200, {
                'ready_to_trade': ready_to_trade,
                'summary': summary,
                'sources': sources,
                'critical_stale': critical_stale,
                'expected_date': str(expected_date),
                'as_of': datetime.now(timezone.utc).isoformat(),
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            logger.error(f'Data unavailable (data status): {e}', extra={'operation': 'fetch data status'})
            return error_response(503, 'service_unavailable', 'Data unavailable')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error (data status): {e}', extra={'operation': 'fetch data status'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error (data status): {e}', extra={'operation': 'fetch data status', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error (data status): {e}', extra={'operation': 'fetch data status', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch data status')

def _get_notifications(cur, params: Dict = None, jwt_claims: Dict = None) -> Dict:
        """Get recent notifications. System broadcasts visible to all authenticated users."""
        try:
            params = params or {}
            kind = params.get('kind', [None])[0] if params.get('kind') else None
            severity = params.get('severity', [None])[0] if params.get('severity') else None
            unread = params.get('unread', [None])[0] if params.get('unread') else None
            limit_str = params.get('limit', [None])[0] if params.get('limit') else None
            limit = safe_limit(limit_str, max_val=10000, default=100)

            # SECURITY M-04: Validate kind and severity against whitelists
            VALID_KINDS = {'signal', 'halt', 'alert', 'error', 'trade', 'position', 'market', 'system', 'safeguard'}
            VALID_SEVERITIES = {'info', 'warning', 'error', 'critical'}

            if kind and kind not in VALID_KINDS:
                return error_response(400, 'bad_request', f'Invalid kind: {kind}')
            if severity and severity not in VALID_SEVERITIES:
                return error_response(400, 'bad_request', f'Invalid severity: {severity}')

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

            cur.execute(query, tuple(where_params))
            notifs = cur.fetchall()
            return list_response([dict(n) for n in notifs])
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to fetch notifications: {type(e).__name__}: {e}', extra={'operation': 'fetch notifications'})
            return list_response([])

def _analyze_pre_trade_impact(cur, body: Dict) -> Dict:
        """Analyze impact of a potential trade on portfolio constraints."""
        try:
            symbol = body.get('symbol', '').upper()
            entry_price = float(body.get('entry_price', 0)) if body.get('entry_price') else None
            position_dollars = body.get('position_dollars')
            position_pct = body.get('position_pct')

            if not symbol:
                return error_response(400, 'bad_request', 'symbol is required')

            cur.execute("""
                SELECT COUNT(*) AS position_count,
                       SUM(CASE WHEN pd.quantity > 0 THEN pd.position_value ELSE 0 END) AS invested
                FROM algo_positions pd
                WHERE LOWER(pd.status) = 'open'
            """)
            portfolio_row = dict(cur.fetchone() or {})
            current_positions = portfolio_row.get('position_count', 0)
            invested = float(portfolio_row.get('invested') or 0)

            cur.execute("""
                SELECT total_portfolio_value FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1
            """)
            snap = cur.fetchone()
            portfolio_value = float(snap['total_portfolio_value']) if snap and snap['total_portfolio_value'] else 100000.0

            cur.execute("""
                SELECT sector, industry FROM company_profile WHERE ticker = %s
            """, (symbol,))
            profile = cur.fetchone()
            sector = profile['sector'] if (profile and hasattr(profile, '__getitem__')) else 'Unknown'
            industry = profile['industry'] if (profile and hasattr(profile, '__getitem__')) else 'Unknown'

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

            # Read live limits from algo_config (fall back to conservative defaults)
            try:
                cur.execute("""
                    SELECT key, value FROM algo_config
                    WHERE key IN ('max_positions', 'max_position_pct', 'max_sector_pct')
                """)
                cfg = {row['key']: row['value'] for row in cur.fetchall()}
            except Exception as e:
                logger.warning(f"API exception: {e}")
                cfg = {}
            max_positions = int(cfg.get('max_positions', 12))
            max_position_pct = float(cfg.get('max_position_pct', 8.0))
            max_sector_pct = float(cfg.get('max_sector_pct', 30.0))

            position_limit_ok = current_positions < max_positions
            position_size_ok = position_pct_calc <= max_position_pct
            cash_available = portfolio_value - invested
            cash_ok = cash_available >= position_size_dollars

            cur.execute("""
                SELECT SUM(CASE WHEN cp.sector = %s THEN pd.position_value ELSE 0 END) /
                       NULLIF((SELECT SUM(position_value) FROM algo_positions), 0) * 100 AS sector_pct
                FROM algo_positions pd
                JOIN company_profile cp ON pd.symbol = cp.ticker
            """, (sector,))
            sector_row = dict(cur.fetchone() or {})
            current_sector_pct = float(sector_row.get('sector_pct') or 0)
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
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            logger.error(f'Data unavailable: {e}', extra={'operation': 'analyze pre trade impact'})
            return error_response(503, 'service_unavailable', 'Data unavailable')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'analyze pre trade impact'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'analyze pre trade impact', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'analyze pre trade impact', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to analyze trade impact')
def _trigger_data_patrol() -> Dict:
        """Trigger async data patrol ECS task."""
        try:
            ecs = boto3.client('ecs')

            cluster_arn = os.getenv('ECS_CLUSTER_ARN', '')
            task_def_arn = os.getenv('PATROL_TASK_DEFINITION_ARN', '')
            container_name = os.getenv('PATROL_CONTAINER_NAME', 'algo-data-patrol')
            subnet_ids = os.getenv('PATROL_SUBNET_IDS', '').split(',') if os.getenv('PATROL_SUBNET_IDS') else []
            sg_id = os.getenv('PATROL_SECURITY_GROUP_ID', '')

            # FIXED Issue #19: Validate patrol task definition before attempting to run
            if not cluster_arn or not task_def_arn:
                logger.error("Patrol task not configured (missing ECS_CLUSTER_ARN or PATROL_TASK_DEFINITION_ARN)")
                return error_response(400, 'bad_request', 'Patrol service not configured (check environment variables)')

            # Validate task definition ARN format
            if not task_def_arn.startswith('arn:aws:ecs:'):
                logger.error(f"Invalid patrol task definition ARN format: {task_def_arn}")
                return error_response(400, 'bad_request', 'Invalid patrol task definition configuration')

            # Attempt to validate task definition exists (early fail if misconfigured)
            try:
                ecs.describe_task_definition(taskDefinition=task_def_arn)
                logger.info(f"Patrol task definition validated: {task_def_arn}")
            except ecs.exceptions.ClientError as desc_err:
                if desc_err.response['Error']['Code'] == 'ClientException':
                    logger.error(f"Patrol task definition not found: {task_def_arn}")
                    return error_response(400, 'bad_request', 'Patrol task definition not found')
                raise  # Re-raise other errors to be caught by outer exception handler

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
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            logger.error(f'Data unavailable: {e}', extra={'operation': 'trigger data patrol'})
            return error_response(503, 'service_unavailable', 'Data unavailable')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'trigger data patrol'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'trigger data patrol', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'trigger data patrol', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to trigger data patrol')
def _get_patrol_log(cur, limit: int = 50, offset: int = 0) -> Dict:
        """Get data patrol findings with pagination."""
        try:
            cur.execute("SELECT COUNT(*) as total FROM data_patrol_log")
            row = cur.fetchone()
            total = row['total'] if row else 0

            cur.execute("""
                SELECT created_at, check_name, severity, target_table, message, patrol_run_id
                FROM data_patrol_log
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            findings = cur.fetchall()
            return list_response([dict(f) for f in findings], total=total)
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to fetch patrol log: {type(e).__name__}: {e}', extra={'operation': 'get patrol log'})
            return list_response([], total=0)
def _get_sector_rotation(cur, days: int = 180) -> Dict:
        """Get sector rotation data: defensive vs cyclical relative strength."""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            cur.execute("""
                WITH defensive_sectors AS (
                    SELECT 'Consumer Defensive' AS sector UNION ALL
                    SELECT 'Utilities' UNION ALL
                    SELECT 'Healthcare' UNION ALL
                    SELECT 'Real Estate'
                ),
                cyclical_sectors AS (
                    SELECT 'Consumer Cyclical' AS sector UNION ALL
                    SELECT 'Industrials' UNION ALL
                    SELECT 'Basic Materials' UNION ALL
                    SELECT 'Technology'
                ),
                sector_perf AS (
                    SELECT
                        date,
                        sector,
                        COALESCE(return_pct, 0) AS return_pct,
                        COALESCE(relative_strength, 0) AS relative_strength
                    FROM sector_performance
                    WHERE date >= %s
                ),
                rotation_stats AS (
                    SELECT
                        sp.date,
                        AVG(CASE WHEN d.sector IS NOT NULL THEN sp.return_pct ELSE NULL END) AS defensive_return,
                        AVG(CASE WHEN c.sector IS NOT NULL THEN sp.return_pct ELSE NULL END) AS cyclical_return,
                        AVG(CASE WHEN d.sector IS NOT NULL THEN sp.relative_strength ELSE NULL END) AS defensive_strength,
                        AVG(CASE WHEN c.sector IS NOT NULL THEN sp.relative_strength ELSE NULL END) AS cyclical_strength
                    FROM sector_perf sp
                    LEFT JOIN defensive_sectors d ON sp.sector = d.sector
                    LEFT JOIN cyclical_sectors c ON sp.sector = c.sector
                    WHERE d.sector IS NOT NULL OR c.sector IS NOT NULL
                    GROUP BY sp.date
                ),
                rotation_with_signal AS (
                    SELECT
                        date,
                        defensive_strength,
                        cyclical_strength,
                        CASE
                            WHEN defensive_strength > cyclical_strength THEN 'DEFENSIVE'
                            WHEN cyclical_strength > defensive_strength THEN 'CYCLICAL'
                            ELSE 'NEUTRAL'
                        END AS signal
                    FROM rotation_stats
                ),
                signal_changes AS (
                    SELECT
                        date,
                        defensive_strength,
                        cyclical_strength,
                        signal,
                        CASE WHEN signal != LAG(signal) OVER (ORDER BY date DESC) THEN 1 ELSE 0 END AS is_signal_change
                    FROM rotation_with_signal
                ),
                signal_groups AS (
                    SELECT
                        date,
                        defensive_strength,
                        cyclical_strength,
                        signal,
                        SUM(is_signal_change) OVER (ORDER BY date DESC) AS signal_group_id
                    FROM signal_changes
                )
                SELECT
                    date,
                    ROUND((COALESCE(defensive_strength, 0))::NUMERIC, 2) AS defensive_lead_score,
                    ROUND((COALESCE(cyclical_strength, 0))::NUMERIC, 2) AS cyclical_weak_score,
                    ROUND((COALESCE(defensive_strength, 0) - COALESCE(cyclical_strength, 0))::NUMERIC, 2) AS spread,
                    signal,
                    ROW_NUMBER() OVER (PARTITION BY signal_group_id ORDER BY date DESC) AS weeks_persistent
                FROM signal_groups
                ORDER BY date DESC
            """, (cutoff_date,))
            rotation = cur.fetchall()
            return list_response([dict(r) for r in rotation])
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to fetch sector rotation: {type(e).__name__}: {e}', extra={'operation': 'get sector rotation'})
            return list_response([])
def _get_sector_breadth(cur) -> Dict:
        """Get sector breadth indicators: % of stocks above 50-day and 200-day moving averages.

        Uses pre-computed sma_50/sma_200 from technical_data_daily (fast indexed lookup)
        instead of recomputing window functions over 290 days of price_daily (too slow on
        t4g.micro — caused 20s timeout). Joins latest tech row per symbol with company_profile.
        """
        try:
            # SAVEPOINT isolation: sector breadth joins price_daily + technical_data_daily.
            # Both tables receive heavy writes from ECS loaders — a timeout here must not
            # abort the outer transaction and break subsequent API requests in the same Lambda.
            cur.execute("SAVEPOINT sector_breadth_check")
            cur.execute("SET LOCAL statement_timeout = '8s'")
            cur.execute("""
                WITH latest_tech AS (
                    SELECT DISTINCT ON (tdd.symbol)
                        tdd.symbol, tdd.sma_50, tdd.sma_200
                    FROM technical_data_daily tdd
                    WHERE tdd.date >= CURRENT_DATE - INTERVAL '7 days'
                    ORDER BY tdd.symbol, tdd.date DESC
                ),
                latest_price AS (
                    SELECT DISTINCT ON (pd.symbol)
                        pd.symbol, pd.close
                    FROM price_daily pd
                    WHERE pd.date >= CURRENT_DATE - INTERVAL '7 days'
                      AND pd.symbol NOT LIKE '^%%'
                    ORDER BY pd.symbol, pd.date DESC
                ),
                sector_breadth AS (
                    SELECT
                        cp.sector,
                        COUNT(lt.symbol) FILTER (WHERE lp.close IS NOT NULL AND lt.sma_50 IS NOT NULL AND lp.close > lt.sma_50) * 100.0 /
                            NULLIF(COUNT(lt.symbol) FILTER (WHERE lt.sma_50 IS NOT NULL AND lp.close IS NOT NULL), 0) AS pct_above_50d,
                        COUNT(lt.symbol) FILTER (WHERE lp.close IS NOT NULL AND lt.sma_200 IS NOT NULL AND lp.close > lt.sma_200) * 100.0 /
                            NULLIF(COUNT(lt.symbol) FILTER (WHERE lt.sma_200 IS NOT NULL AND lp.close IS NOT NULL), 0) AS pct_above_200d
                    FROM latest_tech lt
                    JOIN latest_price lp ON lt.symbol = lp.symbol
                    JOIN company_profile cp ON lt.symbol = cp.ticker
                    WHERE cp.sector IS NOT NULL
                    GROUP BY cp.sector
                )
                SELECT
                    sector,
                    ROUND(COALESCE(pct_above_50d, 0)::NUMERIC, 2) AS pct_above_50d,
                    ROUND(COALESCE(pct_above_200d, 0)::NUMERIC, 2) AS pct_above_200d
                FROM sector_breadth
                ORDER BY pct_above_50d DESC
            """)
            breadth = cur.fetchall()
            cur.execute("RELEASE SAVEPOINT sector_breadth_check")
            return list_response([dict(b) for b in breadth])
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sector_breadth_check")
                cur.execute("RELEASE SAVEPOINT sector_breadth_check")
            except Exception as sp_err:
                logger.debug(f'Failed to rollback sector_breadth_check savepoint: {sp_err}')
            logger.warning(f'Sector breadth data unavailable: {e}')
            return list_response([])
        except (psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sector_breadth_check")
                cur.execute("RELEASE SAVEPOINT sector_breadth_check")
            except Exception as sp_err:
                logger.debug(f'Failed to rollback sector_breadth_check savepoint: {sp_err}')
            logger.warning(f'Sector breadth query failed ({type(e).__name__}) — returning empty. DB may be under write load.')
            return list_response([])
def _get_swing_scores(cur, limit: int = 100, min_score: float = None, symbol: str = None) -> Dict:
        """Get swing trade candidates with scoring."""
        try:
            cur.execute("SET LOCAL statement_timeout = '25000ms'")
            # Use psycopg2.sql for safe SQL composition
            filters = [psycopg2.sql.SQL("s.date >= CURRENT_DATE - INTERVAL '14 days'")]
            query_params = []
            if min_score is not None:
                filters.append(psycopg2.sql.SQL("s.score >= %s"))
                query_params.append(min_score)
            if symbol:
                filters.append(psycopg2.sql.SQL("s.symbol = %s"))
                query_params.append(symbol.upper())
            where_clause = psycopg2.sql.SQL(" AND ").join(filters)
            query_params.append(limit)
            query = psycopg2.sql.SQL("""
                SELECT
                    s.symbol, s.date, s.score AS swing_score,
                    s.components->>'grade' AS grade,
                    COALESCE((s.components->>'pass_gates')::boolean, false) AS pass_gates,
                    s.components->>'fail_reason' AS fail_reason,
                    s.components AS components,
                    cp.sector, cp.industry,
                    t.weinstein_stage AS stage, t.minervini_trend_score AS trend_template_score,
                    jsonb_build_object('weinstein_stage', t.weinstein_stage, 'trend_template_score', t.minervini_trend_score, 'stage_substage', 'Stage ' || COALESCE(t.weinstein_stage::text, '')) AS details
                FROM swing_trader_scores s
                LEFT JOIN company_profile cp ON s.symbol = cp.ticker
                LEFT JOIN trend_template_data t ON s.symbol = t.symbol AND s.date = t.date
                WHERE {where_clause}
                ORDER BY s.date DESC, s.score DESC
                LIMIT %s
            """).format(where_clause=where_clause)
            cur.execute(query, query_params)
            scores = cur.fetchall()
            return list_response([dict(s) for s in scores])
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to fetch swing scores: {type(e).__name__}: {e}', extra={'operation': 'get swing scores'})
            return list_response([])
def _get_swing_scores_history(cur, days: int = 30) -> Dict:
        """Get swing scores historical data."""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            cur.execute("""
                SELECT date AS eval_date,
                    COUNT(CASE WHEN (components->>'grade') = 'A+' THEN 1 END) AS grade_aplus,
                    COUNT(CASE WHEN (components->>'grade') = 'A'  THEN 1 END) AS grade_a,
                    COUNT(CASE WHEN (components->>'pass_gates')::boolean IS TRUE THEN 1 END) AS pass_count,
                    COUNT(*) AS total_candidates,
                    ROUND(AVG(score)::NUMERIC, 1) AS avg_score
                FROM swing_trader_scores
                WHERE date >= %s
                GROUP BY date
                ORDER BY date ASC
            """, (cutoff_date,))
            history = cur.fetchall()
            return list_response([dict(h) for h in history])
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to fetch swing scores history: {type(e).__name__}: {e}', extra={'operation': 'get swing scores history'})
            return list_response([])
def _get_rejection_funnel(cur) -> Dict:
        """Get signal rejection funnel with detailed breakdown by filter."""
        try:
            # Get total initial signals
            cur.execute("""
                SELECT COUNT(DISTINCT symbol) as total_signals
                FROM buy_sell_daily
                WHERE date >= CURRENT_DATE - INTERVAL '14 days'
            """)
            row = cur.fetchone()
            initial_count = dict(row).get('total_signals', 0) if row else 0

            # Get scored candidates
            cur.execute("""
                SELECT COUNT(DISTINCT symbol) as scored
                FROM swing_trader_scores
                WHERE date >= CURRENT_DATE - INTERVAL '14 days'
            """)
            row = cur.fetchone()
            scored_count = dict(row).get('scored', 0) if row else 0

            # Get high-quality candidates (SQS > 60)
            cur.execute("""
                SELECT COUNT(DISTINCT symbol) as high_quality
                FROM swing_trader_scores
                WHERE date >= CURRENT_DATE - INTERVAL '14 days'
                AND score >= 60
            """)
            row = cur.fetchone()
            high_quality_count = dict(row).get('high_quality', 0) if row else 0

            # Build funnel stages with rejection reasons
            funnel = [
                {
                    'stage': 'All Signals Generated',
                    'count': initial_count,
                    'pct': 100,
                    'rejection_reason': None,
                    'rejection_count': 0,
                    'rejection_pct': 0
                }
            ]

            if initial_count > 0:
                scored_rejection = initial_count - scored_count
                scored_pct = round((scored_count / initial_count * 100), 2) if initial_count else 0

                funnel.append({
                    'stage': 'Passed Quality Filters',
                    'count': scored_count,
                    'pct': scored_pct,
                    'rejection_reason': 'Failed SQS calculation or data validation',
                    'rejection_count': scored_rejection,
                    'rejection_pct': round((scored_rejection / initial_count * 100), 2) if initial_count else 0
                })

                if scored_count > 0:
                    hq_rejection = scored_count - high_quality_count
                    hq_pct = round((high_quality_count / scored_count * 100), 2) if scored_count else 0

                    funnel.append({
                        'stage': 'High-Quality Candidates (SQS ≥ 60)',
                        'count': high_quality_count,
                        'pct': hq_pct,
                        'rejection_reason': 'Low signal quality score (SQS < 60)',
                        'rejection_count': hq_rejection,
                        'rejection_pct': round((hq_rejection / scored_count * 100), 2) if scored_count else 0
                    })

            return json_response(200, {
                'funnel': funnel,
                'summary': {
                    'total_initial': initial_count,
                    'total_passed': high_quality_count,
                    'total_rejected': initial_count - high_quality_count,
                    'pass_rate_pct': round((high_quality_count / initial_count * 100), 2) if initial_count else 0
                }
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to fetch rejection funnel: {type(e).__name__}: {e}', extra={'operation': 'get rejection funnel'})
            return json_response(200, {'funnel': [], 'summary': {'total_initial': 0, 'total_passed': 0, 'total_rejected': 0, 'pass_rate_pct': 0}})
_TIER_CONFIG = {
    'confirmed_uptrend': {
        'description': 'Confirmed uptrend — full deployment',
        'min_pct': 70, 'max_pct': 100,
        'risk_mult': 1.0,  'risk_multiplier': 1.0,
        'max_new': 5,      'max_new_positions_today': 5,
        'halt': False,     'halt_new_entries': False,
        'min_grade': 'B',  'min_swing_grade': 'B',
        'min_swing_score': 60.0,
    },
    'uptrend_under_pressure': {
        'description': 'Uptrend under pressure — reduced exposure',
        'min_pct': 45, 'max_pct': 70,
        'risk_mult': 0.6,  'risk_multiplier': 0.6,
        'max_new': 3,      'max_new_positions_today': 3,
        'halt': False,     'halt_new_entries': False,
        'min_grade': 'B',  'min_swing_grade': 'B',
        'min_swing_score': 65.0,
    },
    'caution': {
        'description': 'Caution — entries halted unless exceptional',
        'min_pct': 25, 'max_pct': 45,
        'risk_mult': 0.3,  'risk_multiplier': 0.3,
        'max_new': 1,      'max_new_positions_today': 1,
        'halt': True,      'halt_new_entries': True,
        'min_grade': 'A',  'min_swing_grade': 'A',
        'min_swing_score': 75.0,
    },
    'correction': {
        'description': 'Market correction — preserve capital',
        'min_pct': 0,  'max_pct': 25,
        'risk_mult': 0.2,  'risk_multiplier': 0.2,
        'max_new': 0,      'max_new_positions_today': 0,
        'halt': True,      'halt_new_entries': True,
        'min_grade': 'A+', 'min_swing_grade': 'A+',
        'min_swing_score': 100.0,
    },
}

def _get_markets(cur) -> Dict:
        """Get current market regime data and historical exposure."""
        try:
            cur.execute("SET LOCAL statement_timeout = '8000ms'")
            cur.execute("""
                SELECT date, exposure_pct, raw_score, regime, distribution_days, factors, halt_reasons
                FROM market_exposure_daily
                ORDER BY date DESC
                LIMIT 1
            """)
            latest = cur.fetchone()
            current = dict(latest) if latest else None

            active_tier = {}
            if current:
                tier_key = str(current.get('regime') or '').lower()
                tier_conf = _TIER_CONFIG.get(tier_key, {})
                active_tier = {'name': tier_key, **tier_conf}
                active_tier['halt'] = bool(current.get('halt_reasons')) or tier_conf.get('halt', False)

            cur.execute("""
                SELECT date, exposure_pct, regime
                FROM market_exposure_daily
                WHERE date >= CURRENT_DATE - INTERVAL '30 days'
                ORDER BY date ASC
                LIMIT 250
            """)
            history = [dict(h) for h in cur.fetchall()]

            try:
                cur.execute("""
                    SELECT sector_name AS name, current_rank AS rank, rank_4w_ago, momentum_score AS momentum
                    FROM sector_ranking
                    WHERE date = (SELECT MAX(date) FROM sector_ranking)
                    ORDER BY current_rank
                    LIMIT 20
                """)
                sectors = [dict(s) for s in cur.fetchall()]
            except Exception as e:
                logger.warning(f"[MARKETS] sector_ranking query failed: {e}")
                sectors = []

            market_health = None
            try:
                cur.execute("""
                    SELECT market_trend, market_stage, vix_level
                    FROM market_health_daily
                    ORDER BY date DESC LIMIT 1
                """)
                mh = cur.fetchone()
                if mh:
                    market_health = dict(mh)
            except Exception as e:
                logger.warning(f"[MARKETS] market_health_daily unavailable: {type(e).__name__}: {e}")

            return json_response(200, {
                'success': True,
                'current': current,
                'active_tier': active_tier,
                'history': history,
                'sectors': sectors,
                'market_health': market_health,
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to fetch markets: {type(e).__name__}: {e}', extra={'operation': 'get markets'})
            return json_response(200, {'success': False, 'current': {}, 'active_tier': None, 'history': [], 'sectors': [], 'market_health': None})

def _get_algo_evaluate(cur) -> Dict:
        """Get comprehensive signal evaluation with candidate analysis and constraints."""
        try:
            # Signal candidate metrics
            cur.execute("""
                SELECT
                    COUNT(DISTINCT symbol) AS candidates_screened,
                    COUNT(DISTINCT CASE WHEN score >= 60 THEN symbol END) AS candidates_passing,
                    COUNT(DISTINCT CASE WHEN score >= 70 THEN symbol END) AS candidates_excellent,
                    COUNT(DISTINCT CASE WHEN score >= 80 THEN symbol END) AS candidates_exceptional,
                    MAX(score) AS top_score,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY score) AS median_score,
                    AVG(score) AS avg_score,
                    MIN(score) AS min_score
                FROM swing_trader_scores
                WHERE date >= CURRENT_DATE - INTERVAL '14 days'
            """)
            sig_row = cur.fetchone()
            if not sig_row or not sig_row.get('candidates_screened'):
                return json_response(200, {
                    'stage': 'no_data',
                    'candidates_screened': 0,
                    'candidates_passing': 0,
                    'constraints': {'max_positions': 12, 'current_positions': 0, 'available_slots': 12}
                })

            # Current portfolio positions and constraints
            cur.execute("""
                SELECT COUNT(*) as open_positions
                FROM algo_positions
                WHERE LOWER(status) = 'open'
            """)
            pos_row = cur.fetchone()
            open_positions = pos_row['open_positions'] if pos_row else 0

            max_positions = 12  # From steering doc
            available_slots = max(0, max_positions - open_positions)

            # Sector exposure
            cur.execute("""
                SELECT cp.sector, COUNT(DISTINCT at.symbol) as count
                FROM algo_trades at
                JOIN company_profile cp ON at.symbol = cp.ticker
                WHERE at.status = 'open'
                GROUP BY cp.sector
                ORDER BY count DESC
            """)
            sector_exposure = [dict(r) for r in cur.fetchall()]

            # Risk metrics
            cur.execute("""
                SELECT
                    COALESCE(MAX(CASE WHEN snapshot_date = CURRENT_DATE THEN daily_return_pct END), 0) as today_return_pct,
                    COALESCE(MAX(CASE WHEN snapshot_date = CURRENT_DATE THEN unrealized_pnl_total END), 0) as unrealized_pnl
                FROM algo_portfolio_snapshots
            """)
            risk_row = cur.fetchone()
            today_return = risk_row.get('today_return_pct', 0) if risk_row else 0
            unrealized_pnl = risk_row.get('unrealized_pnl', 0) if risk_row else 0

            sig_dict = dict(sig_row)
            return json_response(200, {
                'stage': 'evaluated',
                'candidates': {
                    'screened': sig_dict.get('candidates_screened', 0),
                    'passing_sqs_60': sig_dict.get('candidates_passing', 0),
                    'excellent_sqs_70': sig_dict.get('candidates_excellent', 0),
                    'exceptional_sqs_80': sig_dict.get('candidates_exceptional', 0),
                    'score_range': {
                        'min': float(sig_dict.get('min_score', 0) or 0),
                        'median': float(sig_dict.get('median_score', 0) or 0),
                        'average': float(sig_dict.get('avg_score', 0) or 0),
                        'max': float(sig_dict.get('top_score', 0) or 0),
                    }
                },
                'constraints': {
                    'max_positions': max_positions,
                    'current_positions': open_positions,
                    'available_slots': available_slots,
                    'can_add_positions': available_slots > 0
                },
                'sector_exposure': sector_exposure,
                'portfolio_health': {
                    'today_return_pct': float(today_return or 0),
                    'unrealized_pnl': float(unrealized_pnl or 0)
                }
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to evaluate algorithm: {type(e).__name__}: {e}', extra={'operation': 'get algo evaluate'})
            return json_response(200, {'signals': {'total_candidates': 0}, 'constraints': {}, 'sector_exposure': {}, 'portfolio_health': {}})
def _get_data_quality(cur) -> Dict:
        """Get detailed data quality summary by table from latest data_patrol_log run."""
        try:
            # Get patrol log entries from last 24 hours
            cur.execute("""
                SELECT
                    target_table AS table_name,
                    severity,
                    message,
                    NULL AS data_detail,
                    created_at,
                    ROW_NUMBER() OVER (PARTITION BY target_table ORDER BY created_at DESC) as rn
                FROM data_patrol_log
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            """)
            patrol_rows = cur.fetchall()

            if not patrol_rows:
                return json_response(200, {
                    'accuracy_check': 'no_data',
                    'last_check': None,
                    'tables': [],
                    'summary': {'critical': 0, 'errors': 0, 'warnings': 0, 'healthy': 0}
                })

            # Organize by table, keeping latest status per table
            tables_dict = {}
            for row in patrol_rows:
                row_dict = dict(row)
                if row_dict.get('rn') == 1:  # Latest entry per table
                    table_name = row_dict.get('table_name', 'unknown')
                    tables_dict[table_name] = row_dict

            # Get latest timestamp
            latest_ts = max([r['created_at'] for r in patrol_rows]) if patrol_rows else None

            # Compute summary
            severity_counts = {'critical': 0, 'error': 0, 'warn': 0, 'healthy': 0}
            table_statuses = []
            for table_name, entry in tables_dict.items():
                severity = entry.get('severity', 'healthy')
                severity_counts[severity if severity in severity_counts else 'warn'] += 1
                status_label = 'failed' if severity == 'critical' else 'warning' if severity in ('error', 'warn') else 'passed'

                table_statuses.append({
                    'table': table_name,
                    'status': status_label,
                    'severity': severity,
                    'message': entry.get('message'),
                    'detail': entry.get('data_detail'),
                    'last_check': entry.get('created_at').isoformat() if entry.get('created_at') else None
                })

            # Determine overall accuracy
            if severity_counts['critical'] > 0:
                accuracy = 'failed'
            elif severity_counts['error'] > 0:
                accuracy = 'error'
            elif severity_counts['warn'] > 0:
                accuracy = 'warning'
            else:
                accuracy = 'passed'

            # Sort tables by status severity
            status_order = {'failed': 0, 'error': 1, 'warning': 2, 'passed': 3}
            table_statuses.sort(key=lambda x: status_order.get(x['status'], 4))

            return json_response(200, {
                'accuracy_check': accuracy,
                'last_check': latest_ts.isoformat() if latest_ts else None,
                'tables': table_statuses,
                'summary': {
                    'critical': severity_counts['critical'],
                    'errors': severity_counts['error'],
                    'warnings': severity_counts['warn'],
                    'healthy': severity_counts['healthy'],
                    'total_tables_checked': len(tables_dict)
                }
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to check data quality: {type(e).__name__}: {e}', extra={'operation': 'get data quality'})
            return json_response(200, {'accuracy_check': 'error', 'last_check': None, 'tables': [], 'summary': {'critical': 0, 'errors': 0, 'warnings': 0, 'healthy': 0}})
def _get_exposure_policy(cur) -> Dict:
        """Get detailed market exposure policy with calculation factors."""
        try:
            cur.execute("""
                SELECT date, exposure_pct, regime, factors, halt_reasons, distribution_days
                FROM market_exposure_daily
                ORDER BY date DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                return json_response(200, {
                    'current_exposure_pct': None,
                    'active_tier': None,
                    'all_tiers': [{'name': k, **v} for k, v in _TIER_CONFIG.items()],
                    'regime_factors': {}
                })

            row = dict(row)
            tier_key = str(row.get('regime') or '').lower()
            tier_conf = _TIER_CONFIG.get(tier_key, {})
            active_tier = {'name': tier_key, **tier_conf}
            active_tier['halt'] = bool(row.get('halt_reasons')) or tier_conf.get('halt', False)

            # Parse factors from JSON if available
            factors = {}
            if row.get('factors'):
                try:
                    if isinstance(row['factors'], str):
                        factors = json.loads(row['factors'])
                    else:
                        factors = row['factors']
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning(f"Failed to parse factors: {e}")
                    factors = {}

            # Get latest market health for additional context
            market_health = {}
            try:
                cur.execute("""
                    SELECT
                        market_stage, market_trend, vix_level,
                        advance_decline_ratio, new_highs_count, new_lows_count,
                        distribution_days_4w, breadth_momentum_10d
                    FROM market_health_daily
                    ORDER BY date DESC
                    LIMIT 1
                """)
                mh_row = cur.fetchone()
                if mh_row:
                    market_health = dict(mh_row)
            except psycopg2.Error as e:
                logger.warning(f"Failed to fetch market health: {e}")

            return json_response(200, {
                'current_exposure_pct': float(row.get('exposure_pct') or 0),
                'exposure_tier': tier_key,
                'is_entry_allowed': not active_tier['halt'],
                'active_tier': active_tier,
                'all_tiers': [{'name': k, **v} for k, v in _TIER_CONFIG.items()],
                'regime_factors': {
                    'sp500_stage': factors.get('stage_number'),
                    'advance_decline_ratio': factors.get('ad_ratio') or market_health.get('advance_decline_ratio'),
                    'vix_level': factors.get('vix') or market_health.get('vix_level'),
                    'breadth_momentum': factors.get('breadth_momentum') or market_health.get('breadth_momentum_10d'),
                    'distribution_days': row.get('distribution_days') or market_health.get('distribution_days_4w'),
                    'market_stage': market_health.get('market_stage'),
                    'market_trend': market_health.get('market_trend'),
                    'mcclellan_oscillator': factors.get('mcclellan'),
                },
                'halt_reasons': row.get('halt_reasons'),
                'as_of': row['date'].isoformat() if row['date'] else None,
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to fetch exposure policy: {type(e).__name__}: {e}', extra={'operation': 'get exposure policy'})
            return json_response(200, {'current_exposure_pct': 0, 'regime': 'unknown', 'halt_reasons': [], 'factors': {}, 'as_of': None})
def _get_sector_stage2(cur) -> Dict:
        """Get percentage of stocks in Stage 2 by sector."""
        try:
            cur.execute("""
                WITH latest_date AS (
                    SELECT date FROM trend_template_data ORDER BY date DESC LIMIT 1
                ),
                stage2_counts AS (
                    SELECT
                        cp.sector,
                        COUNT(CASE WHEN t.weinstein_stage = 2 THEN 1 END) AS stage_2,
                        COUNT(t.symbol) AS total
                    FROM trend_template_data t
                    JOIN company_profile cp ON t.symbol = cp.ticker
                    WHERE t.date = (SELECT date FROM latest_date)
                      AND cp.sector IS NOT NULL
                    GROUP BY cp.sector
                )
                SELECT
                    sector,
                    stage_2,
                    total,
                    ROUND((stage_2::FLOAT / NULLIF(total, 0) * 100)::NUMERIC, 2) AS pct_stage_2
                FROM stage2_counts
                ORDER BY pct_stage_2 DESC
            """)
            rows = cur.fetchall()
            return list_response([dict(r) for r in rows])
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            logger.warning(f'Sector stage2 data unavailable: {e}')
            return error_response(503, 'service_unavailable', 'Data unavailable')
        except psycopg2.OperationalError as e:
            logger.error(f'Sector stage2 DB connection error: {e}')
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Sector stage2 DB error: {e}')
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Sector stage2 unexpected error: {e}')
            return error_response(500, 'internal_error', 'Failed to fetch sector stage2')
def _get_algo_config(cur) -> Dict:
        """Return all algo configuration rows."""
        try:
            cur.execute("SELECT key, value, value_type, description, updated_at FROM algo_config ORDER BY key")
            rows = cur.fetchall()
            return list_response([dict(r) for r in rows])
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            logger.error(f'Data unavailable: {e}', extra={'operation': 'get algo config'})
            return error_response(503, 'service_unavailable', 'Data unavailable')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get algo config'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get algo config', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get algo config', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch algo config')
def _get_algo_config_key(cur, key: str) -> Dict:
        """Return a single algo config key."""
        try:
            cur.execute("SELECT key, value, value_type, description, updated_at FROM algo_config WHERE key = %s", (key,))
            row = cur.fetchone()
            return json_response(200, dict(row) if row else {})
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            logger.error(f'Data unavailable: {e}', extra={'operation': 'get algo config key'})
            return error_response(503, 'service_unavailable', 'Data unavailable')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get algo config key'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get algo config key', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get algo config key', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch config key')
def _get_algo_audit_log(cur, limit: int = 100, offset: int = 0, action_type: str = None) -> Dict:
        """Return algo audit log entries with pagination."""
        try:
            if action_type:
                cur.execute("SELECT COUNT(*) as total FROM algo_audit_log WHERE action_type = %s", (action_type,))
            else:
                cur.execute("SELECT COUNT(*) as total FROM algo_audit_log")
            total = cur.fetchone()['total']

            if action_type:
                cur.execute("""
                    SELECT id, action_type, symbol, action_date, details, actor, status,
                           error_message AS error, created_at
                    FROM algo_audit_log
                    WHERE action_type = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (action_type, limit, offset))
            else:
                cur.execute("""
                    SELECT id, action_type, symbol, action_date, details, actor, status,
                           error_message AS error, created_at
                    FROM algo_audit_log
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
            rows = cur.fetchall()
            return list_response([dict(r) for r in rows], total=total, limit=limit, offset=offset)
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            logger.error(f'Data unavailable: {e}', extra={'operation': 'get algo audit log'})
            return error_response(503, 'service_unavailable', 'Data unavailable')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get algo audit log'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get algo audit log', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get algo audit log', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch audit log')
