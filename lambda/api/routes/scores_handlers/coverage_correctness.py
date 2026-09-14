"""Route: /api/scores/correctness-coverage - for every pillar-input TABLE (as opposed to
/api/scores/coverage, which measures per-FIELD completeness - is a value present at all), has
DataPatrol actually ever logged a finding against it, how recently, and what did it find.

REWRITTEN FROM SCRATCH 2026-09-13 (user directive: the original version - "which check
module's SOURCE TEXT happens to mention this column name" - was rejected outright as
worthless: "it tells us nothing, gives us nothing"). That approach measured whether a check
COULD in principle look at a field, based on a source-code grep; it never asked whether
DataPatrol had ever actually RUN and found (or not found) anything real for that table. This
version answers the real question instead, sourced entirely from `data_patrol_log` - the table
every check module's own `self.log(...)` call writes to (`algo/monitoring/data_patrol/base.py`
-> `PatrolLogger`) - which is ground truth about what has actually executed, not a guess about
what source code could theoretically do.

For each pillar-input table (`_TABLE_GROUP` minus `_UNSCORED_TABLES` and the two non-factor
entries `stock_scores`/`stock_symbols`), this reports:
  - whether ANY row has ever been logged against that exact `target_table` value (never_logged
    if not - the table has no check-execution history at all, not just "no matching source
    text")
  - the most recent `created_at` and how many days ago that was
  - within a trailing window (`_LOOKBACK_DAYS`, default 30 - long enough to catch the monthly
    `xbrl_segment_sum_reconciliation` cadence documented in CLAUDE.md, not just daily checks),
    a severity breakdown (critical/error/warn/info) and the actual most recent finding messages
    per severity - real content, not just a count
  - a `status` bucket: never_logged / stale (has history, nothing in the window) /
    active_clean (recent activity, nothing above info) / active_findings (recent
    warn/error/critical)

`target_table` is a real DB table name for most checks (live-verified: staleness.py,
tie_out_bounds_annual1.py, score_ratio_outliers.py all log against quality_metrics/
growth_metrics/value_metrics/stability_metrics by that exact name), but is table-level, not
per-column - coarser than the old per-factor claim, but every number in it is something that
actually happened, which the old version never was."""

from __future__ import annotations

import logging
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import error_response, handle_db_error, json_response

from algo.monitoring.data_patrol.checks.staleness import build_staleness_sources
from loaders.loader_registry import LOADER_TABLES, PSEUDO_LOADER_TABLES

from .coverage_classification import _TABLE_GROUP, _UNSCORED_TABLES

logger = logging.getLogger(__name__)

# Long enough to catch the monthly xbrl_segment_sum_reconciliation / weekly-ish DQC-Arelle
# cadences documented in CLAUDE.md, not just daily checks like staleness/tie_out - a shorter
# window would mislabel a check that legitimately only runs a few times a month as "stale".
_LOOKBACK_DAYS = 30
_SEVERITIES = ("critical", "error", "warn", "info")

# ADDED 2026-09-13 (goal session follow-up to "what else should the table track" question):
# reads the SAME (table -> freq) mapping StalenessChecker.run() actually enforces, rather than
# a second hand-typed copy of these cadences that could silently drift from the real thresholds
# - the exact bug class ("this table never got a staleness entry") that produced the naaim/
# value_metrics/quality_metrics/momentum_metrics gaps documented in staleness.py's own comments.
# Purely descriptive here (labels "daily"/"weekly"/"monthly"/"quarterly" next to a table's
# days-since-last-checked so a reviewer can tell whether that number is normal for THIS table's
# own cadence), not a second threshold - a table not covered by staleness.py at all (checked
# only by tie_out/coverage/etc., or not yet covered by any check) has no entry and reports None.
_CADENCE_BY_TABLE: dict[str, str] = {tbl: freq for tbl, _col, freq, _max_days, _sev in build_staleness_sources()}

# The two _TABLE_GROUP entries that aren't a pillar INPUT table at all - stock_scores is the
# scoring OUTPUT, stock_symbols is universe/reference metadata - so they're excluded from this
# panel's table universe the same way _UNSCORED_TABLES already excludes whole-table
# display-only cases (positioning_metrics, sec_segment_info, ...).
_NON_FACTOR_TABLES = {"stock_scores", "stock_symbols"}


def _scored_pillar_tables() -> list[str]:
    """Real, actively-loaded pillar-input tables: every _TABLE_GROUP entry except the
    whole-table unscored cases and the two non-factor tables above, further restricted to
    tables an active loader still writes to. Derived from the same single source of truth
    /api/scores/coverage uses for its own scored/unscored classification, so this panel's
    table universe can't silently drift out of sync with that report's.

    FIXED 2026-09-13 (live-caught right after the data_patrol_log rewrite shipped, checking
    its own "never checked" output): the pre-rewrite coverage_correctness.py filtered its
    factor universe to LOADER_TABLES/PSEUDO_LOADER_TABLES-active tables, and that filter was
    dropped in the rewrite. yfinance_snapshot has zero active loader (confirmed via
    LOADER_TABLES/PSEUDO_LOADER_TABLES membership - it's the deprecated table
    coverage_sources.py's own _SOURCE_LABELS already calls out as "Yahoo Finance (snapshot,
    deprecated)") and so would ALWAYS show as a false "never checked" gap - the exact
    "measuring a population nobody actually scores" bug class coverage_classification.py's own
    _UNSCORED_TABLES comments already warn about, just for a dead table instead of a
    display-only field."""
    active = {t for tables in LOADER_TABLES.values() for t in tables} | {
        t for tables in PSEUDO_LOADER_TABLES.values() for t in tables
    }
    return sorted(t for t in _TABLE_GROUP if t not in _UNSCORED_TABLES and t not in _NON_FACTOR_TABLES and t in active)


def _classify_status(total_ever: int, days_since_last: float | None, recent: dict[str, int]) -> str:
    if total_ever == 0:
        return "never_logged"
    if days_since_last is not None and days_since_last > _LOOKBACK_DAYS:
        return "stale"
    if recent["critical"] or recent["error"] or recent["warn"]:
        return "active_findings"
    return "active_clean"


def _fetch_table_history(cur: cursor, tables: list[str]) -> dict[str, dict[str, Any]]:
    """One aggregate query for every table's ever/recent counts and last-seen timestamp."""
    # days_since_last_seen computed IN SQL (EXTRACT(EPOCH ...) on a plain interval), not by
    # subtracting a fetched `now()` from `last_seen` in Python - live-found 2026-09-13:
    # data_patrol_log.created_at is `timestamptz`, but this DB session's own `now()` came back
    # offset-naive, so `server_now - last_seen` raised "can't subtract offset-naive and
    # offset-aware datetimes" on every call. `now() - created_at` inside Postgres never has
    # this problem since both sides are evaluated in the same timezone-aware engine.
    cur.execute(
        f"""
        SELECT target_table,
               MAX(created_at) AS last_seen,
               EXTRACT(EPOCH FROM (now() - MAX(created_at))) / 86400 AS days_since_last_seen,
               COUNT(*) AS total_ever,
               COUNT(*) FILTER (WHERE created_at >= now() - interval '{_LOOKBACK_DAYS} days'
                                 AND severity = 'critical') AS recent_critical,
               COUNT(*) FILTER (WHERE created_at >= now() - interval '{_LOOKBACK_DAYS} days'
                                 AND severity = 'error') AS recent_error,
               COUNT(*) FILTER (WHERE created_at >= now() - interval '{_LOOKBACK_DAYS} days'
                                 AND severity = 'warn') AS recent_warn,
               COUNT(*) FILTER (WHERE created_at >= now() - interval '{_LOOKBACK_DAYS} days'
                                 AND severity = 'info') AS recent_info
        FROM data_patrol_log
        WHERE target_table = ANY(%s)
        GROUP BY target_table
        """,
        (tables,),
    )
    out: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        table, last_seen, days_since, total_ever, crit, err, warn, info = row
        out[table] = {
            "last_seen": last_seen,
            "days_since_last_seen": float(days_since) if days_since is not None else None,
            "total_ever": int(total_ever),
            "recent": {"critical": int(crit), "error": int(err), "warn": int(warn), "info": int(info)},
        }
    return out


def _fetch_recent_findings(cur: cursor, tables: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Up to 3 most-recent, most-severe findings per table within the lookback window - real
    finding text, not just a count, so a reviewer can see what DataPatrol actually said without
    leaving this panel."""
    cur.execute(
        f"""
        SELECT target_table, severity, check_name, message, details, created_at
        FROM (
            SELECT target_table, severity, check_name, message, details, created_at,
                   ROW_NUMBER() OVER (
                       PARTITION BY target_table
                       ORDER BY CASE severity
                                    WHEN 'critical' THEN 0
                                    WHEN 'error' THEN 1
                                    WHEN 'warn' THEN 2
                                    ELSE 3
                                END,
                                created_at DESC
                   ) AS rn
            FROM data_patrol_log
            WHERE target_table = ANY(%s)
              AND created_at >= now() - interval '{_LOOKBACK_DAYS} days'
        ) ranked
        WHERE rn <= 3
        ORDER BY target_table, rn
        """,
        (tables,),
    )
    findings: dict[str, list[dict[str, Any]]] = {}
    for table, severity, check_name, message, details, created_at in cur.fetchall():
        # `details` is the same JSONB payload each check's self.log(...) call builds -
        # typically {"count": N, "examples": [{"symbol": ..., <the specific flagged
        # values>}, ...]} - the actual symbols/inputs behind the finding, not just the
        # summary message. Passed through as-is so the frontend can render whatever shape
        # a given check happened to log, rather than this endpoint guessing a common schema.
        findings.setdefault(table, []).append(
            {
                "severity": severity,
                "check": check_name,
                "message": message,
                "details": details,
                "created_at": created_at.isoformat() if created_at else None,
            }
        )
    return findings


def _fetch_open_quarantine_counts(cur: cursor, tables: list[str]) -> dict[str, int]:
    """Open (unresolved) symbol_quarantine rows per table, so a "Findings open" row can show
    the actual actionable backlog size instead of just "something fired recently".

    ADDED 2026-09-13 (goal session follow-up to "what else should the table track" question).

    symbol_quarantine has no target_table column of its own - only check_name. Most checks log
    to exactly one target_table (live-verified: every check_name currently present in
    symbol_quarantine - ohlc_sanity/quarterly_revenue_sum_vs_annual_extreme - maps 1:1), but a
    handful of check_name values in data_patrol_log fan out across many tables (e.g.
    "staleness" itself logs to 27 different tables, "coverage" to 5) because one checker class
    iterates a table list internally. Attributing a quarantine row to every table a check_name
    has EVER logged against would misattribute for any of those multi-table checks, so this only
    joins check_name -> target_table for check_names that map to exactly one target_table in
    data_patrol_log - unambiguous today, and safe if a future multi-table check ever starts
    quarantining (it simply won't get counted here rather than getting counted everywhere)."""
    cur.execute(
        """
        SELECT dpl.target_table, COUNT(*)
        FROM symbol_quarantine sq
        JOIN (
            SELECT check_name, MIN(target_table) AS target_table
            FROM data_patrol_log
            GROUP BY check_name
            HAVING COUNT(DISTINCT target_table) = 1
        ) dpl ON dpl.check_name = sq.check_name
        WHERE sq.resolved_at IS NULL
          AND dpl.target_table = ANY(%s)
        GROUP BY dpl.target_table
        """,
        (tables,),
    )
    return {table: int(count) for table, count in cur.fetchall()}


def _get_scores_correctness_coverage(cur: cursor) -> Any:
    """Per pillar-input-table DataPatrol execution history - see this module's docstring."""
    try:
        tables = _scored_pillar_tables()
        history = _fetch_table_history(cur, tables)
        findings = _fetch_recent_findings(cur, tables)
        open_quarantine = _fetch_open_quarantine_counts(cur, tables)

        rows: list[dict[str, Any]] = []
        for table in tables:
            h = history.get(
                table,
                {
                    "last_seen": None,
                    "days_since_last_seen": None,
                    "total_ever": 0,
                    "recent": dict.fromkeys(_SEVERITIES, 0),
                },
            )
            last_seen = h["last_seen"]
            days_since = h["days_since_last_seen"]
            status = _classify_status(h["total_ever"], days_since, h["recent"])
            rows.append(
                {
                    "table": table,
                    "group": _TABLE_GROUP.get(table, table),
                    "status": status,
                    "cadence": _CADENCE_BY_TABLE.get(table),
                    "last_seen_at": last_seen.isoformat() if last_seen else None,
                    "days_since_last_seen": round(days_since, 1) if days_since is not None else None,
                    "total_findings_ever": h["total_ever"],
                    "recent": h["recent"],
                    "recent_findings": findings.get(table, []),
                    "open_quarantine_count": open_quarantine.get(table, 0),
                }
            )

        rows.sort(
            key=lambda r: (
                {"never_logged": 0, "active_findings": 1, "stale": 2, "active_clean": 3}[r["status"]],
                -r["open_quarantine_count"],
                r["group"],
                r["table"],
            )
        )

        # Pillar-level rollup - the panel's actual triage question ("which pillar's tables are
        # least monitored") answered without eyeballing a flat list, same "where to look first"
        # intent the old version's headline numbers gestured at, now backed by real status
        # buckets instead of a source-grep percentage.
        pillar_totals: dict[str, dict[str, int]] = {}
        for r in rows:
            bucket = pillar_totals.setdefault(
                r["group"], {"total": 0, "never_logged": 0, "stale": 0, "active_findings": 0, "active_clean": 0}
            )
            bucket["total"] += 1
            bucket[r["status"]] += 1
        pillar_summary: list[dict[str, Any]] = [{"pillar": pillar, **v} for pillar, v in pillar_totals.items()]
        pillar_summary.sort(key=lambda p: (-(int(p["never_logged"]) + int(p["active_findings"])), str(p["pillar"])))

        totals = {
            "total_tables": len(rows),
            "never_logged": sum(1 for r in rows if r["status"] == "never_logged"),
            "stale": sum(1 for r in rows if r["status"] == "stale"),
            "active_findings": sum(1 for r in rows if r["status"] == "active_findings"),
            "active_clean": sum(1 for r in rows if r["status"] == "active_clean"),
            "open_quarantine_count": sum(r["open_quarantine_count"] for r in rows),
        }

        return json_response(
            200,
            {
                "window_days": _LOOKBACK_DAYS,
                "totals": totals,
                "pillar_summary": pillar_summary,
                "tables": rows,
            },
        )
    except Exception as e:
        code, error_type, message = handle_db_error(e, "get scores correctness coverage")
        return error_response(code, error_type, message)
