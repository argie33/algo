"""Route: signals"""

import logging
import re
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    error_response,
    handle_db_error,
    list_response,
    safe_json_serialize,
    safe_limit,
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
) -> Any:
    """Handle /api/signals/* endpoints."""
    try:
        if not params:
            params = {}
        if path in ["/api/signals", "/api/signals/stocks"] or path.startswith(
            ("/api/signals?", "/api/signals/stocks?")
        ):
            # Extract and validate limit parameter (optional, default 500)
            limit_list = params.get("limit", [])
            if not isinstance(limit_list, list):
                return error_response(400, "bad_request", "limit parameter must be a list")
            limit_str = limit_list[0] if limit_list else "500"
            try:
                limit = safe_limit(limit_str, max_val=10000)
            except (ValueError, TypeError) as e:
                return error_response(400, "bad_request", f"Invalid limit value: {e!s}")

            # Extract and validate timeframe parameter (optional, default 'daily')
            timeframe_list = params.get("timeframe", [])
            if not isinstance(timeframe_list, list):
                return error_response(400, "bad_request", "timeframe parameter must be a list")
            timeframe = timeframe_list[0] if timeframe_list else "daily"

            # Extract symbol filter parameter (optional, no default)
            symbol_list = params.get("symbol", [])
            if not isinstance(symbol_list, list):
                return error_response(400, "bad_request", "symbol parameter must be a list")
            symbol_filter = symbol_list[0] if symbol_list else None

            return _get_signals_stocks(cur, limit, timeframe, symbol_filter)
        elif path == "/api/signals/etf":
            # Extract and validate limit parameter (optional, default 500)
            limit_list = params.get("limit", [])
            if not isinstance(limit_list, list):
                return error_response(400, "bad_request", "limit parameter must be a list")
            limit_str = limit_list[0] if limit_list else "500"
            try:
                limit = safe_limit(limit_str, max_val=10000)
            except (ValueError, TypeError) as e:
                return error_response(400, "bad_request", f"Invalid limit value: {e!s}")

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
    cur: cursor, limit: int = 500, timeframe: str = "daily", symbol_filter: str | None = None
) -> Any:
    """Get stock trading signals from buy_sell_daily (primary signal source).

    EOD pipeline runs: prices → metrics → swing_trader_scores → buy_sell_daily.
    buy_sell_daily generates BUY/SELL/HOLD signals from technical indicators and
    quality scores. This endpoint sources from buy_sell_daily with price/sector data.
    """
    try:
        valid_timeframes = {"daily"}
        if timeframe.lower() not in valid_timeframes:
            return error_response(
                400,
                "bad_request",
                f'Unsupported timeframe: {timeframe}. Only "daily" is currently supported.',
            )

        cur.execute("SET LOCAL statement_timeout = '25000ms'")
        params: list[Any] = []
        symbol_clause = ""

        if symbol_filter:
            if not re.match(r"^[A-Z0-9\-\^]{1,10}$", symbol_filter.upper()):
                return error_response(400, "bad_request", "Invalid symbol format")
            symbol_clause = "AND b.symbol = %s"
            params.append(symbol_filter.upper())

        params.append(limit)

        cur.execute(
            f"""
            SELECT
                b.symbol,
                b.date,
                b.signal,
                'daily'::text AS timeframe,
                b.entry_quality_score,
                b.signal_quality_score,
                b.strength,
                TRUE AS pass_gates,
                NULL::text AS grade,
                b.reason,
                NULL::jsonb AS components,
                b.sma_50,
                b.sma_200,
                CASE t.weinstein_stage
                    WHEN 1 THEN 'Stage 1'
                    WHEN 2 THEN 'Stage 2 - Markup'
                    WHEN 3 THEN 'Stage 3 - Topping'
                    WHEN 4 THEN 'Stage 4'
                END AS market_stage,
                t.weinstein_stage AS stage_number,
                b.close,
                b.volume,
                -- CRITICAL FIX: Return NULL for missing sector (don't hide with 'Unknown')
                cp.sector,
                cp.industry,
                b.rsi,
                b.ema_21,
                b.atr,
                b.adx,
                b.mansfield_rs,
                b.rs_rating,
                b.volume_surge_pct,
                b.risk_reward_ratio,
                b.buylevel,
                b.stoplevel,
                b.base_type,
                b.base_length_days,
                b.profit_target_8pct,
                b.profit_target_20pct,
                b.profit_target_25pct,
                b.exit_trigger_1_price,
                b.exit_trigger_2_price,
                b.buy_zone_start,
                b.buy_zone_end,
                b.pivot_price,
                b.initial_stop,
                b.trailing_stop,
                b.sell_level,
                b.avg_volume_50d,
                b.signal_triggered_date,
                b.entry_price,
                b.signal_type,
                b.substage
            FROM buy_sell_daily b
            LEFT JOIN trend_template_data t ON t.symbol = b.symbol AND t.date = b.date
            LEFT JOIN company_profile cp ON cp.ticker = b.symbol
            WHERE b.date >= CURRENT_DATE - INTERVAL '90 days'
            {symbol_clause}
            ORDER BY b.date DESC, b.signal DESC, b.entry_quality_score DESC
            LIMIT %s
            """,
            tuple(params),
        )
        signals = cur.fetchall()
        freshness = check_data_freshness(cur, "buy_sell_daily", "date", warning_days=1)
        if not signals:
            return error_response(
                503,
                "data_unavailable",
                f"No trading signals available for requested symbols. "
                f"buy_sell_daily pipeline may not have run. {freshness}",
            )
        signals_result = list_response([safe_json_serialize(dict(s)) for s in signals], data_freshness=freshness)
        is_valid, error_msg = ResponseValidator.validate_endpoint_response("sig", signals_result)
        if not is_valid:
            logger.error(f"Endpoint response validation failed: {error_msg}")
            return error_response(500, "response_validation_error", error_msg or "Signals validation failed")
        return signals_result
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
def _get_signals_etf(cur: cursor, limit: int = 500) -> Any:
    """Get ETF market-regime signals from price_daily + trend_template_data.

    buy_sell_daily_etf and technical_data_daily were removed from the pipeline.
    This endpoint derives signals from Weinstein stage in trend_template_data:
    stage 2 = BUY, stage 3/4 = SELL, stage 1 = HOLD.
    """
    try:
        cur.execute("SET LOCAL statement_timeout = '15000ms'")
        etf_symbols = ["SPY", "QQQ", "IWM", "DIA", "EEM", "EFA"]
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
                NULL::numeric AS sma_50,
                NULL::numeric AS sma_200,
                CASE tt.weinstein_stage
                    WHEN 1 THEN 'Stage 1'
                    WHEN 2 THEN 'Stage 2 - Markup'
                    WHEN 3 THEN 'Stage 3 - Topping'
                    WHEN 4 THEN 'Stage 4'
                    ELSE 'unknown'
                END AS market_stage,
                COALESCE(cp.short_name, cp.long_name, pd.symbol) AS company_name
            FROM etf_price_daily pd
            INNER JOIN trend_template_data tt ON tt.symbol = pd.symbol AND tt.date = pd.date
            LEFT JOIN company_profile cp ON cp.ticker = pd.symbol
            WHERE pd.symbol = ANY(%s)
            AND pd.date >= CURRENT_DATE - INTERVAL '90 days'
            ORDER BY pd.date DESC, pd.symbol
            LIMIT %s
            """,
            (etf_symbols, limit),
        )
        signals = cur.fetchall()
        # Check freshness for both ETF price data and trend template data
        etf_freshness = check_data_freshness(cur, "etf_price_daily", "date", warning_days=1)
        trend_freshness = check_data_freshness(cur, "trend_template_data", "date", warning_days=1)
        if not signals:
            freshness_detail = f"etf_price_daily: {etf_freshness}; trend_template_data: {trend_freshness}"
            return error_response(
                503,
                "data_unavailable",
                f"No ETF market signals available. "
                f"ETF price_daily or trend_template_data pipeline may not have run. {freshness_detail}",
            )
        etf_signals_result = list_response(
            [safe_json_serialize(dict(s)) for s in signals], data_freshness=etf_freshness
        )
        is_valid, error_msg = ResponseValidator.validate_endpoint_response("sig", etf_signals_result)
        if not is_valid:
            logger.error(f"Endpoint response validation failed: {error_msg}")
            return error_response(500, "response_validation_error", error_msg)
        return etf_signals_result
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch ETF signals")
        return error_response(code, error_type, message)
