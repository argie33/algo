"""Route: /api/scores/correctness-coverage - which pillar-input factors have zero DataPatrol
check actually validating them (as opposed to /api/scores/coverage, which measures
COMPLETENESS - is the value present at all - not CORRECTNESS - is a present value ever
cross-checked for plausibility/consistency).

ADDED 2026-09-13 (goal session: "does the React site have the data-health insights we need"
continuation, companion to ScoresDataCoverage/coverage.py) - the prior session's finding that
"89 of 111 pillar-input fields have zero direct check" was never persisted anywhere (no memory
entry, no script, no commit - confirmed by full-repo/memory search before writing this), so
this re-derives it live instead of trusting the unverifiable number: same factor universe
`_get_scores_coverage` already discovers (every `*_unavailable_reason` column plus the
bare-`reason` allowlist, scoped to actively-loaded tables), cross-referenced against which
`algo/monitoring/data_patrol/checks/*.py` module source text actually mentions both that
table and that factor's column name.

This is a static-text heuristic, not semantic analysis - deliberately conservative in one
direction (requires BOTH the table name and the exact column name as whole words in the same
check file, not just the column name alone) to avoid a common short column name like
"revenue" or "reason" cross-matching an unrelated table's check, at the cost of undercounting
a check that references a factor only via a joined/aliased column name or a shared helper
function. A "checked" verdict here means "worth a closer look to confirm what it actually
validates", not proof of a rigorous check - the same posture xbrl_dqc_arelle_check.py's own
false-positive-filter documentation takes toward its own findings."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import error_response, handle_db_error, json_response

from loaders.loader_registry import LOADER_TABLES, PSEUDO_LOADER_TABLES

from .coverage_sources import _resolve_factor_value_col

logger = logging.getLogger(__name__)

_CHECKS_DIR = Path(__file__).resolve().parents[4] / "algo" / "monitoring" / "data_patrol" / "checks"

_BARE_REASON_TABLES = (
    "institutional_holdings_13f",
    "analyst_earnings_estimates",
    "sec_segment_info",
    "sec_segment_metrics",
    "short_interest_finra",
    "sec_valuations",
    "signal_quality_scores",
)


def _load_check_sources() -> dict[str, str]:
    """Module name -> full source text, for every check module (skips __init__.py and the
    tie_out_shared.py helper, which is imported by other tie_out_* modules rather than being
    a check registered on its own)."""
    sources: dict[str, str] = {}
    if not _CHECKS_DIR.is_dir():
        return sources
    for path in sorted(_CHECKS_DIR.glob("*.py")):
        if path.name in ("__init__.py", "tie_out_shared.py"):
            continue
        try:
            sources[path.stem] = path.read_text(encoding="utf-8")
        except OSError:
            continue
    return sources


def _referencing_checks(table: str, factor_name: str, check_sources: dict[str, str]) -> list[str]:
    """Check module names whose source mentions both `table` and `factor_name` as whole
    words - see this module's docstring for why both are required."""
    if not factor_name:
        # No factor name to search for - nothing to process, not a data-loss case.
        return []
    table_re = re.compile(rf"\b{re.escape(table)}\b")
    factor_re = re.compile(rf"\b{re.escape(factor_name)}\b")
    return [name for name, text in check_sources.items() if table_re.search(text) and factor_re.search(text)]


def _get_scores_correctness_coverage(cur: cursor) -> Any:
    """Factor-level correctness-check coverage: for every pillar-input factor
    /api/scores/coverage tracks, which (if any) DataPatrol check modules reference it.
    Cheap relative to /api/scores/coverage - no per-table data scans, just information_schema
    lookups plus reading ~20 local check-module source files - so this is served in one call,
    no chunking needed."""
    try:
        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE column_name LIKE %s
              AND table_schema = 'public'
            ORDER BY table_name, column_name
            """,
            ("%unavailable_reason%",),
        )
        reason_columns = [(r[0], r[1]) for r in cur.fetchall()]

        _tables_with_active_loader = {t for tables in LOADER_TABLES.values() for t in tables} | {
            t for tables in PSEUDO_LOADER_TABLES.values() for t in tables
        }
        reason_columns = [(t, c) for t, c in reason_columns if t in _tables_with_active_loader]

        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE column_name = 'reason'
              AND table_schema = 'public'
              AND table_name = ANY(%s)
            ORDER BY table_name
            """,
            (list(_BARE_REASON_TABLES),),
        )
        reason_columns.extend((r[0], r[1]) for r in cur.fetchall())

        check_sources = _load_check_sources()
        table_all_cols_cache: dict[str, set[str]] = {}
        factors: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for table, column in reason_columns:
            factor_name, _value_col, _unavailable_col = _resolve_factor_value_col(
                cur, table, column, table_all_cols_cache
            )
            key = (table, factor_name)
            if not factor_name or key in seen:
                continue
            seen.add(key)
            checks = _referencing_checks(table, factor_name, check_sources)
            factors.append(
                {
                    "table": table,
                    "factor": factor_name,
                    "checked": len(checks) > 0,
                    "checks": sorted(checks),
                }
            )

        factors.sort(key=lambda f: (f["checked"], f["table"], f["factor"]))
        checked_count = sum(1 for f in factors if f["checked"])
        return json_response(
            200,
            {
                "factor_count": len(factors),
                "checked_count": checked_count,
                "unchecked_count": len(factors) - checked_count,
                "check_module_count": len(check_sources),
                "factors": factors,
            },
        )
    except Exception as e:
        code, error_type, message = handle_db_error(e, "get scores correctness coverage")
        return error_response(code, error_type, message)
