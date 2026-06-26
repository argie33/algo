"""Route: economic"""

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
    """Get VIX historical data."""
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
    """Get economic calendar data with optional date filtering."""
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
            where_clauses.append("event_date >= CURRENT_DATE - INTERVAL '90 days'")

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


def _get_leading_indicators(cur: cursor) -> Any:
    """Get leading economic indicators formatted for EconomicDashboard."""
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
        "DTWEXBGS": "USD Dollar Index",
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

        # Validate latest data
        if not DatabaseResultValidator.validate_rows_not_empty(latest_data, "economic latest indicators query"):
            latest_data = []

        latest_rows = {}
        for row in latest_data:
            if row is None:
                logger.warning("NULL row in economic latest data")
                continue
            series_id = row.get("series_id")
            if not series_id:
                logger.warning("Row missing series_id in economic latest data")
                continue
            # Safely convert value to float
            value = DatabaseResultValidator.safe_get_float(row, "value", default=0.0, strict=False)
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
            sid = row["series_id"]
            if sid not in history_by_series:
                history_by_series[sid] = []
            history_by_series[sid].append(
                {
                    "date": str(row["date"]),
                    "value": float(row["value"]) if row["value"] else None,
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
                if cur_h and yr_ago and yr_ago.get("value") and cur_h.get("value"):
                    prior = float(yr_ago["value"])
                    if prior != 0:
                        display_value = round((float(cur_h["value"]) - prior) / abs(prior) * 100, 2)
                # Replace history values with rolling YoY % change too
                yoy_history = []
                for idx in range(12, len(history)):
                    cur_v = history[idx].get("value")
                    yr_v = history[idx - 12].get("value")
                    if cur_v is not None and yr_v and float(yr_v) != 0:
                        yoy_history.append(
                            {
                                "date": history[idx]["date"],
                                "value": round(
                                    (float(cur_v) - float(yr_v)) / abs(float(yr_v)) * 100,
                                    2,
                                ),
                            }
                        )
                if yoy_history:
                    history = yoy_history

            # Calculate trend (up/down/flat) on the (possibly transformed) history
            if len(history) >= 2:
                recent_avg = sum([h["value"] for h in history[-3:] if h["value"] is not None] or [0]) / max(
                    1, len([h for h in history[-3:] if h["value"] is not None])
                )
                older_avg = sum([h["value"] for h in history[:3] if h["value"] is not None] or [0]) / max(
                    1, len([h for h in history[:3] if h["value"] is not None])
                )
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
                trend = "flat"

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

        result = {"indicators": indicators}

        is_valid, error_msg = ResponseValidator.validate_endpoint_response("economic/indicators", result)
        if not is_valid:
            logger.error(f"Economic indicators response validation failed: {error_msg}")
            return error_response(
                500, "response_validation_error", error_msg or "Economic indicators validation failed"
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


def _get_yield_curve_full(cur: cursor) -> Any:
    """Get yield curve and credit spread data formatted for EconomicDashboard."""
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
            sid = row["series_id"]
            val = float(row["value"]) if row["value"] else None

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
            sid = row["series_id"]
            if sid not in history_by_series:
                history_by_series[sid] = []
            history_by_series[sid].append(
                {
                    "date": str(row["date"]),
                    "value": float(row["value"]) if row["value"] else None,
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
                "CRITICAL: High-yield credit spreads (BAMLH0A0HYM2) unavailable - "
                "required for risk assessment"
            )
        if bamlc is None:
            raise RuntimeError(
                "CRITICAL: Investment-grade credit spreads (BAMLC0A0CM) unavailable - "
                "required for risk assessment"
            )
        if vixcls is None:
            raise RuntimeError(
                "CRITICAL: VIX volatility data (VIXCLS) unavailable - required for position sizing"
            )

        credit_history = {
            "BAMLH0A0HYM2": bamlh,
            "BAMLH0A0IG": bamlc,
            "VIXCLS": vixcls,
        }
        credit_latest = {k: v[-1].get("value") if v else None for k, v in credit_history.items()}

        # TIPS breakeven inflation expectations
        breakevens_history = {
            "T5YIE": history.get("T5YIE"),
            "T10YIE": history.get("T10YIE"),
        }
        breakevens_latest = {k: v[-1].get("value") if v else None for k, v in breakevens_history.items()}

        # Financial stress indices
        stress_history = {
            "STLFSI4": history.get("STLFSI4"),
            "ANFCI": history.get("ANFCI"),
        }
        stress_latest = {k: v[-1].get("value") if v else None for k, v in stress_history.items()}

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
            return error_response(500, "response_validation_error", error_msg or "Yield curve validation failed")

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
