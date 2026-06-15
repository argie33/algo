"""Route: signals"""

import re
import psycopg2
import psycopg2.extras
import psycopg2.errors
import psycopg2.sql
from typing import Dict, Optional
import logging
from routes.utils import (
    error_response,
    list_response,
    safe_limit,
    handle_db_error,
    check_data_freshness,
    safe_json_serialize,
    db_route_handler,
)

logger = logging.getLogger(__name__)


def handle(
    cur,
    path: str,
    method: str,
    params: Dict,
    body: Dict = None,
    jwt_claims: Dict = None,
) -> Dict:
    """Handle /api/signals/* endpoints."""
    try:
        if not params:
            params = {}
        if (
            path in ["/api/signals", "/api/signals/stocks"]
            or path.startswith("/api/signals?")
            or path.startswith("/api/signals/stocks?")
        ):
            limit_list = params.get("limit", [])
            limit_str = limit_list[0] if limit_list else None
            limit = safe_limit(limit_str, max_val=10000, default=500)
            timeframe_list = params.get("timeframe", [])
            timeframe = timeframe_list[0] if timeframe_list else "daily"
            symbol_list = params.get("symbol", [])
            symbol_filter = symbol_list[0] if symbol_list else None
            return _get_signals_stocks(cur, limit, timeframe, symbol_filter)
        elif path == "/api/signals/etf":
            limit_list = params.get("limit", [])
            limit_str = limit_list[0] if limit_list else None
            limit = safe_limit(limit_str, max_val=10000, default=500)
            return _get_signals_etf(cur, limit)
        else:
            return error_response(404, "not_found", f"No signals handler for {path}")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle signals")
        return error_response(code, error_type, message)


@db_route_handler("fetch stock signals")
def _get_signals_stocks(
    cur, limit: int = 500, timeframe: str = "daily", symbol_filter: Optional[str] = None
) -> Dict:
    """Get stock trading signals from swing_trader_scores (primary signal source).

    buy_sell_daily was removed from both EOD and morning pipelines; orchestrator
    Phase 5 computes signals on-the-fly from price_daily. This endpoint now
    sources from swing_trader_scores + trend_template_data, which are actively
    populated by the pipeline.
    """
    try:
        VALID_TIMEFRAMES = {"daily"}
        if timeframe.lower() not in VALID_TIMEFRAMES:
            return error_response(
                400,
                "bad_request",
                f'Unsupported timeframe: {timeframe}. Only "daily" is currently supported.',
            )

        cur.execute("SET LOCAL statement_timeout = '25000ms'")
        params = []
        symbol_clause = ""

        if symbol_filter:
            if not re.match(r"^[A-Z0-9\-\^]{1,10}$", symbol_filter.upper()):
                return error_response(400, "bad_request", "Invalid symbol format")
            symbol_clause = "AND s.symbol = %s"
            params.append(symbol_filter.upper())

        params.append(limit)

        cur.execute(
            f"""
            SELECT
                s.symbol,
                s.date,
                'BUY'::text AS signal,
                'daily'::text AS timeframe,
                s.score AS entry_quality_score,
                s.score AS signal_quality_score,
                s.score AS strength,
                COALESCE((s.components->>'pass_gates')::boolean, false) AS pass_gates,
                s.components->>'grade' AS grade,
                s.components->>'fail_reason' AS reason,
                s.components AS components,
                t.sma_50,
                t.sma_200,
                CASE t.weinstein_stage
                    WHEN 1 THEN 'Stage 1'
                    WHEN 2 THEN 'Stage 2 - Markup'
                    WHEN 3 THEN 'Stage 3 - Topping'
                    WHEN 4 THEN 'Stage 4'
                END AS market_stage,
                t.weinstein_stage AS stage_number,
                p.close,
                p.volume,
                COALESCE(cp.sector, 'Unknown') AS sector,
                COALESCE(cp.industry, 'Unknown') AS industry,
                NULL::numeric AS rsi,
                NULL::numeric AS ema_21,
                NULL::numeric AS atr,
                NULL::numeric AS adx,
                NULL::numeric AS mansfield_rs,
                NULL::numeric AS rs_rating,
                NULL::numeric AS volume_surge_pct,
                NULL::numeric AS risk_reward_ratio,
                NULL::numeric AS buylevel,
                NULL::numeric AS stoplevel,
                NULL::text AS base_type,
                NULL::integer AS base_length_days,
                NULL::numeric AS profit_target_8pct,
                NULL::numeric AS profit_target_20pct,
                NULL::numeric AS profit_target_25pct,
                NULL::numeric AS exit_trigger_1_price,
                NULL::numeric AS exit_trigger_2_price,
                NULL::numeric AS buy_zone_start,
                NULL::numeric AS buy_zone_end,
                NULL::numeric AS pivot_price,
                NULL::numeric AS initial_stop,
                NULL::numeric AS trailing_stop,
                NULL::numeric AS sell_level,
                NULL::numeric AS avg_volume_50d,
                s.date AS signal_triggered_date,
                NULL::numeric AS entry_price,
                NULL::text AS signal_type,
                NULL::text AS substage
            FROM swing_trader_scores s
            LEFT JOIN trend_template_data t ON t.symbol = s.symbol AND t.date = s.date
            LEFT JOIN LATERAL (
                SELECT close, volume
                FROM price_daily
                WHERE symbol = s.symbol
                ORDER BY date DESC
                LIMIT 1
            ) p ON true
            LEFT JOIN company_profile cp ON cp.ticker = s.symbol
            WHERE s.date >= CURRENT_DATE - INTERVAL '90 days'
            {symbol_clause}
            ORDER BY s.date DESC, s.score DESC
            LIMIT %s
            """,
            tuple(params),
        )
        signals = cur.fetchall()
        freshness = check_data_freshness(cur, "swing_trader_scores", "date", warning_days=1)
        return list_response(
            [safe_json_serialize(dict(s)) for s in signals], data_freshness=freshness
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch stock signals")
        return error_response(code, error_type, message)


@db_route_handler("fetch ETF signals")
def _get_signals_etf(cur, limit: int = 500) -> Dict:
    """Get ETF market-regime signals from price_daily + trend_template_data.

    buy_sell_daily_etf and technical_data_daily were removed from the pipeline.
    This endpoint derives signals from Weinstein stage in trend_template_data:
    stage 2 = BUY, stage 3/4 = SELL, stage 1 = HOLD.
    """
    try:
        cur.execute("SET LOCAL statement_timeout = '15000ms'")
        etf_symbols = ['SPY', 'QQQ', 'IWM', 'DIA', 'EEM', 'EFA']
        cur.execute(
            """
            SELECT
                pd.symbol,
                pd.date,
                CASE
                    WHEN tt.weinstein_stage = 2 THEN 'BUY'
                    WHEN tt.weinstein_stage IN (3, 4) THEN 'SELL'
                    ELSE 'HOLD'
                END AS signal,
                COALESCE(tt.weinstein_stage::text, '—') AS strength,
                NULL::text AS reason,
                pd.close,
                NULL::numeric AS rsi,
                tt.sma_50,
                tt.sma_200,
                CASE tt.weinstein_stage
                    WHEN 1 THEN 'Stage 1'
                    WHEN 2 THEN 'Stage 2 - Markup'
                    WHEN 3 THEN 'Stage 3 - Topping'
                    WHEN 4 THEN 'Stage 4'
                    ELSE 'unknown'
                END AS market_stage,
                COALESCE(cp.short_name, cp.long_name, pd.symbol) AS company_name,
                (tt.symbol IS NULL) AS _is_fallback
            FROM etf_price_daily pd
            LEFT JOIN trend_template_data tt ON tt.symbol = pd.symbol AND tt.date = pd.date
            LEFT JOIN company_profile cp ON cp.ticker = pd.symbol
            WHERE pd.symbol = ANY(%s)
            AND pd.date >= CURRENT_DATE - INTERVAL '90 days'
            ORDER BY pd.date DESC, pd.symbol
            LIMIT %s
            """,
            (etf_symbols, limit),
        )
        signals = cur.fetchall()
        return list_response([safe_json_serialize(dict(s)) for s in signals])
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch ETF signals")
        return error_response(code, error_type, message)
