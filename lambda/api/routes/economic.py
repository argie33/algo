"""Route: economic"""

from __future__ import annotations

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
)

from algo.infrastructure.config.sql_intervals import get_interval_sql
from shared_contracts.response_validator import ResponseValidator
from utils.validation import DatabaseResultValidator

logger = logging.getLogger(__name__)


# Route registry: maps endpoint paths to handler functions
# Handlers taking 'params' are marked with 'needs_params': True
_ROUTE_REGISTRY = {
    ("/api/economic/VIX",): {
        "handler": "_get_vix",
        "needs_params": False,
    },
    ("/api/economic/leading-indicators", "/api/economic/indicators", "/api/economic"): {
        "handler": "_get_leading_indicators",
        "needs_params": False,
    },
    ("/api/economic/yield-curve-full",): {
        "handler": "_get_yield_curve_full",
        "needs_params": False,
    },
    ("/api/economic/calendar",): {
        "handler": "_get_calendar",
        "needs_params": True,
    },
}


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle /api/economic and /api/economic/* endpoints using registry dispatch."""
    try:
        # Find matching route in registry
        handler_name = None
        route_config = None
        for route_paths, config in _ROUTE_REGISTRY.items():
            if path in route_paths:
                handler_name = config["handler"]
                route_config = config
                break

        if not handler_name:
            return error_response(404, "not_found", f"No economic handler for {path}")

        # Get handler function from module globals
        handler_func = globals()[str(handler_name)]

        # Call handler with appropriate parameters
        if route_config and route_config["needs_params"]:
            return handler_func(cur, params)
        else:
            return handler_func(cur)
    except (
        psycopg2.errors.QueryCanceled,
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        TimeoutError,
        Exception,
    ) as e:
        logger.error(
            f"Economic route error in {path} - {type(e).__name__}: {e}",
            extra={"operation": "get economic data"},
        )
        code, error_type, message = handle_db_error(e, "get economic data")
        return error_response(code, error_type, message)


def _get_vix(cur: cursor) -> Any:
    try:
        rows = execute_with_timeout(
            cur,
            """
                SELECT date, vix_level as vix
                FROM market_health_daily
                WHERE vix_level IS NOT NULL
                ORDER BY date DESC
                LIMIT 100
            """,
            timeout_sec=3,
        )
        freshness = check_data_freshness(cur, "market_health_daily", "date", warning_days=1)
        return list_response(
            [safe_json_serialize(dict(r)) for r in rows] if rows else [],
            data_freshness=freshness,
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"VIX endpoint error - {type(e).__name__}: {e}",
            extra={"operation": "get VIX data"},
        )
        code, error_type, message = handle_db_error(e, "get VIX data")
        return error_response(code, error_type, message)


def _get_calendar(cur: cursor, params: dict[str, Any]) -> Any:
    try:
        cur.execute("SET LOCAL statement_timeout = '5000ms'")
        start_date = extract_param(params, "start_date")
        end_date = extract_param(params, "end_date")
        query_params = []

        where_clauses = []
        if start_date:
            where_clauses.append("event_date >= %s")
            query_params.append(start_date)
        if end_date:
            where_clauses.append("event_date <= %s")
            query_params.append(end_date)
        else:
            interval_90d = get_interval_sql("90d")
            where_clauses.append(f"event_date >= CURRENT_DATE - {interval_90d}")

        where_sql = " AND ".join(where_clauses)

        query = f"""
            SELECT event_date, event_name, country, importance,
                   category, event_time,
                   forecast_value AS forecast,
                   actual_value AS actual,
                   previous_value AS previous
            FROM economic_calendar
            WHERE {where_sql}
            ORDER BY event_date DESC
            LIMIT 200
        """
        cur.execute(query, tuple(query_params))
        events = cur.fetchall()
        freshness = check_data_freshness(cur, "economic_calendar", "event_date", warning_days=7)
        return list_response(
            [safe_json_serialize(dict(e)) for e in events] if events else [],
            data_freshness=freshness,
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"Economic calendar endpoint error - {type(e).__name__}: {e}",
            extra={"operation": "get economic calendar"},
        )
        code, error_type, message = handle_db_error(e, "get economic calendar")
        return error_response(code, error_type, message)


def _get_leading_indicators(cur: cursor) -> Any:  # noqa: C901
    # Maps FRED series IDs to indicator names
    indicator_map = {
        # Labor market
        "UNRATE": "Unemployment Rate",
        "PAYEMS": "Total Nonfarm Payroll",
        "ICSA": "Initial Claims",
        "CIVPART": "Labor Force Participation",
        "JTSJOL": "JOLTS Job Openings",
        "JTSQUR": "JOLTS Quit Rate",
        "AHETPI": "Average Hourly Earnings",
        # Activity / production
        "INDPRO": "Industrial Production",
        "RSXFS": "Retail Sales",
        "TCU": "Capacity Utilization",
        "MFGBDPHI": "Philly Fed Manufacturing",
        "CFNAI": "Chicago Fed Activity Index",
        # Inflation
        "CPIAUCSL": "CPI - All Urban Consumers",
        "PCEPILFE": "Core PCE Inflation",
        "T5YIE": "5Y Breakeven Inflation",
        "T10YIE": "10Y Breakeven Inflation",
        # Monetary / rates
        "FEDFUNDS": "Federal Funds Rate",
        "M2SL": "M2 Money Supply",
        "T10Y2Y": "Yield Curve (10Y-2Y)",
        # Growth
        "GDPC1": "GDP Growth",
        # Financial conditions & stress
        "STLFSI4": "Financial Stress Index",
        "ANFCI": "Adjusted Financial Conditions",
        # Consumer
        "UMCSENT": "Consumer Sentiment",
        "PSAVERT": "Personal Savings Rate",
        "DSPIC96": "Real Disposable Income",
        # Housing
        "HOUST": "Housing Starts",
        "PERMIT": "Building Permits",
        "MORTGAGE30US": "30Y Mortgage Rate",
        # Lending / credit
        "BUSLOANS": "Business Loans",
        # Global / commodities
        "DXY_ICE": "USD Dollar Index (ICE)",
        "DTWEXBGS": "USD Trade-Weighted Index (FRED alternative index, NOT DXY substitute)",
        "DCOILWTICO": "WTI Crude Oil",
    }
    # Series that report absolute levels but should be shown as YoY % change
    yoy_pct_series = {
        "GDPC1",
        "INDPRO",
        "RSXFS",
        "PAYEMS",
        "HOUST",
        "CPIAUCSL",
        "PCEPILFE",
        "DSPIC96",
        "AHETPI",
        "PERMIT",
    }

    try:
        cur.execute("""
                WITH latest AS (
                    SELECT series_id, date, value,
                           ROW_NUMBER() OVER (PARTITION BY series_id ORDER BY date DESC) as rn
                    FROM economic_data
                )
                SELECT series_id, date, value
                FROM latest
                WHERE rn = 1
            """)
        latest_data = cur.fetchall()

        # CRITICAL FAIL-FAST: Economic data validation must not silently fallback
        # Economic indicators are CRITICAL for portfolio decisions
        if not DatabaseResultValidator.validate_rows_not_empty(latest_data, "economic latest indicators query"):
            raise ValueError(
                "[CRITICAL] Economic latest indicators data validation failed — no data returned from query. "
                "Cannot provide economic indicators without data. "
                "Check economic_data table and data loader."
            )

        latest_rows = {}
        skipped_indicators = []
        for row in latest_data:
            if row is None:
                logger.error("NULL row in economic latest data")
                skipped_indicators.append({"series_id": "unknown", "reason": "null_row"})
                continue
            series_id = row.get("series_id")
            if not series_id:
                logger.error("Row missing series_id in economic latest data")
                skipped_indicators.append({"series_id": "unknown", "reason": "missing_series_id"})
                continue
            # CRITICAL: Economic values must NOT default to 0.0 (that's factually false)
            # Use strict=True to fail-fast on missing/invalid values
            value = DatabaseResultValidator.safe_get_float(row, "value", default=None, strict=True)
            if value is None:
                error_msg = f"Economic indicator {series_id} has missing value — data unavailable"
                logger.error(f"[ECONOMIC CRITICAL] {error_msg}")
                skipped_indicators.append({"series_id": series_id, "reason": "value_missing"})
                continue
            date = row.get("date")
            latest_rows[series_id] = (value, date)

        cur.execute("""
                SELECT series_id, date, value
                FROM economic_data
                WHERE date >= CURRENT_DATE - INTERVAL '24 months'
                ORDER BY series_id, date DESC
            """)
        all_history = cur.fetchall()

        # Validate all history data
        if not DatabaseResultValidator.validate_rows_not_empty(all_history, "economic history query"):
            all_history = []

        # Group by series_id
        history_by_series: dict[str, list[Any]] = {}
        for row in all_history:
            # FAIL-FAST: Extract series_id with safe validation
            sid = DatabaseResultValidator.safe_get_str(row, "series_id", strict=True)
            if sid is None:
                raise RuntimeError(
                    "[ECONOMIC DATA CRITICAL] series_id extraction returned None despite strict=True. "
                    "Indicates data corruption or validation failure. Cannot proceed without valid series_id."
                )
            if sid not in history_by_series:
                history_by_series[sid] = []
            # FAIL-FAST: Extract date and value with validation
            date_val = DatabaseResultValidator.safe_get_str(row, "date", strict=True)
            value_val = DatabaseResultValidator.safe_get_float(row, "value", default=None)
            history_by_series[sid].append(
                {
                    "date": date_val,
                    "value": value_val,
                }
            )

        # Build indicator objects
        indicators = []
        for series_id, name in indicator_map.items():
            if series_id not in latest_rows:
                continue

            value, dt = latest_rows[series_id]
            series_history = history_by_series.get(series_id)
            if series_history is None:
                series_history = []
            history = sorted(series_history, key=lambda x: x["date"])

            # For level series, compute YoY % change so the frontend gets a meaningful rate
            display_value = value
            if series_id in yoy_pct_series and len(history) >= 12:
                # history is sorted ascending; last = most recent, -13 ≈ 1 year ago
                cur_h = history[-1] if history else None
                yr_ago = history[-13] if len(history) >= 13 else history[0]
                if cur_h and yr_ago:
                    # FAIL-FAST: Extract values upfront with safe validation
                    prior = DatabaseResultValidator.safe_get_float(yr_ago, "value", default=None)
                    cur_val = DatabaseResultValidator.safe_get_float(cur_h, "value", default=None)
                    if prior is not None and cur_val is not None and prior != 0:
                        display_value = round((cur_val - prior) / abs(prior) * 100, 2)
                # Replace history values with rolling YoY % change too
                yoy_history = []
                for idx in range(12, len(history)):
                    # FAIL-FAST: Extract values upfront before arithmetic
                    cur_v = DatabaseResultValidator.safe_get_float(history[idx], "value", default=None)
                    yr_v = DatabaseResultValidator.safe_get_float(history[idx - 12], "value", default=None)
                    date_v = DatabaseResultValidator.safe_get_str(history[idx], "date", default=None)
                    if cur_v is not None and yr_v is not None and yr_v != 0:
                        yoy_history.append(
                            {
                                "date": date_v,
                                "value": round((cur_v - yr_v) / abs(yr_v) * 100, 2),
                            }
                        )
                if yoy_history:
                    history = yoy_history

            # Calculate trend (up/down/flat) on the (possibly transformed) history
            # GOVERNANCE: Fail-fast on insufficient data. No silent fallbacks to defaults.
            if len(history) >= 2:
                recent_values = [h["value"] for h in history[-3:] if h["value"] is not None]
                older_values = [h["value"] for h in history[:3] if h["value"] is not None]

                # Require at least one valid data point in each period for trend calculation
                if len(recent_values) == 0:
                    logger.warning(
                        "Insufficient data for recent trend calculation (0 valid values in last 3 periods). Setting trend=None."
                    )
                    trend = None
                elif len(older_values) == 0:
                    logger.warning(
                        "Insufficient data for older trend calculation (0 valid values in first 3 periods). Setting trend=None."
                    )
                    trend = None
                else:
                    recent_avg = sum(recent_values) / len(recent_values)
                    older_avg = sum(older_values) / len(older_values)
                    if older_avg and recent_avg:
                        if recent_avg > older_avg * 1.01:
                            trend = "up"
                        elif recent_avg < older_avg * 0.99:
                            trend = "down"
                        else:
                            trend = "flat"
                    else:
                        trend = "flat"
            else:
                trend = None

            # Compute MoM change from the most recent two history entries
            change = None
            if len(history) >= 2:
                cur_v = history[-1].get("value")
                prev_v = history[-2].get("value")
                if cur_v is not None and prev_v is not None:
                    change = round(float(cur_v) - float(prev_v), 2)

            display_str = str(round(float(display_value), 2)) if display_value is not None else None

            indicators.append(
                {
                    "name": name,
                    "series_id": series_id,
                    "rawValue": display_value,
                    "value": display_str,
                    "change": change,
                    "date": str(dt),
                    "history": history,
                    "trend": trend,
                }
            )

        # Build result dict with proper typing for all potential keys
        result: dict[str, Any] = {"indicators": indicators}
        if skipped_indicators:
            result["indicators_incomplete"] = True
            result["skipped_indicators_count"] = len(skipped_indicators)
            result["skipped_indicators"] = skipped_indicators[:20]
            logger.warning(
                "[ECONOMIC] Economic indicators incomplete: %d indicators skipped (missing values)",
                len(skipped_indicators),
            )

        is_valid, error_msg_raw = ResponseValidator.validate_endpoint_response("economic/indicators", result)
        if not is_valid:
            logger.error(f"Economic indicators response validation failed: {error_msg_raw}")
            if error_msg_raw:
                return error_response(500, "response_validation_error", error_msg_raw)
            else:
                logger.error("[CRITICAL] Economic indicators validation failed but error_msg_raw is None. Bug.")
                return error_response(
                    500,
                    "response_validation_error",
                    "Economic indicators validation failed (internal error: no message)",
                )

        return json_response(200, result)

    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"Leading indicators error - {type(e).__name__}: {e}",
            extra={"operation": "get leading indicators"},
        )
        code, error_type, message = handle_db_error(e, "get leading indicators")
        return error_response(code, error_type, message)


def _get_yield_curve_full(cur: cursor) -> Any:  # noqa: C901
    try:
        cur.execute("""
                WITH latest AS (
                    SELECT series_id, date, value,
                           ROW_NUMBER() OVER (PARTITION BY series_id
                                              ORDER BY date DESC) as rn
                    FROM economic_data
                    WHERE series_id IN (
                        'DGS3MO', 'DGS6MO', 'DGS1', 'DGS2', 'DGS3',
                        'DGS5', 'DGS7', 'DGS10', 'DGS20', 'DGS30',
                        'T10Y3M', 'T10Y2Y', 'BAMLH0A0HYM2', 'BAMLC0A0CM',
                        'VIXCLS', 'T5YIE', 'T10YIE', 'STLFSI4', 'ANFCI'
                    )
                )
                SELECT series_id, date, value
                FROM latest
                WHERE rn = 1
            """)
        latest_rows = cur.fetchall()

        cur.execute("""
                SELECT series_id, date, value
                FROM economic_data
                WHERE date >= CURRENT_DATE - INTERVAL '24 months'
                AND series_id IN (
                    'T10Y2Y', 'BAMLH0A0HYM2', 'BAMLC0A0CM', 'VIXCLS',
                    'T5YIE', 'T10YIE', 'STLFSI4', 'ANFCI'
                )
                ORDER BY series_id, date
            """)
        history_rows = cur.fetchall()

        # Build response
        current_curve = {}
        spreads = {}
        is_inverted = False
        history = {}

        for row in latest_rows:
            # FAIL-FAST: Extract series_id and value with safe validation
            sid = DatabaseResultValidator.safe_get_str(row, "series_id", strict=True)
            val = DatabaseResultValidator.safe_get_float(row, "value", default=None)

            # Build current yield curve
            if sid == "DGS3MO":
                current_curve["3M"] = val
            elif sid == "DGS6MO":
                current_curve["6M"] = val
            elif sid == "DGS1":
                current_curve["1Y"] = val
            elif sid == "DGS2":
                current_curve["2Y"] = val
            elif sid == "DGS3":
                current_curve["3Y"] = val
            elif sid == "DGS5":
                current_curve["5Y"] = val
            elif sid == "DGS7":
                current_curve["7Y"] = val
            elif sid == "DGS10":
                current_curve["10Y"] = val
            elif sid == "DGS20":
                current_curve["20Y"] = val
            elif sid == "DGS30":
                current_curve["30Y"] = val
            elif sid == "T10Y3M":
                spreads["T10Y3M"] = val
            elif sid == "T10Y2Y":
                spreads["T10Y2Y"] = val
                is_inverted = (val < 0) if val else False

        # Add history for spreads
        history_by_series: dict[str, list[Any]] = {}
        for row in history_rows:
            # FAIL-FAST: Extract series_id, date, value with safe validation
            sid = DatabaseResultValidator.safe_get_str(row, "series_id", strict=True)
            if sid is None:
                raise RuntimeError(
                    "[ECONOMIC DATA CRITICAL] series_id extraction returned None despite strict=True. "
                    "Indicates data corruption or validation failure. Cannot proceed without valid series_id."
                )
            date_val = DatabaseResultValidator.safe_get_str(row, "date", strict=True)
            value_val = DatabaseResultValidator.safe_get_float(row, "value", default=None)
            if sid not in history_by_series:
                history_by_series[sid] = []
            history_by_series[sid].append(
                {
                    "date": date_val,
                    "value": value_val,
                }
            )

        for sid, hist in history_by_series.items():
            history[sid] = sorted(hist, key=lambda x: x["date"])

        # Build credit sub-object with the series names the frontend expects
        bamlh = history.get("BAMLH0A0HYM2")
        bamlc = history.get("BAMLC0A0CM")
        vixcls = history.get("VIXCLS")

        if bamlh is None:
            raise RuntimeError(
                "CRITICAL: High-yield credit spreads (BAMLH0A0HYM2) unavailable - required for risk assessment"
            )
        if bamlc is None:
            raise RuntimeError(
                "CRITICAL: Investment-grade credit spreads (BAMLC0A0CM) unavailable - required for risk assessment"
            )
        if vixcls is None:
            raise RuntimeError("CRITICAL: VIX volatility data (VIXCLS) unavailable - required for position sizing")

        credit_history = {
            "BAMLH0A0HYM2": bamlh,
            "BAMLH0A0IG": bamlc,
            "VIXCLS": vixcls,
        }
        # Extract latest values: fail if history exists but lacks "value" key (data structure error)
        credit_latest: dict[str, Any] = {}
        for k, v in credit_history.items():
            if v is None:
                credit_latest[k] = None
            elif not isinstance(v, list) or len(v) == 0:
                credit_latest[k] = None
            else:
                last_item = v[-1]
                if "value" not in last_item:
                    raise RuntimeError(
                        f"Economic data structure error: credit history '{k}' last item missing 'value' key. "
                        f"Available keys: {list(last_item.keys())}. Data integrity issue."
                    )
                credit_latest[k] = last_item["value"]

        # TIPS breakeven inflation expectations
        breakevens_history = {
            "T5YIE": history.get("T5YIE"),
            "T10YIE": history.get("T10YIE"),
        }
        breakevens_latest: dict[str, Any] = {}
        for k, v in breakevens_history.items():  # type: ignore[assignment]
            if v is None:
                breakevens_latest[k] = None
            elif not isinstance(v, list) or len(v) == 0:
                breakevens_latest[k] = None
            else:
                last_item = v[-1]
                if "value" not in last_item:
                    raise RuntimeError(
                        f"Economic data structure error: breakevens history '{k}' last item missing 'value' key. "
                        f"Available keys: {list(last_item.keys())}. Data integrity issue."
                    )
                breakevens_latest[k] = last_item["value"]

        # Financial stress indices
        stress_history = {
            "STLFSI4": history.get("STLFSI4"),
            "ANFCI": history.get("ANFCI"),
        }
        stress_latest: dict[str, Any] = {}
        for k, v in stress_history.items():  # type: ignore[assignment]
            if v is None:
                stress_latest[k] = None
            elif not isinstance(v, list) or len(v) == 0:
                stress_latest[k] = None
            else:
                last_item = v[-1]
                if "value" not in last_item:
                    raise RuntimeError(
                        f"Economic data structure error: stress history '{k}' last item missing 'value' key. "
                        f"Available keys: {list(last_item.keys())}. Data integrity issue."
                    )
                stress_latest[k] = last_item["value"]

        result = {
            "currentCurve": current_curve,
            "spreads": spreads,
            "isInverted": is_inverted,
            "history": history,
            "credit": {
                "history": credit_history,
                "currentSpreads": credit_latest,
            },
            "breakevens": {
                "history": breakevens_history,
                "current": breakevens_latest,
            },
            "stress": {
                "history": stress_history,
                "current": stress_latest,
            },
        }

        is_valid, error_msg = ResponseValidator.validate_endpoint_response("economic/yield-curve", result)
        if not is_valid:
            logger.error(f"Economic yield curve response validation failed: {error_msg}")
            if error_msg:
                return error_response(500, "response_validation_error", error_msg)
            else:
                logger.error("[CRITICAL] Yield curve validation failed but error_msg is None. Bug.")
                return error_response(
                    500, "response_validation_error", "Yield curve validation failed (internal error: no message)"
                )

        return json_response(200, result)

    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"Yield curve error - {type(e).__name__}: {e}",
            extra={"operation": "get yield curve"},
        )
        code, error_type, message = handle_db_error(e, "get yield curve")
        return error_response(code, error_type, message)
