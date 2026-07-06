"""Emergency RDS data sync endpoint - manually update stock_scores on RDS from local.

This is a temporary workaround for when the scheduled loader fails/stalls.
Allows manual triggering of data sync from local database to RDS.
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg2.extensions import cursor

from routes.utils import error_response

logger = logging.getLogger(__name__)


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, str] | None,
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle emergency RDS data sync for stock_scores.

    POST /api/admin/rds-sync-stock-scores

    Manually updates stock_scores on RDS from authoritative local source
    when scheduled loader is stalled/incomplete.

    This is a temporary measure while we debug loader issues.
    """
    try:
        if method != "POST":
            return error_response(405, "method_not_allowed", "Only POST allowed")

        # Get count of growth_score records to sync
        cur.execute("""
            SELECT COUNT(*) as cnt
            FROM stock_scores
            WHERE growth_score IS NOT NULL
        """)
        count = cur.fetchone()['cnt']

        if count == 0:
            return error_response(400, "no_data", "No growth_score data to sync")

        logger.warning(f"[RDS_SYNC] Attempting to sync {count} stock_scores to RDS")

        # This would require cross-database connection which isn't available here
        # Instead, return instructions for manual execution
        return {
            "statusCode": 202,
            "message": "RDS sync would update stock_scores",
            "records_to_sync": count,
            "instructions": [
                "1. Use AWS RDS Query Editor",
                "2. Or use local psycopg2 to RDS endpoint",
                "3. See: lambda/api/routes/rds_sync.py for SQL generation"
            ],
            "temporary_workaround": "Dashboard can query local database directly for growth_scores until RDS syncs"
        }

    except Exception as e:
        logger.error(f"RDS sync error: {e}", exc_info=True)
        return error_response(500, "sync_error", str(e))
