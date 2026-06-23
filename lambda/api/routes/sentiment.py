"""Route: sentiment"""

import logging
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
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
    safe_page,
)

from shared_contracts.response_validator import ResponseValidator
from utils.validation import DatabaseResultValidator

logger = logging.getLogger(__name__)


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Handle /api/sentiment/* endpoints."""
    try:
        if path == "/api/sentiment/summary":
            fg_rows = execute_with_timeout(
                cur,
                """
                    SELECT fg.fear_greed_value, fg.fear_greed_label, fg.date,
                           mh.put_call_ratio, mh.vix_level
                    FROM fear_greed_index fg
                    LEFT JOIN market_health_daily mh ON mh.date = fg.date
                    ORDER BY fg.date DESC
                    LIMIT 1
                """,
                timeout_sec=3,
            )
            row = fg_rows[0] if fg_rows else None
            fg_value = float(row["fear_greed_value"]) if row and row["fear_greed_value"] else None
            fg_label = row["fear_greed_label"] if row else None

            aaii_row = None
            try:
                aaii_rows = execute_with_timeout(
                    cur,
                    """
                        SELECT bullish, neutral, bearish, date
                        FROM aaii_sentiment
                        ORDER BY date DESC
                        LIMIT 1
                    """,
                    timeout_sec=2,
                )
                aaii_row = aaii_rows[0] if aaii_rows else None
            except (ValueError, ZeroDivisionError, TypeError) as e:
                logger.error(f"Failed to fetch AAII sentiment data: {type(e).__name__}: {e}")

            naaim_row = None
            try:
                naaim_rows = execute_with_timeout(
                    cur,
                    """
                        SELECT naaim_number_mean, date
                        FROM naaim
                        ORDER BY date DESC
                        LIMIT 1
                    """,
                    timeout_sec=2,
                )
                naaim_row = naaim_rows[0] if naaim_rows else None
            except (ValueError, ZeroDivisionError, TypeError) as e:
                logger.error(f"Failed to fetch NAAIM sentiment data: {type(e).__name__}: {e}")

            analyst_row = None
            try:
                analyst_rows = execute_with_timeout(
                    cur,
                    """
                        SELECT SUM(analyst_count) AS analyst_count,
                               SUM(bullish_count) AS bullish_count,
                               SUM(bearish_count) AS bearish_count,
                               MAX(date) AS date
                        FROM analyst_sentiment_analysis
                        WHERE date = (SELECT date FROM analyst_sentiment_analysis ORDER BY date DESC LIMIT 1)
                    """,
                    timeout_sec=2,
                )
                analyst_row = analyst_rows[0] if analyst_rows else None
            except (ValueError, ZeroDivisionError, TypeError) as e:
                logger.error(f"Failed to fetch analyst sentiment data: {type(e).__name__}: {e}")

            freshness = check_data_freshness(cur, "fear_greed_index", "date", warning_days=1)
            sentiment_result = {
                "fear_greed": ({"value": fg_value, "label": fg_label} if fg_value is not None else None),
                "aaii": safe_json_serialize(dict(aaii_row)) if aaii_row else None,
                "naaim": (safe_json_serialize(dict(naaim_row)) if naaim_row else None),
                "analyst": (
                    safe_json_serialize(dict(analyst_row)) if analyst_row and analyst_row.get("analyst_count") else None
                ),
                "put_call_ratio": (float(row["put_call_ratio"]) if row and row["put_call_ratio"] else None),
                "vix_level": (float(row["vix_level"]) if row and row["vix_level"] else None),
                "date": str(row["date"]) if row else None,
                "data_freshness": freshness,
            }
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("sentiment", sentiment_result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return error_response(500, "response_validation_error", error_msg or "Sentiment validation failed")
            return json_response(200, sentiment_result)
        elif path == "/api/sentiment/data" or path.startswith("/api/sentiment/data?"):
            limit_str = params.get("limit", [None])[0] if params else None
            limit = safe_limit(limit_str or "50000", max_val=50000)
            page_str = params.get("page", [None])[0] if params else None
            page = safe_page(page_str or "1")
            offset = (page - 1) * limit
            sentiment = execute_with_timeout(
                cur,
                """
                    SELECT symbol, date, analyst_count, bullish_count, bearish_count, neutral_count,
                           target_price, current_price, upside_downside_percent
                    FROM analyst_sentiment_analysis
                    ORDER BY date DESC, symbol ASC
                    LIMIT %s OFFSET %s
                """,
                (limit, offset),
                timeout_sec=5,
            )
            freshness = check_data_freshness(cur, "analyst_sentiment_analysis", "date", warning_days=7)
            sentiment_data_result = list_response(
                [safe_json_serialize(dict(s)) for s in sentiment] if sentiment else [],
                data_freshness=freshness,
            )
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("sentiment", sentiment_data_result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return error_response(500, "response_validation_error", error_msg or "Sentiment data validation failed")
            return sentiment_data_result
        elif path == "/api/sentiment/divergence":
            rows = execute_with_timeout(
                cur,
                """
                    SELECT asa.symbol, asa.date,
                           asa.bullish_count, asa.bearish_count, asa.analyst_count,
                           asa.upside_downside_percent,
                           ROUND(asa.bullish_count::numeric / NULLIF(asa.analyst_count, 0) * 100, 2) AS bull_percent,
                           ROUND(asa.bearish_count::numeric / NULLIF(asa.analyst_count, 0) * 100, 2) AS bear_percent,
                           ss.composite_score
                    FROM analyst_sentiment_analysis asa
                    LEFT JOIN stock_scores ss ON ss.symbol = asa.symbol
                    WHERE asa.date >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY asa.date DESC, asa.upside_downside_percent DESC NULLS LAST
                    LIMIT 2000
                """,
                timeout_sec=5,
            )
            freshness = check_data_freshness(cur, "analyst_sentiment_analysis", "date", warning_days=7)
            divergence_result = list_response(
                [safe_json_serialize(dict(r)) for r in rows] if rows else [],
                data_freshness=freshness,
            )
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("sentiment", divergence_result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return error_response(
                    500, "response_validation_error", error_msg or "Sentiment divergence validation failed"
                )
            return divergence_result
        elif path.startswith("/api/sentiment/analyst/insights/"):
            symbol = path.split("/api/sentiment/analyst/insights/")[-1].upper()
            # Validate symbol format: max 5 chars, alphanumeric + dash only
            if not symbol or len(symbol) > 5 or not all(c.isalnum() or c == "-" for c in symbol):
                return error_response(400, "bad_request", "Invalid symbol format")
            rows = execute_with_timeout(
                cur,
                """
                    SELECT date, analyst_count, bullish_count, bearish_count, neutral_count,
                           target_price, current_price, upside_downside_percent
                    FROM analyst_sentiment_analysis
                    WHERE symbol = %s
                    ORDER BY date DESC
                    LIMIT 12
                """,
                (symbol,),
                timeout_sec=3,
            )
            latest = DatabaseResultValidator.safe_get_first_row(rows, "analyst sentiment metrics")
            if not latest:
                return json_response(
                    200,
                    {
                        "metrics": None,
                        "priceTargets": [],
                        "momentum": None,
                        "coverage": None,
                        "recentUpgrades": [],
                    },
                )
            # Use latest row for metrics summary
            latest = dict(latest)
            total_val = latest.get("analyst_count")
            bull_val = latest.get("bullish_count")
            bear_val = latest.get("bearish_count")
            neut_val = latest.get("neutral_count")
            total = int(total_val) if total_val is not None else 0
            bull = int(bull_val) if bull_val is not None else 0
            bear = int(bear_val) if bear_val is not None else 0
            neut = int(neut_val) if neut_val is not None else 0
            bp = round(bull / total * 100, 1) if total > 0 else None
            bep = round(bear / total * 100, 1) if total > 0 else None
            np_ = round(neut / total * 100, 1) if total > 0 else None
            metrics = {
                "totalAnalysts": total,
                "bullish": bull,
                "bearish": bear,
                "neutral": neut,
                "bullishPercent": bp,
                "bearishPercent": bep,
                "neutralPercent": np_,
                "avgPriceTarget": (float(latest["target_price"]) if latest.get("target_price") else None),
                "priceTargetVsCurrent": (
                    float(latest["upside_downside_percent"]) if latest.get("upside_downside_percent") else None
                ),
                "consensus": (
                    (
                        "Strong Buy"
                        if bp and bp > 70
                        else ("Buy" if bp and bp > 55 else "Sell" if bep and bep > 55 else "Hold")
                    )
                    if total > 0
                    else None
                ),
            }
            price_targets = [
                {
                    "date": str(dict(r)["date"]),
                    "target": (float(dict(r)["target_price"]) if dict(r).get("target_price") else None),
                }
                for r in rows
                if dict(r).get("target_price")
            ]
            freshness = check_data_freshness(cur, "analyst_sentiment_analysis", "date", warning_days=7)
            analyst_result = {
                "metrics": metrics,
                "priceTargets": price_targets,
                "momentum": None,
                "coverage": None,
                "recentUpgrades": [],
                "data_freshness": freshness,
            }
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("sentiment", analyst_result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return error_response(
                    500, "response_validation_error", error_msg or "Analyst sentiment validation failed"
                )
            return json_response(200, analyst_result)
        elif path.startswith("/api/sentiment/social/insights/"):
            symbol = path.split("/api/sentiment/social/insights/")[-1].upper()
            if not symbol or len(symbol) > 5 or not all(c.isalnum() or c == "-" for c in symbol):
                return error_response(400, "bad_request", "Invalid symbol format")
            cur.execute("SET LOCAL statement_timeout = '3000ms'")
            cur.execute(
                """
                    SELECT date, analyst_count, bullish_count, bearish_count, neutral_count,
                           target_price, current_price, upside_downside_percent
                    FROM analyst_sentiment_analysis
                    WHERE symbol = %s
                    ORDER BY date DESC
                    LIMIT 12
                """,
                (symbol,),
            )
            rows = cur.fetchall()
            latest = DatabaseResultValidator.safe_get_first_row(rows, "analyst sentiment trends")
            if not latest:
                return json_response(
                    200,
                    {
                        "sentiment": None,
                        "priceTargets": [],
                        "coverage": None,
                        "momentum": None,
                        "recentTrends": [],
                    },
                )
            latest = dict(latest)
            total_val = latest.get("analyst_count")
            bull_val = latest.get("bullish_count")
            bear_val = latest.get("bearish_count")
            neut_val = latest.get("neutral_count")
            total = int(total_val) if total_val is not None else 0
            bull = int(bull_val) if bull_val is not None else 0
            bear = int(bear_val) if bear_val is not None else 0
            neut = int(neut_val) if neut_val is not None else 0
            bp = round(bull / total * 100, 1) if total and total > 0 else None
            bep = round(bear / total * 100, 1) if total and total > 0 else None
            np_ = round(neut / total * 100, 1) if total and total > 0 else None
            sentiment_data = {
                "totalAnalysts": total,
                "bullish": bull,
                "bearish": bear,
                "neutral": neut,
                "bullishPercent": bp,
                "bearishPercent": bep,
                "neutralPercent": np_,
                "avgPriceTarget": (float(latest["target_price"]) if latest.get("target_price") else None),
                "priceTargetVsCurrent": (
                    float(latest["upside_downside_percent"]) if latest.get("upside_downside_percent") else None
                ),
                "sentiment": (
                    (
                        "Very Bullish"
                        if bp and bp > 70
                        else ("Bullish" if bp and bp > 55 else "Bearish" if bep and bep > 55 else "Neutral")
                    )
                    if total and total > 0
                    else None
                ),
            }
            price_targets = [
                {
                    "date": str(dict(r)["date"]),
                    "target": (float(dict(r)["target_price"]) if dict(r).get("target_price") else None),
                }
                for r in rows
                if dict(r).get("target_price")
            ]
            social_result = {
                "sentiment": sentiment_data,
                "priceTargets": price_targets,
                "coverage": {"totalAnalysts": total} if total else None,
                "momentum": None,
                "recentTrends": [],
            }
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("sentiment", social_result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return error_response(
                    500, "response_validation_error", error_msg or "Social sentiment validation failed"
                )
            return json_response(200, social_result)
        elif path == "/api/sentiment/vix":
            return _get_vix_data(cur)
        elif path == "/api/sentiment" or path.startswith("/api/sentiment?"):
            # Default: return same shape as /api/sentiment/summary
            cur.execute("""
                    SELECT fg.fear_greed_value, fg.fear_greed_label, fg.date,
                           mh.put_call_ratio, mh.vix_level
                    FROM fear_greed_index fg
                    LEFT JOIN market_health_daily mh ON mh.date = fg.date
                    ORDER BY fg.date DESC
                    LIMIT 1
                """)
            row = cur.fetchone()
            if row:
                default_result = {
                    "fear_greed": (
                        {
                            "value": float(row["fear_greed_value"]),
                            "label": row["fear_greed_label"],
                        }
                        if row["fear_greed_value"]
                        else None
                    ),
                    "put_call_ratio": (float(row["put_call_ratio"]) if row["put_call_ratio"] else None),
                    "vix_level": (float(row["vix_level"]) if row["vix_level"] else None),
                    "date": str(row["date"]),
                }
                is_valid, error_msg = ResponseValidator.validate_endpoint_response("sentiment", default_result)
                if not is_valid:
                    logger.error(f"Endpoint response validation failed: {error_msg}")
                    return error_response(
                        500, "response_validation_error", error_msg or "Default sentiment validation failed"
                    )
                return json_response(200, default_result)
            return error_response(503, "no_data", "Sentiment data not available")
        return error_response(404, "not_found", f"No sentiment handler for {path}")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"Sentiment route error in {path} - {type(e).__name__}: {e}",
            extra={"operation": "get sentiment data"},
        )
        code, error_type, message = handle_db_error(e, "get sentiment data")
        return error_response(code, error_type, message)


def _get_vix_data(cur) -> dict[str, Any]:
    """Get latest VIX data and historical trend."""
    try:
        cur.execute("""
                SELECT date, vix_level, put_call_ratio, market_trend, market_stage
                FROM market_health_daily
                WHERE vix_level IS NOT NULL
                ORDER BY date DESC
                LIMIT 60
            """)
        rows = cur.fetchall()

        if not rows:
            return error_response(503, "no_data", "Market sentiment data not yet available")

        latest = safe_json_serialize(dict(rows[0])) if rows else None
        history = [safe_json_serialize(dict(r)) for r in rows]

        if latest:
            if "vix_level" not in latest:
                logger.warning(
                    f"Market sentiment calculation: vix_level missing from latest data {latest}. "
                    "Cannot compute market sentiment without VIX level (required for fear/greed calculation)."
                )
                signal = None
            elif latest["vix_level"] is None:
                logger.warning(
                    "Market sentiment calculation: vix_level is None. "
                    "Cannot compute market sentiment without VIX level (required for fear/greed calculation)."
                )
                signal = None
            else:
                vix = latest["vix_level"]
                if vix > 25:
                    signal = "fear"
                elif vix > 15:
                    signal = "neutral"
                else:
                    signal = "greed"
        else:
            signal = None

        vix_result = {"latest": latest, "history": history, "signal": signal}
        is_valid, error_msg = ResponseValidator.validate_endpoint_response("sentiment", vix_result)
        if not is_valid:
            logger.error(f"Endpoint response validation failed: {error_msg}")
            return error_response(500, "response_validation_error", error_msg or "VIX sentiment validation failed")
        return json_response(200, vix_result)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"VIX data error - {type(e).__name__}: {e}",
            extra={"operation": "get VIX data"},
        )
        code, error_type, message = handle_db_error(e, "get VIX data")
        return error_response(code, error_type, message)
