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

from utils.db.context import DatabaseContext


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
    return [(r[0], r[1]) for r in cur.fetchall()]


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
