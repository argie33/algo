"""Route: algo"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re, json, os
from datetime import datetime, timedelta, date, timezone
import boto3
from botocore.exceptions import ClientError
from .utils import error_response, success_response, list_response, json_response, safe_limit, safe_days, safe_offset, handle_db_error

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
        """Handle /api/algo/* endpoints."""
        # User identity from verified JWT claims (sub is the Cognito user ID)
        user_id = (jwt_claims or {}).get('sub', '')

        if method == 'PATCH' and path.endswith('/read') and '/notifications/' in path:
            notif_id = path.split('/notifications/')[-1].replace('/read', '')
            if not user_id:
                return error_response(401, 'unauthorized', 'Authentication required')
            try:
                try:
                    notif_id_int = int(notif_id)
                except ValueError:
                    return error_response(400, 'bad_request', 'ID must be numeric')
                cur.execute(
                    "UPDATE algo_notifications SET seen=TRUE, seen_at=NOW() WHERE id=%s AND user_id=%s",
                    (notif_id_int, user_id)
                )
                if cur.rowcount == 0:
                    return error_response(403, 'forbidden', 'Notification not found or access denied')
                cur.connection.commit()
                return json_response(200, {'status': 'updated'})
            except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                    psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
                return handle_db_error(e, logger, 'handle algo')
        if method == 'DELETE' and '/notifications/' in path:
            notif_id = path.split('/notifications/')[-1]
            if not user_id:
                return error_response(401, 'unauthorized', 'Authentication required')
            try:
                cur.execute("DELETE FROM algo_notifications WHERE id=%s AND user_id=%s", (int(notif_id), user_id))
                if cur.rowcount == 0:
                    return error_response(403, 'forbidden', 'Notification not found or access denied')
                cur.connection.commit()
                return json_response(200, {'status': 'deleted'})
            except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                    psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
                return handle_db_error(e, logger, 'handle algo')
        if method == 'POST' and path == '/api/algo/patrol':
            logger.info("Manual patrol triggered via API")
            return json_response(200, {'status': 'triggered', 'message': 'Patrol triggered'})
        if method == 'POST' and path == '/api/algo/pre-trade-impact':
            return _analyze_pre_trade_impact(cur, body)
        if path == '/api/algo/status':
            return _get_algo_status(cur)
        elif path == '/api/algo/trades':
            limit_str = params.get('limit', [None])[0] if params else None
            limit = safe_limit(limit_str, max_val=50000, default=50000)
            return _get_algo_trades(cur, limit)
        elif path == '/api/algo/positions':
            return _get_algo_positions(cur)
        elif path == '/api/algo/performance':
            return _get_algo_performance(cur)
        elif path == '/api/algo/circuit-breakers':
            return _get_circuit_breakers(cur)
        elif path == '/api/algo/equity-curve':
            days_str = params.get('limit', [None])[0] if params else None
            days = safe_days(days_str, max_val=365, default=180)
            return _get_equity_curve(cur, days)
        elif path == '/api/algo/data-status':
            return _get_data_status(cur)
        elif path == '/api/algo/notifications':
            return _get_notifications(cur, params)
        elif path == '/api/algo/patrol-log':
            limit_str = params.get('limit', [None])[0] if params else None
            limit = safe_limit(limit_str, max_val=50000, default=50000)
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
            limit_str = params.get('limit', [None])[0] if params else None
            limit = safe_limit(limit_str, max_val=50000, default=50000)
            min_score_str = params.get('min_score', [None])[0] if params else None
            min_score = float(min_score_str) if min_score_str else None
            return _get_swing_scores(cur, limit, min_score)
        elif path == '/api/algo/swing-scores-history':
            days_str = params.get('days', [None])[0] if params else None
            days = safe_days(days_str, max_val=365, default=30)
            return _get_swing_scores_history(cur, days)
        elif path == '/api/algo/rejection-funnel':
            return _get_rejection_funnel(cur)
        elif path == '/api/algo/markets':
            return _get_markets(cur)
        elif path == '/api/algo/evaluate':
            return _get_algo_evaluate(cur)
        elif path == '/api/algo/data-quality':
            return _get_data_quality(cur)
        elif path == '/api/algo/exposure-policy':
            return _get_exposure_policy(cur)
        elif path == '/api/algo/sector-stage2':
            return _get_sector_stage2(cur)
        elif path == '/api/algo/config':
            return _get_algo_config(cur)
        elif path.startswith('/api/algo/config/'):
            key = path[len('/api/algo/config/'):]
            return _get_algo_config_key(cur, key)
        elif path == '/api/algo/audit-log':
            limit_str = params.get('limit', [None])[0] if params else None
            limit = safe_limit(limit_str, max_val=50000, default=50000)
            offset_str = params.get('offset', [None])[0] if params else None
            offset = safe_offset(offset_str)
            action_type = params.get('action_type', [None])[0] if params else None
            return _get_algo_audit_log(cur, limit, offset, action_type)
        else:
            return error_response(404, 'not_found', f'No algo handler for {path}')

def _get_algo_status(cur) -> Dict:
        """Get latest algo execution status."""
        try:
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
                return json_response(200, {'status': 'no_runs_yet', 'last_run': None})

            return json_response(200, {
                'run_id': row['run_id'],
                'last_run': row['action_date'].isoformat() if row['action_date'] else None,
                'current_phase': row['action_type'],
                'status': row['status'],
                'message': row['message'],
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'fetch algo status')

def _get_algo_trades(cur, limit: int = 200) -> Dict:
        """Get recent trades with all fields for frontend."""
        try:
            cur.execute("""
                SELECT trade_id, symbol, signal_date, trade_date, entry_price, entry_time,
                       entry_quantity, entry_reason, exit_price, exit_date, exit_time,
                       exit_reason, exit_r_multiple, profit_loss_dollars, profit_loss_pct,
                       status, swing_score, swing_grade, base_type, stage_phase,
                       trade_duration_days, mfe_pct, mae_pct, created_at
                FROM algo_trades
                ORDER BY trade_date DESC, trade_id DESC
                LIMIT %s
            """, (limit,))
            trades = cur.fetchall()
            items = [dict(t) for t in trades]
            return json_response(200, {
                'items': items,
                'pagination': {'total': len(items), 'limit': limit, 'offset': 0}
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'fetch algo trades')

def _get_algo_positions(cur) -> Dict:
        """Get current open positions with all tracking fields."""
        try:
            cur.execute("""
                SELECT position_id, symbol, quantity, avg_entry_price, current_price,
                       position_value, unrealized_pnl, unrealized_pnl_pct, status,
                       days_since_entry, distribution_day_count, target_levels_hit,
                       current_stop_price, stage_in_exit_plan, created_at, updated_at
                FROM algo_positions
                WHERE LOWER(status) = 'open'
                ORDER BY position_value DESC
            """)
            positions = cur.fetchall()
            items = [dict(p) for p in positions]
            return json_response(200, {
                'items': items,
                'pagination': {'total': len(items), 'limit': 10000, 'offset': 0}
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'fetch algo positions')

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
                    if vals[0] > 0 and vals[-1] > 0:
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
            return json_response(200, {
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
                'max_drawdown_pct': round(max_dd * 100, 2),
                'calmar_ratio': calmar_ratio,
                'expectancy_r': round((wins_sum - losses_sum) / total if total > 0 else 0.0, 2),
                'avg_hold_days': round(_mean(holding_days), 1),
                'avg_holding_days': round(_mean(holding_days), 1),
                'avg_r_multiple': round(_mean(r_multiples), 2),
                'avg_win_r': round(_mean([r for r in r_multiples if r > 0]), 2),
                'avg_loss_r': round(_mean([r for r in r_multiples if r < 0]), 2),
                'portfolio_snapshots': snapshot_count
            })
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'calculate performance')

def _get_circuit_breakers(cur) -> Dict:
        """Get circuit breaker status from most recent orchestrator run."""
        try:
            # Most recent circuit breaker check (halt or all-clear)
            cur.execute("""
                SELECT details, action_date, status
                FROM algo_audit_log
                WHERE action_type = 'circuit_breaker_halt'
                ORDER BY created_at DESC
                LIMIT 1
            """)
            row = cur.fetchone()

            # Also get last successful (non-halted) orchestrator run details
            cur.execute("""
                SELECT details, action_date
                FROM algo_audit_log
                WHERE action_type IN ('phase_2_complete', 'orchestrator_run')
                ORDER BY created_at DESC
                LIMIT 1
            """)
            last_run = cur.fetchone()

            breakers = []
            if row and row['details']:
                try:
                    details = json.loads(row['details']) if isinstance(row['details'], str) else row['details']
                    if not isinstance(details, dict):
                        details = {}
                    checks = details.get('checks', {})
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
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'fetch circuit breakers')

def _get_equity_curve(cur, days: int = 180) -> Dict:
        """Get equity curve for last N days."""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            cur.execute("""
                SELECT snapshot_date, total_portfolio_value, total_cash,
                       unrealized_pnl_total, position_count, daily_return_pct
                FROM algo_portfolio_snapshots
                WHERE snapshot_date >= %s
                ORDER BY snapshot_date DESC
                LIMIT 1000
            """, (cutoff_date,))
            curve = cur.fetchall()
            return list_response([dict(c) for c in reversed(curve) if c])
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found (equity curve): {e}', extra={'operation': 'fetch equity curve'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found (equity curve): {e}', extra={'operation': 'fetch equity curve'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
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
        """Get data freshness status with summary for ServiceHealth/AlgoTradingDashboard."""
        try:
            cur.execute("""
                SELECT table_name, row_count, last_updated,
                       EXTRACT(EPOCH FROM (NOW() - last_updated)) / 3600 AS age_hours
                FROM data_loader_status
                ORDER BY table_name
            """)
            rows = cur.fetchall()

            # Critical tables that must be fresh for live trading
            CRITICAL_TABLES = {'price_daily', 'buy_sell_daily', 'swing_trader_scores', 'stock_symbols'}

            sources = []
            summary = {'ok': 0, 'stale': 0, 'empty': 0, 'error': 0}
            critical_stale = []

            for row in rows:
                age_h = float(row['age_hours'] or 999)
                row_count = row['row_count'] or 0
                if row_count == 0:
                    status = 'empty'
                elif age_h <= 24:
                    status = 'ok'
                elif age_h <= 72:
                    status = 'stale'
                else:
                    status = 'error'
                summary[status] = summary.get(status, 0) + 1
                if status in ('stale', 'error', 'empty') and row['table_name'] in CRITICAL_TABLES:
                    critical_stale.append(row['table_name'])
                sources.append({
                    'name': row['table_name'],
                    'status': status,
                    'last_updated': row['last_updated'].isoformat() if row.get('last_updated') else None,
                    'age_hours': round(age_h, 1),
                    'row_count': row_count,
                })

            ready_to_trade = len(critical_stale) == 0 and summary.get('ok', 0) > 0

            return json_response(200, {
                'ready_to_trade': ready_to_trade,
                'summary': summary,
                'sources': sources,
                'critical_stale': critical_stale,
                'as_of': datetime.now(timezone.utc).isoformat(),
            })
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found (data status): {e}', extra={'operation': 'fetch data status'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found (data status): {e}', extra={'operation': 'fetch data status'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error (data status): {e}', extra={'operation': 'fetch data status'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error (data status): {e}', extra={'operation': 'fetch data status', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error (data status): {e}', extra={'operation': 'fetch data status', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch data status')

def _get_notifications(cur, params: Dict = None) -> Dict:
        """Get recent notifications with optional filtering."""
        try:
            params = params or {}
            kind = params.get('kind', [None])[0] if params.get('kind') else None
            severity = params.get('severity', [None])[0] if params.get('severity') else None
            unread = params.get('unread', [None])[0] if params.get('unread') else None
            limit_str = params.get('limit', [None])[0] if params.get('limit') else None
            limit = safe_limit(limit_str, max_val=50000, default=50000)

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
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found (notifications): {e}', extra={'operation': 'fetch notifications'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found (notifications): {e}', extra={'operation': 'fetch notifications'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error (notifications): {e}', extra={'operation': 'fetch notifications'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error (notifications): {e}', extra={'operation': 'fetch notifications', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error (notifications): {e}', extra={'operation': 'fetch notifications', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch notifications')

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
            """)
            portfolio_row = dict(cur.fetchone() or {})
            current_positions = portfolio_row.get('position_count', 0)
            invested = float(portfolio_row.get('invested') or 0)

            cur.execute("""
                SELECT total_equity FROM algo_portfolio_snapshots
                ORDER BY created_at DESC LIMIT 1
            """)
            snap = cur.fetchone()
            portfolio_value = float(snap[0]) if snap and snap[0] else 100000.0

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
            except Exception:
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
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'analyze pre trade impact'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'analyze pre trade impact'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'analyze pre trade impact'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'analyze pre trade impact', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'analyze pre trade impact', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to analyze trade impact')
def _trigger_data_patrol(cur) -> Dict:
        """Trigger async data patrol ECS task."""
        try:
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
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'trigger data patrol'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'trigger data patrol'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
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
            total = cur.fetchone()['total']

            cur.execute("""
                SELECT created_at, check_name, severity, target_table, message, patrol_run_id
                FROM data_patrol_log
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            findings = cur.fetchall()
            return list_response([dict(f) for f in findings], total=total)
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get patrol log'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get patrol log'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get patrol log'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get patrol log', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get patrol log', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch patrol log')
def _get_sector_rotation(cur, days: int = 180) -> Dict:
        """Get sector rotation data: defensive vs cyclical relative strength."""
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
            cur.execute("""
                WITH sector_dates AS (
                    SELECT DISTINCT date FROM sector_performance WHERE date >= %s ORDER BY date DESC LIMIT %s
                ),
                defensive_sectors AS (
                    SELECT 'Consumer Staples' AS sector UNION ALL
                    SELECT 'Utilities' UNION ALL
                    SELECT 'Healthcare' UNION ALL
                    SELECT 'Real Estate'
                ),
                cyclical_sectors AS (
                    SELECT 'Consumer Discretionary' AS sector UNION ALL
                    SELECT 'Industrials' UNION ALL
                    SELECT 'Materials' UNION ALL
                    SELECT 'Information Technology'
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
                )
                SELECT
                    date,
                    ROUND((COALESCE(defensive_strength, 0))::NUMERIC, 2) AS defensive_lead_score,
                    ROUND((COALESCE(cyclical_strength, 0))::NUMERIC, 2) AS cyclical_weak_score,
                    ROUND((COALESCE(defensive_strength, 0) - COALESCE(cyclical_strength, 0))::NUMERIC, 2) AS spread,
                    CASE
                        WHEN COALESCE(defensive_strength, 0) > COALESCE(cyclical_strength, 0) THEN 'DEFENSIVE'
                        WHEN COALESCE(cyclical_strength, 0) > COALESCE(defensive_strength, 0) THEN 'CYCLICAL'
                        ELSE 'NEUTRAL'
                    END AS signal,
                    1 AS weeks_persistent
                FROM rotation_stats
                ORDER BY date DESC
            """, (cutoff_date, days, cutoff_date))
            rotation = cur.fetchall()
            return list_response([dict(r) for r in rotation])
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get sector rotation'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get sector rotation'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get sector rotation'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get sector rotation', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get sector rotation', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch sector rotation')
def _get_sector_breadth(cur) -> Dict:
        """Get sector breadth indicators: % of stocks above 50-day and 200-day moving averages."""
        try:
            cur.execute("""
                WITH latest_date AS (
                    SELECT MAX(date) AS date FROM price_daily
                ),
                ma_data AS (
                    SELECT
                        pd.symbol,
                        pd.date,
                        pd.close,
                        AVG(pd.close) OVER (PARTITION BY pd.symbol ORDER BY pd.date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS ma_50,
                        AVG(pd.close) OVER (PARTITION BY pd.symbol ORDER BY pd.date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS ma_200
                    FROM price_daily pd
                    WHERE pd.date >= (SELECT date FROM latest_date) - INTERVAL '200 days'
                ),
                sector_ma AS (
                    SELECT
                        cp.sector,
                        COUNT(ma.symbol) FILTER (WHERE ma.ma_50 IS NOT NULL AND ma.close > ma.ma_50) * 100.0 /
                            NULLIF(COUNT(ma.symbol) FILTER (WHERE ma.ma_50 IS NOT NULL), 0) AS pct_above_50d,
                        COUNT(ma.symbol) FILTER (WHERE ma.ma_200 IS NOT NULL AND ma.close > ma.ma_200) * 100.0 /
                            NULLIF(COUNT(ma.symbol) FILTER (WHERE ma.ma_200 IS NOT NULL), 0) AS pct_above_200d
                    FROM ma_data ma
                    JOIN company_profile cp ON ma.symbol = cp.ticker
                    WHERE ma.date = (SELECT date FROM latest_date)
                      AND cp.sector IS NOT NULL
                    GROUP BY cp.sector
                )
                SELECT
                    sector,
                    ROUND(COALESCE(pct_above_50d, 0)::NUMERIC, 2) AS pct_above_50d,
                    ROUND(COALESCE(pct_above_200d, 0)::NUMERIC, 2) AS pct_above_200d
                FROM sector_ma
                ORDER BY pct_above_50d DESC
            """)
            breadth = cur.fetchall()
            return list_response([dict(b) for b in breadth])
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get sector breadth'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get sector breadth'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get sector breadth'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get sector breadth', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get sector breadth', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch sector breadth')
def _get_swing_scores(cur, limit: int = 100, min_score: float = None) -> Dict:
        """Get swing trade candidates with scoring."""
        try:
            score_filter = "AND s.score >= %s" if min_score is not None else ""
            query_params = [limit] if min_score is None else [min_score, limit]
            cur.execute(f"""
                SELECT
                    s.symbol, s.date, s.score AS swing_score,
                    s.components->>'grade' AS grade,
                    COALESCE((s.components->>'pass_gates')::boolean, false) AS pass_gates,
                    s.components->>'fail_reason' AS fail_reason,
                    s.components AS components,
                    cp.sector, cp.industry
                FROM swing_trader_scores s
                LEFT JOIN company_profile cp ON s.symbol = cp.ticker
                WHERE s.date >= CURRENT_DATE - INTERVAL '7 days'
                {score_filter}
                ORDER BY s.date DESC, s.score DESC
                LIMIT %s
            """, query_params)
            scores = cur.fetchall()
            return list_response([dict(s) for s in scores])
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get swing scores'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get swing scores'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get swing scores'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get swing scores', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get swing scores', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch swing scores')
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
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get swing scores history'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get swing scores history'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get swing scores history'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get swing scores history', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get swing scores history', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch swing scores history')
def _get_rejection_funnel(cur) -> Dict:
        """Get signal rejection funnel."""
        try:
            cur.execute("""
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
            funnel = cur.fetchall()
            return list_response([dict(f) for f in funnel])
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get rejection funnel'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get rejection funnel'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get rejection funnel'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get rejection funnel', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get rejection funnel', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch rejection funnel')
_TIER_CONFIG = {
    'confirmed_uptrend':      {'description': 'Market confirmed uptrend',  'risk_mult': 1.0, 'max_new': 5, 'halt': False},
    'healthy_uptrend':        {'description': 'Healthy uptrend',           'risk_mult': 0.8, 'max_new': 4, 'halt': False},
    'uptrend_under_pressure': {'description': 'Uptrend under pressure',    'risk_mult': 0.6, 'max_new': 3, 'halt': False},
    'pressure':               {'description': 'Market under pressure',     'risk_mult': 0.5, 'max_new': 2, 'halt': False},
    'caution':                {'description': 'Caution — reduce exposure', 'risk_mult': 0.3, 'max_new': 1, 'halt': True},
    'correction':             {'description': 'Market in correction',      'risk_mult': 0.2, 'max_new': 0, 'halt': True},
}

def _get_markets(cur) -> Dict:
        """Get current market regime data and historical exposure."""
        try:
            cur.execute("""
                SELECT date, exposure_pct, regime, distribution_days, factors, halt_reasons
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
                WHERE date >= CURRENT_DATE - INTERVAL '60 days'
                ORDER BY date ASC
            """)
            history = [dict(h) for h in cur.fetchall()]

            try:
                cur.execute("""
                    SELECT sector_name AS name, current_rank AS rank, rank_4w_ago, momentum_score AS momentum
                    FROM sector_ranking
                    WHERE date_recorded = (SELECT MAX(date_recorded) FROM sector_ranking)
                    ORDER BY current_rank
                """)
                sectors = [dict(s) for s in cur.fetchall()]
            except Exception:
                sectors = []

            return json_response(200, {
                'success': True,
                'current': current,
                'active_tier': active_tier,
                'history': history,
                'sectors': sectors,
            })
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get markets'})
            return json_response(200, {'success': False, 'current': None, 'history': [], 'message': 'Data not available yet'})
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get markets'})
            return json_response(200, {'success': False, 'current': None, 'history': [], 'message': 'Data schema incomplete'})
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get markets'})
            return json_response(200, {'success': False, 'current': None, 'history': [], 'message': 'Database unavailable'})
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get markets', 'error_type': type(e).__name__})
            return json_response(200, {'success': False, 'current': None, 'history': [], 'message': 'Database error'})
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get markets', 'error_type': type(e).__name__})
            return json_response(200, {'success': False, 'current': None, 'history': [], 'message': 'Failed to fetch markets data'})

def _get_algo_evaluate(cur) -> Dict:
        """Get latest signal evaluation summary from swing_trader_scores."""
        try:
            cur.execute("""
                SELECT
                    COUNT(DISTINCT symbol) AS candidates_screened,
                    COUNT(DISTINCT CASE WHEN score >= 60 THEN symbol END) AS candidates_passing,
                    MAX(score) AS top_score,
                    AVG(score) AS avg_score
                FROM swing_trader_scores
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            """)
            row = cur.fetchone()
            if not row or not row['candidates_screened']:
                return json_response(200, {'stage': 'no_data', 'candidates_screened': 0, 'candidates_passing': 0})
            return json_response(200, {
                'stage': 'evaluated',
                'candidates_screened': row['candidates_screened'] or 0,
                'candidates_passing': row['candidates_passing'] or 0,
                'top_score': float(row['top_score'] or 0),
                'avg_score': float(row['avg_score'] or 0),
            })
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get algo evaluate'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get algo evaluate'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get algo evaluate'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get algo evaluate', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get algo evaluate', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to evaluate algorithm')
def _get_data_quality(cur) -> Dict:
        """Get data quality summary from latest data_patrol_log run."""
        try:
            cur.execute("""
                SELECT
                    MAX(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) AS has_critical,
                    COUNT(CASE WHEN severity = 'error' THEN 1 END) AS error_count,
                    COUNT(CASE WHEN severity = 'warn' THEN 1 END) AS warn_count,
                    MAX(created_at) AS last_check
                FROM data_patrol_log
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            """)
            row = cur.fetchone()
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
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get data quality'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get data quality'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get data quality'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get data quality', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get data quality', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to check data quality')
def _get_exposure_policy(cur) -> Dict:
        """Get latest market exposure from market_exposure_daily."""
        try:
            cur.execute("""
                SELECT date, exposure_pct, regime, halt_reasons
                FROM market_exposure_daily
                ORDER BY date DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                return json_response(200, {'current_exposure_pct': None, 'active_tier': None, 'all_tiers': list(_TIER_CONFIG.keys())})
            row = dict(row)
            tier_key = str(row.get('regime') or '').lower()
            tier_conf = _TIER_CONFIG.get(tier_key, {})
            active_tier = {'name': tier_key, **tier_conf}
            active_tier['halt'] = bool(row.get('halt_reasons')) or tier_conf.get('halt', False)
            return json_response(200, {
                'current_exposure_pct': float(row['exposure_pct'] or 0),
                'exposure_tier': tier_key,
                'is_entry_allowed': not active_tier['halt'],
                'active_tier': active_tier,
                'all_tiers': [{'name': k, **v} for k, v in _TIER_CONFIG.items()],
                'as_of': row['date'].isoformat() if row['date'] else None,
            })
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get exposure policy'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get exposure policy'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get exposure policy'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get exposure policy', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get exposure policy', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch exposure policy')
def _get_sector_stage2(cur) -> Dict:
        """Get percentage of stocks in Stage 2 by sector."""
        try:
            cur.execute("""
                WITH latest_date AS (
                    SELECT MAX(date) AS date FROM trend_template_data
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
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get sector stage2'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get sector stage2'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get sector stage2'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get sector stage2', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get sector stage2', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch sector stage 2')
def _get_algo_config(cur) -> Dict:
        """Return all algo configuration rows."""
        try:
            cur.execute("SELECT key, value, value_type, description, updated_at FROM algo_config ORDER BY key")
            rows = cur.fetchall()
            return list_response([dict(r) for r in rows])
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get algo config'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get algo config'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
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
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get algo config key'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get algo config key'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
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
                    SELECT id, action_type, symbol, action_date, details, actor, status, error_message
                    FROM algo_audit_log
                    WHERE action_type = %s
                    ORDER BY action_date DESC
                    LIMIT %s OFFSET %s
                """, (action_type, limit, offset))
            else:
                cur.execute("""
                    SELECT id, action_type, symbol, action_date, details, actor, status, error_message
                    FROM algo_audit_log
                    ORDER BY action_date DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
            rows = cur.fetchall()
            return json_response(200, {'data': [dict(r) for r in rows], 'total': total, 'limit': limit, 'offset': offset})
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'get algo audit log'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'get algo audit log'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'get algo audit log'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'get algo audit log', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'get algo audit log', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch audit log')
