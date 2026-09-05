"""Handler for /api/market/seasonality.

Split out of lambda/api/routes/market.py 2026-09-05 (file-size-ratchet decomposition).
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import json_response, raise_api_error, raise_db_error

from utils.validation import safe_float

logger = logging.getLogger(__name__)


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
