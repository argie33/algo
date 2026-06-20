"""Route: signals"""

import logging
import re
from typing import Dict, Optional

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    error_response,
    handle_db_error,
    list_response,
    safe_json_serialize,
    safe_limit,
)


logger = logging.getLogger(__name__)


def handle(
    cur,
    path: str,
    method: str,
    params: Dict,
    body: Dict | None = None,
    jwt_claims: Dict | None = None,
) -> Dict[Any, Any]:
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
            limit = safe_limit(limit_str or "500", max_val=10000)
            timeframe_list = params.get("timeframe", [])
            timeframe = timeframe_list[0] if timeframe_list else "daily"
            symbol_list = params.get("symbol", [])
            symbol_filter = symbol_list[0] if symbol_list else None
            return _get_signals_stocks(cur, limit, timeframe, symbol_filter)
        elif path == "/api/signals/etf":
            limit_list = params.get("limit", [])
            limit_str = limit_list[0] if limit_list else None
            limit = safe_limit(limit_str or "500", max_val=10000)
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
    """Get stock trading signals from buy_sell_daily (primary signal source).

    EOD pipeline runs: prices → metrics → swing_trader_scores → buy_sell_daily.
    buy_sell_daily generates BUY/SELL/HOLD signals from technical indicators and
    quality scores. This endpoint sources from buy_sell_daily with price/sector data.
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
                COALESCE(cp.sector, 'Unknown') AS sector,
                COALESCE(cp.industry, 'Unknown') AS industry,
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
                NULL::numeric AS sma_50,
                NULL::numeric AS sma_200,
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
