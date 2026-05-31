"""Route: stocks"""
import psycopg2, psycopg2.extras, psycopg2.errors
from typing import Dict
import logging
import re
from .utils import error_response, list_response, json_response, safe_limit, safe_offset, handle_db_error, check_data_freshness

logger = logging.getLogger(__name__)

def handle(cur, path: str, method: str, params: Dict, body: Dict = None) -> Dict:
    try:
        parts = path.split('/')
        symbol = parts[3] if len(parts) > 3 and parts[3] not in ('deep-value',) else None

        if symbol and path == f'/api/stocks/{symbol}':
            # Validate symbol format before using in query
            if not re.match(r'^[A-Z0-9\-\^]{1,10}$', symbol.upper()):
                return error_response(400, 'bad_request', 'Invalid symbol format')
            cur.execute("""
                SELECT ss.symbol, ss.security_name as company_name,
                       cp.sector, cp.industry, cp.website, cp.employees, cp.exchange
                FROM stock_symbols ss
                LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
                WHERE ss.symbol = %s
            """, (symbol.upper(),))
            row = cur.fetchone()
            if row:
                return json_response(200, dict(row))
            return error_response(404, 'not_found', f'Stock {symbol} not found')

        if path == '/api/stocks/deep-value':
            limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=1000, default=600)
            # Fast check: return empty if no financial data loaded yet
            cur.execute("SELECT 1 FROM value_metrics WHERE pe_ratio IS NOT NULL LIMIT 1")
            if not cur.fetchone():
                return list_response([])
            cur.execute("SET statement_timeout TO '28s'")
            cur.execute("""
                WITH value_stocks AS (
                    SELECT DISTINCT symbol FROM value_metrics WHERE pe_ratio IS NOT NULL
                ),
                max_date AS (SELECT MAX(date) AS d FROM price_daily),
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
                stats_3y AS (
                    SELECT pd.symbol, MAX(pd.high) AS high_3y
                    FROM price_daily pd
                    JOIN value_stocks vs ON pd.symbol = vs.symbol
                    WHERE pd.date >= CURRENT_DATE - INTERVAL '3 years'
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
                    ss.security_name AS company_name,
                    cp.sector,
                    cp.industry,
                    km.market_cap,
                    lp.current_price,
                    ROUND((
                        COALESCE(sc.value_score, 0) * 0.5 +
                        COALESCE(sc.quality_score, 0) * 0.3 +
                        COALESCE(sc.growth_score, 0) * 0.2
                    )::numeric, 2) AS generational_score,
                    vm.pe_ratio AS trailing_pe,
                    vm.pb_ratio AS price_to_book,
                    vm.ps_ratio AS price_to_sales,
                    NULL::numeric AS ev_to_ebitda,
                    vm.peg_ratio,
                    vm.dividend_yield,
                    ROUND(qm.roe::numeric, 2) AS roe_pct,
                    ROUND(qm.operating_margin::numeric, 2) AS op_margin_pct,
                    ROUND(md.gross_margin_pct::numeric, 2) AS gross_margin_pct,
                    ROUND(qm.net_margin::numeric, 2) AS net_margin_pct,
                    ROUND(qm.roa::numeric, 2) AS roa_pct,
                    qm.debt_to_equity,
                    qm.current_ratio,
                    s52.high_52w,
                    s52.low_52w,
                    s3y.high_3y,
                    ROUND(((s52.high_52w - lp.current_price) / NULLIF(s52.high_52w, 0) * 100)::numeric, 2) AS drop_from_52w_high_pct,
                    ROUND(((s3y.high_3y - lp.current_price) / NULLIF(s3y.high_3y, 0) * 100)::numeric, 2) AS drop_from_3y_high_pct,
                    sm.sector_median_pe,
                    mm.market_median_pe,
                    ROUND(((sm.sector_median_pe - vm.pe_ratio) / NULLIF(sm.sector_median_pe, 0) * 100)::numeric, 2) AS discount_vs_sector_pe_pct,
                    ROUND(((mm.market_median_pe - vm.pe_ratio) / NULLIF(mm.market_median_pe, 0) * 100)::numeric, 2) AS discount_vs_market_pe_pct,
                    ROUND((lp.current_price / NULLIF(vm.pb_ratio, 0))::numeric, 2) AS intrinsic_value_per_share,
                    ROUND(((1 - vm.pb_ratio) * 100)::numeric, 2) AS margin_of_safety_pct,
                    ROUND(gm.revenue_growth_3y::numeric, 2) AS revenue_growth_3y_pct,
                    ROUND(gm.eps_growth_3y::numeric, 2) AS eps_growth_3y_pct,
                    ROUND(gm.revenue_growth_1y::numeric, 2) AS revenue_growth_yoy_pct,
                    ROUND(((fg.fcf_cur - fg.fcf_pri) / NULLIF(ABS(fg.fcf_pri), 0) * 100)::numeric, 2) AS fcf_growth_yoy_pct,
                    NULL::numeric AS sustainable_growth_pct,
                    ROUND((md.op_margin_cur - md.op_margin_pri)::numeric, 2) AS op_margin_trend_pp,
                    ROUND((md.gross_margin_cur - md.gross_margin_pri)::numeric, 2) AS gross_margin_trend_pp,
                    ROUND((md.roe_cur - md.roe_pri)::numeric, 2) AS roe_trend_pp
                FROM stock_symbols ss
                LEFT JOIN company_profile cp ON cp.ticker = ss.symbol
                LEFT JOIN key_metrics km ON km.symbol = ss.symbol
                LEFT JOIN latest_prices lp ON lp.symbol = ss.symbol
                LEFT JOIN stats_52w s52 ON s52.symbol = ss.symbol
                LEFT JOIN stats_3y s3y ON s3y.symbol = ss.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = ss.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = ss.symbol
                LEFT JOIN growth_metrics gm ON gm.symbol = ss.symbol
                LEFT JOIN stock_scores sc ON sc.symbol = ss.symbol
                LEFT JOIN sector_medians sm ON sm.sector = cp.sector
                LEFT JOIN margin_data md ON md.symbol = ss.symbol
                LEFT JOIN fcf_data fg ON fg.symbol = ss.symbol
                CROSS JOIN market_median mm
                WHERE ss.symbol NOT LIKE '^%%'
                ORDER BY generational_score DESC NULLS LAST
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
            freshness = check_data_freshness(cur, 'price_daily', 'date', warning_days=1)
            return list_response([dict(r) for r in rows], data_freshness=freshness)

        limit = safe_limit(params.get('limit', [None])[0] if params else None, max_val=50000, default=500)
        offset = safe_offset(params.get('offset', [None])[0] if params else None)
        search = params.get('search', [None])[0] if params else None
        sector = params.get('sector', [None])[0] if params else None

        where_clauses = ["ss.symbol NOT LIKE '^%%'"]
        query_params = []

        if search:
            where_clauses.append("(ss.symbol ILIKE %s OR ss.security_name ILIKE %s)")
            query_params.extend([f'%{search}%', f'%{search}%'])
        if sector:
            where_clauses.append("cp.sector = %s")
            query_params.append(sector)

        where_sql = " AND ".join(where_clauses)
        query_params_with_limit = query_params + [limit, offset]

        cur.execute("""
            SELECT ss.symbol, ss.security_name as company_name,
                   cp.sector, cp.industry,
                   ss.is_sp500
            FROM stock_symbols ss
            LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
            WHERE """ + where_sql + """
            ORDER BY ss.symbol
            LIMIT %s OFFSET %s
        """, query_params_with_limit)
        rows = cur.fetchall()

        cur.execute("""
            SELECT COUNT(*) FROM stock_symbols ss
            LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
            WHERE """ + where_sql, query_params)
        total = dict(cur.fetchone()).get('count', 0)

        return json_response(200, {
            'items': [dict(r) for r in rows],
            'total': total,
        })
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        return handle_db_error(e, logger, 'handle stocks')
