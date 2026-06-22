"""Route: algo"""

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from psycopg2.extensions import cursor

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    db_route_handler,
    ensure_valid_response,
    error_response,
    handle_db_error,
    json_response,
    list_response,
    normalize_to_utc_datetime,
    safe_dict_convert,
    safe_json_serialize,
)

from shared_contracts.response_validator import ResponseValidator
from utils.validation import format_decimal_string

from .signals import _TIER_CONFIG

logger = logging.getLogger(__name__)


@db_route_handler("get data quality")
def _get_data_quality(cur: cursor) -> dict[str, Any]:
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
            response = list_response([], total=0, limit=None, offset=None)
            response["data"]["accuracy_check"] = "no_data"
            response["data"]["last_check"] = None
            response["data"]["summary"] = {
                "critical": 0,
                "errors": 0,
                "warnings": 0,
                "healthy": 0,
            }
            return response

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
                    "last_check": (entry.get("created_at") if entry.get("created_at") else None),
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

        response = list_response(table_statuses, total=len(table_statuses), limit=None, offset=None)
        response["data"]["accuracy_check"] = accuracy
        response["data"]["last_check"] = latest_ts.isoformat() if latest_ts else None
        response["data"]["summary"] = {
            "critical": severity_counts["critical"],
            "errors": severity_counts["error"],
            "warnings": severity_counts["warn"],
            "healthy": severity_counts["healthy"],
            "total_tables_checked": len(tables_dict),
        }
        return response
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "check data quality")
        logger.error(f"Failed to check data quality: {error_type} - {message}")
        return error_response(code, error_type, message)  # type: ignore[no-any-return]


@db_route_handler("fetch data status")
def _get_data_status(cur: cursor) -> dict[str, Any]:
    """Get data freshness status with summary for ServiceHealth/AlgoTradingDashboard.

    Uses same trading-day-aware freshness logic as Phase 1 orchestrator to avoid
    false stale warnings on Monday holidays or 3-day weekends.
    """
    try:
        from algo.infrastructure import MarketCalendar

        try:
            from utils.validation.freshness_config import FRESHNESS_RULES

            _fr = FRESHNESS_RULES
        except ImportError:
            _fr = {}

        # Tables intentionally removed from the EOD pipeline — orchestrator Phase 5
        # computes these signals on-the-fly. Excluding them prevents permanent false-stale
        # alerts on the health panel (they will never be refreshed again by a loader).
        pipeline_removed_tables = {
            "technical_data_daily",
            "buy_sell_daily",
            "signal_quality_scores",
        }

        cur.execute("""
                SELECT table_name, row_count, last_updated
                FROM data_loader_status
                ORDER BY table_name
            """)
        loader_rows = [dict(r) for r in cur.fetchall() if r["table_name"] not in pipeline_removed_tables]
        loader_names = {r["table_name"] for r in loader_rows}

        # Algo-generated tables written by the orchestrator, not tracked in data_loader_status
        algo_rows = []
        for tbl_name, query in [
            (
                "algo_portfolio_snapshots",
                "SELECT COUNT(*) AS row_count, MAX(snapshot_date) AS last_updated FROM algo_portfolio_snapshots",
            ),
            (
                "algo_performance_daily",
                "SELECT COUNT(*) AS row_count, MAX(report_date) AS last_updated FROM algo_performance_daily",
            ),
            (
                "algo_risk_daily",
                "SELECT COUNT(*) AS row_count, MAX(report_date) AS last_updated FROM algo_risk_daily",
            ),
        ]:
            if tbl_name in loader_names:
                continue
            try:
                cur.execute(query)
                r = cur.fetchone()
                if r:
                    algo_rows.append(
                        {
                            "table_name": tbl_name,
                            "row_count": r["row_count"],
                            "last_updated": r["last_updated"],
                        }
                    )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(f"Unexpected error: {e}") from e

        rows = loader_rows + algo_rows

        # Use freshness_config critical set; fall back to Phase 1 halt tables if unavailable.
        # Note: trend_template_data is warning-only in Phase 1 — stale does NOT prevent
        # trading, so it remains non-critical even though freshness_config marks it otherwise.
        critical_tables = {t for t, r in _fr.items() if r.get("critical")} or {
            "price_daily",
            "market_health_daily",
            "market_exposure_daily",
        }

        # Compute expected data date using trading-day-aware logic (match Phase 1)
        today = date.today()
        expected_date = today - timedelta(days=1)
        try:
            for _ in range(10):
                if MarketCalendar.is_trading_day(expected_date):
                    break
                expected_date -= timedelta(days=1)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            # Fail fast if MarketCalendar unavailable — weekday check is wrong for holidays
            raise RuntimeError(
                f"Data freshness check requires MarketCalendar: {e}. "
                f"Cannot accurately determine expected data date (weekday check ignores holidays). "
                f"Data freshness checks will have false positives/negatives if we continue."
            ) from e

        sources = []
        summary = {"ok": 0, "stale": 0, "empty": 0, "error": 0}
        critical_stale = []

        for row in rows:
            last_updated = row["last_updated"]
            row_count = row.get("row_count")

            # Get freshness rule once per table (consolidate lookups)
            rule = _fr.get(row["table_name"])
            table_name = row["table_name"]

            # Extract max_age with consistent default of 1 day for unknown tables
            max_age_raw = rule.get("max_age_days") if rule is not None else None
            if max_age_raw is None:
                max_age: int = 1
                if table_name in _fr:
                    logger.warning(f"Freshness rule for {table_name} missing max_age_days field")
            else:
                max_age = int(max_age_raw)

            if row_count is None or row_count == 0:
                status = "empty"
            elif last_updated is None:
                status = "empty"
            else:
                data_date = last_updated.date() if hasattr(last_updated, "date") else last_updated
                if max_age <= 1:
                    # Daily tables: use trading-day-aware comparison
                    status = "stale" if data_date < expected_date else "ok"
                else:
                    # Weekly/biweekly tables: use simple calendar-day age threshold
                    status = "stale" if (today - data_date).days > max_age else "ok"

            # Calculate age in hours for display
            last_updated_utc = normalize_to_utc_datetime(last_updated)
            if last_updated_utc:
                age_h = (datetime.now(timezone.utc) - last_updated_utc).total_seconds() / 3600
            else:
                age_h = 999

            # Determine role based on criticality and freshness requirement
            if rule is not None and rule.get("critical"):
                role = "CRIT"
            elif max_age <= 7:
                role = "IMP"
            else:
                role = "NORM"

            current_count = summary.get(status, 0) if isinstance(summary.get(status), int) else 0
            summary[status] = current_count + 1
            if status in ("stale", "empty") and row["table_name"] in critical_tables:
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

        ok_count = summary.get("ok", 0) if isinstance(summary.get("ok"), int) else 0
        ready_to_trade = len(critical_stale) == 0 and ok_count > 0

        response = list_response(sources, total=len(sources), limit=None, offset=None)
        response["data"]["ready_to_trade"] = ready_to_trade
        response["data"]["summary"] = summary
        response["data"]["critical_stale"] = critical_stale
        response["data"]["expected_date"] = str(expected_date)
        response["data"]["as_of"] = datetime.now(timezone.utc).isoformat()

        # Validate health response against contract schema
        is_valid, error_msg = ResponseValidator.validate_endpoint_response("health", response["data"])
        if not is_valid:
            logger.error(f"Health response validation failed: {error_msg}")
            return error_response(500, "response_validation_error", error_msg)  # type: ignore[no-any-return]

        return response
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch data status")
        return error_response(code, error_type, message)  # type: ignore[no-any-return]


def _normalize_market_health(mh: dict) -> dict[str, Any]:
    """Validate and normalize market_health dict. Fails fast if critical fields missing.

    Critical fields (halt circuit breaker): vix_level, market_stage, market_trend
    """
    critical_fields = {"vix_level", "market_stage", "market_trend"}
    missing = critical_fields - {k for k in mh.keys() if mh[k] is not None}
    if missing:
        raise ValueError(f"Market health missing critical fields: {missing}")
    return {
        "market_trend": mh.get("market_trend"),
        "market_stage": mh.get("market_stage"),
        "vix_level": mh.get("vix_level"),
        "up_volume_percent": mh.get("up_volume_percent"),
        "advance_decline_ratio": mh.get("advance_decline_ratio"),
        "new_highs_count": mh.get("new_highs_count"),
        "new_lows_count": mh.get("new_lows_count"),
        "breadth_momentum_10d": mh.get("breadth_momentum_10d"),
        "put_call_ratio": mh.get("put_call_ratio"),
        "yield_curve_slope": mh.get("yield_curve_slope"),
        "fed_rate_environment": mh.get("fed_rate_environment"),
        "spy_change_pct": mh.get("spy_change_pct"),
    }


def _normalize_exposure(exp: dict) -> dict[str, Any]:
    """Validate and normalize exposure dict. Fails fast if critical fields missing.

    Critical fields (position sizing, trading halts): exposure_pct, regime
    """
    critical_fields = {"exposure_pct", "regime"}
    missing = critical_fields - {k for k in exp.keys() if exp[k] is not None}
    if missing:
        raise ValueError(f"Market exposure missing critical fields: {missing}")
    halt_reasons = exp.get("halt_reasons")
    return {
        "exposure_pct": exp.get("exposure_pct"),
        "regime": exp.get("regime"),
        "halt_reasons": halt_reasons if halt_reasons is not None else [],
        "distribution_days": exp.get("distribution_days"),
    }


@db_route_handler("get market")
def _get_market(cur: cursor) -> dict[str, Any]:
    """Get simplified market data for dashboard. Returns market_health_daily + exposure data."""
    try:
        cur.execute("SET LOCAL statement_timeout = '8000ms'")

        # CRITICAL: Fetch market health; fail fast if unavailable
        cur.execute("""
            SELECT market_trend, market_stage, vix_level,
                   up_volume_percent, advance_decline_ratio, new_highs_count,
                   new_lows_count, breadth_momentum_10d, put_call_ratio,
                   yield_curve_slope, fed_rate_environment
            FROM market_health_daily
            ORDER BY date DESC LIMIT 1
        """)
        mh = cur.fetchone()
        if not mh:
            return error_response(503, "data_unavailable", "Market health data unavailable")  # type: ignore[no-any-return]
        mh_raw = safe_json_serialize(safe_dict_convert(mh))
        market_health = _normalize_market_health(mh_raw)

        # CRITICAL: Fetch exposure data; fail fast if unavailable
        cur.execute("""
            SELECT exposure_pct, regime, halt_reasons, distribution_days
            FROM market_exposure_daily
            ORDER BY date DESC LIMIT 1
        """)
        exp = cur.fetchone()
        if not exp:
            return error_response(503, "data_unavailable", "Market exposure data unavailable")  # type: ignore[no-any-return]
        exp_raw = safe_json_serialize(safe_dict_convert(exp))
        exposure = _normalize_exposure(exp_raw)

        # Parse JSON strings from database (halt_reasons is stored as JSON text)
        if exposure["halt_reasons"]:
            try:
                exposure["halt_reasons"] = (
                    json.loads(exposure["halt_reasons"])
                    if isinstance(exposure["halt_reasons"], str)
                    else exposure["halt_reasons"]
                )
            except (json.JSONDecodeError, TypeError):
                exposure["halt_reasons"] = []

        # CRITICAL: Fetch SPY close price; fail fast if unavailable
        cur.execute("""
            SELECT close FROM price_daily
            WHERE symbol = 'SPY'
            ORDER BY date DESC LIMIT 1
        """)
        spy_row = cur.fetchone()
        if not spy_row or spy_row["close"] is None:
            return error_response(503, "data_unavailable", "SPY price data unavailable")  # type: ignore[no-any-return]
        spy_close = float(spy_row["close"])

        data = {
            "exposure_pct": float(exposure["exposure_pct"]),
            "regime": exposure["regime"],
            "halt_reasons": exposure["halt_reasons"],
            "vix_level": float(market_health["vix_level"]),
            "market_stage": int(market_health["market_stage"]),
            "market_trend": market_health["market_trend"],
            "distribution_days_4w": int(exposure["distribution_days"]),
            "spy_close": spy_close,
            "spy_change_pct": float(market_health["spy_change_pct"]),
            "up_volume_percent": float(market_health["up_volume_percent"]),
            "advance_decline_ratio": float(market_health["advance_decline_ratio"]),
            "new_highs_count": int(market_health["new_highs_count"]),
            "new_lows_count": int(market_health["new_lows_count"]),
            "put_call_ratio": float(market_health["put_call_ratio"]),
            "breadth_momentum_10d": float(market_health["breadth_momentum_10d"]),
            "yield_curve_slope": float(market_health["yield_curve_slope"]),
            "fed_rate_environment": market_health["fed_rate_environment"],
        }

        return json_response(200, data)  # type: ignore[no-any-return]
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
        return error_response(503, "service_unavailable", "Failed to fetch market data")  # type: ignore[no-any-return]


@db_route_handler("get market factors")
def _get_market_factors(cur: cursor) -> dict[str, Any]:
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
            )  # type: ignore[no-any-return]

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
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"[MARKET_FACTORS] Failed to parse factors: {e}")
                factors = {}

        data = {
            "exposure_pct": format_decimal_string(data_dict.get("exposure_pct"), precision=2, allow_none=True),
            "raw_score": format_decimal_string(data_dict.get("raw_score"), precision=2, allow_none=True),
            "regime": data_dict.get("regime"),
            "factors": factors,
        }

        return json_response(200, data)  # type: ignore[no-any-return]
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
        return error_response(503, "service_unavailable", "Failed to fetch market factors")  # type: ignore[no-any-return]


@db_route_handler("get market sentiment")
def _get_market_sentiment(cur: cursor) -> dict[str, Any]:
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
        return error_response(503, "no_data", "Market sentiment data not yet available")  # type: ignore[no-any-return]

    if row.get("sentiment_score") is None:
        return error_response(503, "incomplete_data", "Market sentiment data incomplete")  # type: ignore[no-any-return]

    sentiment_score = float(row["sentiment_score"])
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
    )  # type: ignore[no-any-return]


@db_route_handler("get markets")
def _get_markets(cur: cursor) -> dict[str, Any]:
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
            response = list_response([], total=0, limit=None, offset=None)
            response["data"]["current"] = None
            response["data"]["active_tier"] = None
            response["data"]["history"] = []
            return response

        row = safe_json_serialize(safe_dict_convert(row))

        halt_reasons = []
        if row.get("halt_reasons"):
            try:
                halt_reasons = (
                    json.loads(row["halt_reasons"]) if isinstance(row["halt_reasons"], str) else row["halt_reasons"]
                )
            except (json.JSONDecodeError, TypeError):
                halt_reasons = []

        factors = {}
        if row.get("factors"):
            try:
                factors = json.loads(row["factors"]) if isinstance(row["factors"], str) else row["factors"]
            except (json.JSONDecodeError, TypeError):
                factors = {}

        tier_key = str(row.get("regime") or "").lower()
        tier_conf = _TIER_CONFIG.get(tier_key)
        if tier_conf is None:
            logger.warning(f"Missing tier configuration for regime: {tier_key}")
            tier_conf = {}
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
                    "exposure_pct": (float(h["exposure_pct"]) if h.get("exposure_pct") is not None else None),
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
                        "momentum": (float(sr["momentum"]) if sr.get("momentum") is not None else None),
                    }
                )
        except (ValueError, ZeroDivisionError, TypeError) as se:
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
                # FIX: VIX level must be > 0 (invalid values like 0.0 indicate data quality issue)
                # Set to NULL if invalid, so downstream fails-fast rather than showing false data
                vix_val = market_health.get("vix_level")
                if vix_val is not None:
                    try:
                        vix_float = float(vix_val)
                        if vix_float <= 0:
                            logger.warning(
                                f"[MARKETS API] Invalid VIX value {vix_float} in market_health_daily - "
                                f"VIX must be > 0. Setting to NULL to trigger fail-fast in dashboard."
                            )
                            market_health["vix_level"] = None
                    except (ValueError, TypeError):
                        pass
            else:
                return error_response(
                    503,
                    "data_unavailable",
                    "Market health data not available (market_health_daily empty)",
                )  # type: ignore[no-any-return]
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as mhe:
            logger.error(f"CRITICAL: Failed to fetch market_health_daily: {mhe}")
            return error_response(
                503,
                "data_unavailable",
                f"Market health unavailable: {type(mhe).__name__}",
            )  # type: ignore[no-any-return]

        # Fetch latest SPY close for dashboard header (critical for position sizing)
        spy_close = None
        try:
            cur.execute("""
                SELECT close FROM price_daily
                WHERE symbol = 'SPY'
                ORDER BY date DESC LIMIT 1
            """)
            spy_row = cur.fetchone()
            if not spy_row or spy_row["close"] is None:
                return error_response(503, "data_unavailable", "SPY price data not available")  # type: ignore[no-any-return]
            spy_close = float(spy_row["close"])
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as spy_e:
            logger.error(f"CRITICAL: Failed to fetch SPY price: {spy_e}")
            return error_response(
                503,
                "data_unavailable",
                f"SPY price unavailable: {type(spy_e).__name__}",
            )  # type: ignore[no-any-return]

        current_date = row.get("date")

        # CRITICAL: Validate vix_regime is present in factors; fail-fast if missing
        if "vix_regime" not in factors:
            logger.error(
                f"[MARKETS API] CRITICAL: vix_regime missing from factors for {current_date}: "
                f"market exposure computation may not have run or vix_regime computation failed. "
                f"Check market_exposure_daily and load_market_exposure_daily logs."
            )
            return error_response(
                503,
                "data_unavailable",
                "VIX regime data unavailable - cannot assess volatility risk",
            )  # type: ignore[no-any-return]
        vix_regime_obj = factors.get("vix_regime")
        if vix_regime_obj is None or vix_regime_obj.get("value") is None:
            logger.error(
                f"[MARKETS API] CRITICAL: VIX value is None in vix_regime for {current_date}: "
                f"VIX fetch from ^VIX or market_health_daily returned no data. "
                f"Check load_market_health_daily logs and yfinance availability."
            )
            return error_response(
                503,
                "data_unavailable",
                "VIX data unavailable - cannot assess volatility risk",
            )  # type: ignore[no-any-return]

        response = list_response(sectors, total=len(sectors), limit=None, offset=None)
        response_data = {
            "exposure_pct": (float(row["exposure_pct"]) if row.get("exposure_pct") is not None else None),
            "raw_score": (float(row["raw_score"]) if row.get("raw_score") is not None else None),
            "regime": row.get("regime"),
            "halt_reasons": halt_reasons,
            "distribution_days": row.get("distribution_days", 0),
            "factors": factors,
            "spy_close": spy_close,
            "date": (current_date.isoformat() if hasattr(current_date, "isoformat") else str(current_date)),
        }
        response["data"]["current"] = response_data
        response["data"]["active_tier"] = active_tier
        response["data"]["history"] = history
        response["data"]["market_health"] = market_health

        # Validate market response against contract schema
        ensure_valid_response("mkt", response["data"])

        return response
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
        return error_response(503, "service_unavailable", "Failed to fetch markets data")  # type: ignore[no-any-return]


@db_route_handler("get trend criteria")
def _get_trend_criteria(cur: cursor) -> dict[str, Any]:
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
    if not row or int(row["total_symbols"]) == 0:
        return error_response(503, "no_data", "Trend template data not yet available")  # type: ignore[no-any-return]

    total_symbols = int(row["total_symbols"])
    criteria = [
        {
            "name": "Price Above 50-Day MA",
            "passing": int(row["above_sma50"]),
            "total": total_symbols,
        },
        {
            "name": "50-Day Above 200-Day MA",
            "passing": int(row["sma50_above_sma200"]),
            "total": total_symbols,
        },
        {
            "name": "Price Above 200-Day MA",
            "passing": int(row["above_sma200"]),
            "total": total_symbols,
        },
        {
            "name": "Stage 2 Uptrend (Weinstein)",
            "passing": int(row["stage2"]),
            "total": total_symbols,
        },
    ]

    return list_response(criteria, total=total_symbols, limit=None, offset=None)  # type: ignore[no-any-return]
