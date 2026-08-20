#!/usr/bin/env python3
"""Diagnostic (read-only): count rows per unavailable_reason value, for every
*_unavailable_reason column in the DB, on each table's latest row per symbol.

Goal-session tool (2026-08-17, "no SEC data" audit): the ScoresDashboard shows
per-stock reasons but nothing aggregates them across the universe, so there was
no way to see which gaps are widespread (worth chasing as loader/extraction bugs)
vs. rare/legitimate (e.g. non_dividend_paying_stock, unprofitable_stock).

Usage: python scripts/audit_unavailable_reasons.py [--min-count N]
"""

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loaders.loader_registry import LOADER_TABLES, PSEUDO_LOADER_TABLES
from utils.db.context import DatabaseContext

# FIXED 2026-08-19 (goal session continuation): kept in sync with
# lambda/api/routes/scores.py::_get_scores_coverage's identical exclusion - see that
# file's comment for the full rationale. yfinance_snapshot has had no active loader
# since Session 275 (frozen rows, nothing left to fix), so reporting its gaps here
# alongside real, currently-loaded tables' gaps would send this same session's own
# diagnostic tool chasing a table no loader run can ever change.
_TABLES_WITH_ACTIVE_LOADER = {t for tables in LOADER_TABLES.values() for t in tables} | {
    t for tables in PSEUDO_LOADER_TABLES.values() for t in tables
}


def find_reason_columns(cur: Any) -> list[tuple[str, str]]:
    cur.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE column_name LIKE '%unavailable_reason%'
          AND table_schema = 'public'
        ORDER BY table_name, column_name
        """
    )
    columns = [(r[0], r[1]) for r in cur.fetchall() if r[0] in _TABLES_WITH_ACTIVE_LOADER]

    # FIXED 2026-08-19 (goal: "no SEC data" audit continuation): this only ever matched the
    # "{field}_unavailable_reason" naming convention, completely missing a whole second
    # convention this codebase uses - a bare "reason" column (paired with "data_unavailable")
    # on a table's TOP-LEVEL row, not a per-field suffix. That silently blinded this tool (and
    # the live coverage dashboard, which uses the identical pattern - see
    # lambda/api/routes/scores.py's _get_scores_coverage) to gaps in some of the most
    # foundational SEC tables in the whole schema: annual_income_statement,
    # annual_balance_sheet, annual_cash_flow, quarterly_income_statement,
    # quarterly_balance_sheet, quarterly_cash_flow, sec_valuations, company_info_sec (which
    # has NO *_unavailable_reason column at all - it was 100% invisible before this fix).
    # Scoped to tables that actually have BOTH "symbol" and "data_unavailable" alongside
    # "reason" - the real per-symbol-availability contract every table above follows -
    # rather than every bare "reason" column in the schema, which would also pull in
    # unrelated operational/audit-log tables (circuit_breaker_log, algo_orchestrator_state,
    # safeguard_audit_log, data_loader_status, ...) whose "reason" means something entirely
    # different and would just be noise here.
    cur.execute(
        """
        SELECT c.table_name
        FROM information_schema.columns c
        WHERE c.table_schema = 'public' AND c.column_name = 'reason'
          AND EXISTS (
            SELECT 1 FROM information_schema.columns c2
            WHERE c2.table_schema = 'public' AND c2.table_name = c.table_name AND c2.column_name = 'symbol'
          )
          AND EXISTS (
            SELECT 1 FROM information_schema.columns c3
            WHERE c3.table_schema = 'public' AND c3.table_name = c.table_name
              AND c3.column_name = 'data_unavailable'
          )
        ORDER BY c.table_name
        """
    )
    seen_tables = {t for t, _ in columns}
    columns.extend(
        (r[0], "reason") for r in cur.fetchall() if r[0] in _TABLES_WITH_ACTIVE_LOADER and r[0] not in seen_tables
    )
    return columns


def table_columns(cur: Any, table: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
          AND column_name IN ('symbol','date','fiscal_year','updated_at','created_at')
        """,
        (table,),
    )
    return {r[0] for r in cur.fetchall()}


def select_order_col(cols: set[str]) -> str:
    """Pick the best "latest row per symbol" ordering column available on a table.

    FIXED 2026-08-18: originally only recognized "date"/"fiscal_year", so any table
    using "updated_at"/"created_at" instead (e.g. dividend_data, which has
    symbol+created_at+updated_at but neither date nor fiscal_year) got "" back and
    silently fell through to the un-deduplicated query in main() - counting every
    historical row instead of one snapshot per symbol. Live-caught: dividend_data's
    "no_dividend_xbrl_concepts" reported 22,478 (all-history rows) when the real,
    deduplicated distinct-symbol count is 3,097 - a 7x inflation that could send
    someone chasing a "huge systemic bug" that isn't one. Returns "" (falsy) only when
    none of the four candidate columns exist, matching the pre-fix contract.
    """
    for candidate in ("date", "fiscal_year", "updated_at", "created_at"):
        if candidate in cols:
            return candidate
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-count", type=int, default=5)
    args = parser.parse_args()

    with DatabaseContext("read") as cur:
        columns = find_reason_columns(cur)
    print(f"Found {len(columns)} *_unavailable_reason columns across the schema.\n")

    for table, column in columns:
        try:
            with DatabaseContext("read") as cur:
                cols = table_columns(cur, table)
                order_col = select_order_col(cols)
                # FIXED 2026-08-19 (goal: "no SEC data" audit, same-day follow-up): this
                # script scanned {table} directly with no active-universe filter, same bug
                # as /api/algo/scores/coverage (lambda/api/routes/scores.py's
                # _get_scores_coverage) had - live-confirmed 6-9% of rows in quality_metrics/
                # growth_metrics/value_metrics/positioning_metrics/stability_metrics/
                # dividend_data belong to symbols no longer active (delisted, failed SPACs,
                # never pruned), and inactive symbols are disproportionately gap-heavy, not
                # proportional noise. Joining to stock_symbols and filtering active=true
                # keeps this script's output consistent with the now-fixed coverage report
                # instead of re-introducing the same overcounting via a second tool.
                active_join = (
                    f" JOIN stock_symbols _su ON _su.symbol = {table}.symbol AND _su.active = true"
                    if "symbol" in cols
                    else ""
                )
                if "symbol" in cols and order_col:
                    query = f"""
                        SELECT reason_val, COUNT(*) FROM (
                            SELECT DISTINCT ON ({table}.symbol) {table}.symbol, {table}.{column} AS reason_val
                            FROM {table}{active_join}
                            ORDER BY {table}.symbol, {table}.{order_col} DESC
                        ) latest
                        WHERE reason_val IS NOT NULL
                        GROUP BY reason_val
                        ORDER BY COUNT(*) DESC
                    """
                else:
                    query = f"""
                        SELECT {table}.{column} AS reason_val, COUNT(*)
                        FROM {table}{active_join}
                        WHERE {table}.{column} IS NOT NULL
                        GROUP BY {table}.{column}
                        ORDER BY COUNT(*) DESC
                    """
                cur.execute(query)
                rows = cur.fetchall()
        except Exception as e:
            print(f"  [SKIP] {table}.{column}: {e}")
            continue

        rows = [r for r in rows if r[1] >= args.min_count]
        if not rows:
            continue
        print(f"{table}.{column}:")
        for reason_val, count in rows:
            print(f"    {count:>6}  {reason_val}")
        print()


if __name__ == "__main__":
    main()
