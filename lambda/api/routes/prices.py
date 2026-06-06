"""Route: prices"""
import psycopg2, psycopg2.extras, psycopg2.errors, psycopg2.sql
from typing import Dict
import logging
from .utils import error_response, list_response, json_response, handle_db_error, safe_limit, check_data_freshness, execute_with_timeout

logger = logging.getLogger(__name__)

_TABLE_MAP = {
    'daily': 'price_daily',
    'weekly': 'price_weekly',
    'monthly': 'price_monthly',
}
_ETF_TABLE_MAP = {
    'daily': 'etf_price_daily',
    'weekly': 'etf_price_weekly',
    'monthly': 'etf_price_monthly',
}

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
    try:
        parts = path.split('/')

        # /api/prices?symbols=AAPL,MSFT (simple query format - redirect to batch-history)
        if len(parts) == 3 and parts[2] in ['prices', 'prices?symbols']:
            symbols_raw = (params.get('symbols', [None])[0] if params else None) or ''
            if symbols_raw:
                # Delegate to batch-history handler logic
                symbols = [s.strip().upper() for s in symbols_raw.split(',') if s.strip()]
                if not symbols:
                    return error_response(400, 'bad_request', 'symbols parameter required')
                if len(symbols) > 20:
                    return error_response(400, 'bad_request', 'maximum 20 symbols per batch')
                for sym in symbols:
                    if not all(c.isalnum() or c in ('-', '.', '^') for c in sym):
                        return error_response(400, 'bad_request', f'Invalid symbol: {sym}')

                limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=252, default=30)
                timeframe = (params.get('timeframe', [None])[0] if params else None) or 'daily'
                table_name = _TABLE_MAP.get(timeframe, 'price_daily')
                etf_table_name = _ETF_TABLE_MAP.get(timeframe, 'etf_price_daily')

                # Set statement timeout for batch price queries (20s for non-blocking performance)
                cur.execute("SET LOCAL statement_timeout = '20000ms'")

                result = {sym: [] for sym in symbols}

                batch_query = psycopg2.sql.SQL("""
                    WITH ranked AS (
                        SELECT symbol, date, open, high, low, close, volume,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                        FROM {}
                        WHERE symbol = ANY(%s)
                    )
                    SELECT symbol, date, open, high, low, close, volume
                    FROM ranked
                    WHERE rn <= %s
                    ORDER BY symbol, date DESC
                """).format(psycopg2.sql.Identifier(table_name))
                cur.execute(batch_query, [symbols, limit])
                found_symbols = set()
                for row in cur.fetchall():
                    sym = row['symbol']
                    result[sym].append(dict(row))
                    found_symbols.add(sym)

                missing = [s for s in symbols if s not in found_symbols]
                if missing:
                    etf_query = psycopg2.sql.SQL("""
                        WITH ranked AS (
                            SELECT symbol, date, open, high, low, close, volume,
                                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                            FROM {}
                            WHERE symbol = ANY(%s)
                        )
                        SELECT symbol, date, open, high, low, close, volume
                        FROM ranked
                        WHERE rn <= %s
                        ORDER BY symbol, date DESC
                    """).format(psycopg2.sql.Identifier(etf_table_name))
                    cur.execute(etf_query, [missing, limit])
                    for row in cur.fetchall():
                        sym = row['symbol']
                        result[sym].append(dict(row))

                return json_response(200, {'symbols': result, 'limit': limit})
            else:
                return error_response(400, 'bad_request', 'symbols parameter required')

        # /api/prices/history/{symbol}
        if len(parts) >= 5 and parts[3] == 'history':
            symbol = parts[4].upper()
            if not symbol or not all(c.isalnum() or c in ('-', '.', '^') for c in symbol):
                return error_response(400, 'bad_request', 'Invalid symbol')

            limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=2000, default=252)
            timeframe = (params.get('timeframe', [None])[0] if params else None) or 'daily'
            days_str = params.get('days', [None])[0] if params else None

            table_name = _TABLE_MAP.get(timeframe, 'price_daily')

            where_parts = [psycopg2.sql.SQL("symbol = %s")]
            qparams = [symbol]

            if days_str:
                try:
                    days_int = max(1, min(int(days_str), 3650))
                    where_parts.append(psycopg2.sql.SQL("date >= CURRENT_DATE - INTERVAL %s"))
                    qparams.append(f"{days_int} days")
                except ValueError:
                    pass

            # Query stock price table first; fall back to ETF table if no results
            etf_table_name = _ETF_TABLE_MAP.get(timeframe, 'etf_price_daily')
            query = psycopg2.sql.SQL("""
                SELECT date, open, high, low, close, volume
                FROM {}
                WHERE {}
                ORDER BY date DESC
                LIMIT %s
            """).format(
                psycopg2.sql.Identifier(table_name),
                psycopg2.sql.SQL(" AND ").join(where_parts),
            )
            cur.execute(query, qparams + [limit])
            rows = cur.fetchall()
            used_table = table_name
            if not rows:
                # No data in stock table — try ETF table
                etf_query = psycopg2.sql.SQL("""
                    SELECT date, open, high, low, close, volume
                    FROM {}
                    WHERE {}
                    ORDER BY date DESC
                    LIMIT %s
                """).format(
                    psycopg2.sql.Identifier(etf_table_name),
                    psycopg2.sql.SQL(" AND ").join(where_parts),
                )
                cur.execute(etf_query, qparams + [limit])
                rows = cur.fetchall()
                used_table = etf_table_name
            freshness = check_data_freshness(cur, used_table, 'date', warning_days=1)
            return list_response([dict(r) for r in rows] if rows else [], data_freshness=freshness)

        # /api/prices/batch-history?symbols=SPY,QQQ,IWM&limit=30&timeframe=daily
        # Returns {symbols: {SYM: [{date, open, high, low, close, volume}, ...]}}
        # Replaces N concurrent per-symbol calls with one batch query.
        elif len(parts) >= 4 and parts[3] == 'batch-history':
            symbols_raw = (params.get('symbols', [None])[0] if params else None) or ''
            symbols = [s.strip().upper() for s in symbols_raw.split(',') if s.strip()]
            if not symbols:
                return error_response(400, 'bad_request', 'symbols parameter required')
            if len(symbols) > 20:
                return error_response(400, 'bad_request', 'maximum 20 symbols per batch')
            for sym in symbols:
                if not all(c.isalnum() or c in ('-', '.', '^') for c in sym):
                    return error_response(400, 'bad_request', f'Invalid symbol: {sym}')

            limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=252, default=30)
            timeframe = (params.get('timeframe', [None])[0] if params else None) or 'daily'
            table_name = _TABLE_MAP.get(timeframe, 'price_daily')
            etf_table_name = _ETF_TABLE_MAP.get(timeframe, 'etf_price_daily')

            result = {sym: [] for sym in symbols}

            batch_query = psycopg2.sql.SQL("""
                WITH ranked AS (
                    SELECT symbol, date, open, high, low, close, volume,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM {}
                    WHERE symbol = ANY(%s)
                )
                SELECT symbol, date, open, high, low, close, volume
                FROM ranked
                WHERE rn <= %s
                ORDER BY symbol, date DESC
            """).format(psycopg2.sql.Identifier(table_name))
            cur.execute(batch_query, [symbols, limit])
            found_symbols = set()
            for row in cur.fetchall():
                sym = row['symbol']
                result[sym].append(dict(row))
                found_symbols.add(sym)

            missing = [s for s in symbols if s not in found_symbols]
            if missing:
                etf_query = psycopg2.sql.SQL("""
                    WITH ranked AS (
                        SELECT symbol, date, open, high, low, close, volume,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                        FROM {}
                        WHERE symbol = ANY(%s)
                    )
                    SELECT symbol, date, open, high, low, close, volume
                    FROM ranked
                    WHERE rn <= %s
                    ORDER BY symbol, date DESC
                """).format(psycopg2.sql.Identifier(etf_table_name))
                cur.execute(etf_query, [missing, limit])
                for row in cur.fetchall():
                    sym = row['symbol']
                    result[sym].append(dict(row))

            return json_response(200, {'symbols': result, 'limit': limit})

        return error_response(404, 'not_found', f'No prices handler for {path}')
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        code, error_type, message = handle_db_error(e, 'handle prices')
            return error_response(code, error_type, message)
