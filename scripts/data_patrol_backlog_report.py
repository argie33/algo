#!/usr/bin/env python3
"""Surface the current open data_patrol_log backlog to a human.

Added 2026-09-09 (goal session: "is our XBRL/tie-out validation actually working - are we not
finding weird values, or are we finding them and ignoring them"). Live audit that day found:
`data_patrol_log.status` was a dead column (100% NULL across 7,208 rows, no code ever wrote to
it), the same ~77 (check_name, target_table) combos were re-logged on effectively every patrol
run since 2026-09-07 with no dedup, and the oldest unresolved finding dated back to 2026-06-27.
Findings WERE being detected every run - they were just functionally invisible, indistinguishable
from "not checked" to anyone scanning the flat, ever-growing log by hand. This is the tool that
was missing: nothing previously summarized "what's actually open right now, and how long has it
been open."

PatrolLogger.log_results() (algo/monitoring/data_patrol/logger.py) now supersedes a
(check_name, target_table)'s prior 'open' row(s) when that check fires again, so `status='open'`
reflects only the latest run's state per check/table - this script reads that state. A combo that
stops firing keeps its last 'open' row forever (this write path has no registry of every check
that could theoretically fire), which is exactly the case this report's --stale-days flag exists
to surface: an 'open' row with no newer patrol_run touching it at all is worth a human's attention
either way (still broken, or the check quietly stopped running).

Usage:
    python scripts/data_patrol_backlog_report.py                  # full open backlog, newest first
    python scripts/data_patrol_backlog_report.py --min-age-days 7 # only backlog older than 7 days
    python scripts/data_patrol_backlog_report.py --severity warn  # filter by severity
    python scripts/data_patrol_backlog_report.py --check-name revenue_yoy_magnitude_jump
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.db.context import DatabaseContext


def _age_str(created_at: datetime) -> str:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - created_at).total_seconds() / 86400
    return f"{days:.1f}d"


def main() -> int:
    parser = argparse.ArgumentParser(description="Report the current open data_patrol_log backlog")
    parser.add_argument("--min-age-days", type=float, default=0.0, help="Only show findings open at least N days")
    parser.add_argument("--severity", choices=["info", "warn", "error", "critical"], help="Filter by severity")
    parser.add_argument("--check-name", help="Filter by exact check_name")
    parser.add_argument("--limit", type=int, default=200, help="Max rows to print (default 200)")
    args = parser.parse_args()

    where = ["status = 'open'"]
    params: list[object] = []
    if args.severity:
        where.append("severity = %s")
        params.append(args.severity)
    if args.check_name:
        where.append("check_name = %s")
        params.append(args.check_name)
    where_sql = " AND ".join(where)

    with DatabaseContext("read", timeout=20) as cur:
        cur.execute(
            f"""
            SELECT check_name, target_table, severity, message, created_at,
                   (SELECT MAX(created_at) FROM data_patrol_log p2 WHERE p2.check_name = p1.check_name
                    AND p2.target_table = p1.target_table) AS last_seen_at
            FROM data_patrol_log p1
            WHERE {where_sql}
            ORDER BY created_at ASC
            """,
            params,
        )
        rows = cur.fetchall()

    if not rows:
        print("No open data_patrol_log findings match the given filters.")
        return 0

    filtered = []
    for row in rows:
        opened_at = row["created_at"]
        age_days = (datetime.now(timezone.utc) - opened_at.replace(tzinfo=timezone.utc)).total_seconds() / 86400
        if age_days >= args.min_age_days:
            filtered.append(row)

    if not filtered:
        print(f"No open findings older than {args.min_age_days} day(s).")
        return 0

    print(f"{len(filtered)} open data_patrol_log finding(s) (oldest first):\n")
    for row in filtered[: args.limit]:
        opened_at, last_seen_at = row["created_at"], row["last_seen_at"]
        stale_note = ""
        if (
            last_seen_at
            and (datetime.now(timezone.utc) - last_seen_at.replace(tzinfo=timezone.utc)).total_seconds() > 86400
        ):
            stale_note = (
                f"  [no newer run has touched this since {last_seen_at.date()} - check may have stopped firing]"
            )
        print(
            f"[{row['severity'].upper():8}] {row['check_name']} ({row['target_table']}) "
            f"- open {_age_str(opened_at)}{stale_note}\n    {row['message']}"
        )

    if len(filtered) > args.limit:
        print(f"\n...and {len(filtered) - args.limit} more (use --limit to see more)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
