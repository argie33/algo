"""Route: trades"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re
from datetime import datetime, timedelta, date, timezone

logger = logging.getLogger(__name__)

def error_response(code, typ, msg):
    return {"statusCode": code, "errorType": typ, "message": msg}

def success_response(data):
    return {"statusCode": 200, "data": data}

def list_response(items, total=None):
    return {"statusCode": 200, "items": items, "total": total or len(items)}

def _safe_limit(limit_str, max_val=50000, default=500):
    if not limit_str:
        return default
    try:
        return min(int(limit_str), max_val)
    except:
        return default

def _handle_trades(self, path: str, method: str, params: Dict) -> Dict:
        """Handle /api/trades and /api/trades/* endpoints."""
        try:
            if path == '/api/trades':
                limit_str = params.get('limit', [None])[0] if params else None
                limit = _safe_limit(limit_str, max_val=50000, default=50000)
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
                cur.execute(query, args)
                trades = cur.fetchall()
                # Count total trades
                count_query = "SELECT COUNT(*) FROM algo_trades WHERE 1=1"
                count_args = []
                if status_filter:
                    count_query += " AND status = %s"
                    count_args.append(status_filter)
                cur.execute(count_query, count_args)
                total = cur.fetchone()[0]
                return json_response(200, {'data': [dict(t) for t in trades], 'total': total})
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
                return json_response(200, dict(summary) if summary else {})
            return error_response(404, 'not_found', f'Unknown trade endpoint: {path}')
        except psycopg2.errors.UndefinedTable as e:
            logger.error(f'Required table not found: {e}', extra={'operation': 'handle trades'})
            return error_response(503, 'service_unavailable', 'Data pipeline loading')
        except psycopg2.errors.UndefinedColumn as e:
            logger.error(f'Column not found: {e}', extra={'operation': 'handle trades'})
            return error_response(503, 'service_unavailable', 'Data schema mismatch')
        except psycopg2.OperationalError as e:
            logger.error(f'Database connection error: {e}', extra={'operation': 'handle trades'})
            return error_response(503, 'service_unavailable', 'Database unavailable')
        except psycopg2.DatabaseError as e:
            logger.error(f'Database error: {e}', extra={'operation': 'handle trades', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Database query failed')
        except Exception as e:
            logger.error(f'Unexpected error: {e}', extra={'operation': 'handle trades', 'error_type': type(e).__name__})
            return error_response(500, 'internal_error', 'Failed to fetch trades')
            logger.error(f"Error in trades handler: {e}", exc_info=True)
            return error_response(500, 'internal_error', 'Failed to fetch trades')


