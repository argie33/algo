"""Sync fresh stock_scores from Aurora read replica or backup to main instance.

Emergency endpoint to manually trigger RDS data sync when loader is stalled.
"""

from __future__ import annotations

import logging
import subprocess
import sys
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
    """Handle emergency stock_scores sync.

    POST /api/admin/sync-stock-scores-rds

    This endpoint attempts to sync fresh stock_scores from the local/read database
    to the main RDS instance when the scheduled ECS loader is stalled or stuck.

    Requires: Admin-level access (JWT claims must have admin role)
    """
    try:
        if method != "POST":
            return error_response(405, "method_not_allowed", "Only POST allowed")

        # Check authorization
        if not jwt_claims or jwt_claims.get('role') != 'admin':
            logger.warning("[SYNC_SCORES] Unauthorized sync attempt")
            return error_response(403, "forbidden", "Admin access required")

        logger.info("[SYNC_SCORES] Starting emergency stock_scores sync...")

        # Get fresh data from current connection (should be RDS primary)
        cur.execute("""
            SELECT COUNT(*) as cnt, MAX(updated_at) as latest
            FROM stock_scores
            WHERE growth_score IS NOT NULL
        """)
        current = cur.fetchone()
        current_count = current['cnt']
        current_date = current['latest']

        if current_count < 3000:
            # RDS doesn't have fresh data, need to load it
            logger.warning(f"[SYNC_SCORES] RDS has only {current_count} records with growth_score")

            # Attempt to trigger load_stock_scores via ECS
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "loaders.load_stock_scores"],
                    capture_output=True,
                    text=True,
                    timeout=600
                )

                if result.returncode == 0:
                    logger.info("[SYNC_SCORES] Loader completed successfully")

                    # Verify
                    cur.execute("""
                        SELECT COUNT(*) as cnt, MAX(updated_at) as latest
                        FROM stock_scores
                        WHERE growth_score IS NOT NULL
                    """)
                    after = cur.fetchone()

                    return {
                        "statusCode": 200,
                        "message": "Stock scores synced successfully",
                        "before": {"count": current_count, "date": str(current_date)},
                        "after": {"count": after['cnt'], "date": str(after['latest'])},
                        "records_added": after['cnt'] - current_count
                    }
                else:
                    logger.error(f"[SYNC_SCORES] Loader failed: {result.stderr[:200]}")
                    return error_response(500, "loader_failed", result.stderr[:200])

            except subprocess.TimeoutExpired:
                return error_response(504, "loader_timeout", "Stock scores loader timed out")
            except Exception as e:
                logger.error(f"[SYNC_SCORES] Loader error: {e}")
                return error_response(500, "loader_error", str(e))

        else:
            # Already has fresh data
            return {
                "statusCode": 200,
                "message": "RDS already has fresh stock_scores",
                "count": current_count,
                "latest_date": str(current_date)
            }

    except Exception as e:
        logger.error(f"[SYNC_SCORES] Error: {e}", exc_info=True)
        return error_response(500, "sync_error", str(e))
