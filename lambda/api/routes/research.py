"""Route: research"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, safe_offset, handle_db_error, check_data_freshness

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
        """Handle /api/research/* endpoints."""
        try:
            if path == '/api/research/backtests' or path.startswith('/api/research/backtests?'):
                limit_str = params.get('limit', [None])[0] if params else None
                limit = safe_limit(limit_str, max_val=50000, default=50000)
                cur.execute("""
                    SELECT run_id, strategy_name, start_date AS date_start, end_date AS date_end,
                           total_return AS total_return_pct, sharpe_ratio AS sharpe,
                           max_drawdown AS max_drawdown_pct, win_rate, num_trades AS total_trades
                    FROM backtest_runs
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                backtests = cur.fetchall()
                freshness = check_data_freshness(cur, 'backtest_runs', 'created_at', warning_days=7)
                return list_response([dict(b) for b in backtests] if backtests else [], data_freshness=freshness)
            elif path.startswith('/api/research/backtests/'):
                run_id = path.split('/api/research/backtests/')[-1]
                try:
                    run_id_int = int(run_id)
                except ValueError:
                    return error_response(400, 'bad_request', 'Run ID must be numeric')

                cur.execute("""
                    SELECT run_id, strategy_name, start_date AS date_start, end_date AS date_end,
                           total_return AS total_return_pct, sharpe_ratio AS sharpe_annualized,
                           max_drawdown AS max_drawdown_pct, win_rate,
                           num_trades AS total_trades,
                           NULL AS best_trade_pct, NULL AS worst_trade_pct, NULL AS avg_trade_pct,
                           NULL AS consecutive_wins, NULL AS consecutive_losses,
                           created_at, NULL AS notes
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
                    SELECT trade_id, symbol, NULL AS signal_date, entry_date, entry_price,
                           quantity AS entry_quantity, exit_date, exit_price,
                           profit_loss_percent AS profit_loss_pct,
                           NULL AS mfe_pct, NULL AS mae_pct
                    FROM backtest_trades
                    WHERE run_id = %s
                    ORDER BY entry_date DESC
                    LIMIT %s OFFSET %s
                """, (run_id_int, limit, offset))
                trades = cur.fetchall()

                cur.execute("""
                    SELECT COUNT(*) FROM backtest_trades WHERE run_id = %s
                """, (run_id_int,))
                total_trades_count = next(iter(dict(cur.fetchone() or {}).values()), 0)

                # Build response
                run_dict = dict(backtest)
                freshness = check_data_freshness(cur, 'backtest_runs', 'created_at', warning_days=7)
                return json_response(200, {
                    'run': run_dict,
                    'trades': [dict(t) for t in trades] if trades else [],
                    'trade_pagination': {'total': total_trades_count},
                    'data_freshness': freshness
                })
            return error_response(404, 'not_found', f'No research handler for {path}')
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'handle research')

