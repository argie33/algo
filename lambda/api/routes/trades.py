"""Route: trades"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, safe_offset, handle_db_error, check_data_freshness
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

def handle(path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
        """Handle /api/trades and /api/trades/* endpoints."""
        try:
            if path == '/api/trades':
                limit_str = params.get('limit', [None])[0] if params else None
                limit = safe_limit(limit_str, max_val=50000, default=50000)
                offset_str = params.get('offset', [None])[0] if params else None
                offset = safe_offset(offset_str)
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
                cur.execute(query, args)
                trades = cur.fetchall()
                # Count total trades
                count_query = "SELECT COUNT(*) FROM algo_trades WHERE 1=1"
                count_args = []
                if status_filter:
                    count_query += " AND status = %s"
                    count_args.append(status_filter)
                cur.execute(count_query, count_args)
                total = next(iter(dict(cur.fetchone() or {}).values()), 0)
                freshness = check_data_freshness(cur, 'algo_trades', 'created_at', warning_days=1)
                return json_response(200, {'items': [dict(t) for t in trades], 'total': total, 'data_freshness': freshness})
            elif path == '/api/trades/summary':
                cur.execute("""
                    SELECT
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN exit_price > entry_price THEN 1 ELSE 0 END) as winning_trades,
                        COUNT(DISTINCT symbol) as unique_symbols,
                        SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_trades
                    FROM algo_trades
                """)
                summary = cur.fetchone()
                freshness = check_data_freshness(cur, 'algo_trades', 'created_at', warning_days=1)
                result = dict(summary) if summary else {}
                result['data_freshness'] = freshness
                return json_response(200, result)
            return error_response(404, 'not_found', f'Unknown trade endpoint: {path}')
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
            return handle_db_error(e, logger, 'handle trades')

