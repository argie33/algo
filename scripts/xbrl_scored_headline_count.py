#!/usr/bin/env python3
"""Diagnostic (read-only): distinct-symbol count for the scored "Missing SEC/XBRL data"
headline the goal session has been tracking (309 as of 2026-09-11 EOD per memory).

/api/scores/coverage reports per-FACTOR row counts (a symbol missing both pe_ratio and
ps_ratio for the same underlying no_income_statement gap counts twice there) - this script
dedupes to distinct symbols, reusing the exact same categorization rulebook
(coverage_category_rules.py's _categorize_reason) and active-universe filter
(get_active_symbols(exclude_etfs=True)) the live dashboard uses, so the number is directly
comparable to what /api/scores/coverage would show if it exposed a deduped total.

Usage: python scripts/xbrl_scored_headline_count.py
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "lambda" / "api"))

from routes.scores_handlers.coverage_classification import (  # noqa: E402
    _UNSCORED_FACTORS,
    _UNSCORED_TABLES,
    _categorize_reason,
)

from loaders.loader_registry import LOADER_TABLES, PSEUDO_LOADER_TABLES  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.loaders.helpers import get_active_symbols  # noqa: E402

_TABLES_WITH_ACTIVE_LOADER = {t for tables in LOADER_TABLES.values() for t in tables} | {
    t for tables in PSEUDO_LOADER_TABLES.values() for t in tables
}

_BARE_REASON_TABLES = (
    "institutional_holdings_13f",
    "analyst_earnings_estimates",
    "sec_segment_info",
    "sec_segment_metrics",
    "short_interest_finra",
    "sec_valuations",
    "signal_quality_scores",
)


def _find_reason_columns(cur: object) -> list[tuple[str, str]]:
    cur.execute(  # type: ignore[attr-defined]
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE column_name LIKE '%unavailable_reason%' AND table_schema = 'public'
        ORDER BY table_name, column_name
        """
    )
    columns = [(r[0], r[1]) for r in cur.fetchall() if r[0] in _TABLES_WITH_ACTIVE_LOADER]  # type: ignore[attr-defined]

    cur.execute(  # type: ignore[attr-defined]
        """
        SELECT table_name, column_name FROM information_schema.columns
        WHERE column_name = 'reason' AND table_schema = 'public' AND table_name = ANY(%s)
        ORDER BY table_name
        """,
        (list(_BARE_REASON_TABLES),),
    )
    columns.extend((r[0], r[1]) for r in cur.fetchall())  # type: ignore[attr-defined]
    return columns


def main() -> None:
    active = set(get_active_symbols(exclude_etfs=True))
    print(f"active universe (exclude_etfs): {len(active)}")

    with DatabaseContext("read") as cur:
        reason_columns = _find_reason_columns(cur)

        missing_symbols: set[str] = set()
        per_factor: list[tuple[str, str, int]] = []
        for table, column in reason_columns:
            factor_name = column.replace("_unavailable_reason", "") if column != "reason" else table
            if table in _UNSCORED_TABLES or (table, factor_name) in _UNSCORED_FACTORS:
                continue
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name=%s
                  AND column_name IN ('symbol','fiscal_year','date','computed_at','updated_at','created_at')
                """,
                (table,),
            )
            cols = {r[0] for r in cur.fetchall()}
            if "symbol" not in cols:
                continue
            order_col = next(
                (c for c in ("fiscal_year", "date", "computed_at", "updated_at", "created_at") if c in cols), None
            )
            if order_col is None:
                continue
            column_safe = column.replace('"', "")
            table_safe = table.replace('"', "")
            order_col_safe = order_col.replace('"', "")
            # Do NOT filter WHERE column IS NOT NULL before taking the latest row per
            # symbol - a symbol resolved on its most recent row (reason now NULL) would
            # otherwise still surface an older, stale non-null reason as if unresolved
            # (live-caught: this exact bug inflated dividend_data's contribution 549->79
            # before this fix, e.g. ABNB's stale historical 'no_dividend_xbrl_concepts'
            # row outranking its current, correct 'non_dividend_paying_stock' row once
            # the NOT NULL filter excluded the real latest row from DISTINCT ON's view).
            cur.execute(
                f"""
                SELECT DISTINCT ON (symbol) symbol, "{column_safe}"
                FROM "{table_safe}"
                ORDER BY symbol, "{order_col_safe}" DESC
                """
            )
            hit_this_factor = 0
            for symbol, reason in cur.fetchall():
                if symbol not in active or reason is None:
                    continue
                if _categorize_reason(reason) == "Missing SEC/XBRL data":
                    missing_symbols.add(symbol)
                    hit_this_factor += 1
            if hit_this_factor:
                per_factor.append((table, column, hit_this_factor))

    print(f"\nDISTINCT-SYMBOL SCORED 'Missing SEC/XBRL data' HEADLINE: {len(missing_symbols)}\n")
    per_factor.sort(key=lambda x: -x[2])
    for table, column, count in per_factor[:20]:
        print(f"  {table}.{column}: {count}")


if __name__ == "__main__":
    main()
