"""Per-table/per-factor ordering-column and data-source-provenance helpers for the
/api/scores/coverage report.

Split 2026-09-05 (file-size-ratchet compliance split of coverage.py): `_coverage_order_col`
(pick the best "latest row per symbol" column), the `_SOURCE_LABELS`/`_SOURCE_ACRONYMS` ->
`_prettify_source` display-label mapping, the `data_source`/`source_tracking` breakdown
fetchers, and `_resolve_factor_sources`/`_resolve_factor_value_col` - all pure query/lookup
helpers `_get_scores_coverage` (coverage.py) calls per table/factor, none of which reference
the reason-categorization rulebook or classification logic in the other coverage_* siblings.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from psycopg2.extensions import cursor

logger = logging.getLogger(__name__)


def _coverage_order_col(cur: cursor, table: str, cols: set[str]) -> str:
    """Pick the best "latest row per symbol" ordering column available on a table.

    Same candidate order/fallback contract as scripts/audit_unavailable_reasons.py's
    select_order_col() - keep the two in sync if either changes.

    FIXED 2026-08-21 (goal session: "is missing data really missing, or are we doing it
    wrong again"): picking the first candidate that merely EXISTS on the table (old
    behavior) breaks on event-log tables where that column exists but is never populated -
    live-confirmed on earnings_calendar, which has a `fiscal_year` column (ranked above
    updated_at) that is NULL on all 450,856 rows. `DISTINCT ON (symbol) ORDER BY
    fiscal_year DESC` then has no real sort key at all (every row ties), so Postgres
    returns an arbitrary row per symbol instead of the actual latest one - live-reproduced
    on symbol A: a fresh, real row from today (updated_at 2026-08-21 06:10, eps_estimate
    populated) coexists with two stale, already-self-healed fetch_error rows from
    2026-08-12, and the old logic picked one of the stale errors, not today's real data.
    That's exactly the kind of "different freshness methodologies disagree" trap already
    documented for monitor_data_staleness.py vs Phase 1 - except here it wasn't even two
    real methodologies, just a candidate column nobody checked was populated. Now queries
    each present candidate's non-null count and picks the first that actually has data;
    tables where fiscal_year IS the real per-row key (annual/quarterly statements,
    sec_segment_info) are unaffected since it's populated on every row there.
    """
    candidates = [c for c in ("date", "fiscal_year", "updated_at", "created_at") if c in cols]
    if not candidates:
        return ""
    cur.execute(f"SELECT {', '.join(f'count({c})' for c in candidates)} FROM {table}")
    counts = cur.fetchone()
    for candidate, count in zip(candidates, counts, strict=True):
        if count:
            return candidate
    return candidates[0]


# Known *_data_source / *_source_tracking raw values -> human-readable labels (2026-08-21,
# goal: "show which source - SEC/yfinance/FRED/etc - each factor's data comes from"). These
# are the actual literal strings loaders write (see migrations 1022/1023/1135/1185/1202/1207
# and each loader's own `"data_source": "..."` assignment) - not guessed. Anything not in this
# map falls back to _prettify_source()'s generic token-capitalization instead of silently
# showing a raw snake_case value.
_SOURCE_LABELS: dict[str, str] = {
    "sec_audited": "SEC (audited financials)",
    "sec_audited_except_dual_class_shares_yfinance": "SEC (audited, dual-class shares via Yahoo Finance)",
    "sec_audited_except_forward_pe_yfinance": "SEC (audited, forward P/E via Yahoo Finance)",
    # ADDED 2026-08-29 (goal session: coverage-categorization sweep continuation): load_sec_
    # valuations.py's data_source for foreign private issuers, whose shares_outstanding comes
    # from a live yfinance fetch instead of SEC XBRL (SEC's own domestic-only shares tag isn't
    # usable for FPIs - see fpi_shares_excluded_domestic_only in
    # [[scores_coverage_other_bucket_96pct_fixed_20260829]]). Was falling through to the
    # generic snake_case-to-Title-Case fallback ("SEC Audited Except Fpi Shares Yahoo
    # Finance" - "Fpi" not expanded since "fpi" wasn't in _SOURCE_ACRONYMS either) instead of
    # a real label, unlike every sibling sec_audited_except_* entry above/below it (539 live
    # rows).
    "sec_audited_except_fpi_shares_yfinance": "SEC (audited, foreign-issuer shares via Yahoo Finance)",
    "sec_edgar_submissions": "SEC EDGAR submissions",
    "sec_edgar_filings": "SEC EDGAR filings",
    "sec_13f": "SEC Form 13F",
    "sec_form13f_bulk": "SEC Form 13F (bulk)",
    "sec_form4": "SEC Form 4/5",
    "sec_form345_bulk": "SEC Form 3/4/5 (bulk)",
    "yfinance_api": "Yahoo Finance",
    "yfinance_snapshot": "Yahoo Finance (snapshot, deprecated)",
    "yfinance_earnings_estimate": "Yahoo Finance (estimates)",
    "finra": "FINRA",
    "finra_query_api": "FINRA",
    "price_daily_aggregated": "Computed (price history)",
    "computed_from_price_daily": "Computed (price history)",
    "alpaca_api": "Alpaca",
    "mixed": "Mixed / legacy",
    "none": "Unavailable",
    "unavailable": "Unavailable",
    "not_recorded": "Not recorded",
}
_SOURCE_ACRONYMS = {
    "sec",
    "api",
    "xbrl",
    "fred",
    "cik",
    "13f",
    "10k",
    "20f",
    "finra",
    "cef",
    "reit",
    "spac",
    "gaap",
    "etf",
    "aaii",
    "naaim",
    "cusip",
    "ad",
    # ADDED 2026-08-29 (goal session: coverage-categorization sweep continuation): future-
    # proofs the generic fallback path for any not-yet-mapped raw source string containing
    # "fpi" (foreign private issuer) - see the sec_audited_except_fpi_shares_yfinance
    # _SOURCE_LABELS entry added the same session for the one already-known case.
    "fpi",
}


def _prettify_source(raw: str) -> str:
    """Turn a raw `data_source`/`source_tracking` value into a display label.

    Known values get an exact label from _SOURCE_LABELS (most of them, live-verified above).
    Anything else - a future loader's new source string this map hasn't been updated for -
    gets a generic snake_case-to-Title-Case pass instead of showing raw underscores, so a new
    source never renders as garbage, just as slightly-less-polished.
    """
    if raw in _SOURCE_LABELS:
        return _SOURCE_LABELS[raw]
    words = raw.replace("-", "_").split("_")
    out = []
    for w in words:
        lw = w.lower()
        if lw == "yfinance":
            out.append("Yahoo Finance")
        elif lw in _SOURCE_ACRONYMS:
            out.append(lw.upper())
        else:
            out.append(w.capitalize() if w else w)
    return " ".join(p for p in out if p)


def _fetch_table_source_breakdown(
    cur: cursor, table: str, cols: set[str], has_symbol: bool, order_col: str
) -> list[dict[str, Any]] | None:
    """Latest-row-per-symbol breakdown of a table's `data_source` column, or None if the
    table has no such column (or isn't per-symbol). See _get_scores_coverage's call site
    comment for why this is computed once per table rather than per factor.

    REWRITTEN 2026-09-01 (goal session: "this one timing out") - unlike the sparse
    *_unavailable_reason columns this loop otherwise deals with, `data_source` is dense
    (populated on essentially every row), so the "candidates" trick in the main query above
    doesn't apply here - genuinely needs each active symbol's actual latest-row source.
    The original `DISTINCT ON (symbol) ... ORDER BY symbol, order_col DESC` form forces
    Postgres to sort every one of the table's rows per symbol before picking the top one -
    live-confirmed this cost price_daily.data_source ~8s alone (26.2M rows across ~5,100
    active symbols), on top of the main query's own cost. A `LATERAL ... ORDER BY order_col
    DESC LIMIT 1` per active symbol instead lets Postgres walk the existing (symbol, date DESC)
    index straight to each symbol's one latest row without materializing or sorting the rest -
    live-verified byte-identical output, ~0.5s (16x faster) on price_daily, and
    indistinguishable on every smaller table tested.
    """
    if not (has_symbol and order_col and "data_source" in cols):
        return None
    try:
        cur.execute(
            f"""
            SELECT source_val, COUNT(*) FROM (
                SELECT pd.data_source AS source_val
                FROM stock_symbols _su
                CROSS JOIN LATERAL (
                    SELECT {table}.data_source
                    FROM {table}
                    WHERE {table}.symbol = _su.symbol
                    ORDER BY {table}.{order_col} DESC
                    LIMIT 1
                ) pd (data_source)
                WHERE _su.active = true
            ) latest
            GROUP BY source_val
            ORDER BY COUNT(*) DESC
            """
        )
        src_rows = cur.fetchall()
        src_total = sum(int(r[1]) for r in src_rows) or 1
        return [
            {
                "source": str(r[0]) if r[0] is not None else "not_recorded",
                "label": _prettify_source(str(r[0]) if r[0] is not None else "not_recorded"),
                "count": int(r[1]),
                "pct": round(100 * int(r[1]) / src_total, 1),
            }
            for r in src_rows
        ]
    except Exception as src_err:
        logger.warning(f"[SCORES_COVERAGE] Skipping data_source for {table}: {src_err}")
        return None


def _fetch_table_source_tracking(
    cur: cursor, table: str, cols: set[str], has_symbol: bool, order_col: str
) -> dict[str, list[dict[str, Any]]] | None:
    """Latest-row-per-symbol breakdown of a table's `source_tracking` JSONB column (per-field
    provenance, e.g. positioning_metrics' short_interest/institutional/insider), keyed by field
    name. None if the table has no such column.

    Same LATERAL-per-symbol rewrite as _fetch_table_source_breakdown above, for the same
    reason - see that function's docstring.
    """
    if not (has_symbol and order_col and "source_tracking" in cols):
        return None
    try:
        cur.execute(
            f"""
            SELECT kv.field_key, kv.source_val, COUNT(*) FROM (
                SELECT pd.source_tracking AS st
                FROM stock_symbols _su
                CROSS JOIN LATERAL (
                    SELECT {table}.source_tracking
                    FROM {table}
                    WHERE {table}.symbol = _su.symbol
                    ORDER BY {table}.{order_col} DESC
                    LIMIT 1
                ) pd (source_tracking)
                WHERE _su.active = true
            ) latest, LATERAL jsonb_each_text(COALESCE(latest.st, '{{}}'::jsonb)) AS kv(field_key, source_val)
            GROUP BY kv.field_key, kv.source_val
            ORDER BY kv.field_key, COUNT(*) DESC
            """
        )
        st_rows = cur.fetchall()
        field_totals: dict[str, int] = {}
        for field_key, _source_val, cnt in st_rows:
            field_totals[field_key] = field_totals.get(field_key, 0) + int(cnt)
        per_field: dict[str, list[dict[str, Any]]] = {}
        for field_key, source_val, cnt in st_rows:
            total = field_totals.get(field_key) or 1
            per_field.setdefault(field_key, []).append(
                {
                    "source": str(source_val),
                    "label": _prettify_source(str(source_val)),
                    "count": int(cnt),
                    "pct": round(100 * int(cnt) / total, 1),
                }
            )
        return per_field
    except Exception as st_err:
        logger.warning(f"[SCORES_COVERAGE] Skipping source_tracking for {table}: {st_err}")
        return None


# BUG FOUND 2026-08-24 (goal session data-source audit): a plain `field_key in factor_name`
# substring check missed positioning_metrics' top_10_institutions_pct - the source_tracking
# field key is "institutional" (from load_positioning_metrics.py's institutional_source), but
# the column is spelled "institutions" (no trailing "al"), so the two words never matched as
# substrings of each other. top_10_institutions_pct is always SEC Form 13F-sourced (same
# sec_inst_row as institutional_ownership_pct/institutional_holders_count, which DO match) but
# silently fell through to the table-wide data_source breakdown instead - which, for
# positioning_metrics, is dominated by FINRA (load_positioning_metrics.py's data_source column
# picks short_interest_source over institutional_source/insider_source whenever short-interest
# data exists, which is true for most symbols) - so this one factor's SEC-sourced data was
# misattributed to FINRA in the Data Sources dashboard. Aliases below cover known field_key /
# factor_name spelling mismatches; add to this list rather than the substring check itself if
# another one turns up.
_SOURCE_TRACKING_FACTOR_ALIASES: dict[str, tuple[str, ...]] = {
    "institutional": ("institutional", "institutions"),
}


def _resolve_factor_sources(
    table_source_cache: dict[str, list[dict[str, Any]] | None],
    table_source_tracking_cache: dict[str, dict[str, list[dict[str, Any]]] | None],
    table: str,
    factor_name: str,
) -> list[dict[str, Any]] | None:
    """Pick this factor's source breakdown: a source_tracking per-field split when the factor
    name matches one of its keys, else the table-wide data_source breakdown. See
    table_source_cache's definition at the _get_scores_coverage call site for why sources are
    computed per-table, not per-factor."""
    st_detail = table_source_tracking_cache.get(table)
    if st_detail:
        for field_key, breakdown in st_detail.items():
            aliases = _SOURCE_TRACKING_FACTOR_ALIASES.get(field_key, (field_key,))
            if any(alias in factor_name for alias in aliases):
                return breakdown
    return table_source_cache.get(table)


def _resolve_factor_value_col(
    cur: cursor, table: str, column: str, table_all_cols_cache: dict[str, set[str]]
) -> tuple[str, str | None, str | None]:
    """Derives the factor name from a `*_unavailable_reason` column and, if a same-named
    value column exists on `table`, returns it too - see _get_scores_coverage's own
    2026-09-01 call-site comment for why: some loaders deliberately keep a real value (e.g.
    dividend_yield=0.0 for a confirmed non-payer) alongside a non-NULL reason "for
    transparency", so the reason column alone isn't sufficient to infer "missing". Returns
    (factor_name, None, unavailable_col) when no matching value column exists (the
    bare_reason_tables case, where "reason" describes the whole row rather than one specific
    field).

    unavailable_col (2026-09-08 fix, live-found via the scores/coverage "Other" bucket audit):
    a bare "reason" column on these tables isn't reliably "row is missing" either -
    load_institutional_holdings_13f.py writes a real, non-NULL institutional_ownership_pct
    (just capped at 100.0, a documented SEC 13F double-counting quirk) ALONGSIDE a non-NULL
    `reason` purely as an explanatory annotation, `data_unavailable=False` throughout - the
    same "value present, reason non-NULL 'for transparency'" shape the value_col cross-check
    above already handles, just on a bare-reason table so there's no single matching value
    column to check. 1,647 institutional_holdings_13f rows (and 30 sec_valuations rows) were
    being counted as coverage gaps despite having real data, because this bare-reason branch
    never had an analogous cross-check. Falls back to the table's own `data_unavailable`
    boolean when present (all 7 bare_reason_tables have one) - a row only counts as missing
    if BOTH `reason IS NOT NULL` AND `data_unavailable = true`, mirroring the value_col
    cross-check's "reason alone isn't sufficient" principle for tables where no per-field
    value column exists to check directly."""
    factor_name_candidate = re.sub(r"_?unavailable_reason$", "", column).rstrip("_")
    if table not in table_all_cols_cache:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
            (table,),
        )
        table_all_cols_cache[table] = {r[0] for r in cur.fetchall()}
    if not factor_name_candidate or factor_name_candidate in ("data", "reason"):
        unavailable_col = "data_unavailable" if "data_unavailable" in table_all_cols_cache[table] else None
        return factor_name_candidate, None, unavailable_col
    value_col = factor_name_candidate if factor_name_candidate in table_all_cols_cache[table] else None
    return factor_name_candidate, value_col, None


def _value_missing_clause(table: str, value_col: str | None, unavailable_col: str | None) -> str:
    """SQL fragment (leading " AND ..." or "") for whether a row's actual value is missing,
    on top of its reason column being non-NULL - see _resolve_factor_value_col's docstring
    for why reason-non-NULL alone isn't sufficient. Extracted out of _get_scores_coverage's
    two call sites to keep that function's cyclomatic complexity under the repo's ruff C901
    limit."""
    if value_col:
        return f" AND {table}.{value_col} IS NULL"
    if unavailable_col:
        return f" AND {table}.{unavailable_col} = true"
    return ""


def _never_available_clause(table: str, column: str, value_col: str | None, unavailable_col: str | None) -> str:
    """SQL fragment for the has_symbol+order_col branch's "this symbol's latest real-value
    row" NOT EXISTS check - the t2-aliased counterpart to _value_missing_clause above."""
    if value_col:
        return f"t2.{value_col} IS NOT NULL"
    if unavailable_col:
        return f"t2.{unavailable_col} IS NOT TRUE"
    return f"t2.{column} IS NULL"
