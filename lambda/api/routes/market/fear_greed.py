"""Handler for the fear/greed history used by /api/market/fear-greed.

Split out of lambda/api/routes/market.py 2026-09-05 (file-size-ratchet decomposition).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import db_route_handler, error_response, json_response, safe_json_serialize

logger = logging.getLogger(__name__)


@db_route_handler("get fear greed history")
def _get_fear_greed_history(cur: cursor, days: int = 30) -> Any:
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
