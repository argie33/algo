"""Route: algo"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re, json, os, sys, importlib.util
from datetime import datetime, timedelta, date, timezone
import boto3
from botocore.exceptions import ClientError
from pathlib import Path
from routes.utils import (
    error_response, success_response, list_response, json_response,
    safe_limit, safe_days, safe_offset, handle_db_error, db_route_handler,
    check_data_freshness, safe_json_serialize
)

# Import from root utils package using importlib to avoid package shadowing issues
# (there's both /lambda/api/utils/ and /utils/ which causes conflicts)
_root_dir = str(Path(__file__).parent.parent.parent.parent)
# Ensure root utils is in sys.path for importlib modules to find it
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)
import importlib.util
_admin_spec = importlib.util.spec_from_file_location(
    "admin_rate_limiter",
    str(Path(_root_dir) / "utils" / "admin_rate_limiter.py")
)
_admin_module = importlib.util.module_from_spec(_admin_spec)
_admin_spec.loader.exec_module(_admin_module)
check_admin_rate_limit = _admin_module.check_admin_rate_limit
ADMIN_RATE_LIMITS = _admin_module.ADMIN_RATE_LIMITS

_safe_spec = importlib.util.spec_from_file_location(
    "safe_data_conversion",
    str(Path(_root_dir) / "utils" / "safe_data_conversion.py")
)
_safe_module = importlib.util.module_from_spec(_safe_spec)
_safe_spec.loader.exec_module(_safe_module)
safe_float = _safe_module.safe_float
safe_float_strict = _safe_module.safe_float_strict
safe_int = _safe_module.safe_int

# Import unified metrics fetcher (same source used by dashboard)
_fetcher_spec = importlib.util.spec_from_file_location(
    "algo_metrics_fetcher",
    str(Path(_root_dir) / "utils" / "algo_metrics_fetcher.py")
)
_fetcher_module = importlib.util.module_from_spec(_fetcher_spec)
_fetcher_spec.loader.exec_module(_fetcher_module)
AlgoMetricsFetcher = _fetcher_module.AlgoMetricsFetcher

# Import fallback registry to use documented fallback values
_fallback_spec = importlib.util.spec_from_file_location(
    "fallback_registry",
    str(Path(_root_dir) / "utils" / "fallback_registry.py")
)
_fallback_module = importlib.util.module_from_spec(_fallback_spec)
_fallback_spec.loader.exec_module(_fallback_module)
get_hardcoded_fallback_values = _fallback_module.get_hardcoded_fallback_values
log_fallback_usage = _fallback_module.log_fallback_usage
FallbackTrigger = _fallback_module.FallbackTrigger

logger = logging.getLogger(__name__)

def _check_admin_access(jwt_claims: Dict) -> bool:
    """Check if user has admin access from verified JWT claims only."""
    if not jwt_claims:
        return False
    groups = jwt_claims.get('cognito:groups')
    if groups is None:
        groups = []
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
                return json_response(code, {'errorType': error_type, 'message': message})
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
                return json_response(code, {'errorType': error_type, 'message': message})
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
        elif path == '/api/algo/dashboard-signals':
            # Dashboard signals with aggregations for the Ops Terminal
            return _get_dashboard_signals(cur)
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
        elif path == '/api/algo/sector-position-warnings':
            return _get_sector_position_warnings(cur)
        elif path == '/api/algo/swing-scores':
            # Swing scores accessible to authenticated users (AlgoTradingDashboard)
            limit_str = params.get('limit', [None])[0] if params else None
            limit = safe_limit(limit_str, max_val=10000, default=100)
            min_score_str = params.get('min_score', [None])[0] if params else None
            min_score = safe_float_strict(min_score_str, context='query param min_score') if min_score_str else None
            if min_score_str and min_score is None:
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
        elif path == '/api/algo/market':
            # Simplified market data for dashboard display - public endpoint
            return _get_market(cur)
        elif path == '/api/algo/market-factors':
            # Market exposure factors for dashboard display - public endpoint
            return _get_market_factors(cur)
        elif path == '/api/algo/portfolio':
            # Portfolio snapshot accessible to authenticated users
            return _get_algo_portfolio(cur)
        elif path == '/api/algo/metrics':
            # Algo metrics accessible to authenticated users
            return _get_algo_metrics(cur)
        elif path == '/api/algo/risk-metrics':
            # Risk metrics accessible to authenticated users
            return _get_risk_metrics(cur)
        elif path == '/api/algo/performance-analytics':
            # Performance analytics accessible to authenticated users
            return _get_performance_analytics(cur)
        elif path == '/api/algo/sentiment':
            # Sentiment data accessible to authenticated users
            return _get_sentiment(cur)
        elif path == '/api/algo/economic-calendar':
            # Economic calendar accessible to authenticated users
            return _get_economic_calendar(cur)
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
            if method == 'GET':
                return _get_algo_config_key(cur, key)
            elif method == 'PUT':
                actor = (jwt_claims or {}).get('sub', 'unknown')
                return _update_algo_config_key(cur, key, body, actor)
            elif method == 'DELETE':
                actor = (jwt_claims or {}).get('sub', 'unknown')
                return _reset_algo_config_key(cur, key, actor)
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
        elif path == '/api/algo/execution/recent':
            # FIXED Issue #6: View recent orchestrator execution history
            if not _check_admin_access(jwt_claims):
                logger.warning(f"Unauthorized execution history access attempt by {(jwt_claims or {}).get('sub')}")
                return error_response(403, 'forbidden', 'Admin access required')
            days_str = params.get('days', [None])[0] if params else None
            days = safe_days(days_str, default=7, max_val=90)
            limit_str = params.get('limit', [None])[0] if params else None
            limit = safe_limit(limit_str, max_val=1000, default=50)
            return _get_orchestrator_execution_recent(cur, days, limit)
        elif path == '/api/algo/execution/failed':
            # View failed/halted runs for diagnostics
            if not _check_admin_access(jwt_claims):
                logger.warning(f"Unauthorized execution history access attempt by {(jwt_claims or {}).get('sub')}")
                return error_response(403, 'forbidden', 'Admin access required')
            days_str = params.get('days', [None])[0] if params else None
            days = safe_days(days_str, default=30, max_val=90)
            return _get_orchestrator_execution_failed(cur, days)
        elif path.startswith('/api/algo/execution/details/'):
            # View details of a specific orchestrator run
            if not _check_admin_access(jwt_claims):
                logger.warning(f"Unauthorized execution history access attempt by {(jwt_claims or {}).get('sub')}")
                return error_response(403, 'forbidden', 'Admin access required')
            run_id = path.split('/api/algo/execution/details/')[-1]
            return _get_orchestrator_execution_details(cur, run_id)
        elif path == '/api/algo/execution/patterns':
            # Analyze halt patterns - which phases halt most often
            if not _check_admin_access(jwt_claims):
                logger.warning(f"Unauthorized execution history access attempt by {(jwt_claims or {}).get('sub')}")
                return error_response(403, 'forbidden', 'Admin access required')
            days_str = params.get('days', [None])[0] if params else None
            days = safe_days(days_str, default=30, max_val=90)
            return _get_orchestrator_execution_patterns(cur, days)
        elif path == '/api/algo/execution/stats':
            # View execution statistics
            if not _check_admin_access(jwt_claims):
                logger.warning(f"Unauthorized execution history access attempt by {(jwt_claims or {}).get('sub')}")
                return error_response(403, 'forbidden', 'Admin access required')
            days_str = params.get('days', [None])[0] if params else None
            days = safe_days(days_str, default=7, max_val=90)
            return _get_orchestrator_execution_stats(cur, days)
        else:
            return error_response(404, 'not_found', f'No algo handler for {path}')

@db_route_handler('get last run')
def _get_last_run(cur) -> Dict:
    """Get the most recent orchestrator run with per-phase status."""
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
        return json_response(200, {'run_id': None, 'run_at': None, 'halted': False, 'phases': []})

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
    phases = [safe_json_serialize(dict(r)) for r in cur.fetchall()]

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

@db_route_handler('fetch algo status', default_error_response={'status': 'unavailable', 'last_run': None, 'portfolio': {}, 'data_freshness': {'data_age_days': None, 'is_stale': True, 'warning': 'Data unavailable'}, '_error': 'Data unavailable'})
def _get_algo_status(cur) -> Dict:
        """Get latest algo execution status plus latest portfolio snapshot."""
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
                pv = safe_float(snap[0])
                portfolio = {
                    'total_value': round(pv, 2),
                    'daily_return_pct': round(safe_float(snap[1]), 2),
                    'unrealized_pnl_pct': round((safe_float(snap[2]) / pv * 100) if pv > 0 else 0, 2),
                    'open_positions': safe_int(snap[3]),
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

@db_route_handler('fetch algo trades', default_error_response={'items': [], 'pagination': {'total': 0, 'limit': 200, 'offset': 0}, 'data_freshness': {'data_age_days': None, 'is_stale': True, 'warning': 'Data unavailable'}, '_error': 'Data unavailable'})
def _get_algo_trades(cur, limit: int = 200, user_id: str = None) -> Dict:
        """Get recent trades with all fields for frontend (scoped to user if user_id provided)."""
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
        items = [safe_json_serialize(dict(t)) for t in trades]
        freshness = check_data_freshness(cur, 'algo_trades', 'created_at', warning_days=1)
        return json_response(200, {
            'items': items,
            'pagination': {'total': len(items), 'limit': limit, 'offset': 0},
            'data_freshness': freshness
        })

@db_route_handler('fetch algo positions', default_error_response={'items': [], 'sector_allocation': [], 'pagination': {'total': 0, 'limit': 10000, 'offset': 0}, 'data_freshness': {'data_age_days': None, 'is_stale': True, 'warning': 'Data unavailable'}, '_error': 'Data unavailable'})
def _get_algo_positions(cur, user_id: str = None) -> Dict:
        """Get current open positions with computed fields.

        Provides comprehensive position data with:
        - Current price, unrealized P&L, risk metrics
        - Stop/target levels and distance percentages
        - Technical scores (Weinstein stage, Minervini trend)
        - Sector allocation for pie chart
        - Ladder percentage points for visualization
        """
        cur.execute("SET LOCAL statement_timeout = '30000ms'")

        cur.execute("""
            SELECT
            symbol,
            quantity,
            avg_entry_price,
            current_price,
            position_value,
            unrealized_pnl,
            unrealized_pnl_pct,
            status,
            days_since_entry,
            stop_loss_price,
            target_1_price,
            target_2_price,
            target_3_price,
            target_1_r_multiple,
            target_2_r_multiple,
            target_3_r_multiple,
            sector,
            industry,
            r_multiple,
            initial_risk_per_share,
            open_risk_dollars,
            distance_to_stop_pct,
            distance_to_t1_pct,
            distance_to_t2_pct,
            distance_to_t3_pct,
            minervini_trend_score,
            weinstein_stage,
            percent_from_52w_low,
            percent_from_52w_high,
            stage_in_exit_plan
            FROM algo_positions_with_risk
            ORDER BY position_value DESC
        """)
        positions = cur.fetchall()

        items = []
        sector_risk = {}  # For aggregating sector allocation

        for p in positions:
            d = safe_json_serialize(dict(p))

            # Compute ladder_pct_* fields for visualization (Issue #2)
            entry = safe_float(d.get('avg_entry_price'))
            cur_price = safe_float(d.get('current_price'))
            stop = safe_float(d.get('stop_loss_price'))
            t1 = safe_float(d.get('target_1_price'))
            t2 = safe_float(d.get('target_2_price'))
            t3 = safe_float(d.get('target_3_price'))

            if entry and cur_price and stop:
                lo = min(stop, entry, cur_price)
                hi = max(t3 or t2 or t1 or entry, cur_price)
                span = max(0.0001, hi - lo)

                def pos(price):
                    return ((price - lo) / span) * 100 if price is not None else None

                d['ladder_pct_stop'] = pos(stop)
                d['ladder_pct_entry'] = pos(entry)
                d['ladder_pct_current'] = pos(cur_price)
                d['ladder_pct_t1'] = pos(t1)
                d['ladder_pct_t2'] = pos(t2)
                d['ladder_pct_t3'] = pos(t3)
            else:
                d['ladder_pct_stop'] = None
                d['ladder_pct_entry'] = None
                d['ladder_pct_current'] = None
                d['ladder_pct_t1'] = None
                d['ladder_pct_t2'] = None
                d['ladder_pct_t3'] = None

            # Compute stage_label for stage distribution (Issue #8)
            stage = safe_int(d.get('weinstein_stage'))
            trend_score = safe_float(d.get('minervini_trend_score'))
            if stage == 2:
                if trend_score and trend_score < 4:
                    d['stage_label'] = 'Early Stage-2'
                elif trend_score and trend_score >= 6:
                    d['stage_label'] = 'Late Stage-2'
                else:
                    d['stage_label'] = 'Mid Stage-2'
            elif stage == 1:
                d['stage_label'] = 'Stage 1 (base)'
            elif stage == 3:
                d['stage_label'] = 'Stage 3 (top)'
            elif stage == 4:
                d['stage_label'] = 'Stage 4 (down)'
            else:
                d['stage_label'] = 'Unknown'

            # Normalize field names for frontend compatibility
            if 'percent_from_52w_low' in d:
                d['pct_from_52w_low'] = d.pop('percent_from_52w_low')
            if 'percent_from_52w_high' in d:
                d['pct_from_52w_high'] = d.pop('percent_from_52w_high')

            items.append(d)

            # Accumulate sector allocation for aggregation (Issue #1)
            sector = d.get('sector', 'Unknown')
            pos_val = safe_float(d.get('position_value')) or 0
            if sector not in sector_risk:
                sector_risk[sector] = 0
            sector_risk[sector] += pos_val

        # Compute sector_allocation array after processing all positions (E5 fix)
        total_value = sum(sector_risk.values()) or 1
        sector_allocation = [
            {
                'sector': sector,
                'allocation_pct': round((value / total_value) * 100, 1),
                'pct': round((value / total_value) * 100, 1),
                'is_overweight': (value / total_value) * 100 > 30
            }
            for sector, value in sorted(sector_risk.items(), key=lambda x: x[1], reverse=True)
        ]

        freshness = check_data_freshness(cur, 'algo_trades', 'trade_date', warning_days=1)

        return json_response(200, {
            'items': items,
            'sector_allocation': sector_allocation,
            'pagination': {'total': len(items), 'limit': 10000, 'offset': 0},
            'data_freshness': freshness
        })

@db_route_handler('calculate performance', default_error_response={'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0, 'win_rate': 0.0, 'profit_factor': 0.0, 'total_pnl_dollars': 0.0, 'total_pnl_pct': 0.0, 'total_return_pct': 0.0, 'avg_trade_pct': 0.0, 'best_trade_pct': 0.0, 'worst_trade_pct': 0.0, 'sharpe_ratio': 0.0, 'sortino_ratio': 0.0, 'max_drawdown_pct': 0.0, 'avg_holding_days': 0.0, 'data_freshness': {'data_age_days': None, 'is_stale': True, 'warning': 'Data unavailable'}, '_error': 'Data unavailable'})
def _get_algo_performance(cur) -> Dict:
        """Get comprehensive algo performance metrics using unified fetcher.

        ARCHITECTURE FIX: Uses unified AlgoMetricsFetcher to ensure performance metrics
        and positions use identical data sources. Eliminates redundant metric calculations.
        """
        fetcher = AlgoMetricsFetcher(cur)
        perf = fetcher.fetch_performance_metrics()

        if "_error" in perf:
            logger.error(f"Performance metrics fetch failed: {perf['_error']}")
            log_fallback_usage('performance_metrics', 'hardcoded_defaults', FallbackTrigger.PRIMARY_UNAVAILABLE, error=perf.get('_error'))

            # Use documented fallback values from fallback_registry
            fallback_values = get_hardcoded_fallback_values('performance_metrics', 'hardcoded_defaults')
            fallback_response = fallback_values.copy() if fallback_values else {}

            # Add metadata indicating these are placeholder/fallback values
            fallback_response.update({
                '_is_fallback_data': True,
                '_is_placeholder': True,
                '_error': perf.get('_error'),
                '_fallback_reason': 'Performance data unavailable - using all-zero placeholder metrics',
                'data_freshness': {
                    'is_stale': True,
                    'warning': 'Data unavailable',
                    'message': 'Unable to fetch performance metrics. Showing placeholder values. Check system logs for details.'
                },
                'confidence_metadata': {
                    'sharpe_confidence': 'critical_unavailable',
                    'win_rate_confidence': 'critical_unavailable',
                    'return_confidence': 'critical_unavailable',
                    'snapshot_count': 0,
                    'total_trades': 0,
                }
            })
            return json_response(200, fallback_response)

        # Fetch equity curve and recent returns
        equity_curve = fetcher.fetch_equity_curve(limit=252)
        recent_returns = fetcher.fetch_recent_returns(limit=252)

        # Wrap fetched data in response format expected by frontend
        # Return None for metrics without sufficient data, not 0 (dashboard handles None gracefully)
        result = {
            'total_trades': perf.get('total_trades', 0),
            'winning_trades': perf.get('winning_trades', 0),
            'losing_trades': perf.get('losing_trades', 0),
            'breakeven_trades': perf.get('breakeven_trades', 0),
            'win_rate': perf.get('win_rate_pct'),
            'win_rate_pct': perf.get('win_rate_pct'),
            'win_rate_confidence': perf.get('win_rate_confidence', 'low'),
            'profit_factor': perf.get('profit_factor'),
            'total_pnl_dollars': perf.get('total_pnl_dollars'),
            'total_pnl_pct': perf.get('total_pnl_pct'),
            'total_return_pct': perf.get('total_return_pct'),
            'avg_trade_pct': perf.get('avg_win_pct'),
            'avg_win_pct': perf.get('avg_win_pct'),
            'avg_loss_pct': perf.get('avg_loss_pct'),
            'best_trade_pct': perf.get('best_trade_pct'),
            'worst_trade_pct': perf.get('worst_trade_pct'),
            'sharpe_annualized': perf.get('sharpe_ratio'),
            'sharpe_ratio': perf.get('sharpe_ratio'),
            'sharpe_confidence': perf.get('sharpe_confidence', 'low'),
            'sortino_annualized': perf.get('sortino_ratio'),
            'sortino_ratio': perf.get('sortino_ratio'),
            'max_drawdown_pct': perf.get('max_drawdown_pct'),
            'expectancy_r': perf.get('expectancy_r'),
            'avg_hold_days': perf.get('avg_holding_days'),
            'avg_holding_days': perf.get('avg_holding_days'),
            'portfolio_snapshots': perf.get('portfolio_snapshots', 0),
            'best_win_streak': perf.get('best_win_streak'),
            'worst_loss_streak': perf.get('worst_loss_streak'),
            'current_streak': perf.get('current_streak'),
            'gross_win_dollars': perf.get('gross_win_dollars'),
            'gross_loss_dollars': perf.get('gross_loss_dollars'),
            'equity_vals': equity_curve.get('equity_vals', []),
            'recent_rets': recent_returns.get('recent_rets', []),
            'data_freshness': {},
            'confidence_metadata': {
                'sharpe_confidence': perf.get('sharpe_confidence', 'low'),
                'win_rate_confidence': perf.get('win_rate_confidence', 'low'),
                'return_confidence': 'low',
                'snapshot_count': perf.get('portfolio_snapshots', 0),
                'total_trades': perf.get('total_trades', 0),
            }
        }
        return json_response(200, result)

@db_route_handler('fetch dashboard signals', default_error_response={'n': 0, 'total': 0, 'date': None, 'buy_sigs': [], 'grades': {}, 'near': [], 'top_a': [], 'trend': [], 'data_freshness': {}, '_error': 'Data unavailable'})
def _get_dashboard_signals(cur) -> Dict:
        """Get dashboard-specific signal data with aggregations for the Ops Terminal.

        Returns: BUY signals with quality scores, grade distribution (A-D by score),
        near-miss signals, top A-grade stocks, and signal trend.
        """
        try:
            cur.execute("SET LOCAL statement_timeout = '30000ms'")

            cur.execute("""
                SELECT COUNT(*) AS n, MAX(date) AS d FROM buy_sell_daily
                WHERE signal='BUY' AND timeframe IN ('1d', 'daily', 'Daily')
                  AND date=(SELECT MAX(date) FROM buy_sell_daily WHERE signal='BUY' AND timeframe IN ('1d', 'daily', 'Daily'))""")
            sig = cur.fetchone()

            cur.execute("""SELECT COUNT(*) AS n FROM buy_sell_daily
                           WHERE timeframe IN ('1d', 'daily', 'Daily') AND date=(SELECT MAX(date) FROM buy_sell_daily WHERE timeframe IN ('1d', 'daily', 'Daily'))""")
            total_r = cur.fetchone()
            total_n = int(total_r["n"] or 0) if total_r else 0

            # Actual BUY signals with rich setup detail
            cur.execute("""
                SELECT b.symbol, b.signal_type, b.stage_number, b.signal_quality_score,
                       b.entry_quality_score, b.close, b.buylevel, b.stoplevel,
                       b.risk_reward_ratio, b.volume_surge_pct, b.rs_rating,
                       b.breakout_quality, b.base_type, b.reason,
                       cp.sector,
                       s.score AS swing_score
                FROM buy_sell_daily b
                LEFT JOIN company_profile cp ON cp.ticker = b.symbol
                LEFT JOIN (
                    SELECT DISTINCT ON (symbol) symbol, score
                    FROM swing_trader_scores ORDER BY symbol, date DESC
                ) s ON s.symbol = b.symbol
                WHERE b.signal='BUY' AND b.timeframe IN ('1d', 'daily', 'Daily')
                  AND b.date=(SELECT MAX(date) FROM buy_sell_daily WHERE signal='BUY' AND timeframe IN ('1d', 'daily', 'Daily'))
                ORDER BY COALESCE(b.signal_quality_score, b.entry_quality_score, 0) DESC
                LIMIT 30""")
            buy_sigs = [safe_json_serialize(dict(row)) for row in cur.fetchall()]

            # Grade distribution (A/B/C/D by swing score)
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE score >= 80) AS a,
                       COUNT(*) FILTER (WHERE score >= 60 AND score < 80) AS b,
                       COUNT(*) FILTER (WHERE score >= 40 AND score < 60) AS c,
                       COUNT(*) FILTER (WHERE score < 40) AS d,
                       COUNT(*) AS total
                FROM swing_trader_scores
                WHERE date=(SELECT MAX(date) FROM swing_trader_scores)""")
            grades_r = cur.fetchone()
            grades = dict(grades_r) if grades_r else {}

            # Near-misses: scored stocks close to BUY threshold
            cur.execute("""
                SELECT s.symbol, s.score, cp.sector
                FROM swing_trader_scores s
                LEFT JOIN company_profile cp ON cp.ticker = s.symbol
                WHERE s.date=(SELECT MAX(date) FROM swing_trader_scores)
                  AND s.score BETWEEN 55 AND 69
                ORDER BY s.score DESC LIMIT 15""")
            near = [safe_json_serialize(dict(row)) for row in cur.fetchall()]

            # Top A-grade stocks by name (radar display — score ≥ 80)
            cur.execute("""
                SELECT s.symbol, s.score
                FROM swing_trader_scores s
                WHERE s.date=(SELECT MAX(date) FROM swing_trader_scores)
                  AND s.score >= 80
                ORDER BY s.score DESC LIMIT 20""")
            top_a = [safe_json_serialize(dict(row)) for row in cur.fetchall()]

            # Signal count trend: last 7 trading days
            cur.execute("""
                SELECT date,
                       COUNT(*) FILTER (WHERE signal='BUY') AS buy_n,
                       COUNT(*) AS total_n
                FROM buy_sell_daily
                WHERE timeframe IN ('1d', 'daily', 'Daily') AND date >= CURRENT_DATE - 14
                GROUP BY date ORDER BY date DESC LIMIT 7""")
            trend = [safe_json_serialize(dict(row)) for row in cur.fetchall()]

            freshness = check_data_freshness(cur, 'buy_sell_daily', 'date', warning_days=1)

            return json_response(200, {
                'n': int(sig["n"] or 0) if sig else 0,
                'total': total_n,
                'date': sig["d"] if sig else None,
                'buy_sigs': buy_sigs,
                'grades': grades,
                'near': near,
                'top_a': top_a,
                'trend': trend,
                'data_freshness': freshness
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            code, error_type, message = handle_db_error(e, 'fetch dashboard signals')
            return json_response(code, {'_error': message, 'errorType': error_type})

@db_route_handler('fetch circuit breakers', default_error_response={'breakers': [], 'any_triggered': False, 'triggered_count': 0, 'data_freshness': {'data_age_days': None, 'is_stale': True, 'warning': 'Data unavailable'}, '_error': 'Data unavailable'})
def _get_circuit_breakers(cur) -> Dict:
        """Get real-time circuit breaker state with current values vs thresholds."""
        try:
            today = date.today()
            breakers = []

            # CRITICAL: Validate required circuit breaker configuration tables exist
            required_tables = ['algo_portfolio_snapshots', 'algo_trades', 'market_health_daily', 'algo_positions']
            missing_tables = []
            for table in required_tables:
                try:
                    from algo.algo_sql_safety import assert_safe_table
                    table_safe = assert_safe_table(table)
                    cur.execute(
                        psycopg2.sql.SQL("SELECT 1 FROM {} LIMIT 1").format(
                            psycopg2.sql.Identifier(table_safe)
                        )
                    )
                except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedSchema):
                    missing_tables.append(table)
                except Exception as e:
                    logger.error(f"Unexpected error checking table {table}: {type(e).__name__}: {e}")
                    missing_tables.append(table)

            if missing_tables:
                logger.error(f'ALERT: Circuit breaker CRITICAL config tables missing: {missing_tables}')
                return json_response(200, {
                    'breakers': [],
                    'any_triggered': False,
                    'triggered_count': 0,
                    'data_freshness': {'data_age_days': None, 'is_stale': True, 'warning': 'Data unavailable'},
                    'error': f'Circuit breaker configuration incomplete: missing tables {missing_tables}. Trading is disabled until data is available.',
                    'error_type': 'missing_critical_tables'
                })

            # Fetch pre-computed circuit breaker metrics from database
            cbm_data = None
            try:
                cur.execute("SELECT current_drawdown_pct, daily_loss_pct, weekly_loss_pct, total_risk_pct, consecutive_losses FROM circuit_breaker_metrics LIMIT 1")
                cbm_row = cur.fetchone()
                if cbm_row:
                    cbm_data = {
                        'drawdown': safe_float(cbm_row[0]) if cbm_row[0] is not None else 0,
                        'daily_loss': safe_float(cbm_row[1]) if cbm_row[1] is not None else 0,
                        'weekly_loss': safe_float(cbm_row[2]) if cbm_row[2] is not None else 0,
                        'total_risk': safe_float(cbm_row[3]) if cbm_row[3] is not None else 0,
                        'consecutive_losses': safe_int(cbm_row[4]) if cbm_row[4] is not None else 0,
                    }
            except Exception as e:
                logger.warning(f"Circuit breaker metrics view unavailable: {e}")

            # CB1: Portfolio drawdown (from pre-computed metrics)
            try:
                dd = cbm_data['drawdown'] if cbm_data else 0
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

            # CB2: Daily loss (from pre-computed metrics)
            try:
                daily_loss = cbm_data['daily_loss'] if cbm_data else 0
                threshold_dl = 2.0
                breakers.append({
                    'id': 'daily_loss', 'label': 'Daily Loss',
                    'triggered': daily_loss >= threshold_dl,
                    'current': daily_loss, 'threshold': threshold_dl, 'unit': '%',
                    'description': f'Halt when today\'s loss ≥ {threshold_dl:.0f}%',
                })
            except Exception as e:
                logger.warning(f"API exception: {e}")
                breakers.append({'id': 'daily_loss', 'label': 'Daily Loss',
                    'triggered': False, 'current': 0, 'threshold': 2, 'unit': '%',
                    'description': 'No today snapshot yet'})

            # CB3: Consecutive losses (from pre-computed metrics)
            try:
                streak = cbm_data['consecutive_losses'] if cbm_data else 0
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
                vix_val = row[0] if row and row[0] is not None else None
                vix = round(float(vix_val), 1) if vix_val is not None else None
                threshold_vix = 35.0
                breakers.append({
                    'id': 'vix_spike', 'label': 'VIX Spike',
                    'triggered': vix is not None and vix >= threshold_vix,
                    'current': vix, 'threshold': threshold_vix, 'unit': '',
                    'description': f'Halt when VIX ≥ {threshold_vix:.0f} (extreme fear)',
                })
            except Exception as e:
                logger.warning(f"API exception: {e}")
                breakers.append({'id': 'vix_spike', 'label': 'VIX Spike',
                    'triggered': False, 'current': 0, 'threshold': 35, 'unit': '',
                    'description': 'No market data yet'})

            # CB5: Weekly portfolio loss (from pre-computed metrics)
            try:
                weekly_loss = cbm_data['weekly_loss'] if cbm_data else 0
                threshold_wl = 5.0
                breakers.append({
                    'id': 'weekly_loss', 'label': 'Weekly Loss',
                    'triggered': weekly_loss >= threshold_wl,
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
                stage = safe_int(row[0]) if row else 0
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

            # CB7: Total open risk (from pre-computed metrics)
            try:
                risk_pct = cbm_data['total_risk'] if cbm_data else 0
                threshold_risk = 4.0
                breakers.append({
                    'id': 'total_risk', 'label': 'Total Open Risk',
                    'triggered': risk_pct >= threshold_risk,
                    'current': risk_pct, 'threshold': threshold_risk, 'unit': '%',
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
                    latest = safe_float(prices[0][0])
                    prior = safe_float(prices[1][0])
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
                    wins = safe_int(wr_result[0])
                    losses = safe_int(wr_result[1])
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
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            logger.error(f'Data unavailable (circuit breakers): {type(e).__name__}: {str(e)}', extra={'operation': 'fetch circuit breakers'}, exc_info=True)
            return error_response(503, 'service_unavailable', 'Data unavailable')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error (circuit breakers): {type(e).__name__}: {str(e)}', extra={'operation': 'fetch circuit breakers'}, exc_info=True)
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error (circuit breakers): {type(e).__name__}: {str(e)}', extra={'operation': 'fetch circuit breakers'}, exc_info=True)
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error (circuit breakers): {type(e).__name__}: {str(e)}', extra={'operation': 'fetch circuit breakers'}, exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch circuit breakers')

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
            return list_response([safe_json_serialize(dict(c)) for c in reversed(curve) if c], data_freshness=freshness)
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            logger.error(f'Data unavailable (equity curve): {type(e).__name__}: {str(e)}', extra={'operation': 'fetch equity curve'}, exc_info=True)
            return error_response(503, 'service_unavailable', 'Data unavailable')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error (equity curve): {type(e).__name__}: {str(e)}', extra={'operation': 'fetch equity curve'}, exc_info=True)
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error (equity curve): {type(e).__name__}: {str(e)}', extra={'operation': 'fetch equity curve'}, exc_info=True)
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error (equity curve): {type(e).__name__}: {str(e)}', extra={'operation': 'fetch equity curve'}, exc_info=True)
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
                row_count = row.get('row_count')

                if row_count is None or row_count == 0:
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
                last_updated_utc = normalize_to_utc_datetime(last_updated)
                if last_updated_utc:
                    age_h = (datetime.now(timezone.utc) - last_updated_utc).total_seconds() / 3600
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
            logger.error(f'Data unavailable (data status): {type(e).__name__}: {str(e)}', extra={'operation': 'fetch data status'}, exc_info=True)
            return error_response(503, 'service_unavailable', 'Data unavailable')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error (data status): {type(e).__name__}: {str(e)}', extra={'operation': 'fetch data status'}, exc_info=True)
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error (data status): {type(e).__name__}: {str(e)}', extra={'operation': 'fetch data status'}, exc_info=True)
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error (data status): {type(e).__name__}: {str(e)}', extra={'operation': 'fetch data status'}, exc_info=True)
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
            return list_response([safe_json_serialize(dict(n)) for n in notifs])
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to fetch notifications: {type(e).__name__}: {str(e)}', extra={'operation': 'fetch notifications'}, exc_info=True)
            return error_response(500, 'internal_error', f'Failed to fetch notifications: {type(e).__name__}')

@db_route_handler('analyze trade impact')
def _analyze_pre_trade_impact(cur, body: Dict) -> Dict:
        """Analyze impact of a potential trade on portfolio constraints."""
        symbol = body.get('symbol', '').upper()
        entry_price = body.get('entry_price')
        position_dollars = body.get('position_dollars')
        position_pct = body.get('position_pct')

        if not symbol:
            return error_response(400, 'bad_request', 'symbol is required')

        # Call stored procedure to compute all impact metrics in database
        cur.execute("""
            SELECT position_size_dollars, position_size_percent, new_total_positions,
                   new_sector_percent, new_sector_invested, drawdown_impact_pct,
                   sector_name, sector_count,
                   meets_position_limit, meets_size_limit, meets_sector_limit,
                   meets_cash_requirement, meets_risk_limit
            FROM calculate_pretrade_impact(%s, %s, %s, %s)
        """, (symbol, entry_price, position_dollars, position_pct))
        impact_row = cur.fetchone()

        if not impact_row:
            return error_response(500, 'internal_error', f'Unable to calculate impact for {symbol}')

        impact = safe_json_serialize(dict(impact_row))

        allOk = (impact.get('meets_position_limit', False) and
                impact.get('meets_size_limit', False) and
                impact.get('meets_sector_limit', False) and
                impact.get('meets_cash_requirement', False) and
                impact.get('meets_risk_limit', False))

        return json_response(200, {
            'symbol': symbol,
            'entry_price': float(entry_price) if entry_price else 0,
            'position_size_dollars': float(impact.get('position_size_dollars', 0)),
            'position_size_percent': float(impact.get('position_size_percent', 0)),
            'sector': impact.get('sector_name'),
            'risk_score': 0.0 if allOk else 0.5,
            'all_constraints_met': allOk,
            'recommendation': 'APPROVED' if allOk else 'REJECTED',
            'portfolio_impact': {
                'new_total_positions': impact.get('new_total_positions', 0),
                'position_limit': 6,
                'position_limit_ok': impact.get('meets_position_limit', False),
                'new_position_percent': float(impact.get('position_size_percent', 0)),
                'max_position_percent': 15,
                'position_size_ok': impact.get('meets_size_limit', False),
                'new_sector_percent': float(impact.get('new_sector_percent', 0)),
                'max_sector_percent': 30,
                'sector_limit_ok': impact.get('meets_sector_limit', False),
                'worst_case_drawdown_impact': float(impact.get('drawdown_impact_pct', 0)),
                'max_acceptable_impact': 0.05,
                'drawdown_risk_ok': impact.get('meets_risk_limit', False),
                'cash_available': 0,
                'cash_required': float(impact.get('position_size_dollars', 0)),
                'cash_ok': impact.get('meets_cash_requirement', False)
            }
        })
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
@db_route_handler('get patrol log')
def _get_patrol_log(cur, limit: int = 50, offset: int = 0) -> Dict:
        """Get data patrol findings with pagination."""
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
        return list_response([safe_json_serialize(dict(f)) for f in findings], total=total)
@db_route_handler('get sector rotation')
def _get_sector_rotation(cur, days: int = 180) -> Dict:
        """Get sector rotation data: defensive vs cyclical relative strength."""
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
                ROW_NUMBER() OVER (PARTITION BY signal_group_id ORDER BY date DESC) AS weeks_persistent,
                (defensive_strength IS NULL OR cyclical_strength IS NULL) AS _is_fallback
            FROM signal_groups
            ORDER BY date DESC
        """, (cutoff_date,))
        rotation = cur.fetchall()
        return list_response([safe_json_serialize(dict(r)) for r in rotation])
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
                distinct_symbols AS (
                    SELECT DISTINCT ON (lt.symbol)
                        lt.symbol, lp.close, lt.sma_50, lt.sma_200, cp.sector
                    FROM latest_tech lt
                    JOIN latest_price lp ON lt.symbol = lp.symbol
                    JOIN company_profile cp ON lt.symbol = cp.ticker
                    WHERE cp.sector IS NOT NULL
                    ORDER BY lt.symbol
                ),
                sector_breadth AS (
                    SELECT
                        sector,
                        COUNT(symbol) FILTER (WHERE close IS NOT NULL AND sma_50 IS NOT NULL AND close > sma_50) * 100.0 /
                            NULLIF(COUNT(symbol) FILTER (WHERE sma_50 IS NOT NULL AND close IS NOT NULL), 0) AS pct_above_50d,
                        COUNT(symbol) FILTER (WHERE close IS NOT NULL AND sma_200 IS NOT NULL AND close > sma_200) * 100.0 /
                            NULLIF(COUNT(symbol) FILTER (WHERE sma_200 IS NOT NULL AND close IS NOT NULL), 0) AS pct_above_200d
                    FROM distinct_symbols
                    GROUP BY sector
                )
                SELECT
                    sector,
                    ROUND(COALESCE(pct_above_50d, 0)::NUMERIC, 2) AS pct_above_50d,
                    ROUND(COALESCE(pct_above_200d, 0)::NUMERIC, 2) AS pct_above_200d,
                    (pct_above_50d IS NULL OR pct_above_200d IS NULL) AS _is_fallback
                FROM sector_breadth
                ORDER BY pct_above_50d DESC
            """)
            breadth = cur.fetchall()
            cur.execute("RELEASE SAVEPOINT sector_breadth_check")
            return list_response([safe_json_serialize(dict(b)) for b in breadth])
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sector_breadth_check")
                cur.execute("RELEASE SAVEPOINT sector_breadth_check")
            except Exception as sp_err:
                logger.debug(f'Failed to rollback sector_breadth_check savepoint: {sp_err}')
            logger.error(f'Sector breadth data unavailable: {type(e).__name__}: {str(e)}', extra={'operation': 'get sector breadth'}, exc_info=True)
            return error_response(500, 'internal_error', f'Failed to fetch sector breadth: {type(e).__name__}')
        except (psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sector_breadth_check")
                cur.execute("RELEASE SAVEPOINT sector_breadth_check")
            except Exception as sp_err:
                logger.debug(f'Failed to rollback sector_breadth_check savepoint: {sp_err}')
            logger.error(f'Sector breadth query failed: {type(e).__name__}: {str(e)}', extra={'operation': 'get sector breadth'}, exc_info=True)
            return error_response(500, 'internal_error', f'Failed to fetch sector breadth: {type(e).__name__}')

def _get_sector_position_warnings(cur) -> Dict:
        """Get sector position concentration warnings (FIX: missing endpoint for dashboard fallback).

        Returns list of sectors with position counts and concentration warnings.
        """
        try:
            cur.execute("SET LOCAL statement_timeout = '5000ms'")

            cur.execute("""
                SELECT cp.sector, COUNT(DISTINCT ap.symbol) as position_count
                FROM algo_positions ap
                LEFT JOIN company_profile cp ON ap.symbol = cp.ticker
                WHERE ap.status = 'open' AND ap.quantity > 0
                GROUP BY cp.sector
                ORDER BY position_count DESC
            """)
            sector_counts = [(dict(row).get('sector'), dict(row).get('position_count')) for row in cur.fetchall()]

            cur.execute("SELECT value FROM algo_config WHERE key = %s LIMIT 1", ('max_positions_per_sector',))
            max_per_sector_row = cur.fetchone()
            max_per_sector = int(max_per_sector_row[0]) if max_per_sector_row and max_per_sector_row[0] else 3

            warnings = []
            at_cap = []
            for sector, count in sector_counts:
                if not sector:
                    continue
                if count >= max_per_sector:
                    at_cap.append({
                        "sector": sector,
                        "position_count": count,
                        "max": max_per_sector,
                        "status": "AT_CAP"
                    })
                elif count >= max_per_sector - 1:
                    warnings.append({
                        "sector": sector,
                        "position_count": count,
                        "max": max_per_sector,
                        "status": "NEAR_CAP"
                    })

            return json_response(200, {
                "warnings": warnings,
                "at_cap": at_cap,
                "data": {
                    "warnings": warnings,
                    "at_cap": at_cap
                }
            })

        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            logger.error(f'Sector position warnings data unavailable: {type(e).__name__}: {str(e)}')
            return error_response(503, 'service_unavailable', f'Data unavailable: {type(e).__name__}')
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
            logger.error(f'Sector position warnings query failed: {type(e).__name__}: {str(e)}')
            return error_response(503, 'service_unavailable', f'Database unavailable: {type(e).__name__}')
        except Exception as e:
            logger.error(f'Sector position warnings failed: {type(e).__name__}: {str(e)}', exc_info=True)
            return error_response(500, 'internal_error', f'Failed to fetch sector position warnings: {type(e).__name__}')

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
            return list_response([safe_json_serialize(dict(s)) for s in scores])
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to fetch swing scores: {type(e).__name__}: {str(e)}', extra={'operation': 'get swing scores'}, exc_info=True)
            return error_response(500, 'internal_error', f'Failed to fetch swing scores: {type(e).__name__}')
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
            return list_response([safe_json_serialize(dict(h)) for h in history])
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to fetch swing scores history: {type(e).__name__}: {str(e)}', extra={'operation': 'get swing scores history'}, exc_info=True)
            return error_response(500, 'internal_error', f'Failed to fetch swing scores history: {type(e).__name__}')
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
            initial_count = safe_json_serialize(dict(row)).get('total_signals', 0) if row else 0

            # Get scored candidates
            cur.execute("""
                SELECT COUNT(DISTINCT symbol) as scored
                FROM swing_trader_scores
                WHERE date >= CURRENT_DATE - INTERVAL '14 days'
            """)
            row = cur.fetchone()
            scored_count = safe_json_serialize(dict(row)).get('scored', 0) if row else 0

            # Get high-quality candidates (SQS > 60)
            cur.execute("""
                SELECT COUNT(DISTINCT symbol) as high_quality
                FROM swing_trader_scores
                WHERE date >= CURRENT_DATE - INTERVAL '14 days'
                AND score >= 60
            """)
            row = cur.fetchone()
            high_quality_count = safe_json_serialize(dict(row)).get('high_quality', 0) if row else 0

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

            # EARLY VALIDATION: Check data freshness before processing
            freshness = check_data_freshness(cur, 'market_exposure_daily', 'date', warning_days=1)
            if freshness.get('is_stale'):
                logger.error(f'CRITICAL: market_exposure_daily is stale (age: {freshness.get("data_age_days")} days)')

            cur.execute("""
                SELECT date, exposure_pct, raw_score, regime, distribution_days, factors, halt_reasons
                FROM market_exposure_daily
                ORDER BY date DESC
                LIMIT 1
            """)
            latest = cur.fetchone()
            current = safe_json_serialize(dict(latest)) if latest else None

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
            history = [safe_json_serialize(dict(h)) for h in cur.fetchall()]

            try:
                cur.execute("""
                    SELECT sector_name AS name, current_rank AS rank, rank_4w_ago, momentum_score AS momentum
                    FROM sector_ranking
                    WHERE date = (SELECT MAX(date) FROM sector_ranking)
                    ORDER BY current_rank
                    LIMIT 20
                """)
                sectors = [safe_json_serialize(dict(s)) for s in cur.fetchall()]
            except Exception as e:
                logger.warning(f"[MARKETS] sector_ranking query failed: {e}")
                sectors = []

            market_health = {}
            try:
                cur.execute("""
                    SELECT market_trend, market_stage, vix_level, spy_change_pct,
                           up_volume_percent, advance_decline_ratio, new_highs_count,
                           new_lows_count, breadth_momentum_10d, put_call_ratio,
                           yield_curve_slope, fed_rate_environment
                    FROM market_health_daily
                    ORDER BY date DESC LIMIT 1
                """)
                mh = cur.fetchone()
                if mh:
                    market_health = safe_json_serialize(dict(mh))
            except Exception as e:
                logger.warning(f"[MARKETS] market_health_daily unavailable: {type(e).__name__}: {e}")

            spy_price = None
            try:
                cur.execute("""
                    SELECT close FROM price_daily
                    WHERE symbol = 'SPY'
                    ORDER BY date DESC LIMIT 1
                """)
                spy_row = cur.fetchone()
                if spy_row:
                    spy_price = float(spy_row[0])
            except Exception as e:
                logger.warning(f"[MARKETS] SPY price unavailable: {type(e).__name__}: {e}")

            return json_response(200, {
                'success': True,
                'current': current,
                'active_tier': active_tier,
                'history': history,
                'sectors': sectors,
                'market_health': market_health,
                'exposure_pct': current.get('exposure_pct') if current else None,
                'halt_reasons': current.get('halt_reasons', []) if current else [],
                'vix_level': market_health.get('vix_level') if market_health else None,
                'distribution_days_4w': current.get('distribution_days') if current else None,
                'market_stage': market_health.get('market_stage') if market_health else None,
                'market_trend': market_health.get('market_trend') if market_health else None,
                'spy_price': spy_price,
                'spy_change_pct': market_health.get('spy_change_pct') if market_health else None,
                'up_volume_percent': market_health.get('up_volume_percent') if market_health else None,
                'advance_decline_ratio': market_health.get('advance_decline_ratio') if market_health else None,
                'new_highs_count': market_health.get('new_highs_count') if market_health else None,
                'new_lows_count': market_health.get('new_lows_count') if market_health else None,
                'put_call_ratio': market_health.get('put_call_ratio') if market_health else None,
                'yield_curve_slope': market_health.get('yield_curve_slope') if market_health else None,
                'breadth_momentum_10d': market_health.get('breadth_momentum_10d') if market_health else None,
                'fed_rate_environment': market_health.get('fed_rate_environment') if market_health else None,
                'data_freshness': freshness,
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to fetch markets: {type(e).__name__}: {e}', extra={'operation': 'get markets'})
            return json_response(503, {'errorType': 'service_unavailable', 'message': 'Failed to fetch markets: database connection failed'})

def _get_market(cur) -> Dict:
    """Get simplified market data for dashboard. Returns market_health_daily + exposure data."""
    try:
        cur.execute("SET LOCAL statement_timeout = '8000ms'")

        # Fetch market health: 12 fields from market_health_daily
        cur.execute("""
            SELECT market_trend, market_stage, vix_level, spy_change_pct,
                   up_volume_percent, advance_decline_ratio, new_highs_count,
                   new_lows_count, breadth_momentum_10d, put_call_ratio,
                   yield_curve_slope, fed_rate_environment
            FROM market_health_daily
            ORDER BY date DESC LIMIT 1
        """)
        mh = cur.fetchone()
        market_health = safe_json_serialize(dict(mh)) if mh else {}

        # Fetch exposure data and distribution days from market_exposure_daily
        cur.execute("""
            SELECT exposure_pct, regime, halt_reasons, distribution_days
            FROM market_exposure_daily
            ORDER BY date DESC LIMIT 1
        """)
        exp = cur.fetchone()
        exposure = safe_json_serialize(dict(exp)) if exp else {}

        # Fetch SPY close price
        spy_close = None
        try:
            cur.execute("""
                SELECT close FROM price_daily
                WHERE symbol = 'SPY'
                ORDER BY date DESC LIMIT 1
            """)
            spy_row = cur.fetchone()
            if spy_row:
                spy_close = safe_float(spy_row[0]) if spy_row[0] else None
        except Exception as e:
            logger.warning(f"[MARKET] SPY price unavailable: {e}")

        # Combine all data in the format the dashboard expects
        data = {
            'exposure_pct': safe_float(exposure.get('exposure_pct')),
            'regime': exposure.get('regime'),
            'halt_reasons': exposure.get('halt_reasons') or [],
            'vix_level': safe_float(market_health.get('vix_level')),
            'market_stage': safe_int(market_health.get('market_stage')),
            'market_trend': market_health.get('market_trend'),
            'distribution_days_4w': safe_int(exposure.get('distribution_days')),
            'spy_close': spy_close,
            'spy_change_pct': safe_float(market_health.get('spy_change_pct')),
            'up_volume_percent': safe_float(market_health.get('up_volume_percent')),
            'advance_decline_ratio': safe_float(market_health.get('advance_decline_ratio')),
            'new_highs_count': safe_int(market_health.get('new_highs_count')),
            'new_lows_count': safe_int(market_health.get('new_lows_count')),
            'put_call_ratio': safe_float(market_health.get('put_call_ratio')),
            'breadth_momentum_10d': safe_float(market_health.get('breadth_momentum_10d')),
            'yield_curve_slope': safe_float(market_health.get('yield_curve_slope')),
            'fed_rate_environment': market_health.get('fed_rate_environment'),
        }

        return json_response(200, {'data': data})
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        logger.error(f'Failed to fetch market: {type(e).__name__}: {e}')
        return json_response(503, {'errorType': 'service_unavailable', 'message': 'Failed to fetch market data'})

def _get_market_factors(cur) -> Dict:
    """Get market exposure factors for dashboard display."""
    try:
        cur.execute("SET LOCAL statement_timeout = '8000ms'")

        # Fetch exposure factors from market_exposure_daily
        cur.execute("""
            SELECT exposure_pct, raw_score, regime, factors
            FROM market_exposure_daily
            ORDER BY date DESC LIMIT 1
        """)
        row = cur.fetchone()

        if not row:
            return json_response(200, {'data': {
                'exposure_pct': None,
                'raw_score': None,
                'regime': None,
                'factors': {}
            }})

        data_dict = safe_json_serialize(dict(row))

        # Parse factors if it's a JSON string
        factors = {}
        if data_dict.get('factors'):
            try:
                factors_val = data_dict.get('factors')
                if isinstance(factors_val, str):
                    factors = json.loads(factors_val)
                else:
                    factors = factors_val if isinstance(factors_val, dict) else {}
            except Exception as e:
                logger.warning(f"[MARKET_FACTORS] Failed to parse factors: {e}")
                factors = {}

        data = {
            'exposure_pct': safe_float(data_dict.get('exposure_pct')),
            'raw_score': safe_float(data_dict.get('raw_score')),
            'regime': data_dict.get('regime'),
            'factors': factors,
        }

        return json_response(200, {'data': data})
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        logger.error(f'Failed to fetch market factors: {type(e).__name__}: {e}')
        return json_response(503, {'errorType': 'service_unavailable', 'message': 'Failed to fetch market factors'})

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
                WITH distinct_trades AS (
                    SELECT DISTINCT ON (at.symbol)
                        at.symbol, cp.sector
                    FROM algo_trades at
                    JOIN company_profile cp ON at.symbol = cp.ticker
                    WHERE at.status = 'open'
                    ORDER BY at.symbol
                )
                SELECT sector, COUNT(symbol) as count
                FROM distinct_trades
                GROUP BY sector
                ORDER BY count DESC
            """)
            sector_exposure = [safe_json_serialize(dict(r)) for r in cur.fetchall()]

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

            sig_dict = safe_json_serialize(dict(sig_row))
            return json_response(200, {
                'stage': 'evaluated',
                'candidates': {
                    'screened': sig_dict.get('candidates_screened', 0),
                    'passing_sqs_60': sig_dict.get('candidates_passing', 0),
                    'excellent_sqs_70': sig_dict.get('candidates_excellent', 0),
                    'exceptional_sqs_80': sig_dict.get('candidates_exceptional', 0),
                    'score_range': {
                        'min': float(sig_dict.get('min_score')) if sig_dict.get('min_score') is not None else None,
                        'median': float(sig_dict.get('median_score')) if sig_dict.get('median_score') is not None else None,
                        'average': float(sig_dict.get('avg_score')) if sig_dict.get('avg_score') is not None else None,
                        'max': float(sig_dict.get('top_score')) if sig_dict.get('top_score') is not None else None,
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
                    'today_return_pct': safe_float(today_return),
                    'unrealized_pnl': safe_float(unrealized_pnl)
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
                row_dict = safe_json_serialize(dict(row))
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
                if severity == 'critical':
                    status_label = 'failed'
                elif severity in ('error', 'warn'):
                    status_label = 'warning'
                else:
                    status_label = 'passed'

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
            code, error_type, message = handle_db_error(e, 'check data quality')
            logger.error(f'Failed to check data quality: {error_type} - {message}')
            return json_response(code, {'errorType': error_type, 'message': message})
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

            row = safe_json_serialize(dict(row))
            tier_key = str(row.get('regime') or '').lower()
            tier_conf = _TIER_CONFIG.get(tier_key, {})
            active_tier = {'name': tier_key, **tier_conf}
            active_tier['halt'] = bool(row.get('halt_reasons')) or tier_conf.get('halt', False)

            # Parse factors from JSON if available
            factors = {}
            factor_quality = 'ok'
            if row.get('factors'):
                try:
                    if isinstance(row['factors'], str):
                        factors = json.loads(row['factors'])
                    else:
                        factors = row['factors']
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning(f"Failed to parse factors: {e}")
                    factors = {}
                    factor_quality = 'parse_error'

            # Validate expected factor keys are present
            expected_factor_keys = {'stage_number', 'ad_ratio', 'vix', 'breadth_momentum', 'mcclellan'}
            if factors and not isinstance(factors, dict):
                logger.error(f"Factors not a dict: {type(factors)}")
                factor_quality = 'invalid_structure'
            elif factors:
                found_keys = set(factors.keys())
                missing_keys = expected_factor_keys - found_keys
                if missing_keys:
                    logger.warning(f"Market exposure factors missing keys: {missing_keys} (found: {found_keys})")
                    factor_quality = 'degraded' if missing_keys else 'ok'

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
                    market_health = safe_json_serialize(dict(mh_row))
            except psycopg2.Error as e:
                logger.warning(f"Failed to fetch market health: {e}")

            exposure_pct_val = row.get('exposure_pct')
            return json_response(200, {
                'current_exposure_pct': float(exposure_pct_val) if exposure_pct_val is not None else None,
                'exposure_tier': tier_key,
                'is_entry_allowed': not active_tier['halt'],
                'active_tier': active_tier,
                'all_tiers': [{'name': k, **v} for k, v in _TIER_CONFIG.items()],
                'regime_factors': {
                    'sp500_stage': factors.get('stage_number'),
                    'advance_decline_ratio': factors.get('ad_ratio') if factors.get('ad_ratio') is not None else market_health.get('advance_decline_ratio'),
                    'vix_level': factors.get('vix') if factors.get('vix') is not None else market_health.get('vix_level'),
                    'breadth_momentum': factors.get('breadth_momentum') if factors.get('breadth_momentum') is not None else market_health.get('breadth_momentum_10d'),
                    'distribution_days': row.get('distribution_days') or market_health.get('distribution_days_4w'),
                    'market_stage': market_health.get('market_stage'),
                    'market_trend': market_health.get('market_trend'),
                    'mcclellan_oscillator': factors.get('mcclellan'),
                },
                'factor_quality': factor_quality,
                'halt_reasons': row.get('halt_reasons'),
                'as_of': row['date'].isoformat() if row['date'] else None,
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            logger.error(f'Failed to fetch exposure policy: {type(e).__name__}: {e}', extra={'operation': 'get exposure policy'})
            return json_response(200, {'current_exposure_pct': 0, 'regime': 'unknown', 'halt_reasons': [], 'factor_quality': 'unavailable', 'factors': {}, 'as_of': None})
def _get_sector_stage2(cur) -> Dict:
        """Get percentage of stocks in Stage 2 by sector."""
        try:
            cur.execute("""
                WITH latest_date AS (
                    SELECT date FROM trend_template_data ORDER BY date DESC LIMIT 1
                ),
                distinct_trends AS (
                    SELECT DISTINCT ON (t.symbol)
                        t.symbol, t.weinstein_stage, cp.sector
                    FROM trend_template_data t
                    JOIN company_profile cp ON t.symbol = cp.ticker
                    WHERE t.date = (SELECT date FROM latest_date)
                      AND cp.sector IS NOT NULL
                    ORDER BY t.symbol
                ),
                stage2_counts AS (
                    SELECT
                        sector,
                        COUNT(CASE WHEN weinstein_stage = 2 THEN 1 END) AS stage_2,
                        COUNT(symbol) AS total
                    FROM distinct_trends
                    GROUP BY sector
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
            return list_response([safe_json_serialize(dict(r)) for r in rows])
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
def _categorize_config_key(key: str) -> str:
        """Categorize configuration key for TIER 3 visibility grouping."""
        if 'drawdown' in key or 'halt' in key or 'risk_reduction' in key:
            return 'Drawdown Defense'
        elif 'circuit' in key or 'max_daily_loss' in key or 'max_consecutive' in key or 'min_win_rate' in key or 'max_total_risk' in key or 'max_weekly' in key or 'daily_profit_cap' in key or 'sector_drawdown' in key:
            return 'Circuit Breakers'
        elif 'swing' in key or 'swing_weight' in key or 'swing_grade' in key or 'swing_min' in key or 'swing_days' in key:
            return 'Swing Trader Scoring'
        elif 'vix' in key or 'put_call' in key or 'upvol' in key or 'breadth' in key or 'yield_curve' in key or 'beta' in key or 'max_distribution' in key or 'require_stage' in key:
            return 'Market Conditions'
        elif 'min_completeness' in key or 'min_stock_price' in key or 'min_signal' in key or 'min_volume' in key or 'min_avg_daily' in key or 'require_stock_stage' in key or 'max_stop_distance' in key or 'max_positions_per' in key or 'min_swing_score' in key or 'max_total_invested' in key or 'advanced_filters_grade' in key:
            return 'Filter Thresholds'
        elif 'require_sma50' in key or 'min_percent_from' in key or 'max_percent_from' in key or 'min_trend_template' in key:
            return 'Entry Rules (Minervini)'
        elif 'max_signal_age' in key or 'min_close_quality' in key or 'min_breakout_volume' in key or 'require_weekly_stage' in key or 'min_rs_line' in key or 'max_rs_pct' in key or 'rs_slope_gate' in key or 'volume_decay_gate' in key:
            return 'Entry Quality Gates'
        elif 'require_target_pullback' in key or 't1_target' in key or 't2_target' in key or 't3_target' in key or 'imported_position' in key or 'min_hold' in key or 'max_hold' in key or 'exit_on' in key or 'use_chandelier' in key or 'switch_to_21ema' in key or 'eight_week_rule' in key or 'chandelier_atr' in key or 'move_be' in key:
            return 'Exit Rules'
        elif 'pyramid' in key or 're_engage' in key:
            return 'Pyramid & Re-engagement'
        elif 'position_halt_flag' in key or 'max_reentries' in key or 'min_days_before_reentry' in key:
            return 'Position Monitoring'
        elif 'earnings' in key or 'halt_entries_before' in key or 'block_days_before' in key:
            return 'Economic & Earnings'
        elif 'min_price_history' in key or 'min_daily_volume' in key or 'max_spread' in key or 'min_market_cap' in key or 'min_float' in key or 'max_short_interest' in key:
            return 'Fundamental Filters'
        elif 'max_extension' in key or 'strong_sector' in key:
            return 'Advanced Filters'
        elif 'var_percentile' in key or 'cvar_percentile' in key or 'stressed_var' in key or 'dashboard_grade' in key:
            return 'Risk Metrics'
        elif 'execution_mode' in key or 'alpaca_paper' in key or 'max_trades_per_day' in key or 'default_portfolio' in key:
            return 'Execution Mode'
        elif 'enable_' in key or 'verbose_' in key:
            return 'Feature Flags'
        elif 'api_request' in key or 'db_connection' in key:
            return 'Network Configuration'
        elif 'failsafe' in key:
            return 'Failsafe Configuration'
        elif 'base_risk' in key or 'max_position_size' in key or 'max_concentration' in key:
            return 'Risk Management'
        else:
            return 'Other'

@db_route_handler('fetch algo config', default_error_response={'items': [], 'total': 0, '_error': 'Data unavailable'})
def _get_algo_config(cur) -> Dict:
    """Return all algo configuration rows with defaults and categorization for TIER 3 visibility."""
    from algo.algo_config import AlgoConfig

    cur.execute("SELECT key, value, value_type, description, updated_at FROM algo_config ORDER BY key")
    rows = cur.fetchall()

    # Build config with defaults and categorization
    config_items = []
    for row in rows:
        config_dict = safe_json_serialize(dict(row))
        key = config_dict['key']

        # Get default value and metadata from AlgoConfig.DEFAULTS
        if key in AlgoConfig.DEFAULTS:
            default_val, _, _ = AlgoConfig.DEFAULTS[key]
            config_dict['default_value'] = default_val
            config_dict['is_custom'] = str(config_dict['value']).strip() != str(default_val).strip()
        else:
            config_dict['default_value'] = None
            config_dict['is_custom'] = True

        # Categorize by key name patterns
        config_dict['category'] = _categorize_config_key(key)
        config_items.append(config_dict)

    return list_response(config_items)

@db_route_handler('fetch algo config key', default_error_response={'_error': 'Data unavailable'})
def _get_algo_config_key(cur, key: str) -> Dict:
    """Return a single algo config key."""
    cur.execute("SELECT key, value, value_type, description, updated_at FROM algo_config WHERE key = %s", (key,))
    row = cur.fetchone()
    return json_response(200, safe_json_serialize(dict(row)) if row else {})

@db_route_handler('update algo config key')
def _update_algo_config_key(cur, key: str, body: Dict, actor: str) -> Dict:
        """Update a configuration key (TIER 4: Configuration Editing)."""
        from algo.algo_config import AlgoConfig

        if not body or 'value' not in body:
            return error_response(400, 'bad_request', 'value required in request body')

        # Validate the key exists and get its type
        cur.execute("SELECT key, value_type FROM algo_config WHERE key = %s", (key,))
        row = cur.fetchone()
        if not row:
            return error_response(404, 'not_found', f'Config key not found: {key}')

        value_type = row['value_type']
        new_value = body.get('value')

        # Validate the new value against AlgoConfig constraints
        try:
            if not AlgoConfig.DEFAULTS.get(key):
                return error_response(400, 'bad_request', f'Unknown config key: {key}')

            _, expected_type, _ = AlgoConfig.DEFAULTS[key]
            # Validate bounds and type
            config = AlgoConfig()
            config._validate_value(key, str(new_value), expected_type)
        except ValueError as e:
            logger.warning(f'Config validation failed for {key}={new_value}: {e}')
            return error_response(400, 'bad_request', f'Invalid value for {key}: {str(e)}')

        # Get old value for audit
        cur.execute("SELECT value FROM algo_config WHERE key = %s", (key,))
        old_row = cur.fetchone()
        old_value = old_row['value'] if old_row else None

        # Update the config
        cur.execute("""
            UPDATE algo_config
            SET value = %s, updated_at = CURRENT_TIMESTAMP, updated_by = %s
            WHERE key = %s
        """, (str(new_value), actor, key))

        # Log to audit trail
        cur.execute("""
            INSERT INTO algo_config_audit (config_key, old_value, new_value, changed_by, changed_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        """, (key, old_value, str(new_value), actor))

        logger.info(f'[TIER4] Config updated by {actor}: {key} = {new_value} (was {old_value})')

        return json_response(200, {
            'status': 'success',
            'key': key,
            'old_value': old_value,
            'new_value': str(new_value),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'updated_by': actor,
        })

@db_route_handler('reset algo config key')
def _reset_algo_config_key(cur, key: str, actor: str) -> Dict:
    """Reset a configuration key to its default value (TIER 5: Reset capability)."""
    from algo.algo_config import AlgoConfig

    # Validate the key exists
    if key not in AlgoConfig.DEFAULTS:
        return error_response(404, 'not_found', f'Config key not found: {key}')

    default_val, _, _ = AlgoConfig.DEFAULTS[key]

    # Get current value for audit
    cur.execute("SELECT value FROM algo_config WHERE key = %s", (key,))
    old_row = cur.fetchone()
    old_value = old_row['value'] if old_row else None

    # Reset to default
    cur.execute("""
        UPDATE algo_config
        SET value = %s, updated_at = CURRENT_TIMESTAMP, updated_by = %s
        WHERE key = %s
    """, (default_val, actor, key))

    # Log to audit trail
    cur.execute("""
        INSERT INTO algo_config_audit (config_key, old_value, new_value, changed_by, changed_at)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
    """, (key, old_value, default_val, actor))

    logger.info(f'[TIER5] Config reset by {actor}: {key} = {default_val} (was {old_value})')

    return json_response(200, {
        'status': 'success',
        'key': key,
        'old_value': old_value,
        'new_value': default_val,
        'reset_to_default': True,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'updated_by': actor,
    })

@db_route_handler('get algo audit log')
def _get_algo_audit_log(cur, limit: int = 100, offset: int = 0, action_type: str = None) -> Dict:
        """Return algo audit log entries with pagination."""
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
        return list_response([safe_json_serialize(dict(r)) for r in rows], total=total, limit=limit, offset=offset)

# FIXED Issue #6: Orchestrator execution history endpoints
@db_route_handler('fetch orchestrator execution recent', default_error_response={'items': [], 'total': 0, '_error': 'Data unavailable'})
def _get_orchestrator_execution_recent(cur, days: int = 7, limit: int = 50) -> Dict:
    """Return recent orchestrator execution runs."""
    cur.execute("""
        SELECT run_id, run_date, started_at, completed_at, overall_status,
               phases_completed, phases_halted, phases_errored, summary
        FROM orchestrator_execution_log
        WHERE run_date >= CURRENT_DATE - %s
        ORDER BY started_at DESC
        LIMIT %s
    """, (days, limit))
    rows = cur.fetchall()
    return list_response([safe_json_serialize(dict(r)) for r in rows], total=len(rows), limit=limit)

@db_route_handler('fetch orchestrator execution failed', default_error_response={'items': [], 'total': 0, '_error': 'Data unavailable'})
def _get_orchestrator_execution_failed(cur, days: int = 30) -> Dict:
    """Return failed/halted orchestrator runs."""
    cur.execute("""
        SELECT run_id, run_date, started_at, overall_status, summary, halt_reason
        FROM orchestrator_execution_log
        WHERE run_date >= CURRENT_DATE - %s
          AND overall_status IN ('halted', 'error')
        ORDER BY started_at DESC
    """, (days,))
    rows = cur.fetchall()
    return list_response([safe_json_serialize(dict(r)) for r in rows], total=len(rows))

@db_route_handler('fetch orchestrator execution details', default_error_response={'data': {}, '_error': 'Data unavailable'})
def _get_orchestrator_execution_details(cur, run_id: str) -> Dict:
    """Return full details of a specific orchestrator run."""
    cur.execute("""
        SELECT run_id, run_date, started_at, completed_at, overall_status,
               phase_results, summary, halt_reason, phases_completed,
               phases_halted, phases_errored
        FROM orchestrator_execution_log
        WHERE run_id = %s
    """, (run_id,))
    row = cur.fetchone()
    if not row:
        return error_response(404, 'not_found', f'Run {run_id} not found')

    result = safe_json_serialize(dict(row))
    # Parse phase_results JSONB
    if result.get('phase_results'):
        try:
            result['phase_results'] = json.loads(result['phase_results'])
        except Exception as e:
            logger.warning(f'Failed to parse phase_results JSON: {e}')
            result['phase_results'] = {}
    return success_response(result)

@db_route_handler('fetch orchestrator execution patterns', default_error_response={'data': {'patterns': [], 'period_days': 0}, '_error': 'Data unavailable'})
def _get_orchestrator_execution_patterns(cur, days: int = 30) -> Dict:
    """Analyze halt patterns - which phases halt most often."""
    cur.execute("""
        SELECT
            phase_results->>'name' as phase_name,
            COUNT(*) as halt_count,
            array_agg(DISTINCT phase_results->>'summary') as reasons
        FROM orchestrator_execution_log,
             jsonb_array_elements(phase_results) as phase_results
        WHERE run_date >= CURRENT_DATE - %s
          AND phase_results->>'status' = 'halt'
        GROUP BY phase_results->>'name'
        ORDER BY halt_count DESC
    """, (days,))
    rows = cur.fetchall()
    patterns = [
        {
            'phase': r['phase_name'],
            'total_halts': r['halt_count'],
            'example_reasons': r['reasons'][:3] if r['reasons'] else []
        }
        for r in rows
    ]
    return success_response({'patterns': patterns, 'period_days': days})

@db_route_handler('fetch orchestrator execution stats', default_error_response={'data': {'total_runs': 0, 'by_status': {}, 'success_rate': 'N/A', 'halt_rate': 'N/A', 'error_rate': 'N/A', 'period_days': 0}, '_error': 'Data unavailable'})
def _get_orchestrator_execution_stats(cur, days: int = 7) -> Dict:
    """Return execution statistics."""
    cur.execute("""
        SELECT
            overall_status,
            COUNT(*) as count
        FROM orchestrator_execution_log
        WHERE run_date >= CURRENT_DATE - %s
        GROUP BY overall_status
    """, (days,))
    rows = cur.fetchall()

    stats_by_status = {r['overall_status']: r['count'] for r in rows}
    total = sum(stats_by_status.values())

    success_count = stats_by_status.get('success', 0)
    halt_count = stats_by_status.get('halted', 0)
    error_count = stats_by_status.get('error', 0)

    return success_response({
        'total_runs': total,
        'by_status': stats_by_status,
        'success_rate': f"{(success_count / total * 100):.1f}%" if total > 0 else "N/A",
        'halt_rate': f"{(halt_count / total * 100):.1f}%" if total > 0 else "N/A",
        'error_rate': f"{(error_count / total * 100):.1f}%" if total > 0 else "N/A",
        'period_days': days
    })

@db_route_handler('get algo portfolio', default_error_response={'data': {}})
def _get_algo_portfolio(cur) -> Dict:
    """Get latest portfolio snapshot data."""
    try:
        cur.execute("""
            SELECT snapshot_date, total_portfolio_value, total_cash,
                   unrealized_pnl_total, position_count, daily_return_pct, unrealized_pnl_pct,
                   cumulative_return_pct, max_drawdown_pct, largest_position_pct
            FROM algo_portfolio_snapshots
            ORDER BY snapshot_date DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return success_response({
                'total_portfolio_value': None,
                'total_cash': None,
                'open_positions': 0,
                'daily_return_pct': None,
                'unrealized_pnl_pct': None,
                'cumulative_return_pct': None,
                'max_drawdown_pct': None,
                'largest_position_pct': None,
                'last_run': None
            })
        data = dict(row)
        return success_response({
            'total_portfolio_value': safe_float(data.get('total_portfolio_value')),
            'total_cash': safe_float(data.get('total_cash')),
            'open_positions': safe_int(data.get('position_count')),
            'daily_return_pct': safe_float(data.get('daily_return_pct')),
            'unrealized_pnl_pct': safe_float(data.get('unrealized_pnl_pct')),
            'cumulative_return_pct': safe_float(data.get('cumulative_return_pct')),
            'max_drawdown_pct': safe_float(data.get('max_drawdown_pct')),
            'largest_position_pct': safe_float(data.get('largest_position_pct')),
            'last_run': data.get('snapshot_date')
        })
    except Exception as e:
        logger.error(f'Portfolio fetch error: {type(e).__name__}: {e}')
        return error_response(503, 'service_unavailable', 'Portfolio data unavailable')

@db_route_handler('get algo metrics', default_error_response={'data': []})
def _get_algo_metrics(cur) -> Dict:
    """Get daily algo metrics (total actions, entries, exits)."""
    try:
        cur.execute("""
            SELECT date, total_actions, entries, exits, avg_signal_score
            FROM algo_metrics_daily
            ORDER BY date DESC
            LIMIT 30
        """)
        rows = cur.fetchall()
        metrics = [safe_json_serialize(dict(r)) for r in rows]
        return success_response(metrics)
    except Exception as e:
        logger.error(f'Algo metrics fetch error: {type(e).__name__}: {e}')
        return error_response(503, 'service_unavailable', 'Algo metrics unavailable')

@db_route_handler('get risk metrics', default_error_response={'data': {}})
def _get_risk_metrics(cur) -> Dict:
    """Get portfolio risk metrics."""
    try:
        cur.execute("""
            SELECT report_date, var_pct_95, cvar_pct_95, stressed_var_pct,
                   portfolio_beta, top_5_concentration
            FROM algo_risk_daily
            ORDER BY report_date DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return success_response({
                'report_date': None,
                'var_pct_95': None,
                'cvar_pct_95': None,
                'stressed_var_pct': None,
                'portfolio_beta': None,
                'top_5_concentration': None
            })
        data = dict(row)
        return success_response({
            'report_date': data.get('report_date'),
            'var_pct_95': safe_float(data.get('var_pct_95')),
            'cvar_pct_95': safe_float(data.get('cvar_pct_95')),
            'stressed_var_pct': safe_float(data.get('stressed_var_pct')),
            'portfolio_beta': safe_float(data.get('portfolio_beta')),
            'top_5_concentration': safe_float(data.get('top_5_concentration'))
        })
    except Exception as e:
        logger.error(f'Risk metrics fetch error: {type(e).__name__}: {e}')
        return error_response(503, 'service_unavailable', 'Risk metrics unavailable')

@db_route_handler('get performance analytics', default_error_response={'data': {}})
def _get_performance_analytics(cur) -> Dict:
    """Get performance analytics data."""
    try:
        cur.execute("""
            SELECT rolling_sharpe_252d, rolling_sortino_252d, calmar_ratio,
                   win_rate_50t, avg_win_r_50t, avg_loss_r_50t, expectancy, max_drawdown_pct
            FROM algo_performance_daily
            ORDER BY report_date DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return success_response({
                'rolling_sharpe_252d': None,
                'rolling_sortino_252d': None,
                'calmar_ratio': None,
                'win_rate_50t': None,
                'avg_win_r_50t': None,
                'avg_loss_r_50t': None,
                'expectancy': None,
                'max_drawdown_pct': None
            })
        data = dict(row)
        return success_response({
            'rolling_sharpe_252d': safe_float(data.get('rolling_sharpe_252d')),
            'rolling_sortino_252d': safe_float(data.get('rolling_sortino_252d')),
            'calmar_ratio': safe_float(data.get('calmar_ratio')),
            'win_rate_50t': safe_float(data.get('win_rate_50t')),
            'avg_win_r_50t': safe_float(data.get('avg_win_r_50t')),
            'avg_loss_r_50t': safe_float(data.get('avg_loss_r_50t')),
            'expectancy': safe_float(data.get('expectancy')),
            'max_drawdown_pct': safe_float(data.get('max_drawdown_pct'))
        })
    except Exception as e:
        logger.error(f'Performance analytics fetch error: {type(e).__name__}: {e}')
        return error_response(503, 'service_unavailable', 'Performance analytics unavailable')

@db_route_handler('get sentiment', default_error_response={'data': {}})
def _get_sentiment(cur) -> Dict:
    """Get market sentiment data."""
    try:
        cur.execute("""
            SELECT date, fear_greed_index, label
            FROM market_sentiment
            ORDER BY date DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            return success_response({
                'date': None,
                'fear_greed_index': 50.0,
                'label': 'Neutral'
            })
        data = dict(row)
        return success_response({
            'date': data.get('date'),
            'fear_greed_index': safe_float(data.get('fear_greed_index'), default=50.0),
            'label': data.get('label', 'Neutral')
        })
    except Exception as e:
        logger.error(f'Sentiment fetch error: {type(e).__name__}: {e}')
        return error_response(503, 'service_unavailable', 'Sentiment data unavailable')

@db_route_handler('get economic calendar', default_error_response={'data': []})
def _get_economic_calendar(cur) -> Dict:
    """Get economic calendar data."""
    try:
        cur.execute("""
            SELECT event_date, event_name, country, actual, forecast, previous, impact
            FROM economic_calendar
            WHERE event_date >= CURRENT_DATE
            ORDER BY event_date ASC
            LIMIT 100
        """)
        rows = cur.fetchall()
        events = [safe_json_serialize(dict(r)) for r in rows]
        return success_response(events)
    except Exception as e:
        logger.error(f'Economic calendar fetch error: {type(e).__name__}: {e}')
        return error_response(503, 'service_unavailable', 'Economic calendar unavailable')
