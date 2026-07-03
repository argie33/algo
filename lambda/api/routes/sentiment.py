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
    extract_param,
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


def handle(  # noqa: C901
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
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
            if not fg_rows:
                raise RuntimeError(
                    "Sentiment endpoint requires fear_greed_index data but table is empty. "
                    "Cannot provide sentiment analysis without fear/greed index. "
                    "Check fear_greed_index table and data loader."
                )
            row = fg_rows[0]
            if not row or row.get("fear_greed_value") is None:
                raise RuntimeError(
                    "Sentiment endpoint requires fear_greed_value but data is NULL. "
                    "Cannot compute market sentiment without fear/greed metric. "
                    "Check data source and fetched row."
                )
            # FAIL-FAST: Extract required fields upfront, fail if missing/invalid
            fg_value = DatabaseResultValidator.safe_get_float(row, "fear_greed_value", strict=True)
            fg_label = DatabaseResultValidator.safe_get_str(row, "fear_greed_label", strict=True)
            if not fg_label:
                raise RuntimeError(
                    "Sentiment endpoint requires fear_greed_label but data is missing/NULL. "
                    "Cannot provide sentiment classification without label. "
                    "Check fear_greed_index data or API."
                )

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

            # FAIL-FAST: Extract market health data upfront with safe validation
            put_call = DatabaseResultValidator.safe_get_float(row, "put_call_ratio", default=None)
            vix = DatabaseResultValidator.safe_get_float(row, "vix_level", default=None)
            date_val = DatabaseResultValidator.safe_get_str(row, "date", default=None)

            freshness = check_data_freshness(cur, "fear_greed_index", "date", warning_days=1)
            sentiment_result = {
                "fear_greed": ({"value": fg_value, "label": fg_label} if fg_value is not None else None),
                "aaii": safe_json_serialize(dict(aaii_row)) if aaii_row else None,
                "naaim": (safe_json_serialize(dict(naaim_row)) if naaim_row else None),
                "analyst": (
                    safe_json_serialize(dict(analyst_row)) if analyst_row and analyst_row.get("analyst_count") else None
                ),
                "put_call_ratio": put_call,
                "vix_level": vix,
                "date": date_val,
                "data_freshness": freshness,
            }
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("sentiment", sentiment_result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return error_response(500, "response_validation_error", error_msg or "Sentiment validation failed")
            return json_response(200, sentiment_result)
        elif path == "/api/sentiment/data" or path.startswith("/api/sentiment/data?"):
            limit = safe_limit(extract_param(params, "limit"), max_val=50000, default=50000)
            page = safe_page(extract_param(params, "page"), default=1)
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
            if isinstance(latest, dict) and latest.get("data_unavailable"):
                return error_response(
                    503,
                    "service_unavailable",
                    f"Analyst sentiment data unavailable for {symbol} — no coverage in analyst_sentiment_analysis table",
                )
            # Use latest row for metrics summary
            latest = dict(latest)
            total_val = latest.get("analyst_count")
            bull_val = latest.get("bullish_count")
            bear_val = latest.get("bearish_count")
            neut_val = latest.get("neutral_count")

            # CRITICAL: Analyst counts must be present - fallback to 0 corrupts sentiment
            missing_fields = []
            if total_val is None:
                missing_fields.append("analyst_count")
            if bull_val is None:
                missing_fields.append("bullish_count")
            if bear_val is None:
                missing_fields.append("bearish_count")
            if neut_val is None:
                missing_fields.append("neutral_count")

            if missing_fields:
                logger.warning(
                    f"[SENTIMENT] Missing analyst count data: {', '.join(missing_fields)}. "
                    f"Sentiment metrics unavailable - not using fallback to 0."
                )
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"Missing analyst counts: {', '.join(missing_fields)}",
                    "lastUpdated": None,
                }

            try:
                total = int(total_val)
                bull = int(bull_val)
                bear = int(bear_val)
                neut = int(neut_val)
            except (ValueError, TypeError) as e:
                logger.error(f"[SENTIMENT] Invalid analyst count data: {e}")
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"Invalid analyst count format: {e!s}",
                    "lastUpdated": None,
                }

            if total <= 0:
                logger.warning(f"[SENTIMENT] Invalid analyst total {total} (must be > 0)")
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"Invalid analyst total: {total}",
                    "lastUpdated": None,
                }

            bp = round(bull / total * 100, 1)
            bep = round(bear / total * 100, 1)
            np_ = round(neut / total * 100, 1)
            # FAIL-FAST: Extract optional price target fields upfront
            target_price = DatabaseResultValidator.safe_get_float(latest, "target_price", default=None)
            upside_downside = DatabaseResultValidator.safe_get_float(latest, "upside_downside_percent", default=None)

            metrics = {
                "totalAnalysts": total,
                "bullish": bull,
                "bearish": bear,
                "neutral": neut,
                "bullishPercent": bp,
                "bearishPercent": bep,
                "neutralPercent": np_,
                "avgPriceTarget": target_price,
                "priceTargetVsCurrent": upside_downside,
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
            # FAIL-FAST: Extract price target data with safe validation
            price_targets = []
            for r in rows:
                rd = dict(r)
                target = DatabaseResultValidator.safe_get_float(rd, "target_price", default=None)
                if target is not None:
                    date_str = DatabaseResultValidator.safe_get_str(rd, "date", default=None)
                    price_targets.append({
                        "date": date_str,
                        "target": target,
                    })
            freshness = check_data_freshness(cur, "analyst_sentiment_analysis", "date", warning_days=7)
            analyst_result = {
                "metrics": metrics,
                "priceTargets": price_targets,
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
            if isinstance(latest, dict) and latest.get("data_unavailable"):
                logger.warning("[SENTIMENT] No analyst sentiment trends available - data unavailable")
                return json_response(
                    200,
                    {
                        "data_unavailable": True,
                        "reason": "Analyst sentiment trends not yet available",
                        "sentiment": None,
                        "priceTargets": [],
                    },
                )
            latest = dict(latest)
            total_val = latest.get("analyst_count")
            bull_val = latest.get("bullish_count")
            bear_val = latest.get("bearish_count")
            neut_val = latest.get("neutral_count")

            # CRITICAL: Analyst counts must be present - fallback to 0 corrupts sentiment
            missing_fields = []
            if total_val is None:
                missing_fields.append("analyst_count")
            if bull_val is None:
                missing_fields.append("bullish_count")
            if bear_val is None:
                missing_fields.append("bearish_count")
            if neut_val is None:
                missing_fields.append("neutral_count")

            if missing_fields:
                logger.warning(
                    f"[SENTIMENT] Missing analyst count data: {', '.join(missing_fields)}. "
                    f"Sentiment metrics unavailable - not using fallback to 0."
                )
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"Missing analyst counts: {', '.join(missing_fields)}",
                    "lastUpdated": None,
                }

            try:
                total = int(total_val)
                bull = int(bull_val)
                bear = int(bear_val)
                neut = int(neut_val)
            except (ValueError, TypeError) as e:
                logger.error(f"[SENTIMENT] Invalid analyst count data: {e}")
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"Invalid analyst count format: {e!s}",
                    "lastUpdated": None,
                }

            if total <= 0:
                logger.warning(f"[SENTIMENT] Invalid analyst total {total} (must be > 0)")
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"Invalid analyst total: {total}",
                    "lastUpdated": None,
                }

            bp = round(bull / total * 100, 1)
            bep = round(bear / total * 100, 1)
            np_ = round(neut / total * 100, 1)

            # FAIL-FAST: Extract optional price target fields upfront
            target_price_social = DatabaseResultValidator.safe_get_float(latest, "target_price", default=None)
            upside_downside_social = DatabaseResultValidator.safe_get_float(latest, "upside_downside_percent", default=None)

            sentiment_data = {
                "totalAnalysts": total,
                "bullish": bull,
                "bearish": bear,
                "neutral": neut,
                "bullishPercent": bp,
                "bearishPercent": bep,
                "neutralPercent": np_,
                "avgPriceTarget": target_price_social,
                "priceTargetVsCurrent": upside_downside_social,
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
                    "target": (float(dict(r)["target_price"]) if dict(r).get("target_price") is not None else None),
                }
                for r in rows
                if dict(r).get("target_price")
            ]
            social_result = {
                "sentiment": sentiment_data,
                "priceTargets": price_targets,
                "coverage": {"totalAnalysts": total} if total else None,
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
            if not row:
                return error_response(
                    503, "no_data", "Sentiment data not available — fear_greed_index table empty or data not loaded"
                )
            if row["fear_greed_value"] is None:
                raise RuntimeError(
                    "Default sentiment endpoint requires fear_greed_value but data is NULL. "
                    "Cannot provide sentiment analysis without fear/greed metric. "
                    "Check fear_greed_index data loader."
                )
            if not row.get("fear_greed_label"):
                raise RuntimeError(
                    "Default sentiment endpoint requires fear_greed_label but data is missing/NULL. "
                    "Cannot provide sentiment classification without label. "
                    "Check fear_greed_index data or API."
                )
            default_result = {
                "fear_greed": {
                    "value": float(row["fear_greed_value"]),
                    "label": row["fear_greed_label"],
                },
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


def _get_vix_data(cur) -> Any:
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

        if not rows:
            return error_response(503, "no_data", "VIX data not available — market_health_daily table empty")

        latest = safe_json_serialize(dict(rows[0]))
        history = [safe_json_serialize(dict(r)) for r in rows]

        if not latest or "vix_level" not in latest or latest["vix_level"] is None:
            raise RuntimeError(
                "VIX data endpoint requires vix_level for signal calculation but data is missing/NULL. "
                "Cannot compute market sentiment without VIX level. "
                "Check market_health_daily table and data loader."
            )

        vix = latest["vix_level"]
        if vix > 25:
            signal = "fear"
        elif vix > 15:
            signal = "neutral"
        else:
            signal = "greed"

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
