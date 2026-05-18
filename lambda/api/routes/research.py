"""Route: research"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, safe_offset

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
        """Handle /api/research/* endpoints."""
        try:
            if path == '/api/research/backtests' or path.startswith('/api/research/backtests?'):
                limit_str = params.get('limit', [None])[0] if params else None
                limit = safe_limit(limit_str, max_val=50000, default=50000)
                cur.execute("""
                    SELECT run_id, strategy_name, date_start, date_end, total_return_pct,
                           sharpe_annualized AS sharpe, max_drawdown_pct, win_rate, total_trades
                    FROM backtest_runs
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                backtests = cur.fetchall()
                return list_response([dict(b) for b in backtests] if backtests else [])
            elif path.startswith('/api/research/backtests/'):
                run_id = path.split('/api/research/backtests/')[-1]
                try:
                    run_id_int = int(run_id)
                except ValueError:
                    return error_response(400, 'bad_request', 'Run ID must be numeric')

                cur.execute("""
                    SELECT run_id, strategy_name, date_start, date_end,
                           total_return_pct, sharpe_annualized, max_drawdown_pct, win_rate,
                           total_trades, best_trade_pct, worst_trade_pct, avg_trade_pct,
                           consecutive_wins, consecutive_losses, created_at, notes
                    FROM backtest_runs
                    WHERE run_id = %s
                """, (run_id_int,))
                backtest = cur.fetchone()
                if not backtest:
                    return error_response(404, 'not_found', f'Backtest run {run_id} not found')

                limit_str = params.get('limit', [None])[0] if params else None
                offset_str = params.get('offset', [None])[0] if params else None
                limit = safe_limit(limit_str, max_val=50000, default=50000)
                offset = safe_offset(offset_str)

                cur.execute("""
                    SELECT trade_id, symbol, signal_date, entry_date, entry_price, entry_quantity,
                           exit_date, exit_price, profit_loss_pct, mfe_pct, mae_pct
                    FROM backtest_trades
                    WHERE run_id = %s
                    ORDER BY entry_date DESC
                    LIMIT %s OFFSET %s
                """, (run_id_int, limit, offset))
                trades = cur.fetchall()

                cur.execute("""
                    SELECT COUNT(*) FROM backtest_trades WHERE run_id = %s
                """, (run_id_int,))
                total_trades_count = cur.fetchone()[0]

                # Build response
                run_dict = dict(backtest)
                return json_response(200, {
                    'run': run_dict,
                    'trades': [dict(t) for t in trades] if trades else [],
                    'trade_pagination': {'total': total_trades_count}
                })
            return error_response(404, 'not_found', f'No research handler for {path}')
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'handle research'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'handle research'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'handle research'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'handle research', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'handle research', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch backtest results')
            logger.error(f"get_backtests failed: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch backtest results')


