"""Route: market"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
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
    execute_with_timeout,
    json_response,
    list_response,
    raise_api_error,
    raise_db_error,
    safe_json_serialize,
)

from shared_contracts.response_validator import ResponseValidator
from utils.validation import safe_float

logger = logging.getLogger(__name__)


def _rollback_savepoint(cur: cursor, name: str) -> None:
    """Consolidate savepoint rollback error handling."""
    try:
        cur.execute(f"ROLLBACK TO SAVEPOINT {name}")
        cur.execute(f"RELEASE SAVEPOINT {name}")
    except (psycopg2.OperationalError, psycopg2.DatabaseError) as sp_err:
        logger.debug(f"[SAVEPOINT_ROLLBACK] Error rolling back {name}: {type(sp_err).__name__}")


def _handle_market_status(cur: cursor) -> Any:
    """Handle /api/market and /api/market/status endpoints."""
    cur.execute("SET LOCAL statement_timeout = '5000ms'")
    cur.execute("""
        SELECT date, market_trend, market_stage, advance_decline_ratio,
                   new_highs_count, new_lows_count, vix_level, put_call_ratio
        FROM market_health_daily
        ORDER BY date DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        raise_api_error(503, "no_data", "Market status data not yet available")

    result = safe_json_serialize(dict(row))

    # Add freshness check
    freshness = check_data_freshness(cur, "market_health_daily", "date", warning_days=1)

    is_valid, error_msg = ResponseValidator.validate_endpoint_response("market/status", result)
    if not is_valid:
        logger.error(f"Market status response validation failed: {error_msg}")
        raise_api_error(500, "response_validation_error", error_msg or "Market status validation failed")

    return json_response(200, result, data_freshness=freshness)


def _handle_breadth(cur: cursor) -> Any:
    """Handle /api/market/breadth endpoint."""
    # Compute A/D per day using a self-join on consecutive trading dates.
    # Self-join is faster than LAG window over 35 days x 9000 symbols.
    # Uses retry logic with exponential backoff to handle transient timeouts
    # when DB is under heavy write load from loaders.
    breadth = []
    freshness = {}

    # MATERIALIZED CTEs force one evaluation each; explicit NOT LIKE on y lets
    # PostgreSQL use the idx_price_daily_date_symbol partial index for both joins.
    breadth_query = """
        WITH trading_dates AS MATERIALIZED (
            SELECT DISTINCT date
            FROM price_daily
            WHERE date >= CURRENT_DATE - INTERVAL '25 days'
            ORDER BY date DESC LIMIT 12
        ),
        date_pairs AS MATERIALIZED (
            SELECT d1.date AS d, MAX(d2.date) AS prev_d
            FROM trading_dates d1
            JOIN trading_dates d2 ON d2.date < d1.date
            GROUP BY d1.date
        )
        SELECT
            dp.d AS date,
            COUNT(*) FILTER (WHERE t.close > y.close) AS advances,
            COUNT(*) FILTER (WHERE t.close < y.close) AS declines,
            COUNT(*) FILTER (WHERE t.close = y.close) AS unchanged,
            COUNT(t.symbol) AS total
        FROM date_pairs dp
        JOIN price_daily t ON t.date = dp.d
            AND t.symbol NOT LIKE '^%' AND t.close IS NOT NULL
        JOIN price_daily y ON y.date = dp.prev_d AND y.symbol = t.symbol
            AND y.symbol NOT LIKE '^%' AND y.close IS NOT NULL
        GROUP BY dp.d
        ORDER BY dp.d DESC
        LIMIT 10
    """

    # 20s timeout — Lambda is 25s, APIGW is 29s; single attempt avoids double-hit.
    try:
        breadth = execute_with_timeout(cur, breadth_query, timeout_sec=20, max_attempts=1)
    except psycopg2.errors.QueryCanceled as e:
        logger.error(f"[MARKET_BREADTH] Query timeout: {type(e).__name__}: {e}")
        raise_api_error(504, "timeout", "Market breadth data query exceeded timeout")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        logger.error(f"[MARKET_BREADTH] Database error: {type(e).__name__}: {e}")
        raise_db_error(e, "market breadth query")

    if breadth:
        # Only fetch freshness if query succeeded
        try:
            freshness = check_data_freshness(cur, "price_daily", "date", warning_days=1)
        except (
            psycopg2.errors.UndefinedTable,
            psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError,
            psycopg2.DatabaseError,
        ) as e:
            raise RuntimeError(f"Market breadth freshness check failed - cannot verify data: {e}") from e

    return list_response(
        [safe_json_serialize(dict(b)) for b in breadth],
        data_freshness=freshness,
    )


def _handle_technicals(cur: cursor) -> Any:
    """Handle /api/market/technicals endpoint."""
    try:
        cur.execute("SET LOCAL statement_timeout = '3000ms'")
        rows = execute_with_timeout(
            cur,
            """
            SELECT date, advance_decline_ratio, new_highs_count, new_lows_count,
                       up_volume_percent, breadth_momentum_10d,
                       vix_level, put_call_ratio, market_trend, market_stage
            FROM market_health_daily
            ORDER BY date DESC
            LIMIT 1
        """,
            timeout_sec=3,
        )
    except psycopg2.errors.QueryCanceled as e:
        logger.error(f"[MARKET_TECHNICALS] Query timeout: {type(e).__name__}: {e}")
        raise_api_error(504, "timeout", "Market technicals data query exceeded timeout")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        logger.error(f"[MARKET_TECHNICALS] Database error: {type(e).__name__}: {e}")
        raise_db_error(e, "market technicals query")

    if not rows:
        raise RuntimeError("No market technicals data available")
    base = safe_json_serialize(dict(rows[0]))

    # Compute today's advancing/declining counts from price_daily.
    # OPTIMIZATION: Use date-based index for faster filtering
    try:
        cur.execute("SAVEPOINT technicals_breadth")
        cur.execute("SET LOCAL statement_timeout = '3000ms'")
        breadth_query = """
            WITH latest AS (
                SELECT date AS d FROM price_daily
                WHERE close IS NOT NULL AND symbol NOT LIKE '^%'
                ORDER BY date DESC LIMIT 1
            ),
            prev_day AS (
                SELECT date AS d FROM price_daily
                WHERE date < (SELECT d FROM latest)
                      AND close IS NOT NULL AND symbol NOT LIKE '^%'
                ORDER BY date DESC LIMIT 1
            )
            SELECT
                COUNT(*) FILTER (WHERE t.close > y.close) AS advancing,
                COUNT(*) FILTER (WHERE t.close < y.close) AS declining,
                COUNT(*) FILTER (WHERE t.close = y.close) AS unchanged,
                COUNT(t.symbol) AS total_stocks
            FROM price_daily t
            JOIN price_daily y ON t.symbol = y.symbol
            WHERE t.date = (SELECT d FROM latest)
              AND y.date = (SELECT d FROM prev_day)
              AND t.close IS NOT NULL
              AND y.close IS NOT NULL
        """
        breadth_rows = execute_with_timeout(cur, breadth_query, timeout_sec=3)
        cur.execute("RELEASE SAVEPOINT technicals_breadth")
        if not breadth_rows:
            logger.critical("[TECHNICALS_BREADTH] No breadth data available — market health calculation incomplete")
            raise RuntimeError(
                "Critical market breadth data unavailable. "
                "Market breadth (advancing/declining counts) required for complete market health assessment. "
                "Cannot proceed with incomplete market data."
            )
        else:
            base["breadth"] = dict(breadth_rows[0])
    except psycopg2.errors.QueryCanceled as e:
        _rollback_savepoint(cur, "technicals_breadth")
        raise RuntimeError(f"Market technicals breadth calculation timed out: {e}") from e
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        _rollback_savepoint(cur, "technicals_breadth")
        raise RuntimeError(f"Market technicals breadth query failed: {e}") from e

    # Build 30-day A/D line history (formerly labeled mcclellan_oscillator)
    try:
        cur.execute("SET LOCAL statement_timeout = '3000ms'")
        cur.execute("""
            SELECT date,
                   (factors->'ad_line'->>'value')::float AS advance_decline_line
            FROM market_exposure_daily
            WHERE date >= CURRENT_DATE - INTERVAL '35 days'
                  AND factors IS NOT NULL
                  AND factors->'ad_line' IS NOT NULL
                  AND (factors->'ad_line'->>'value') IS NOT NULL
            ORDER BY date DESC
            LIMIT 30
        """)
        adrows = cur.fetchall()
        base["mcclellan_oscillator"] = [safe_json_serialize(dict(r)) for r in adrows]
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        psycopg2.errors.QueryCanceled,
    ) as e:
        logger.error(f"[MCCLELLAN] Database error - McClellan oscillator unavailable: {type(e).__name__}: {e}")
        return error_response(
            503,
            "mcclellan_unavailable",
            f"McClellan oscillator calculation failed: {type(e).__name__}",
        )

    freshness = check_data_freshness(cur, "market_health_daily", "date", warning_days=1)
    return json_response(200, base, data_freshness=freshness)


def _handle_top_movers(cur: cursor) -> Any:
    """Handle /api/market/top-movers endpoint."""
    movers = []
    gainers = []
    losers = []
    try:
        cur.execute("SAVEPOINT top_movers")
        cur.execute("SET LOCAL statement_timeout = '8s'")
        # OPTIMIZATION: Simplified query with better index usage
        # Pre-filter at lower level to avoid joining all symbols
        cur.execute("""
            WITH latest_d AS (
                SELECT date AS d FROM price_daily
                WHERE close IS NOT NULL
                ORDER BY date DESC LIMIT 1
            ),
            prev_d AS (
                SELECT date AS d FROM price_daily
                WHERE date < (SELECT d FROM latest_d)
                      AND close IS NOT NULL
                ORDER BY date DESC LIMIT 1
            ),
            today AS (
                SELECT symbol, close
                FROM price_daily
                WHERE date = (SELECT d FROM latest_d)
                      AND symbol NOT LIKE '^%'
                      AND close > 0
            ),
            yesterday AS (
                SELECT symbol, close
                FROM price_daily
                WHERE date = (SELECT d FROM prev_d)
                      AND symbol NOT LIKE '^%'
                      AND close > 0
            )
            SELECT t.symbol, COALESCE(ss.security_name, t.symbol) AS security_name,
                   ROUND(((t.close - y.close) / y.close * 100)::numeric, 2) as pct_change
            FROM today t
            INNER JOIN yesterday y ON t.symbol = y.symbol
            LEFT JOIN stock_symbols ss ON t.symbol = ss.symbol
                                          AND (ss.etf IS NULL OR ss.etf != 'Y')
            ORDER BY ABS(t.close - y.close) / y.close DESC
            LIMIT 40
        """)
        movers = cur.fetchall()
        cur.execute("RELEASE SAVEPOINT top_movers")
    except psycopg2.errors.QueryCanceled as e:
        logger.warning(f"[TOP_MOVERS] Query timeout: {type(e).__name__}")
        _rollback_savepoint(cur, "top_movers")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        logger.warning(f"[TOP_MOVERS] Database error: {type(e).__name__}")
        _rollback_savepoint(cur, "top_movers")

    if not movers:
        raise_api_error(503, "no_data", "Top movers data not yet available")

    items = [safe_json_serialize(dict(m)) for m in movers]
    valid_items = []
    invalid_count = 0
    for m in items:
        pct_val = safe_float(m.get("pct_change"), default=None)
        if pct_val is not None:
            m["pct_change"] = pct_val
            valid_items.append(m)
        else:
            invalid_count += 1

    if not valid_items:
        raise_api_error(503, "no_data", "Top movers data validation failed - no valid price change data")

    if invalid_count > 0:
        logger.warning(
            f"[TOP_MOVERS] Filtered {invalid_count} items with missing pct_change; showing {len(valid_items)} valid items"
        )

    gainers = sorted(
        [m for m in valid_items if m["pct_change"] >= 0],
        key=lambda x: -x["pct_change"],
    )[:10]
    losers = sorted(
        [m for m in valid_items if m["pct_change"] < 0],
        key=lambda x: x["pct_change"],
    )[:10]
    return json_response(200, {"gainers": gainers, "losers": losers, "items": valid_items})


def _handle_distribution_days(cur: cursor) -> Any:
    """Handle /api/market/distribution-days endpoint."""
    dist_index_names = {
        "^GSPC": "S&P 500",
        "^IXIC": "Nasdaq Composite",
        "^NYA": "NYSE Composite",
        "^DJI": "Dow Jones",
        "^RUT": "Russell 2000",
    }
    try:
        cur.execute("SAVEPOINT dist_days")
        cur.execute("SET LOCAL statement_timeout = '15s'")  # Complex window function query
        cur.execute("""
            WITH recent_sessions AS (
                SELECT symbol, date, close, volume,
                       LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS prev_close
                FROM price_daily
                WHERE symbol IN ('^GSPC', '^IXIC', '^NYA', '^DJI')
                      AND date >= CURRENT_DATE - INTERVAL '35 days'
            ),
            volume_window AS (
                SELECT symbol, date, close, volume, prev_close,
                       AVG(volume) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN 50 PRECEDING AND 1 PRECEDING) AS avg_vol
                FROM recent_sessions
            )
            SELECT symbol, date, (CURRENT_DATE - date)::INTEGER AS days_ago,
                       ROUND(((close - prev_close) / NULLIF(prev_close, 0) * 100)::NUMERIC, 2) AS change_pct,
                       ROUND((volume::NUMERIC / NULLIF(avg_vol, 0))::NUMERIC, 2) AS volume_ratio
            FROM volume_window
            WHERE prev_close IS NOT NULL
                  AND close < prev_close * 0.998
                  AND (avg_vol IS NULL OR volume > avg_vol * 1.01)
            ORDER BY symbol, date DESC
        """)
        rows = cur.fetchall()
        by_sym: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            r = dict(row)
            sym = r["symbol"]
            if sym not in by_sym:
                by_sym[sym] = []
            by_sym[sym].append(
                {
                    "date": str(r["date"]),
                    "change_pct": (float(r["change_pct"]) if r["change_pct"] is not None else None),
                    "volume_ratio": (float(r["volume_ratio"]) if r["volume_ratio"] is not None else None),
                    "days_ago": r["days_ago"],
                }
            )
        result = {}
        for sym, days in by_sym.items():
            count = len(days)
            signal = "DANGER" if count >= 5 else ("CAUTION" if count >= 3 else "WATCH" if count >= 1 else "NORMAL")
            result[sym] = {
                "name": dist_index_names.get(sym, sym),
                "count": count,
                "signal": signal,
                "days": days,
            }
        cur.execute("RELEASE SAVEPOINT dist_days")
        return json_response(200, result)
    except (
        psycopg2.errors.QueryCanceled,
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        _rollback_savepoint(cur, "dist_days")
        logger.error(f"[DIST_DAYS] Error: {type(e).__name__}: {e}")
        raise_db_error(e, "distribution days query")
        raise  # unreachable — raise_db_error is NoReturn


def _handle_seasonality(cur: cursor) -> Any:
    """Handle /api/market/seasonality endpoint."""
    # Seasonality tables are market-wide aggregates (SPY-based)
    monthly_data: list[dict[str, Any]] = []
    best_month: dict[str, Any] | None = None
    worst_month: dict[str, Any] | None = None
    cur.execute("SET LOCAL statement_timeout = '2000ms'")
    try:
        cur.execute("""
            SELECT month, month_name, avg_return, best_return, worst_return,
                   winning_years, losing_years, years_counted
            FROM seasonality_monthly_stats
            ORDER BY month
        """)
        monthly_rows = cur.fetchall()
        for r in monthly_rows:
            r_dict = dict(r)
            monthly_data.append(r_dict)
            avg_ret = safe_float(r_dict.get("avg_return"), default=None)
            if avg_ret is not None:
                best_ret = safe_float(best_month.get("avg_return"), default=None) if best_month else None
                worst_ret = safe_float(worst_month.get("avg_return"), default=None) if worst_month else None
                if best_ret is None or avg_ret > best_ret:
                    best_month = r_dict
                if worst_ret is None or avg_ret < worst_ret:
                    worst_month = r_dict
    except psycopg2.errors.QueryCanceled as e:
        logger.error(f"[SEASONALITY] Monthly query timeout: {type(e).__name__}")
        raise_api_error(504, "timeout", "Seasonality data query exceeded timeout")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[SEASONALITY] Monthly query error: {type(e).__name__}")
        raise_db_error(e, "seasonality monthly query")

    dow_data: list[dict[str, Any]] = []
    best_dow: dict[str, Any] | None = None
    worst_dow: dict[str, Any] | None = None
    try:
        cur.execute("""
            SELECT day, day_num, avg_return, win_rate, days_counted
            FROM seasonality_day_of_week
            ORDER BY day_num
        """)
        dow_rows = cur.fetchall()
        for r in dow_rows:
            r_dict = dict(r)
            if "day" not in r_dict or r_dict["day"] is None:
                raise ValueError(f"[SEASONALITY] Day-of-week record missing 'day' field: {list(r_dict.keys())}")
            dow_data.append(r_dict)
            avg_ret = safe_float(r_dict.get("avg_return"), default=None)
            if avg_ret is not None:
                best_ret = safe_float(best_dow.get("avg_return"), default=None) if best_dow else None
                worst_ret = safe_float(worst_dow.get("avg_return"), default=None) if worst_dow else None
                if best_ret is None or avg_ret > best_ret:
                    best_dow = r_dict
                if worst_ret is None or avg_ret < worst_ret:
                    worst_dow = r_dict
    except psycopg2.errors.QueryCanceled as e:
        logger.error(f"[SEASONALITY] DOW query timeout: {type(e).__name__}")
        raise_api_error(504, "timeout", "Seasonality data query exceeded timeout")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[SEASONALITY] DOW query error: {type(e).__name__}")
        raise_db_error(e, "seasonality day of week query")

    if not monthly_data:
        raise_api_error(503, "no_data", "Seasonality monthly data not yet available")
    if not dow_data:
        raise_api_error(503, "no_data", "Seasonality day-of-week data not yet available")

    return json_response(
        200,
        {
            "monthly": monthly_data,
            "day_of_week": dow_data,
            "summary": {
                "best_month": (
                    {
                        "name": (best_month.get("month_name") if best_month else None),
                        "avg_return_pct": (float(val) if (val := best_month.get("avg_return")) is not None else None),
                        "win_rate_pct": (
                            round(
                                (float(wy) / float(yc) * 100),
                                1,
                            )
                            if (wy := best_month.get("winning_years")) is not None
                            and (yc := best_month.get("years_counted")) is not None
                            else None
                        ),
                    }
                    if best_month
                    else None
                ),
                "worst_month": (
                    {
                        "name": (worst_month.get("month_name") if worst_month else None),
                        "avg_return_pct": (float(val) if (val := worst_month.get("avg_return")) is not None else None),
                        "win_rate_pct": (
                            round(
                                (float(wy) / float(yc) * 100),
                                1,
                            )
                            if (wy := worst_month.get("winning_years")) is not None
                            and (yc := worst_month.get("years_counted")) is not None
                            else None
                        ),
                    }
                    if worst_month
                    else None
                ),
                "best_day": (
                    {
                        "name": best_dow.get("day") if best_dow else None,
                        "avg_return_pct": (float(val) if (val := best_dow.get("avg_return")) is not None else None),
                        "win_rate_pct": (float(val) if (val := best_dow.get("win_rate")) is not None else None),
                    }
                    if best_dow
                    else None
                ),
                "worst_day": (
                    {
                        "name": worst_dow.get("day") if worst_dow else None,
                        "avg_return_pct": (float(val) if (val := worst_dow.get("avg_return")) is not None else None),
                        "win_rate_pct": (float(val) if (val := worst_dow.get("win_rate")) is not None else None),
                    }
                    if worst_dow
                    else None
                ),
            },
            "insights": {
                "sell_in_may_effect": "May seasonality indicates potential strength" if monthly_data else None,
                "monday_effect": "Historical day-of-week effect data available" if dow_data else None,
            },
        },
    )


def _handle_sentiment(cur: cursor, params: dict[str, Any] | None) -> Any:
    """Handle /api/market/sentiment endpoint."""
    range_days = _parse_range_param(params) if params else 30
    sentiment_data = {}
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=range_days)).date()

    # OPTIMIZATION: Set timeout to prevent slow queries from blocking
    cur.execute("SET LOCAL statement_timeout = '4000ms'")

    # AAII investor sentiment
    try:
        cur.execute(
            """
            SELECT date, bullish, neutral, bearish
            FROM aaii_sentiment
            WHERE date >= %s
            ORDER BY date ASC
            LIMIT 100
        """,
            (cutoff_date,),
        )
        aaii_rows = [safe_json_serialize(dict(r)) for r in cur.fetchall()]
        aaii_current = aaii_rows[-1] if aaii_rows else None

        # Compute trend: is bullish rising or falling?
        aaii_trend = "neutral"
        if len(aaii_rows) >= 2:
            prev_bull = aaii_rows[-2].get("bullish")
            curr_bull = aaii_rows[-1].get("bullish")
            if prev_bull is not None and curr_bull is not None:
                prev = float(prev_bull)
                curr = float(curr_bull)
                if curr > prev * 1.02:
                    aaii_trend = "rising"
                elif curr < prev * 0.98:
                    aaii_trend = "falling"
                else:
                    aaii_trend = "neutral"

        sentiment_data["aaii"] = {
            "current": aaii_current,
            "history": aaii_rows,
            "trend": aaii_trend,
            "data": aaii_rows,
            "bullish_pct": (
                float(aaii_current.get("bullish")) if aaii_current and aaii_current.get("bullish") is not None else None
            ),
        }
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error(f"[SENTIMENT_AAII] Error: {type(e).__name__}")
        raise_db_error(e, "AAII sentiment query")

    # NAAIM manager exposure
    try:
        cur.execute(
            """
            SELECT date, naaim_number_mean, bullish, bearish
            FROM naaim
            WHERE date >= %s
            ORDER BY date ASC
            LIMIT 52
        """,
            (cutoff_date,),
        )
        naaim_rows = [safe_json_serialize(dict(r)) for r in cur.fetchall()]
        naaim_current = naaim_rows[-1] if naaim_rows else None

        # Compute trend
        naaim_trend = "neutral"
        if len(naaim_rows) >= 2:
            prev_mean = naaim_rows[-2].get("naaim_number_mean")
            curr_mean = naaim_rows[-1].get("naaim_number_mean")
            if prev_mean is not None and curr_mean is not None:
                prev = float(prev_mean)
                curr = float(curr_mean)
                if curr > prev * 1.02:
                    naaim_trend = "rising"
                elif curr < prev * 0.98:
                    naaim_trend = "falling"
                else:
                    naaim_trend = "neutral"

        sentiment_data["naaim"] = {
            "current": (
                float(naaim_current.get("naaim_number_mean"))
                if naaim_current and naaim_current.get("naaim_number_mean") is not None
                else None
            ),
            "history": naaim_rows,
            "trend": naaim_trend,
            "bullish_pct": (
                float(naaim_current.get("bullish"))
                if naaim_current and naaim_current.get("bullish") is not None
                else None
            ),
            "bearish_pct": (
                float(naaim_current.get("bearish"))
                if naaim_current and naaim_current.get("bearish") is not None
                else None
            ),
        }
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error(f"[SENTIMENT_NAAIM] Error: {type(e).__name__}")
        raise_db_error(e, "NAAIM sentiment query")

    # Fear & Greed
    try:
        cur.execute(
            """
            SELECT date, fear_greed_value as value, fear_greed_label as label
            FROM fear_greed_index
            WHERE date >= %s
            ORDER BY date ASC
            LIMIT 100
        """,
            (cutoff_date,),
        )
        fg_rows = [safe_json_serialize(dict(r)) for r in cur.fetchall()]
        fg_current = fg_rows[-1] if fg_rows else None

        # Compute trend
        fg_trend = "neutral"
        if len(fg_rows) >= 2:
            prev_val = fg_rows[-2].get("value")
            curr_val = fg_rows[-1].get("value")
            if prev_val is not None and curr_val is not None:
                prev = float(prev_val)
                curr = float(curr_val)
                if curr < prev * 0.98:
                    fg_trend = "rising_fear"
                elif curr > prev * 1.02:
                    fg_trend = "rising_greed"
                else:
                    fg_trend = "neutral"

        sentiment_data["fearGreed"] = {
            "current": {
                "value": (float(fg_current["value"]) if fg_current and fg_current.get("value") is not None else None),
                "label": fg_current.get("label") if fg_current else None,
            },
            "history": fg_rows,
            "trend": fg_trend,
            "data": fg_rows,
        }
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error(f"[SENTIMENT_FG] Error: {type(e).__name__}")
        raise_db_error(e, "fear/greed sentiment query")

    freshness = check_data_freshness(cur, "aaii_sentiment", "date", warning_days=1)
    return json_response(200, sentiment_data, data_freshness=freshness)


def _handle_naaim(cur: cursor) -> Any:
    """Handle /api/market/naaim endpoint."""
    try:
        cur.execute("SET LOCAL statement_timeout = '5000ms'")
        cur.execute("""
            SELECT date, naaim_number_mean, bullish, bearish
            FROM naaim
            ORDER BY date ASC
            LIMIT 52
        """)
        rows = cur.fetchall()
        if not rows:
            return error_response(503, "no_data", "NAAIM data not yet available")

        history = []
        for r in rows:
            r_dict = dict(r)
            naaim_val = r_dict.get("naaim_number_mean")
            bullish_val = r_dict.get("bullish")
            bearish_val = r_dict.get("bearish")
            date_val = r_dict.get("date")
            if date_val is None:
                logger.error(f"[NAAIM] Record missing date: {list(r_dict.keys())}")
                raise_api_error(500, "data_integrity_error", "NAAIM record missing date field")
            history.append(
                {
                    "date": str(date_val),
                    "value": (float(naaim_val) if naaim_val is not None else None),
                    "bullish_pct": (float(bullish_val) if bullish_val is not None else None),
                    "bearish_pct": (float(bearish_val) if bearish_val is not None else None),
                }
            )

        if history:
            current = history[-1]
            values: list[float] = [float(h["value"]) for h in history if h["value"] is not None]

            # Compute moving averages
            ma_10 = sum(values[-10:]) / min(10, len(values)) if len(values) >= 10 else None
            ma_20 = sum(values[-20:]) / min(20, len(values)) if len(values) >= 20 else None
            ma_50 = sum(values[-50:]) / min(50, len(values)) if len(values) >= 50 else None

            # Identify extremes (>80 = extreme bullish, <20 = extreme bearish)
            _cv = current["value"]
            curr_val: float | None = float(_cv) if _cv is not None else None
            signals = {
                "extreme_bullish": (curr_val > 80 if curr_val is not None else None),
                "extreme_bearish": (curr_val < 20 if curr_val is not None else None),
                "overbought": curr_val > 70 if curr_val is not None else None,
                "oversold": curr_val < 30 if curr_val is not None else None,
                "above_50": curr_val > 50 if curr_val is not None else None,
                "below_50": curr_val <= 50 if curr_val is not None else None,
            }

            return json_response(
                200,
                {
                    "current": current["value"],
                    "bullish_pct": current["bullish_pct"],
                    "bearish_pct": current["bearish_pct"],
                    "history": history,
                    "moving_averages": {
                        "ma_10": round(ma_10, 2) if ma_10 else None,
                        "ma_20": round(ma_20, 2) if ma_20 else None,
                        "ma_50": round(ma_50, 2) if ma_50 else None,
                    },
                    "signals": signals,
                    "interpretation": {
                        "meaning": "Manager equity allocation %; 0=all cash, 100=fully invested",
                        "current_stance": ("bullish" if curr_val is not None and curr_val > 50 else "bearish"),
                        "extremity": (
                            "extreme_bullish"
                            if curr_val is not None and curr_val > 80
                            else ("extreme_bearish" if curr_val is not None and curr_val < 20 else "normal")
                        ),
                    },
                },
            )
        else:
            return error_response(503, "no_data", "NAAIM data processing failed")
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error(f"[NAAIM] Error: {type(e).__name__}")
        raise_db_error(e, "NAAIM query")
        raise  # unreachable — raise_db_error is NoReturn; satisfies mypy without lambda path config


@db_route_handler("get fear greed history")

def _get_fear_greed_history(cur: cursor, days: int = 30) -> Any:
    """Get fear/greed index history with signals."""
    cur.execute("SET LOCAL statement_timeout = '5000ms'")
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    cur.execute(
        """
        SELECT date, fear_greed_value as value, fear_greed_label as label
        FROM fear_greed_index
        WHERE date >= %s
        ORDER BY date ASC
        LIMIT 100
    """,
        (cutoff_date,),
    )
    history_rows = cur.fetchall()

    if not history_rows:
        logger.error(f"[FEAR_GREED] No fear/greed index data available for {days}-day period")
        return error_response(
            503,
            "fear_greed_unavailable",
            f"Fear/Greed index data not available for {days}-day period",
        )

    history = [safe_json_serialize(dict(h)) for h in history_rows]

    if history:
        current = history[-1]
        values = [h["value"] for h in history]

        # Compute stats
        min_val = min(values)
        max_val = max(values)
        avg_val = sum(values) / len(values) if values else None
        curr_val = current["value"]

        # Identify extremes and signals
        signals = {
            "extreme_fear": curr_val < 25 if curr_val is not None else None,
            "extreme_greed": curr_val > 75 if curr_val is not None else None,
            "moderate_fear": 25 <= curr_val < 45 if curr_val is not None else None,
            "moderate_greed": 55 < curr_val <= 75 if curr_val is not None else None,
            "neutral": 45 <= curr_val <= 55 if curr_val is not None else None,
        }

        return json_response(
            200,
            {
                "current": {
                    "value": float(curr_val),
                    "label": current.get("label"),
                    "date": str(current["date"]) if current.get("date") else None,
                },
                "history": [
                    {
                        "date": str(h["date"]) if h.get("date") else None,
                        "value": (float(h["value"]) if h.get("value") is not None else None),
                        "label": h.get("label"),
                    }
                    for h in history
                ],
                "statistics": {
                    "min": float(min_val),
                    "max": float(max_val),
                    "avg": round(float(avg_val), 2) if avg_val else None,
                    "current": float(curr_val) if curr_val is not None else None,
                    "range_days": days,
                },
                "signals": signals,
                "interpretation": {
                    "meaning": "Market sentiment gauge; 0=Fear, 50=Neutral, 100=Greed",
                    "current_stance": "fear" if curr_val < 50 else "greed",
                    "extremity": ("extreme_fear" if curr_val < 25 else "extreme_greed" if curr_val > 75 else "normal"),
                },
            },
        )
    else:
        return json_response(
            200,
            {
                "current": None,
                "history": [],
                "statistics": {"min": None, "max": None, "avg": None},
                "signals": {},
            },
        )


@db_route_handler("get market latest")

def _get_market_latest(cur: cursor) -> Any:
    """Get latest market data including indices, breadth, and sentiment."""
    cur.execute("""
        SELECT date, market_trend, market_stage, advance_decline_ratio,
                   new_highs_count, new_lows_count, vix_level, put_call_ratio,
                   up_volume_percent, breadth_momentum_10d
        FROM market_health_daily
        ORDER BY date DESC
        LIMIT 1
    """)
    market_row = cur.fetchone()

    cur.execute("""
        SELECT date, fear_greed_value, fear_greed_label
        FROM fear_greed_index
        ORDER BY date DESC
        LIMIT 1
    """)
    sentiment_row = cur.fetchone()

    cur.execute("""
        SELECT symbol, close
        FROM price_daily
        WHERE date = (SELECT date FROM price_daily ORDER BY date DESC LIMIT 1)
        ORDER BY symbol
        LIMIT 10
    """)
    recent_prices = cur.fetchall()

    result: dict[str, Any] = {}
    if market_row:
        result["market"] = dict(market_row)
    if sentiment_row:
        result["sentiment"] = dict(sentiment_row)
    if recent_prices:
        result["prices"] = [safe_json_serialize(dict(p)) for p in recent_prices]

    # FAIL-FAST: Require at least market data; don't return empty response
    if not market_row:
        return json_response(
            503,
            {
                "isDataError": True,
                "message": "Market data unavailable",
                "available": list(result.keys()),
            },
        )

    return json_response(200, result)


def _parse_range_param(params: dict[str, Any], default: int = 30) -> int:
    if not params:
        return default

    # CRITICAL: Fail-fast on malformed params. Range/days must be explicit, not silent fallback.
    range_val = params.get("range")
    if range_val:
        if not isinstance(range_val, list) or not range_val:
            raise ValueError("CRITICAL: 'range' parameter must be a non-empty list")
        try:
            parsed = int(range_val[0])
            if parsed <= 0:
                raise ValueError(f"CRITICAL: 'range' must be positive, got {parsed}")
            return parsed
        except (ValueError, TypeError) as e:
            raise ValueError(f"CRITICAL: 'range' parameter invalid: {e}") from e

    days_val = params.get("days")
    if days_val:
        if not isinstance(days_val, list) or not days_val:
            raise ValueError("CRITICAL: 'days' parameter must be a non-empty list")
        try:
            parsed = int(days_val[0])
            if parsed <= 0:
                raise ValueError(f"CRITICAL: 'days' must be positive, got {parsed}")
            return parsed
        except (ValueError, TypeError) as e:
            raise ValueError(f"CRITICAL: 'days' parameter invalid: {e}") from e

    return default


@db_route_handler("get correlation matrix")

def _get_correlation_matrix(cur: cursor) -> Any:  # noqa: C901
    """Compute and return correlation matrix between key market indices.

    Returns correlation matrix with statistics and analysis when sufficient data available.
    When data is insufficient (no price history or < 2 valid symbols), returns response
    with data_unavailable marker indicating reason for unavailable data.
    """
    symbols = ["^GSPC", "^IXIC", "SPY", "QQQ", "IVV", "TLT", "GLD"]

    cur.execute("SAVEPOINT correlation_matrix")
    cur.execute("SET LOCAL statement_timeout = '12s'")  # Query on 252 days of data
    cur.execute(
        """
        SELECT symbol, date, close
        FROM price_daily
        WHERE symbol = ANY(%s)
              AND date >= CURRENT_DATE - INTERVAL '252 days'
        ORDER BY symbol, date
    """,
        (symbols,),
    )
    rows = cur.fetchall()
    cur.execute("RELEASE SAVEPOINT correlation_matrix")

    if not rows:
        logger.error("[CORRELATION_MATRIX] No price history available for correlation calculation")
        return error_response(
            503,
            "insufficient_price_data",
            "Correlation matrix requires price history for 2+ symbols. Insufficient data available.",
        )

    prices_by_symbol: dict[str, list[Any]] = {}
    skipped_price_rows: list[dict[str, Any]] = []
    for row in rows:
        sym = row["symbol"]
        if sym not in prices_by_symbol:
            prices_by_symbol[sym] = []
        if row["close"] is None or row["close"] <= 0:
            if "date" not in row or row["date"] is None:
                raise ValueError(
                    f"[MARKET_API_DATA_INCOMPLETE] Market data for {sym} missing required 'date' field. "
                    f"Cannot process price data without date. Row keys: {list(row.keys())}. "
                    f"Check upstream price data source and loader."
                )
            logger.warning(f"Market API: Invalid close price for {sym} on {row['date']}: {row['close']}; skipping")
            skipped_price_rows.append({"symbol": sym, "date": row.get("date"), "close": row["close"]})
            continue
        prices_by_symbol[sym].append((row["date"], float(row["close"])))

    for sym in prices_by_symbol:
        prices_by_symbol[sym] = [(d, p) for d, p in sorted(prices_by_symbol[sym])]

    returns_by_symbol = {}
    for sym, prices in prices_by_symbol.items():
        if len(prices) < 2:
            continue
        returns = []
        for i in range(1, len(prices)):
            prev_p = prices[i - 1][1]
            curr_p = prices[i][1]
            if prev_p > 0:
                ret = (curr_p - prev_p) / prev_p
                returns.append(ret)
        returns_by_symbol[sym] = returns

    valid_symbols = [s for s in symbols if s in returns_by_symbol and len(returns_by_symbol[s]) >= 10]
    if len(valid_symbols) < 2:
        return json_response(
            200,
            {
                "correlations": [],
                "statistics": {
                    "avg_correlation": None,
                    "max_correlation": {"value": None, "pair": []},
                    "min_correlation": {"value": None, "pair": []},
                },
                "analysis": {
                    "market_regime": "insufficient_data",
                    "diversification_score": None,
                    "risk_assessment": {
                        "concentration_risk": "unknown",
                        "diversification_benefit": "unknown",
                        "portfolio_stability": "unknown",
                    },
                },
                "data_unavailable": True,
                "reason": "insufficient_valid_symbols",
            },
        )

    def pearson_corr(x_ret: list[float], y_ret: list[float]) -> dict[str, Any] | float:
        """Compute Pearson correlation coefficient.

        Returns float correlation value on success, or dict with data_unavailable marker
        when data is insufficient for calculation.
        """
        if len(x_ret) < 2 or len(y_ret) < 2:
            return {"data_unavailable": True, "reason": "insufficient_returns_data"}
        min_len = min(len(x_ret), len(y_ret))
        if min_len < 2:
            return {"data_unavailable": True, "reason": "insufficient_returns_data"}
        x = x_ret[-min_len:]
        y = y_ret[-min_len:]
        mx = sum(x) / len(x)
        my = sum(y) / len(y)
        num: float = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y, strict=False))
        dx: float = sum((xi - mx) ** 2 for xi in x)
        dy: float = sum((yi - my) ** 2 for yi in y)
        denom = (dx * dy) ** 0.5
        if denom == 0:
            return {"data_unavailable": True, "reason": "zero_deviation"}
        return float(num / denom)

    correlations_data = []
    all_corrs = []
    unavailable_pairs = []

    for sym1 in valid_symbols:
        row_corrs: list[float | None] = []
        for sym2 in valid_symbols:
            if sym1 == sym2:
                corr_val: dict[str, Any] | float | None = 1.0
            else:
                corr_val = pearson_corr(returns_by_symbol[sym1], returns_by_symbol[sym2])
            # Handle case where pearson_corr returns data_unavailable marker
            if isinstance(corr_val, dict):
                row_corrs.append(None)
                if sym1 != sym2:
                    unavailable_pairs.append({"pair": [sym1, sym2], "reason": corr_val.get("reason", "unknown")})
            else:
                row_corrs.append(corr_val)
                if sym1 != sym2 and corr_val is not None:
                    all_corrs.append(corr_val)
        correlations_data.append({"symbol": sym1, "correlations": row_corrs})

    max_corr = max(all_corrs) if all_corrs else None
    min_corr = min(all_corrs) if all_corrs else None
    avg_corr = sum(all_corrs) / len(all_corrs) if all_corrs else None

    max_pair = None
    min_pair = None

    if max_corr is not None:
        for i, sym1 in enumerate(valid_symbols):
            for j, sym2 in enumerate(valid_symbols):
                if i < j and correlations_data[i]["correlations"][j] == max_corr:
                    max_pair = [sym1, sym2]
                    break

    if min_corr is not None:
        for i, sym1 in enumerate(valid_symbols):
            for j, sym2 in enumerate(valid_symbols):
                if i < j and correlations_data[i]["correlations"][j] == min_corr:
                    min_pair = [sym1, sym2]
                    break

    # Validate correlation pair discovery
    if max_corr is not None and max_pair is None:
        logger.error(
            f"[MARKET_CORRELATION] Max correlation {max_corr} identified but pair lookup failed. "
            f"Data integrity error in correlation matrix computation."
        )
        raise_api_error(
            500, "correlation_computation_error", "Max correlation pair computation failed—cannot verify data integrity"
        )
    if min_corr is not None and min_pair is None:
        logger.error(
            f"[MARKET_CORRELATION] Min correlation {min_corr} identified but pair lookup failed. "
            f"Data integrity error in correlation matrix computation."
        )
        raise_api_error(
            500, "correlation_computation_error", "Min correlation pair computation failed—cannot verify data integrity"
        )

    avg_corr_val = round(avg_corr, 2) if avg_corr is not None else None

    if avg_corr_val is not None and avg_corr_val > 0.5:
        market_regime = "high_correlation"
    elif avg_corr_val is not None and avg_corr_val > 0.2:
        market_regime = "moderate_correlation"
    else:
        market_regime = "low_correlation"

    diversification_score = round(max(0, 1.0 - (avg_corr_val)) * 100, 1) if avg_corr_val is not None else None

    if avg_corr_val is not None and avg_corr_val > 0.6:
        concentration_risk = "high"
        diversification_benefit = "low"
        portfolio_stability = "volatile"
    elif avg_corr_val is not None and avg_corr_val > 0.3:
        concentration_risk = "moderate"
        diversification_benefit = "moderate"
        portfolio_stability = "moderate"
    else:
        concentration_risk = "low"
        diversification_benefit = "high"
        portfolio_stability = "stable"

    freshness = check_data_freshness(cur, "price_daily", "date", warning_days=1)
    response_data: dict[str, Any] = {
        "correlations": correlations_data,
        "statistics": {
            "avg_correlation": avg_corr_val,
            "max_correlation": {
                "value": round(max_corr, 2) if max_corr else None,
                "pair": max_pair,
            },
            "min_correlation": {
                "value": round(min_corr, 2) if min_corr else None,
                "pair": min_pair,
            },
        },
        "analysis": {
            "market_regime": market_regime,
            "diversification_score": diversification_score,
            "risk_assessment": {
                "concentration_risk": concentration_risk,
                "diversification_benefit": diversification_benefit,
                "portfolio_stability": portfolio_stability,
            },
        },
    }

    # Flag if any price rows were skipped due to invalid data
    if skipped_price_rows:
        response_data["correlation_incomplete"] = True
        response_data["skipped_price_rows_count"] = len(skipped_price_rows)
        response_data["skipped_price_samples"] = skipped_price_rows[:10]
        logger.warning(
            "[MARKET] Correlation analysis incomplete: %d price rows skipped (invalid data)",
            len(skipped_price_rows),
        )

    # Flag if any correlation pairs have unavailable data
    if unavailable_pairs:
        response_data["correlation_pairs_incomplete"] = True
        response_data["unavailable_pairs_count"] = len(unavailable_pairs)
        response_data["unavailable_pairs_samples"] = unavailable_pairs[:10]
        logger.warning(
            "[MARKET] Correlation pairs incomplete: %d pairs have insufficient data",
            len(unavailable_pairs),
        )

    return json_response(
        200,
        response_data,
        data_freshness=freshness,
    )


@db_route_handler("get cap distribution")

def _get_cap_distribution(cur: cursor) -> Any:
    """Get market cap distribution across market cap buckets and sectors."""
    # market_cap is in key_metrics, sector is in company_profile — stock_symbols has neither
    cur.execute("""
        SELECT ss.symbol, cp.sector, km.market_cap,
            CASE
                WHEN km.market_cap >= 200000000000 THEN 'mega_cap'
                WHEN km.market_cap >= 10000000000 THEN 'large_cap'
                WHEN km.market_cap >= 2000000000 THEN 'mid_cap'
                WHEN km.market_cap >= 300000000 THEN 'small_cap'
                ELSE 'micro_cap'
            END AS market_cap_category
        FROM stock_symbols ss
        JOIN company_profile cp ON ss.symbol = cp.ticker AND cp.sector IS NOT NULL
        JOIN key_metrics km ON ss.symbol = km.symbol AND km.market_cap > 0
        WHERE COALESCE(ss.etf, 'N') != 'Y'
              AND ss.symbol NOT IN (SELECT symbol FROM etf_symbols)
        ORDER BY km.market_cap DESC
        LIMIT 10000
    """)
    rows = cur.fetchall()

    if not rows:
        # Distinguish between "no stocks loaded" vs "data quality issue"
        # Check if company_profile or key_metrics tables are empty
        cur.execute("SELECT COUNT(*) FROM company_profile WHERE sector IS NOT NULL")
        profile_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM key_metrics WHERE market_cap > 0")
        metrics_count = cur.fetchone()[0]

        if profile_count == 0 or metrics_count == 0:
            raise_api_error(
                503,
                "incomplete_data",
                f"Market cap data not fully loaded. company_profile: {profile_count} records, "
                f"key_metrics: {metrics_count} records. Data loaders may not have completed.",
            )

        return json_response(
            200,
            {
                "by_category": {},
                "by_sector": {},
                "summary": {
                    "total_stocks": 0,
                    "total_market_cap": 0,
                    "largest_cap": None,
                    "category_distribution": {},
                },
            },
        )

    stocks = [safe_json_serialize(dict(r)) for r in rows]

    # CRITICAL: Validate market cap data exists for all stocks before using in calculations
    # Market cap missing/None breaks sector concentration limits used by position sizing
    missing_cap = [s.get("symbol", "unknown") for s in stocks if "market_cap" not in s or s.get("market_cap") is None]
    if missing_cap:
        raise ValueError(
            f"[MARKET DATA CRITICAL] {len(missing_cap)} stocks missing market_cap: {missing_cap[:10]}. "
            f"Market cap required for sector concentration calculations used in position sizing. "
            f"Cannot compute accurate sector distribution without complete market cap data. "
            f"Check that price_daily loader populated market_cap for all universe symbols."
        )

    total_cap = sum(s["market_cap"] for s in stocks if s["market_cap"])
    if total_cap <= 0:
        raise ValueError(
            f"[MARKET DATA CRITICAL] Total market cap is {total_cap} (must be > 0). "
            f"All stocks have zero market cap — data quality issue. "
            f"Check price_daily loader."
        )

    by_category: dict[Any, dict[str, Any]] = {}
    by_sector: dict[Any, dict[str, Any]] = {}

    for stock in stocks:
        # Market cap guaranteed to exist by validation above; no .get() fallback
        cap = stock["market_cap"]
        if cap is None or cap <= 0:
            raise ValueError(
                f"[MARKET DATA CRITICAL] {stock.get('symbol', 'unknown')}: "
                f"market_cap is {cap} after validation passed. Data integrity error."
            )
        category = stock.get("market_cap_category", "unknown")
        sector = stock.get("sector", "unknown")

        if category not in by_category:
            by_category[category] = {"count": 0, "total_cap": 0, "stocks": []}
        by_category[category]["count"] += 1
        by_category[category]["total_cap"] += cap
        by_category[category]["stocks"].append(stock["symbol"])

        if sector not in by_sector:
            by_sector[sector] = {"count": 0, "total_cap": 0, "pct_of_market": 0}
        by_sector[sector]["count"] += 1
        by_sector[sector]["total_cap"] += cap

    for sector in by_sector:
        if total_cap > 0:
            by_sector[sector]["pct_of_market"] = round(by_sector[sector]["total_cap"] / total_cap * 100, 2)

    category_dist = {}
    for cat in by_category:
        if total_cap > 0:
            pct = by_category[cat]["total_cap"] / total_cap * 100
            category_dist[cat] = {
                "count": by_category[cat]["count"],
                "pct_of_market": round(pct, 2),
                "total_cap": by_category[cat]["total_cap"],
                "avg_cap": (
                    round(by_category[cat]["total_cap"] / by_category[cat]["count"], 0)
                    if by_category[cat]["count"] > 0
                    else 0
                ),
            }

    sector_dist = {}
    for sector in sorted(by_sector.keys(), key=lambda s: by_sector[s]["total_cap"], reverse=True):
        sector_dist[sector] = {
            "count": by_sector[sector]["count"],
            "total_cap": by_sector[sector]["total_cap"],
            "pct_of_market": by_sector[sector]["pct_of_market"],
            "avg_cap": (
                round(by_sector[sector]["total_cap"] / by_sector[sector]["count"], 0)
                if by_sector[sector]["count"] > 0
                else 0
            ),
        }

    freshness = check_data_freshness(cur, "stock_symbols", "created_at", warning_days=7)

    # CRITICAL FAIL-FAST: Market cap extremes must exist, no defaults to 0
    market_caps = [s["market_cap"] for s in stocks if s["market_cap"] and s["market_cap"] > 0]
    if not market_caps:
        raise ValueError(
            "[MARKET DATA CRITICAL] No valid market cap values found in stocks list. "
            "Cannot compute largest/smallest market cap without data. "
            "Check price_daily loader populated valid market caps."
        )

    largest_cap = max(market_caps)
    smallest_cap = min(market_caps)

    return json_response(
        200,
        {
            "by_category": {
                k: {
                    "count": v["count"],
                    "total_cap": v["total_cap"],
                    "pct_of_market": (round(v["total_cap"] / total_cap * 100, 2) if total_cap > 0 else None),
                    "avg_cap": (round(v["total_cap"] / v["count"], 0) if v["count"] > 0 else None),
                }
                for k, v in by_category.items()
            },
            "by_sector": sector_dist,
            "summary": {
                "total_stocks": len(stocks),
                "total_market_cap": total_cap,
                "largest_cap": largest_cap,
                "smallest_cap": smallest_cap,
                "category_distribution": category_dist,
            },
        },
        data_freshness=freshness,
    )


def _get_index_symbols() -> list[str]:
    """Get market index symbols from configuration."""
    from typing import cast
    from utils.market_symbols_config import MarketSymbolsConfig

    result = MarketSymbolsConfig.get_index_symbols()
    return cast(list[str], result)


def _get_index_names() -> dict[str, str]:
    """Get index symbol names from configuration."""
    from typing import cast
    from utils.market_symbols_config import MarketSymbolsConfig

    result = MarketSymbolsConfig.get_index_names()
    return cast(dict[str, str], result)


@db_route_handler("get market indices")

def _get_markets(cur: cursor) -> Any:
    index_symbols = _get_index_symbols()
    cur.execute(
        """
        WITH latest_date AS (
            SELECT date AS d FROM price_daily WHERE symbol = ANY(%s) ORDER BY date DESC LIMIT 1
        ),
        prev_date AS (
            SELECT date AS d FROM price_daily
            WHERE symbol = ANY(%s)
                  AND date < (SELECT d FROM latest_date)
            ORDER BY date DESC LIMIT 1
        ),
        today AS (
            SELECT symbol, date, close
            FROM price_daily
            WHERE symbol = ANY(%s)
                  AND date = (SELECT d FROM latest_date)
        ),
        yesterday AS (
            SELECT symbol, close AS prev_close
            FROM price_daily
            WHERE symbol = ANY(%s)
                  AND date = (SELECT d FROM prev_date)
        )
        SELECT t.symbol, t.date, t.close,
                   COALESCE(y.prev_close, t.close) AS prev_close,
                   (y.prev_close IS NULL) AS _is_fallback
        FROM today t
        LEFT JOIN yesterday y ON t.symbol = y.symbol
        ORDER BY t.symbol
    """,
        (index_symbols, index_symbols, index_symbols, index_symbols),
    )
    latest = cur.fetchall()

    cur.execute(
        """
        SELECT symbol, date, close
        FROM price_daily
        WHERE symbol = ANY(%s)
              AND date >= CURRENT_DATE - INTERVAL '90 days'
        ORDER BY symbol, date DESC
    """,
        (index_symbols,),
    )
    history_rows = cur.fetchall()

    history: dict[str, list[Any]] = {}
    for row in history_rows:
        sym = row["symbol"]
        if sym not in history:
            history[sym] = []
        # Validate price data exists before adding to history
        if row["close"] is None or row["close"] <= 0:
            logger.warning(f"[MARKET_INDICES] Skipping {sym} on {row['date']}: invalid close price {row['close']}")
            continue
        if row["date"] is None:
            logger.error(f"[MARKET_INDICES] Missing date for {sym}: cannot add to history without date")
            raise ValueError(f"[MARKET_INDICES] {sym} history record missing required date field")
        history[sym].append(
            {
                "date": str(row["date"]),
                "close": float(row["close"]),
            }
        )

    indices = []
    stale_alerts = []

    for row in latest:
        if "symbol" not in row or row["symbol"] is None:
            raise ValueError(
                "[MARKET_API_INDICES_INCOMPLETE] Index row missing required 'symbol' field. "
                f"Cannot process index data without symbol. Row keys: {list(row.keys())}"
            )
        symbol = row["symbol"]

        if row["close"] is None or row["close"] <= 0:
            logger.warning(f"Market API indices: Invalid close price for {symbol}: {row['close']}; skipping")
            continue
        price = float(row["close"])
        if row["prev_close"] is None or row["prev_close"] <= 0:
            logger.warning(
                f"Market API indices: Invalid prev_close for {symbol}: {row['prev_close']}; cannot calculate change"
            )
            continue
        prev_price = float(row["prev_close"])
        change = price - prev_price
        change_pct = change / prev_price * 100

        # Fail-fast on fallback prices: if today's quote is missing during market hours, raise 503
        if "_is_fallback" not in row:
            raise ValueError(
                f"[MARKET_API_FALLBACK_MISSING] Index {symbol} row missing '_is_fallback' indicator. "
                f"Cannot determine if price is fresh or fallback. Check data source. "
                f"Row keys: {list(row.keys())}"
            )
        is_fallback = bool(row["_is_fallback"])
        if is_fallback:
            raise_api_error(503, "stale_data", f"Index {symbol} price unavailable (today's quote missing)")

        # Check data age and add to stale alerts
        if row.get("date"):
            row_date = row["date"]
            if isinstance(row_date, str):
                from datetime import datetime

                row_date = datetime.fromisoformat(row_date).date()
            data_age = (date.today() - row_date).days
            if data_age > 1:
                stale_alerts.append(f"{row['symbol']} {data_age}d old")

        index_names = _get_index_names()
        indices.append(
            {
                "symbol": row["symbol"],
                "name": index_names.get(row["symbol"], row["symbol"]),
                "date": str(row["date"]),
                "price": round(price, 2),
                "change": round(change, 2),
                "changePercent": round(change_pct, 2),
                "pe": None,
            }
        )

    if not indices:
        raise_api_error(503, "no_data", "No valid index price data available for latest market indices")

    result = {
        "indices": indices,
        "history": history,
        "stale_alerts": stale_alerts,
    }
    return json_response(200, result)


@db_route_handler("get sector overview")

def _get_sector_overview(cur: cursor) -> Any:
    """Get latest sector performance overview from sectors table."""
    cur.execute("""
        SELECT sector_name, performance_ytd, performance_1y, pe_ratio,
               dividend_yield, market_cap, stock_count, metric_date
        FROM sectors
        WHERE metric_date = (SELECT MAX(metric_date) FROM sectors)
        ORDER BY market_cap DESC NULLS LAST
        LIMIT 100
    """)
    rows = cur.fetchall()
    if not rows:
        cur.execute("""
            SELECT DISTINCT sector, COUNT(*) as stock_count
            FROM company_profile WHERE sector IS NOT NULL AND sector != ''
            GROUP BY sector ORDER BY stock_count DESC
            LIMIT 100
        """)
        rows = cur.fetchall()
        return list_response([{"sector_name": r["sector"], "stock_count": r["stock_count"]} for r in rows])
    return list_response([safe_json_serialize(dict(r)) for r in rows])


class _MarketHandlerRegistry:
    """Registry mapping market endpoint paths to handler functions."""

    def __init__(self) -> None:
        self._handlers = {
            "/api/market/status": _handle_market_status,
            "/api/market/indices": _get_markets,
            "/api/market/breadth": _handle_breadth,
            "/api/market/technicals": _handle_technicals,
            "/api/market/top-movers": _handle_top_movers,
            "/api/market/distribution-days": _handle_distribution_days,
            "/api/market/seasonality": _handle_seasonality,
            "/api/market/sentiment": self._wrap_sentiment,
            "/api/market/fear-greed": self._wrap_fear_greed,
            "/api/market/naaim": _handle_naaim,
            "/api/market/latest": _get_market_latest,
            "/api/market/cap-distribution": _get_cap_distribution,
            "/api/market/correlation": _get_correlation_matrix,
            "/api/market/sectors": _get_sector_overview,
        }

    def _wrap_sentiment(self, cur: cursor, params: dict[str, Any] | None = None) -> Any:
        return _handle_sentiment(cur, params)

    def _wrap_fear_greed(self, cur: cursor, params: dict[str, Any] | None = None) -> Any:
        range_days = _parse_range_param(params) if params else 30
        return _get_fear_greed_history(cur, range_days)

    def get_handler(self, path: str) -> Any:
        """Get handler for path, handling aliases like /api/market → /api/market/status."""
        if path in ["/api/market", "/api/market/status"] or path.startswith("/api/market?"):
            return self._handlers["/api/market/status"]
        return self._handlers.get(path)


_MARKET_REGISTRY = _MarketHandlerRegistry()


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle /api/market/* endpoints."""
    try:
        handler = _MARKET_REGISTRY.get_handler(path)
        if handler is None:
            raise_api_error(404, "not_found", f"No market handler for {path}")

        if path == "/api/market/sentiment":
            return handler(cur, params)
        elif path == "/api/market/fear-greed":
            return handler(cur, params)
        else:
            return handler(cur)
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error(f"[MARKET] Unhandled error: {type(e).__name__}: {e}")
        raise_db_error(e, "handle market")
