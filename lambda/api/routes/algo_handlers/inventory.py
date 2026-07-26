"""Route: table inventory - complete visibility into all tracked and untracked tables"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import psycopg2
from psycopg2.extensions import cursor
from routes.utils import (
    db_route_handler,
    error_response,
    handle_db_error,
    list_response,
)

logger = logging.getLogger(__name__)


@db_route_handler("get table inventory")
def _get_table_inventory(cur: cursor) -> Any:
    """Get COMPLETE table inventory - all tracked, deprecated, untracked tables with staleness status.

    No filtering. Shows:
    - All tables in data_loader_status (active/deprecated/archived)
    - All actual tables in database not yet tracked
    - Summary of inventory gaps
    """
    try:
        # 1. Get all tracked tables
        cur.execute("""
            SELECT table_name, status, stale_threshold_days, age_days, row_count, last_updated
            FROM data_loader_status
            ORDER BY status, age_days DESC NULLS LAST, table_name
        """)
        tracked_rows = cur.fetchall()

        tracked_tables = []
        for row in tracked_rows:
            tbl_name, status, threshold, age, count, last_updated = row
            tracked_tables.append(
                {
                    "name": tbl_name,
                    "type": "tracked",
                    "status": status,
                    "stale_threshold_days": threshold,
                    "age_days": age,
                    "row_count": count or 0,
                    "last_updated": last_updated.isoformat() if last_updated else None,
                    "is_stale": (age and threshold and age > threshold) if (age and threshold) else None,
                }
            )

        # 2. Get all actual tables in database
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)

        actual_tables_set = {row[0] for row in cur.fetchall()}
        tracked_tables_set = {t["name"] for t in tracked_tables}

        # 3. Find untracked tables (exist but not in data_loader_status)
        untracked_tables = []
        for tbl_name in sorted(actual_tables_set - tracked_tables_set):
            try:
                cur.execute(f'SELECT COUNT(*) FROM "{tbl_name}"')
                cnt = cur.fetchone()[0]
                untracked_tables.append(
                    {
                        "name": tbl_name,
                        "type": "untracked",
                        "status": None,
                        "stale_threshold_days": None,
                        "age_days": None,
                        "row_count": cnt,
                        "last_updated": None,
                        "is_stale": None,
                    }
                )
            except Exception as e:
                logger.warning(f"Could not count rows in {tbl_name}: {e}")
                untracked_tables.append(
                    {
                        "name": tbl_name,
                        "type": "untracked",
                        "status": None,
                        "stale_threshold_days": None,
                        "age_days": None,
                        "row_count": None,
                        "last_updated": None,
                        "is_stale": None,
                    }
                )

        # 4. Combine all tables
        all_tables = tracked_tables + untracked_tables

        # 5. Compute summary
        summary = {
            "total_tables": len(all_tables),
            "tracked": sum(1 for t in tracked_tables),
            "untracked": len(untracked_tables),
            "active_loaders": sum(1 for t in tracked_tables if t["status"] and t["status"].lower() == "ok"),
            "deprecated": sum(1 for t in tracked_tables if t["status"] == "deprecated"),
            "archived": sum(1 for t in tracked_tables if t["status"] == "archived"),
            "stale_active": sum(1 for t in tracked_tables if t.get("is_stale")),
        }

        # 6. Find gaps (tracked but don't exist)
        tracked_names = {row[0] for row in tracked_rows}
        missing_tables = sorted(tracked_names - actual_tables_set)

        response = list_response(all_tables, total=len(all_tables), limit=None, offset=None)
        response["data"]["summary"] = summary
        response["data"]["missing_tables"] = missing_tables
        response["data"]["as_of"] = datetime.now(timezone.utc).isoformat()

        return response

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        code, error_type, message = handle_db_error(e, "fetch table inventory")
        logger.error(f"Failed to fetch table inventory: {error_type} - {message}")
        return error_response(code, error_type, message)
    except Exception as e:
        logger.error(f"Unexpected error in table inventory: {e}", exc_info=True)
        return error_response(500, "server_error", str(e))
