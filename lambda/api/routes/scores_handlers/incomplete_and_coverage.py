"""Score route handler: the /api/scores/incomplete stocks listing.

Split 2026-09-05 (file-size-ratchet compliance) - the categorization rulebook and the
/api/scores/coverage report (_categorize_reason, _get_scores_coverage, and everything only
they use) moved to the sibling coverage.py; nothing here referenced any of it.
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    error_response,
    execute_with_timeout,
    handle_db_error,
    json_response,
)

logger = logging.getLogger(__name__)


def _get_incomplete_stocks(
    cur: cursor,
    limit: int,
    offset: int,
    sort_by: str = "data_completeness",
    sort_order: str = "asc",
) -> Any:
    """Get stocks with incomplete data (data_unavailable=True or data_completeness < 70%).

    Returns stocks that cannot be reliably scored due to missing data, with reason codes.
    Useful for understanding what data sources are still needed.
    """
    try:
        # Get count of incomplete stocks
        cur.execute("""
            SELECT COUNT(*)
            FROM stock_scores
            WHERE (data_unavailable = true OR data_completeness < 70)
        """)
        total_count = cur.fetchone()[0]

        # Sort by appropriate field. sort_order is interpolated below, so it must never
        # come from the raw query-param string - map it to a fixed SQL keyword first.
        sort_direction = "DESC" if sort_order == "desc" else "ASC"
        if sort_by == "symbol":
            sort_clause = f"ORDER BY symbol {sort_direction}"
        else:
            sort_clause = f"ORDER BY data_completeness {sort_direction}, symbol ASC"

        # Fetch incomplete stocks
        query = f"""
            SELECT
                symbol,
                composite_score,
                data_completeness,
                data_unavailable,
                reason,
                unavailable_metrics,
                updated_at
            FROM stock_scores
            WHERE (data_unavailable = true OR data_completeness < 70)
            {sort_clause}
            LIMIT %s OFFSET %s
        """

        rows = execute_with_timeout(cur, query, [limit, offset], timeout_sec=20, max_attempts=1)

        items = []
        for row in rows:
            d = dict(row)
            # Clean up unavailable_metrics for display
            if d.get("unavailable_metrics"):
                try:
                    if isinstance(d["unavailable_metrics"], str):
                        import json

                        d["unavailable_metrics"] = json.loads(d["unavailable_metrics"])
                except (TypeError, ValueError) as parse_err:
                    logger.warning(f"Could not parse unavailable_metrics, keeping raw value: {parse_err}")

            items.append(d)

        # Data freshness
        freshness = check_data_freshness(cur, "stock_scores", "updated_at", warning_days=1)

        result = {
            "items": items,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "page": (offset // limit) + 1 if limit > 0 else 1,
                "totalPages": ((total_count - 1) // limit) + 1 if limit > 0 else 1,
            },
            "note": "Stocks with data_unavailable=true or completeness < 70%. These are SPACs, new listings, or stocks with insufficient SEC data.",
        }
        return json_response(200, result, data_freshness=freshness)

    except Exception as e:
        code, error_type, message = handle_db_error(e, "get incomplete stocks")
        return error_response(code, error_type, message)
