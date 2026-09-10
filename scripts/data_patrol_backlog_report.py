#!/usr/bin/env python3
"""Surface the current open data_patrol_log backlog to a human, and let a human triage it.

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

EXTENDED 2026-09-10 (goal session: "identify bad data, quarantine, triage, fix, verify"): the
open/resolved lifecycle above still couldn't distinguish "nobody has ever looked at this" from
"a human reviewed this and it's an accepted condition" - the actual triage gap. Adds
data_patrol_review (migration 1278): --review to record a triage decision for a (check_name,
target_table) pair, and --unreviewed-only to surface exactly what still needs a human's
attention. A review does NOT track the specific finding text it was made against - a finding
whose severity/scale changes materially after being marked "acceptable" (e.g. a symbol count
jumping 5x) still shows as reviewed, not automatically re-flagged. Re-reviewing periodically
is a human process, not (yet) an automated one.

Usage:
    python scripts/data_patrol_backlog_report.py                  # full open backlog, newest first
    python scripts/data_patrol_backlog_report.py --min-age-days 7 # only backlog older than 7 days
    python scripts/data_patrol_backlog_report.py --severity warn  # filter by severity
    python scripts/data_patrol_backlog_report.py --check-name revenue_yoy_magnitude_jump
    python scripts/data_patrol_backlog_report.py --unreviewed-only

    python scripts/data_patrol_backlog_report.py --review revenue_yoy_magnitude_jump \\
        --table annual_income_statement --status acceptable \\
        --note "Real M&A/divestiture-driven swings, not a bug - see check's own module docstring"
"""

from __future__ import annotations

import argparse
import getpass
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


def _record_review(check_name: str, target_table: str | None, status: str, note: str) -> int:
    with DatabaseContext("write", timeout=20) as cur:
        cur.execute(
            """
            INSERT INTO data_patrol_review (check_name, target_table, status, note, reviewed_by)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (check_name, target_table)
            DO UPDATE SET status = EXCLUDED.status, note = EXCLUDED.note,
                          reviewed_by = EXCLUDED.reviewed_by, reviewed_at = CURRENT_TIMESTAMP
            """,
            (check_name, target_table, status, note, getpass.getuser()),
        )
    print(f"Recorded review: {check_name} ({target_table}) = {status}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Report and triage the current open data_patrol_log backlog")
    parser.add_argument("--min-age-days", type=float, default=0.0, help="Only show findings open at least N days")
    parser.add_argument("--severity", choices=["info", "warn", "error", "critical"], help="Filter by severity")
    parser.add_argument("--check-name", help="Filter by exact check_name")
    parser.add_argument("--limit", type=int, default=200, help="Max rows to print (default 200)")
    parser.add_argument(
        "--unreviewed-only",
        action="store_true",
        help="Only show actionable (warn/error/critical) findings with no current review - "
        "excludes info-severity health confirmations, which are never findings to triage",
    )
    parser.add_argument("--review", metavar="CHECK_NAME", help="Record a triage decision instead of listing")
    parser.add_argument("--table", help="target_table for --review (omit for a table-less check)")
    parser.add_argument("--status", choices=["acceptable", "needs_fix"], help="Status for --review")
    parser.add_argument("--note", help="Reason for --review (required)")
    args = parser.parse_args()

    if args.review:
        if not args.status or not args.note:
            parser.error("--review requires --status and --note")
        return _record_review(args.review, args.table, args.status, args.note)

    where = ["p1.status = 'open'"]
    params: list[object] = []
    if args.severity:
        where.append("p1.severity = %s")
        params.append(args.severity)
    if args.check_name:
        where.append("p1.check_name = %s")
        params.append(args.check_name)
    where_sql = " AND ".join(where)

    with DatabaseContext("read", timeout=20) as cur:
        cur.execute(
            """
            SELECT symbol, check_name, reason, detected_at
            FROM symbol_quarantine
            WHERE resolved_at IS NULL
            ORDER BY detected_at DESC
            """
        )
        quarantined = cur.fetchall()
        if quarantined:
            print(f"{len(quarantined)} symbol(s) currently quarantined (excluded from scoring/trading):")
            for row in quarantined[:50]:
                print(f"  {row['symbol']:8} {row['check_name']:30} {row['reason']}")
            if len(quarantined) > 50:
                print(f"  ...and {len(quarantined) - 50} more")
            print()

        cur.execute(
            f"""
            SELECT p1.check_name, p1.target_table, p1.severity, p1.message, p1.created_at,
                   (SELECT MAX(created_at) FROM data_patrol_log p2 WHERE p2.check_name = p1.check_name
                    AND p2.target_table = p1.target_table) AS last_seen_at,
                   r.status AS review_status, r.note AS review_note, r.reviewed_at
            FROM data_patrol_log p1
            LEFT JOIN data_patrol_review r
              ON r.check_name = p1.check_name
             AND r.target_table IS NOT DISTINCT FROM p1.target_table
            WHERE {where_sql}
            ORDER BY p1.created_at ASC
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
        if age_days < args.min_age_days:
            continue
        if args.unreviewed_only and (row["review_status"] is not None or row["severity"] == "info"):
            continue
        filtered.append(row)

    if not filtered:
        print("No findings match the given filters.")
        return 0

    # INFO-severity rows are health CONFIRMATIONS (e.g. "price_daily fresh", "loader_contract
    # OK") - re-logged every run whether or not anything is wrong, not findings that need a
    # triage decision. Counting them as "unreviewed" alongside real WARN/ERROR/CRITICAL
    # findings would make the backlog look far larger and less triaged than it actually is -
    # split the summary so "needs triage" means what it says.
    actionable = [r for r in rows if r["severity"] != "info"]
    reviewed_acceptable = sum(1 for r in actionable if r["review_status"] == "acceptable")
    reviewed_needs_fix = sum(1 for r in actionable if r["review_status"] == "needs_fix")
    unreviewed = len(actionable) - reviewed_acceptable - reviewed_needs_fix
    print(
        f"{len(rows)} open finding(s) ({len(rows) - len(actionable)} info-only health "
        f"confirmations, {len(actionable)} actionable): {reviewed_acceptable} reviewed-acceptable, "
        f"{reviewed_needs_fix} reviewed-needs_fix, {unreviewed} actionable findings never reviewed\n"
    )

    print(f"Showing {len(filtered)} finding(s) (oldest first):\n")
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
        review_note = ""
        if row["review_status"]:
            review_note = f"  [REVIEWED: {row['review_status']} - {row['review_note']}]"
        print(
            f"[{row['severity'].upper():8}] {row['check_name']} ({row['target_table']}) "
            f"- open {_age_str(opened_at)}{stale_note}{review_note}\n    {row['message']}"
        )

    if len(filtered) > args.limit:
        print(f"\n...and {len(filtered) - args.limit} more (use --limit to see more)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
