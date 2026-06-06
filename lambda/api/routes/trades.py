"""Route: trades"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict, Any, Optional, List
import logging, re, uuid
from datetime import datetime, timedelta, date, timezone
from .utils import error_response, success_response, list_response, json_response, safe_limit, safe_offset, handle_db_error, check_data_freshness, execute_with_timeout

logger = logging.getLogger(__name__)

def _check_admin_access(jwt_claims: Dict) -> bool:
    if not jwt_claims:
        return False
    return 'admin' in (jwt_claims.get('cognito:groups') or [])

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
        """Handle /api/trades and /api/trades/* endpoints."""
        try:
            if path == '/api/trades/manual' and method == 'POST':
                if not _check_admin_access(jwt_claims):
                    return error_response(403, 'forbidden', 'Admin access required')
                return _create_manual_trade(cur, body or {})
            if path == '/api/trades':
                if not _check_admin_access(jwt_claims):
                    return error_response(403, 'forbidden', 'Admin access required')
                limit_str = params.get('limit', [None])[0] if params else None
                limit = safe_limit(limit_str, max_val=5000, default=500)
                offset_str = params.get('offset', [None])[0] if params else None
                offset = safe_offset(offset_str)
                status_filter = params.get('status', [None])[0] if params else None

                # SECURITY FIX: Validate status filter against whitelist (enum validation)
                VALID_STATUSES = {'pending', 'open', 'closed', 'filled', 'cancelled', 'rejected'}
                if status_filter:
                    if status_filter.lower() not in VALID_STATUSES:
                        return error_response(400, 'bad_request', f'Invalid status value: {status_filter}')
                    status_filter = status_filter.lower()

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
                cur.execute("SET LOCAL statement_timeout = '5000ms'")
                cur.execute(query, args)
                trades = cur.fetchall()
                # Count total trades
                count_query = "SELECT COUNT(*) FROM algo_trades WHERE 1=1"
                count_args = []
                if status_filter:
                    count_query += " AND status = %s"
                    count_args.append(status_filter)
                cur.execute("SET LOCAL statement_timeout = '3000ms'")
                cur.execute(count_query, count_args)
                total = next(iter(dict(cur.fetchone() or {}).values()), 0)
                freshness = check_data_freshness(cur, 'algo_trades', 'created_at', warning_days=1)
                return json_response(200, {'items': [dict(t) for t in trades], 'total': total, 'data_freshness': freshness})
            elif path == '/api/trades/summary':
                if not _check_admin_access(jwt_claims):
                    return error_response(403, 'forbidden', 'Admin access required')
                cur.execute("SET LOCAL statement_timeout = '4000ms'")
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

def _create_manual_trade(cur, body: Dict) -> Dict:
    """POST /api/trades/manual — manually log a trade entry."""
    try:
        symbol = (body.get('symbol') or '').upper().strip()
        trade_type = (body.get('trade_type') or 'buy').lower()
        quantity = body.get('quantity')
        price = body.get('price')
        execution_date = body.get('execution_date') or date.today().isoformat()
        stop_loss = body.get('stop_loss_price')

        if not symbol:
            return error_response(400, 'bad_request', 'symbol is required')
        if not re.match(r'^[A-Z0-9\-\^]{1,10}$', symbol):
            return error_response(400, 'bad_request', 'Invalid symbol format')
        if trade_type not in ('buy', 'sell'):
            return error_response(400, 'bad_request', 'trade_type must be buy or sell')
        try:
            quantity = int(float(quantity))
            price = float(price)
        except (TypeError, ValueError):
            return error_response(400, 'bad_request', 'quantity and price must be numeric')
        if quantity <= 0 or price <= 0:
            return error_response(400, 'bad_request', 'quantity and price must be positive')

        trade_id = f"MANUAL-{uuid.uuid4().hex[:12].upper()}"
        trade_date = date.fromisoformat(execution_date)
        status = 'open' if trade_type == 'buy' else 'closed'

        cur.execute("""
            INSERT INTO algo_trades (
                trade_id, symbol, signal_date, trade_date, entry_price, entry_quantity,
                entry_reason, status, execution_mode, stop_loss_price, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            RETURNING id, trade_id
        """, (
            trade_id, symbol, trade_date, trade_date, price, quantity,
            f'manual_{trade_type}', status, 'manual',
            float(stop_loss) if stop_loss else None,
        ))
        row = cur.fetchone()
        return json_response(201, {'success': True, 'data': {'id': row['trade_id'], 'trade_id': row['trade_id']}})
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        return handle_db_error(e, logger, 'create manual trade')

