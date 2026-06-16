"""Route: algo"""

import psycopg2
import psycopg2.extras
import psycopg2.errors
import psycopg2.sql
from typing import Dict
import logging
import re
import json
import os
from datetime import datetime, timedelta, date, timezone
import boto3
from botocore.exceptions import ClientError
from pydantic import ValidationError

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from utils import (
    error_response,
    success_response,
    list_response,
    json_response,
    safe_limit,
    safe_days,
    safe_offset,
    handle_db_error,
    db_route_handler,
    check_data_freshness,
    safe_json_serialize,
    safe_dict_convert,
    normalize_to_utc_datetime,
)

from utils.rate_limiting import (
    check_admin_rate_limit,
    ADMIN_RATE_LIMITS,
    check_public_rate_limit,
    PUBLIC_RATE_LIMITS,
)
from utils.validation import (
    safe_float,
    safe_float_strict,
    safe_int,
    safe_int_strict,
    APIResponseValidator,
)
from models.requests import TradePreviewRequest, PreTradeImpactRequest
import math

logger = logging.getLogger(__name__)



@db_route_handler("get data quality")
def _get_data_quality(cur) -> Dict:
    """Get detailed data quality summary by table from latest data_patrol_log run."""
    try:
        # Get patrol log entries from last 24 hours
        cur.execute("""
                SELECT
                    target_table AS table_name,
                    severity,
                    message,
                    NULL AS data_detail,
                    created_at,
                    ROW_NUMBER() OVER (PARTITION BY target_table ORDER BY created_at DESC) as rn
                FROM data_patrol_log
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            """)
        patrol_rows = cur.fetchall()

        if not patrol_rows:
            return json_response(
                200,
                {
                    "accuracy_check": "no_data",
                    "last_check": None,
                    "tables": [],
                    "summary": {
                        "critical": 0,
                        "errors": 0,
                        "warnings": 0,
                        "healthy": 0,
                    },
                },
            )

        # Organize by table, keeping latest status per table
        tables_dict = {}
        for row in patrol_rows:
            row_dict = safe_json_serialize(safe_dict_convert(row))
            if row_dict.get("rn") == 1:  # Latest entry per table
                table_name = row_dict.get("table_name", "unknown")
                tables_dict[table_name] = row_dict

        # Get latest timestamp
        latest_ts = max([r["created_at"] for r in patrol_rows]) if patrol_rows else None

        # Compute summary
        severity_counts = {"critical": 0, "error": 0, "warn": 0, "healthy": 0}
        table_statuses = []
        for table_name, entry in tables_dict.items():
            severity = entry.get("severity", "healthy")
            severity_counts[severity if severity in severity_counts else "warn"] += 1
            if severity == "critical":
                status_label = "failed"
            elif severity in ("error", "warn"):
                status_label = "warning"
            else:
                status_label = "passed"

            table_statuses.append(
                {
                    "table": table_name,
                    "status": status_label,
                    "severity": severity,
                    "message": entry.get("message"),
                    "detail": entry.get("data_detail"),
                    "last_check": (
                        entry.get("created_at") if entry.get("created_at") else None
                    ),
                }
            )

        # Determine overall accuracy
        if severity_counts["critical"] > 0:
            accuracy = "failed"
        elif severity_counts["error"] > 0:
            accuracy = "error"
        elif severity_counts["warn"] > 0:
            accuracy = "warning"
        else:
            accuracy = "passed"

        # Sort tables by status severity
        status_order = {"failed": 0, "error": 1, "warning": 2, "passed": 3}
        table_statuses.sort(key=lambda x: status_order.get(x["status"], 4))

        return json_response(
            200,
            {
                "accuracy_check": accuracy,
                "last_check": latest_ts.isoformat() if latest_ts else None,
                "tables": table_statuses,
                "summary": {
                    "critical": severity_counts["critical"],
                    "errors": severity_counts["error"],
                    "warnings": severity_counts["warn"],
                    "healthy": severity_counts["healthy"],
                    "total_tables_checked": len(tables_dict),
                },
            },
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "check data quality")
        logger.error(f"Failed to check data quality: {error_type} - {message}")
        return error_response(code, error_type, message)



@db_route_handler("fetch data status")
def _get_data_status(cur) -> Dict:
    """Get data freshness status with summary for ServiceHealth/AlgoTradingDashboard.

    Uses same trading-day-aware freshness logic as Phase 1 orchestrator to avoid
    false stale warnings on Monday holidays or 3-day weekends.
    """
    try:
        from algo.infrastructure import MarketCalendar
        try:
            from utils.validation.freshness_config import FRESHNESS_RULES as _FR
        except ImportError:
            _FR = {}

        # Tables intentionally removed from the EOD pipeline — orchestrator Phase 5
        # computes these signals on-the-fly. Excluding them prevents permanent false-stale
        # alerts on the health panel (they will never be refreshed again by a loader).
        PIPELINE_REMOVED_TABLES = {"technical_data_daily", "buy_sell_daily", "signal_quality_scores"}

        cur.execute("""
                SELECT table_name, row_count, last_updated
                FROM data_loader_status
                ORDER BY table_name
            """)
        loader_rows = [dict(r) for r in cur.fetchall() if r["table_name"] not in PIPELINE_REMOVED_TABLES]
        loader_names = {r["table_name"] for r in loader_rows}

        # Algo-generated tables written by the orchestrator, not tracked in data_loader_status
        algo_rows = []
        for tbl_name, query in [
            ("algo_portfolio_snapshots", "SELECT COUNT(*) AS row_count, MAX(snapshot_date) AS last_updated FROM algo_portfolio_snapshots"),
            ("algo_performance_daily", "SELECT COUNT(*) AS row_count, MAX(report_date) AS last_updated FROM algo_performance_daily"),
            ("algo_risk_daily", "SELECT COUNT(*) AS row_count, MAX(report_date) AS last_updated FROM algo_risk_daily"),
        ]:
            if tbl_name in loader_names:
                continue
            try:
                cur.execute(query)
                r = cur.fetchone()
                if r:
                    algo_rows.append({"table_name": tbl_name, "row_count": r["row_count"], "last_updated": r["last_updated"]})
            except Exception:
                pass

        rows = loader_rows + algo_rows

        # Use freshness_config critical set; fall back to Phase 1 halt tables if unavailable.
        # Note: trend_template_data is warning-only in Phase 1 — stale does NOT prevent
        # trading, so it remains non-critical even though freshness_config marks it otherwise.
        CRITICAL_TABLES = {t for t, r in _FR.items() if r.get("critical")} or {
            "price_daily", "market_health_daily", "market_exposure_daily"
        }

        # Compute expected data date using trading-day-aware logic (match Phase 1)
        today = date.today()
        expected_date = today - timedelta(days=1)
        try:
            for _ in range(10):
                if MarketCalendar.is_trading_day(expected_date):
                    break
                expected_date -= timedelta(days=1)
        except Exception:
            # Fallback: weekday check if MarketCalendar unavailable
            while expected_date.weekday() >= 5:
                expected_date -= timedelta(days=1)

        sources = []
        summary = {"ok": 0, "stale": 0, "empty": 0, "error": 0}
        critical_stale = []

        for row in rows:
            last_updated = row["last_updated"]
            row_count = row.get("row_count")

            if row_count is None or row_count == 0:
                status = "empty"
            elif last_updated is None:
                status = "empty"
            else:
                data_date = (
                    last_updated.date()
                    if hasattr(last_updated, "date")
                    else last_updated
                )
                rule = _FR.get(row["table_name"], {})
                max_age = rule.get("max_age_days", 1)
                if max_age <= 1:
                    # Daily tables: use trading-day-aware comparison
                    status = "stale" if data_date < expected_date else "ok"
                else:
                    # Weekly/biweekly tables: use simple calendar-day age threshold
                    status = "stale" if (today - data_date).days > max_age else "ok"

            # Calculate age in hours for display
            last_updated_utc = normalize_to_utc_datetime(last_updated)
            if last_updated_utc:
                age_h = (
                    datetime.now(timezone.utc) - last_updated_utc
                ).total_seconds() / 3600
            else:
                age_h = 999

            rule = _FR.get(row["table_name"], {})
            if rule.get("critical"):
                role = "CRIT"
            elif rule.get("max_age_days", 999) <= 7:
                role = "IMP"
            else:
                role = "NORM"

            summary[status] = summary.get(status, 0) + 1
            if status in ("stale", "empty") and row["table_name"] in CRITICAL_TABLES:
                critical_stale.append(row["table_name"])
            sources.append(
                {
                    "name": row["table_name"],
                    "role": role,
                    "status": status,
                    "last_updated": last_updated.isoformat() if last_updated else None,
                    "age_hours": round(age_h, 1),
                    "row_count": row_count,
                }
            )

        ready_to_trade = len(critical_stale) == 0 and summary.get("ok", 0) > 0

        return json_response(
            200,
            {
                "ready_to_trade": ready_to_trade,
                "summary": summary,
                "sources": sources,
                "critical_stale": critical_stale,
                "expected_date": str(expected_date),
                "as_of": datetime.now(timezone.utc).isoformat(),
            },
        )
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
        logger.error(
            f"Data unavailable (data status): {type(e).__name__}: {str(e)}",
            extra={"operation": "fetch data status"},
            exc_info=True,
        )
        return error_response(503, "service_unavailable", "Data unavailable")
    except psycopg2.OperationalError as e:
        logger.error(
            f"Database connection error (data status): {type(e).__name__}: {str(e)}",
            extra={"operation": "fetch data status"},
            exc_info=True,
        )
        return error_response(503, "service_unavailable", "Database unavailable")
    except psycopg2.DatabaseError as e:
        logger.error(
            f"Database error (data status): {type(e).__name__}: {str(e)}",
            extra={"operation": "fetch data status"},
            exc_info=True,
        )
        return error_response(500, "internal_error", "Database query failed")
    except Exception as e:
        logger.error(
            f"Unexpected error (data status): {type(e).__name__}: {str(e)}",
            extra={"operation": "fetch data status"},
            exc_info=True,
        )
        return error_response(500, "internal_error", "Failed to fetch data status")



@db_route_handler("get market")
def _get_market(cur) -> Dict:
    """Get simplified market data for dashboard. Returns market_health_daily + exposure data."""
    try:
        cur.execute("SET LOCAL statement_timeout = '8000ms'")

        # Fetch market health: 11 fields from market_health_daily
        cur.execute("""
            SELECT market_trend, market_stage, vix_level,
                   up_volume_percent, advance_decline_ratio, new_highs_count,
                   new_lows_count, breadth_momentum_10d, put_call_ratio,
                   yield_curve_slope, fed_rate_environment
            FROM market_health_daily
            ORDER BY date DESC LIMIT 1
        """)
        mh = cur.fetchone()
        market_health = safe_json_serialize(safe_dict_convert(mh)) if mh else {}

        # Fetch exposure data and distribution days from market_exposure_daily
        cur.execute("""
            SELECT exposure_pct, regime, halt_reasons, distribution_days
            FROM market_exposure_daily
            ORDER BY date DESC LIMIT 1
        """)
        exp = cur.fetchone()
        exposure = safe_json_serialize(safe_dict_convert(exp)) if exp else {}

        # Parse JSON strings from database (halt_reasons is stored as JSON text)
        if exposure and exposure.get("halt_reasons"):
            try:
                exposure["halt_reasons"] = (
                    json.loads(exposure["halt_reasons"])
                    if isinstance(exposure["halt_reasons"], str)
                    else exposure["halt_reasons"]
                )
            except (json.JSONDecodeError, TypeError):
                exposure["halt_reasons"] = []
        else:
            exposure["halt_reasons"] = []

        # Fetch SPY close price
        spy_close = None
        try:
            cur.execute("""
                SELECT close FROM price_daily
                WHERE symbol = 'SPY'
                ORDER BY date DESC LIMIT 1
            """)
            spy_row = cur.fetchone()
            if spy_row:
                spy_close = safe_float(spy_row["close"]) if spy_row["close"] else None
        except Exception as e:
            logger.warning(f"[MARKET] SPY price unavailable: {e}")

        # Combine all data in the format the dashboard expects
        # Use safe_float_strict/safe_int_strict for optional numeric fields so the dashboard
        # can distinguish between NULL (data not available) and 0 (actual zero value)
        data = {
            "exposure_pct": safe_float(exposure.get("exposure_pct")),
            "regime": exposure.get("regime"),
            "halt_reasons": exposure.get("halt_reasons") or [],
            "vix_level": safe_float_strict(
                market_health.get("vix_level"), context="market_health.vix_level"
            ),
            "market_stage": safe_int_strict(
                market_health.get("market_stage"), context="market_health.market_stage"
            ),
            "market_trend": market_health.get("market_trend"),
            "distribution_days_4w": safe_int_strict(
                exposure.get("distribution_days"), context="exposure.distribution_days"
            ),
            "spy_close": spy_close,
            "spy_change_pct": safe_float_strict(
                market_health.get("spy_change_pct"),
                context="market_health.spy_change_pct",
            ),
            "up_volume_percent": safe_float_strict(
                market_health.get("up_volume_percent"),
                context="market_health.up_volume_percent",
            ),
            "advance_decline_ratio": safe_float_strict(
                market_health.get("advance_decline_ratio"),
                context="market_health.advance_decline_ratio",
            ),
            "new_highs_count": safe_int_strict(
                market_health.get("new_highs_count"),
                context="market_health.new_highs_count",
            ),
            "new_lows_count": safe_int_strict(
                market_health.get("new_lows_count"),
                context="market_health.new_lows_count",
            ),
            "put_call_ratio": safe_float_strict(
                market_health.get("put_call_ratio"),
                context="market_health.put_call_ratio",
            ),
            "breadth_momentum_10d": safe_float_strict(
                market_health.get("breadth_momentum_10d"),
                context="market_health.breadth_momentum_10d",
            ),
            "yield_curve_slope": safe_float_strict(
                market_health.get("yield_curve_slope"),
                context="market_health.yield_curve_slope",
            ),
            "fed_rate_environment": market_health.get("fed_rate_environment"),
        }

        return json_response(200, data)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"Failed to fetch market: {type(e).__name__}: {e}\n  Operation: Query market_health_daily with date filter\n  Endpoint: GET /api/algo/market"
        )
        return error_response(503, "service_unavailable", "Failed to fetch market data")



@db_route_handler("get market factors")
def _get_market_factors(cur) -> Dict:
    """Get market exposure factors for dashboard display."""
    try:
        cur.execute("SET LOCAL statement_timeout = '8000ms'")

        # Fetch exposure factors from market_exposure_daily
        cur.execute("""
            SELECT exposure_pct, raw_score, regime, factors
            FROM market_exposure_daily
            ORDER BY date DESC LIMIT 1
        """)
        row = cur.fetchone()

        if not row:
            return json_response(
                200,
                {
                    "exposure_pct": None,
                    "raw_score": None,
                    "regime": None,
                    "factors": {},
                },
            )

        data_dict = safe_json_serialize(safe_dict_convert(row))

        # Parse factors if it's a JSON string
        factors = {}
        if data_dict.get("factors"):
            try:
                factors_val = data_dict.get("factors")
                if isinstance(factors_val, str):
                    factors = json.loads(factors_val)
                else:
                    factors = factors_val if isinstance(factors_val, dict) else {}
            except Exception as e:
                logger.warning(f"[MARKET_FACTORS] Failed to parse factors: {e}")
                factors = {}

        data = {
            "exposure_pct": safe_float(data_dict.get("exposure_pct")),
            "raw_score": safe_float(data_dict.get("raw_score")),
            "regime": data_dict.get("regime"),
            "factors": factors,
        }

        return json_response(200, data)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"Failed to fetch market factors: {type(e).__name__}: {e}\n  Operation: Calculate market exposure factors\n  Endpoint: GET /api/algo/market-factors"
        )
        return error_response(
            503, "service_unavailable", "Failed to fetch market factors"
        )



@db_route_handler("get market sentiment")
def _get_market_sentiment(cur) -> Dict:
    """Return latest market sentiment score and trend."""
    # market_sentiment view provides: date, fear_greed_index, label, put_call_ratio, vix, sentiment_score
    cur.execute("""
        SELECT sentiment_score,
               COALESCE(put_call_ratio, NULL::numeric) AS bullish_pct,
               COALESCE(vix, NULL::numeric) AS bearish_pct,
               NULL::numeric AS neutral_pct,
               date
        FROM market_sentiment
        ORDER BY date DESC
        LIMIT 1
    """)
    row = cur.fetchone()

    if not row:
        return error_response(503, "no_data", "Market sentiment data not yet available")

    if not row.get("sentiment_score"):
        return error_response(
            503, "incomplete_data", "Market sentiment data incomplete"
        )

    sentiment_score = safe_float(row["sentiment_score"])
    bullish = None  # Not available in market_sentiment view
    bearish = None  # Not available in market_sentiment view
    neutral = None  # Not available in market_sentiment view

    trend = None
    if sentiment_score is not None:
        if sentiment_score > 60:
            trend = "BULLISH"
        elif sentiment_score > 40:
            trend = "NEUTRAL"
        else:
            trend = "BEARISH"

    return json_response(
        200,
        {
            "sentiment": round(sentiment_score, 2) if sentiment_score else None,
            "trend": trend,
            "bullish_pct": round(bullish, 1) if bullish else None,
            "bearish_pct": round(bearish, 1) if bearish else None,
            "neutral_pct": round(neutral, 1) if neutral else None,
        },
    )



@db_route_handler("get markets")
def _get_markets(cur) -> Dict:
    """Get market regime, exposure, and 12-factor data for the Markets Health dashboard."""
    try:
        # Latest exposure row
        cur.execute("""
                SELECT date, exposure_pct, raw_score, regime, factors, halt_reasons, distribution_days
                FROM market_exposure_daily
                ORDER BY date DESC
                LIMIT 1
            """)
        row = cur.fetchone()

        if not row:
            return json_response(
                200, {"current": None, "active_tier": None, "history": []}
            )

        row = safe_json_serialize(safe_dict_convert(row))

        halt_reasons = []
        if row.get("halt_reasons"):
            try:
                halt_reasons = (
                    json.loads(row["halt_reasons"])
                    if isinstance(row["halt_reasons"], str)
                    else row["halt_reasons"]
                )
            except (json.JSONDecodeError, TypeError):
                halt_reasons = []

        factors = {}
        if row.get("factors"):
            try:
                factors = (
                    json.loads(row["factors"])
                    if isinstance(row["factors"], str)
                    else row["factors"]
                )
            except (json.JSONDecodeError, TypeError):
                factors = {}

        tier_key = str(row.get("regime") or "").lower()
        tier_conf = _TIER_CONFIG.get(tier_key, {})
        active_tier = {"name": tier_key, **tier_conf}
        active_tier["halt"] = bool(halt_reasons) or tier_conf.get("halt", False)

        # History: last 90 sessions for ExposureHistory chart
        cur.execute("""
                SELECT date, exposure_pct, regime, distribution_days
                FROM market_exposure_daily
                ORDER BY date DESC
                LIMIT 90
            """)
        history = []
        for h in cur.fetchall():
            h = safe_json_serialize(safe_dict_convert(h))
            d = h.get("date")
            history.append(
                {
                    "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
                    "exposure_pct": (
                        float(h["exposure_pct"])
                        if h.get("exposure_pct") is not None
                        else None
                    ),
                    "regime": h.get("regime"),
                    "distribution_days": h.get("distribution_days"),
                }
            )

        # Sector rankings for SectorRotationMap
        sectors = []
        try:
            cur.execute("""
                    SELECT sector_name AS name, current_rank AS rank, rank_4w_ago, momentum_score AS momentum
                    FROM sector_ranking
                    WHERE date = (SELECT MAX(date) FROM sector_ranking)
                    ORDER BY current_rank ASC NULLS LAST
                """)
            for sr in cur.fetchall():
                sr = safe_json_serialize(safe_dict_convert(sr))
                sectors.append(
                    {
                        "name": sr.get("name"),
                        "rank": sr.get("rank"),
                        "rank_4w_ago": sr.get("rank_4w_ago"),
                        "momentum": (
                            float(sr["momentum"])
                            if sr.get("momentum") is not None
                            else None
                        ),
                    }
                )
        except Exception as se:
            logger.warning(f"Could not fetch sector rankings: {se}")

        # Fetch market health from market_health_daily for dashboard KPIs
        market_health = {}
        try:
            cur.execute("""
                    SELECT market_trend, market_stage, vix_level, spy_change_pct,
                           up_volume_percent, advance_decline_ratio, new_highs_count,
                           new_lows_count, breadth_momentum_10d, put_call_ratio,
                           yield_curve_slope, fed_rate_environment
                    FROM market_health_daily
                    ORDER BY date DESC LIMIT 1
                """)
            mh_row = cur.fetchone()
            if mh_row:
                market_health = safe_json_serialize(safe_dict_convert(mh_row))
        except Exception as mhe:
            logger.warning(f"Could not fetch market_health_daily: {mhe}")

        # Fetch latest SPY close for dashboard header
        spy_close = None
        try:
            cur.execute("""
                SELECT close FROM price_daily
                WHERE symbol = 'SPY'
                ORDER BY date DESC LIMIT 1
            """)
            spy_row = cur.fetchone()
            if spy_row:
                spy_close = safe_float(spy_row["close"]) if spy_row["close"] else None
        except Exception as spy_e:
            logger.warning(f"Could not fetch SPY price: {spy_e}")

        current_date = row.get("date")

        # Validate vix_regime is present in factors; log if missing
        if "vix_regime" not in factors:
            logger.warning(
                f"[MARKETS API] vix_regime missing from factors for {current_date}: "
                f"market exposure computation may not have run or vix_regime computation failed. "
                f"Check market_exposure_daily and load_market_exposure_daily logs."
            )
        elif factors.get("vix_regime", {}).get("value") is None:
            logger.warning(
                f"[MARKETS API] VIX value is None in vix_regime for {current_date}: "
                f"VIX fetch from ^VIX or market_health_daily returned no data. "
                f"Check load_market_health_daily logs and yfinance availability."
            )

        return json_response(
            200,
            {
                "current": {
                    "exposure_pct": (
                        float(row["exposure_pct"])
                        if row.get("exposure_pct") is not None
                        else None
                    ),
                    "raw_score": (
                        float(row["raw_score"])
                        if row.get("raw_score") is not None
                        else None
                    ),
                    "regime": row.get("regime"),
                    "halt_reasons": halt_reasons,
                    "distribution_days": row.get("distribution_days", 0),
                    "factors": factors,
                    "spy_close": spy_close,
                    "date": (
                        current_date.isoformat()
                        if hasattr(current_date, "isoformat")
                        else str(current_date)
                    ),
                },
                "active_tier": active_tier,
                "history": history,
                "sectors": sectors,
                "market_health": market_health,
            },
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"Failed to fetch markets: {type(e).__name__}: {e}\n  Operation: Query market_exposure_daily\n  Endpoint: GET /api/algo/markets"
        )
        return error_response(
            503, "service_unavailable", "Failed to fetch markets data"
        )



@db_route_handler("get trend criteria")
def _get_trend_criteria(cur) -> Dict:
    """Return trend criteria analysis with passing count from actual data."""
    cur.execute("""
        SELECT
            COUNT(*) as total_symbols,
            COUNT(*) FILTER (WHERE price_above_sma50 = true) as above_sma50,
            COUNT(*) FILTER (WHERE sma50_above_sma200 = true) as sma50_above_sma200,
            COUNT(*) FILTER (WHERE price_above_sma200 = true) as above_sma200,
            COUNT(*) FILTER (WHERE weinstein_stage = 2) as stage2
        FROM trend_template_data
        WHERE date = (SELECT MAX(date) FROM trend_template_data)
    """)
    row = cur.fetchone()
    if not row or safe_int(row["total_symbols"]) == 0:
        return error_response(503, "no_data", "Trend template data not yet available")

    total_symbols = safe_int(row["total_symbols"])
    criteria = [
        {"name": "Price Above 50-Day MA", "passing": safe_int(row["above_sma50"]), "total": total_symbols},
        {"name": "50-Day Above 200-Day MA", "passing": safe_int(row["sma50_above_sma200"]), "total": total_symbols},
        {"name": "Price Above 200-Day MA", "passing": safe_int(row["above_sma200"]), "total": total_symbols},
        {"name": "Stage 2 Uptrend (Weinstein)", "passing": safe_int(row["stage2"]), "total": total_symbols},
    ]

    return json_response(200, {"criteria": criteria, "total_symbols": total_symbols})



