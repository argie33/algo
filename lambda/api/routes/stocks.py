"""Route: stocks"""

import logging
import re
from typing import Any, cast

import psycopg2
import psycopg2.errors
import psycopg2.extras
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    error_response,
    execute_with_timeout,
    handle_db_error,
    json_response,
    list_response,
    safe_json_serialize,
    safe_limit,
    safe_offset,
)

from shared_contracts.response_validator import ResponseValidator

logger = logging.getLogger(__name__)


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        parts = path.split("/")
        known_non_symbol_paths = (
            "deep-value",
            "screener",
            "search",
            "list",
            "watchlist",
        )
        symbol = parts[3] if len(parts) > 3 and parts[3] not in known_non_symbol_paths else None

        if symbol and path == f"/api/stocks/{symbol}":
            # Validate symbol format before using in query
            if not re.match(r"^[A-Z0-9\-\^]{1,10}$", symbol.upper()):
                return cast(dict[str, Any], error_response(400, "bad_request", "Invalid symbol format")  # type: ignore[no-any-return])
            cur.execute("SET LOCAL statement_timeout = '3000ms'")
            cur.execute(
                """
                SELECT ss.symbol, ss.security_name as company_name,
                       cp.sector, cp.industry, cp.website, cp.employees, cp.exchange
                FROM stock_symbols ss
                LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
                WHERE ss.symbol = %s
            """,
                (symbol.upper(),),
            )
            row = cur.fetchone()
            if row:
                stock_result = safe_json_serialize(dict(row))
                is_valid, error_msg = ResponseValidator.validate_endpoint_response("stocks", stock_result)
                if not is_valid:
                    logger.error(f"Endpoint response validation failed: {error_msg}")
                    return cast(dict[str, Any], error_response(500, "response_validation_error", error_msg)  # type: ignore[no-any-return])
                return cast(dict[str, Any], json_response(200, stock_result)  # type: ignore[no-any-return])
            return cast(dict[str, Any], error_response(404, "not_found", f"Stock {symbol} not found")  # type: ignore[no-any-return])

        if path == "/api/stocks/deep-value":
            limit = safe_limit(
                (params.get("limit", [None])[0] if params else None) or "200",
                max_val=1000,
            )
            # Fast check: return empty if financial data not loaded yet (table missing or empty)
            try:
                # Use adaptive timeout: 3s for quick existence check
                results = execute_with_timeout(
                    cur,
                    "SELECT 1 FROM value_metrics WHERE pe_ratio IS NOT NULL LIMIT 1",
                    timeout_sec=3,
                    max_attempts=1,
                )
                if not results:
                    return list_response([])  # type: ignore[no-any-return]
            except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
                logger.debug("[DEEP_VALUE] value_metrics table not found - financial data not loaded yet")
                return list_response([])  # type: ignore[no-any-return]
            except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
                logger.error(f"[DEEP_VALUE] Database error checking value_metrics: {type(e).__name__}: {e}")
                code, error_type, message = handle_db_error(e, "deep-value check")
                return cast(dict[str, Any], error_response(code, error_type, message)  # type: ignore[no-any-return])
            try:
                deep_value_query = (
                    """
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
                    vm.market_cap,
                    lp.current_price,
                    (lp.current_price IS NULL OR s52.high_52w IS NULL OR s52.low_52w IS NULL) AS _is_fallback,
                    (qm.symbol IS NULL OR (qm.roe IS NULL AND qm.operating_margin IS NULL AND qm.net_margin IS NULL)) AS _financial_data_unavailable,
                    ROUND((
                        sc.value_score * 0.5 +
                        sc.quality_score * 0.3 +
                        sc.growth_score * 0.2
                    )::numeric, 2) AS generational_score,
                    vm.pe_ratio AS trailing_pe,
                    vm.pb_ratio AS price_to_book,
                    vm.ps_ratio AS price_to_sales,
                    NULL::numeric AS ev_to_ebitda,
                    vm.peg_ratio AS peg_ratio,
                    vm.dividend_yield AS dividend_yield,
                    ROUND(qm.roe::numeric, 2) AS roe_pct,
                    ROUND(qm.operating_margin::numeric, 2) AS op_margin_pct,
                    ROUND(md.gross_margin_pct::numeric, 2) AS gross_margin_pct,
                    ROUND(qm.net_margin::numeric, 2) AS net_margin_pct,
                    ROUND(qm.roa::numeric, 2) AS roa_pct,
                    qm.debt_to_equity AS debt_to_equity,
                    qm.current_ratio AS current_ratio,
                    qm.quick_ratio AS quick_ratio,
                    qm.interest_coverage AS interest_coverage,
                    s52.high_52w AS high_52w,
                    s52.low_52w AS low_52w,
                    NULL::numeric AS high_3y,
                    ROUND(((s52.high_52w - lp.current_price) / NULLIF(s52.high_52w, 0) * 100)::numeric, 2) AS drop_from_52w_high_pct,
                    NULL::numeric AS drop_from_3y_high_pct,
                    sm.sector_median_pe AS sector_median_pe,
                    mm.market_median_pe AS market_median_pe,
                    ROUND(((sm.sector_median_pe - vm.pe_ratio) / NULLIF(sm.sector_median_pe, 0) * 100)::numeric, 2) AS discount_vs_sector_pe_pct,
                    ROUND(((mm.market_median_pe - vm.pe_ratio) / NULLIF(mm.market_median_pe, 0) * 100)::numeric, 2) AS discount_vs_market_pe_pct,
                    ROUND((lp.current_price / NULLIF(vm.pb_ratio, 0))::numeric, 2) AS intrinsic_value_per_share,
                    ROUND(gm.revenue_growth_3y::numeric, 2) AS revenue_growth_3y_pct,
                    ROUND(gm.eps_growth_3y::numeric, 2) AS eps_growth_3y_pct,
                    ROUND(gm.revenue_growth_1y::numeric, 2) AS revenue_growth_yoy_pct,
                    ROUND(((fg.fcf_cur - fg.fcf_pri) / NULLIF(ABS(fg.fcf_pri), 0) * 100)::numeric, 2) AS fcf_growth_yoy_pct,
                    NULL::numeric AS sustainable_growth_pct,
                    ROUND((md.op_margin_cur - md.op_margin_pri)::numeric, 2) AS op_margin_trend_pp,
                    ROUND((md.gross_margin_cur - md.gross_margin_pri)::numeric, 2) AS gross_margin_trend_pp,
                    ROUND((md.roe_cur - md.roe_pri)::numeric, 2) AS roe_trend_pp,
                    CASE
                        WHEN qm.roe >= 25 AND qm.operating_margin >= 15 THEN 'tier1'
                        WHEN qm.roe >= 20 AND qm.operating_margin >= 12 THEN 'tier2'
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
                """
                    % limit
                )

                # Execute with single attempt at 23s — complex multi-CTE query needs headroom.
                # Lambda timeout is 25s; provisioned concurrency keeps instance warm so no cold-start risk.
                # Migration 060 adds a covering index (symbol, date) INCLUDE (high, low) to speed 52w stats.
                rows = execute_with_timeout(cur, deep_value_query, timeout_sec=23, max_attempts=1)
                if rows:
                    freshness = check_data_freshness(cur, "price_daily", "date", warning_days=1)
                    deep_value_result = list_response(
                        [safe_json_serialize(dict(r)) for r in rows],
                        data_freshness=freshness,
                    )
                    is_valid, error_msg = ResponseValidator.validate_endpoint_response("stocks", deep_value_result)
                    if not is_valid:
                        logger.error(f"Endpoint response validation failed: {error_msg}")
                        return cast(dict[str, Any], error_response(500, "response_validation_error", error_msg)  # type: ignore[no-any-return])
                    return deep_value_result
                empty_result = list_response([])
                is_valid, error_msg = ResponseValidator.validate_endpoint_response("stocks", empty_result)
                if not is_valid:
                    logger.error(f"Endpoint response validation failed: {error_msg}")
                    return cast(dict[str, Any], error_response(500, "response_validation_error", error_msg)  # type: ignore[no-any-return])
                return empty_result
            except (
                psycopg2.errors.UndefinedTable,
                psycopg2.errors.UndefinedColumn,
            ) as e:
                logger.error(
                    f"Deep-value query failed - schema error: {type(e).__name__}: {e}",
                    extra={"operation": "deep-value"},
                )
                return cast(dict[str, Any], error_response(
                    503,
                    "schema_error",
                    "Database schema mismatch - please check RDS migrations",
                ))  # type: ignore[no-any-return]
            except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
                logger.error(
                    f"Deep-value query failed - database error: {type(e).__name__}: {e}",
                    extra={"operation": "deep-value"},
                )
                return cast(dict[str, Any], error_response(503, "connection_error", "Database connection failed - please retry")  # type: ignore[no-any-return])

        limit = safe_limit(
            params.get("limit", [None])[0] if params else None,
            max_val=50000,
            default=500,
        )
        offset = safe_offset(params.get("offset", [None])[0] if params else None)
        search = params.get("search", [None])[0] if params else None
        sector = params.get("sector", [None])[0] if params else None

        where_clauses = ["ss.symbol NOT LIKE '^%%'", "COALESCE(ss.etf, 'N') != 'Y'"]
        query_params = []

        if search:
            if len(search) > 200:
                return cast(dict[str, Any], error_response(400, "bad_request", "Search query too long (max 200 characters)")  # type: ignore[no-any-return])
            where_clauses.append("(ss.symbol ILIKE %s OR ss.security_name ILIKE %s)")
            query_params.extend([f"%{search}%", f"%{search}%"])
        if sector:
            where_clauses.append("cp.sector = %s")
            query_params.append(sector)

        where_sql = " AND ".join(where_clauses)
        query_params_with_limit = [*query_params, limit, offset]

        # Set timeout for main listing query to prevent hangs
        cur.execute("SET LOCAL statement_timeout = '8000ms'")
        cur.execute(
            """
            SELECT ss.symbol, COALESCE(ss.security_name, ss.symbol) as company_name,
                   COALESCE(cp.sector, 'Unknown') as sector,
                   COALESCE(cp.industry, 'Unknown') as industry,
                   ss.is_sp500
            FROM stock_symbols ss
            LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
            WHERE """
            + where_sql
            + """
            ORDER BY ss.symbol
            LIMIT %s OFFSET %s
        """,
            query_params_with_limit,
        )
        rows = cur.fetchall()

        # Set timeout for count query as well
        cur.execute("SET LOCAL statement_timeout = '5000ms'")
        cur.execute(
            """
            SELECT COUNT(*) FROM stock_symbols ss
            LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
            WHERE """
            + where_sql,
            query_params,
        )
        count_row = cur.fetchone()
        if count_row is None or len(count_row) == 0:
            raise ValueError("COUNT(*) query returned no result")
        total = count_row[0]

        stocks_list_result = {
            "items": [safe_json_serialize(dict(r)) for r in rows],
            "total": total,
        }
        is_valid, error_msg = ResponseValidator.validate_endpoint_response("stocks", stocks_list_result)
        if not is_valid:
            logger.error(f"Endpoint response validation failed: {error_msg}")
            return cast(dict[str, Any], error_response(500, "response_validation_error", error_msg)  # type: ignore[no-any-return])
        return cast(dict[str, Any], json_response(200, stocks_list_result)  # type: ignore[no-any-return])
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle stocks")
        return cast(dict[str, Any], error_response(code, error_type, message)  # type: ignore[no-any-return])
