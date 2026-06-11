"""Route: stocks"""
import psycopg2, psycopg2.extras, psycopg2.errors
from typing import Dict
import logging
import re
from .utils import error_response, list_response, json_response, safe_limit, safe_offset, handle_db_error, check_data_freshness, execute_with_timeout, safe_json_serialize

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None, jwt_claims: Dict = None) -> Dict:
    try:
        parts = path.split('/')
        known_non_symbol_paths = ('deep-value', 'screener', 'search', 'list', 'watchlist')
        symbol = parts[3] if len(parts) > 3 and parts[3] not in known_non_symbol_paths else None

        if symbol and path == f'/api/stocks/{symbol}':
            # Validate symbol format before using in query
            if not re.match(r'^[A-Z0-9\-\^]{1,10}$', symbol.upper()):
                return error_response(400, 'bad_request', 'Invalid symbol format')
            cur.execute("SET LOCAL statement_timeout = '3000ms'")
            cur.execute("""
                SELECT ss.symbol, ss.security_name as company_name,
                       cp.sector, cp.industry, cp.website, cp.employees, cp.exchange
                FROM stock_symbols ss
                LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
                WHERE ss.symbol = %s
            """, (symbol.upper(),))
            row = cur.fetchone()
            if row:
                return json_response(200, safe_json_serialize(dict(row)))
            return error_response(404, 'not_found', f'Stock {symbol} not found')

        if path == '/api/stocks/deep-value':
            limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=1000, default=200)
            # Fast check: return empty if financial data not loaded yet (table missing or empty)
            try:
                # Use adaptive timeout: 3s for quick existence check
                results = execute_with_timeout(cur, "SELECT 1 FROM value_metrics WHERE pe_ratio IS NOT NULL LIMIT 1", timeout_sec=3, max_attempts=1)
                if not results:
                    return list_response([])
            except Exception:
                return list_response([])
            try:
                deep_value_query = """
                WITH value_stocks AS (
                    SELECT DISTINCT symbol FROM value_metrics WHERE pe_ratio IS NOT NULL
                ),
                max_date AS (SELECT date AS d FROM price_daily ORDER BY date DESC LIMIT 1),
                latest_prices AS (
                    SELECT pd.symbol, pd.close AS current_price
                    FROM price_daily pd
                    JOIN value_stocks vs ON pd.symbol = vs.symbol
                    WHERE pd.date = (SELECT d FROM max_date)
                ),
                stats_52w AS (
                    SELECT pd.symbol, MAX(pd.high) AS high_52w, MIN(pd.low) AS low_52w
                    FROM price_daily pd
                    JOIN value_stocks vs ON pd.symbol = vs.symbol
                    WHERE pd.date >= CURRENT_DATE - INTERVAL '52 weeks'
                    GROUP BY pd.symbol
                ),
                sector_medians AS (
                    SELECT cp.sector,
                           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY vm.pe_ratio) AS sector_median_pe
                    FROM value_metrics vm
                    JOIN company_profile cp ON cp.ticker = vm.symbol
                    WHERE vm.pe_ratio > 0 AND vm.pe_ratio < 200
                    GROUP BY cp.sector
                ),
                market_median AS (
                    SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pe_ratio) AS market_median_pe
                    FROM value_metrics
                    WHERE pe_ratio > 0 AND pe_ratio < 200
                ),
                income_ranked AS (
                    SELECT symbol, fiscal_year, gross_profit, revenue, operating_income, net_income,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_income_statement
                    WHERE symbol IN (SELECT symbol FROM value_stocks)
                ),
                balance_ranked AS (
                    SELECT symbol, stockholders_equity,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                    FROM annual_balance_sheet
                    WHERE symbol IN (SELECT symbol FROM value_stocks)
                ),
                margin_data AS (
                    SELECT
                        cur.symbol,
                        CASE WHEN cur.revenue > 0 AND cur.gross_profit IS NOT NULL
                             THEN cur.gross_profit / cur.revenue * 100 END AS gross_margin_pct,
                        CASE WHEN cur.revenue > 0 AND cur.operating_income IS NOT NULL
                             THEN cur.operating_income / cur.revenue * 100 END AS op_margin_cur,
                        CASE WHEN pri.revenue > 0 AND pri.operating_income IS NOT NULL
                             THEN pri.operating_income / pri.revenue * 100 END AS op_margin_pri,
                        CASE WHEN cur.revenue > 0 AND cur.gross_profit IS NOT NULL
                             THEN cur.gross_profit / cur.revenue * 100 END AS gross_margin_cur,
                        CASE WHEN pri.revenue > 0 AND pri.gross_profit IS NOT NULL
                             THEN pri.gross_profit / pri.revenue * 100 END AS gross_margin_pri,
                        CASE WHEN be.stockholders_equity > 0 AND cur.net_income IS NOT NULL
                             THEN cur.net_income / be.stockholders_equity * 100 END AS roe_cur,
                        CASE WHEN bp.stockholders_equity > 0 AND pri.net_income IS NOT NULL
                             THEN pri.net_income / bp.stockholders_equity * 100 END AS roe_pri
                    FROM income_ranked cur
                    LEFT JOIN income_ranked pri ON pri.symbol = cur.symbol AND pri.rn = 2
                    LEFT JOIN balance_ranked be ON be.symbol = cur.symbol AND be.rn = 1
                    LEFT JOIN balance_ranked bp ON bp.symbol = cur.symbol AND bp.rn = 2
                    WHERE cur.rn = 1
                ),
                fcf_data AS (
                    SELECT symbol,
                           MAX(CASE WHEN rn = 1 THEN free_cash_flow END) AS fcf_cur,
                           MAX(CASE WHEN rn = 2 THEN free_cash_flow END) AS fcf_pri
                    FROM (
                        SELECT symbol, free_cash_flow,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY fiscal_year DESC) AS rn
                        FROM annual_cash_flow
                        WHERE free_cash_flow IS NOT NULL
                          AND symbol IN (SELECT symbol FROM value_stocks)
                    ) t
                    GROUP BY symbol
                )
                SELECT
                    ss.symbol,
                    COALESCE(ss.security_name, ss.symbol) AS company_name,
                    COALESCE(cp.sector, 'Unknown') AS sector,
                    COALESCE(cp.industry, 'Unknown') AS industry,
                    cp.market_cap,
                    COALESCE(lp.current_price, 0) AS current_price,
                    ROUND((
                        COALESCE(sc.value_score, 0) * 0.5 +
                        COALESCE(sc.quality_score, 0) * 0.3 +
                        COALESCE(sc.growth_score, 0) * 0.2
                    )::numeric, 2) AS generational_score,
                    COALESCE(vm.pe_ratio, 0) AS trailing_pe,
                    COALESCE(vm.pb_ratio, 0) AS price_to_book,
                    COALESCE(vm.ps_ratio, 0) AS price_to_sales,
                    NULL::numeric AS ev_to_ebitda,
                    COALESCE(vm.peg_ratio, 0) AS peg_ratio,
                    COALESCE(vm.dividend_yield, 0) AS dividend_yield,
                    ROUND(COALESCE(qm.roe, 0)::numeric, 2) AS roe_pct,
                    ROUND(COALESCE(qm.operating_margin, 0)::numeric, 2) AS op_margin_pct,
                    ROUND(COALESCE(md.gross_margin_pct, 0)::numeric, 2) AS gross_margin_pct,
                    ROUND(COALESCE(qm.net_margin, 0)::numeric, 2) AS net_margin_pct,
                    ROUND(COALESCE(qm.roa, 0)::numeric, 2) AS roa_pct,
                    COALESCE(qm.debt_to_equity, 0) AS debt_to_equity,
                    COALESCE(qm.current_ratio, 0) AS current_ratio,
                    COALESCE(s52.high_52w, 0) AS high_52w,
                    COALESCE(s52.low_52w, 0) AS low_52w,
                    NULL::numeric AS high_3y,
                    ROUND(((COALESCE(s52.high_52w, 0) - lp.current_price) / NULLIF(COALESCE(s52.high_52w, 0), 0) * 100)::numeric, 2) AS drop_from_52w_high_pct,
                    NULL::numeric AS drop_from_3y_high_pct,
                    COALESCE(sm.sector_median_pe, 0) AS sector_median_pe,
                    COALESCE(mm.market_median_pe, 0) AS market_median_pe,
                    ROUND(((COALESCE(sm.sector_median_pe, 0) - COALESCE(vm.pe_ratio, 0)) / NULLIF(COALESCE(sm.sector_median_pe, 0), 0) * 100)::numeric, 2) AS discount_vs_sector_pe_pct,
                    ROUND(((COALESCE(mm.market_median_pe, 0) - COALESCE(vm.pe_ratio, 0)) / NULLIF(COALESCE(mm.market_median_pe, 0), 0) * 100)::numeric, 2) AS discount_vs_market_pe_pct,
                    ROUND((lp.current_price / NULLIF(COALESCE(vm.pb_ratio, 0), 0))::numeric, 2) AS intrinsic_value_per_share,
                    ROUND(((1 - COALESCE(vm.pb_ratio, 0)) * 100)::numeric, 2) AS margin_of_safety_pct,
                    ROUND(COALESCE(gm.revenue_growth_3y, 0)::numeric, 2) AS revenue_growth_3y_pct,
                    ROUND(COALESCE(gm.eps_growth_3y, 0)::numeric, 2) AS eps_growth_3y_pct,
                    ROUND(COALESCE(gm.revenue_growth_1y, 0)::numeric, 2) AS revenue_growth_yoy_pct,
                    ROUND(((COALESCE(fg.fcf_cur, 0) - COALESCE(fg.fcf_pri, 0)) / NULLIF(ABS(COALESCE(fg.fcf_pri, 0)), 0) * 100)::numeric, 2) AS fcf_growth_yoy_pct,
                    NULL::numeric AS sustainable_growth_pct,
                    ROUND((COALESCE(md.op_margin_cur, 0) - COALESCE(md.op_margin_pri, 0))::numeric, 2) AS op_margin_trend_pp,
                    ROUND((COALESCE(md.gross_margin_cur, 0) - COALESCE(md.gross_margin_pri, 0))::numeric, 2) AS gross_margin_trend_pp,
                    ROUND((COALESCE(md.roe_cur, 0) - COALESCE(md.roe_pri, 0))::numeric, 2) AS roe_trend_pp,
                    CASE
                        WHEN COALESCE(qm.roe, 0) >= 25 AND COALESCE(qm.operating_margin, 0) >= 15 THEN 'tier1'
                        WHEN COALESCE(qm.roe, 0) >= 20 AND COALESCE(qm.operating_margin, 0) >= 12 THEN 'tier2'
                        ELSE 'other'
                    END AS quality_rank
                FROM value_stocks vs
                JOIN stock_symbols ss ON ss.symbol = vs.symbol
                LEFT JOIN company_profile cp ON cp.ticker = vs.symbol
                LEFT JOIN latest_prices lp ON lp.symbol = vs.symbol
                LEFT JOIN stats_52w s52 ON s52.symbol = vs.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = vs.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = vs.symbol
                LEFT JOIN growth_metrics gm ON gm.symbol = vs.symbol
                LEFT JOIN stock_scores sc ON sc.symbol = vs.symbol
                LEFT JOIN sector_medians sm ON sm.sector = cp.sector
                LEFT JOIN margin_data md ON md.symbol = vs.symbol
                LEFT JOIN fcf_data fg ON fg.symbol = vs.symbol
                CROSS JOIN market_median mm
                ORDER BY generational_score DESC NULLS LAST
                LIMIT %s
                """ % limit

                # Execute with retry logic and exponential backoff on timeout
                rows = execute_with_timeout(cur, deep_value_query, timeout_sec=8, max_attempts=2, backoff_multiplier=1.5)
                if rows:
                    freshness = check_data_freshness(cur, 'price_daily', 'date', warning_days=1)
                    return list_response([safe_json_serialize(dict(r)) for r in rows], data_freshness=freshness)
                return list_response([])
            except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
                logger.error(f'Deep-value query failed - schema error: {type(e).__name__}: {e}', extra={'operation': 'deep-value'})
                return error_response(503, 'schema_error', 'Database schema mismatch - please check RDS migrations')
            except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
                logger.error(f'Deep-value query failed - database error: {type(e).__name__}: {e}', extra={'operation': 'deep-value'})
                return error_response(503, 'connection_error', 'Database connection failed - please retry')
            except Exception as e:
                logger.error(f'Deep-value query failed: {type(e).__name__}: {str(e)[:200]}', extra={'operation': 'deep-value'})
                return error_response(500, 'internal_error', f'Failed to fetch deep-value stocks: {type(e).__name__}')

        limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=50000, default=500)
        offset = safe_offset(params.get('offset', [None])[0] if params else None)
        search = params.get('search', [None])[0] if params else None
        sector = params.get('sector', [None])[0] if params else None

        where_clauses = ["ss.symbol NOT LIKE '^%%'", "COALESCE(ss.etf, 'N') != 'Y'"]
        query_params = []

        if search:
            where_clauses.append("(ss.symbol ILIKE %s OR ss.security_name ILIKE %s)")
            query_params.extend([f'%{search}%', f'%{search}%'])
        if sector:
            where_clauses.append("cp.sector = %s")
            query_params.append(sector)

        where_sql = " AND ".join(where_clauses)
        query_params_with_limit = query_params + [limit, offset]

        # Set timeout for main listing query to prevent hangs
        cur.execute("SET LOCAL statement_timeout = '8000ms'")
        cur.execute("""
            SELECT ss.symbol, COALESCE(ss.security_name, ss.symbol) as company_name,
                   COALESCE(cp.sector, 'Unknown') as sector,
                   COALESCE(cp.industry, 'Unknown') as industry,
                   ss.is_sp500
            FROM stock_symbols ss
            LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
            WHERE """ + where_sql + """
            ORDER BY ss.symbol
            LIMIT %s OFFSET %s
        """, query_params_with_limit)
        rows = cur.fetchall()

        # Set timeout for count query as well
        cur.execute("SET LOCAL statement_timeout = '5000ms'")
        cur.execute("""
            SELECT COUNT(*) FROM stock_symbols ss
            LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
            WHERE """ + where_sql, query_params)
        total = safe_json_serialize(dict(cur.fetchone())).get('count', 0)

        return json_response(200, {
            'items': [safe_json_serialize(dict(r)) for r in rows],
            'total': total,
        })
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        code, error_type, message = handle_db_error(e, 'handle stocks')
        return error_response(code, error_type, message)
