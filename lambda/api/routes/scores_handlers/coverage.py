"""Score route handler: the /api/scores/coverage factor-level data-coverage report.

Split 2026-09-05 (file-size-ratchet compliance split of the original incomplete_and_coverage.py,
which held both /api/scores/incomplete and this report in one 1934-line file). This module now
holds only `_get_scores_coverage` itself plus the one SQL constant it uses
(`_NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE`); the reason-categorization rulebook lives in
coverage_category_rules.py, the reason-categorization function and scoring-scope classification
live in coverage_classification.py, and the per-table ordering/data-source-provenance helpers
live in coverage_sources.py - all pure moves, no logic changed anywhere.
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import (
    error_response,
    handle_db_error,
    json_response,
)

from loaders.loader_registry import LOADER_TABLES, PSEUDO_LOADER_TABLES

from .coverage_category_rules import _COVERAGE_CATEGORY_ORDER
from .coverage_classification import _TABLE_GROUP, _UNSCORED_FACTORS, _UNSCORED_TABLES, _categorize_reason
from .coverage_sources import (
    _coverage_order_col,
    _fetch_table_source_breakdown,
    _fetch_table_source_tracking,
    _resolve_factor_sources,
    _resolve_factor_value_col,
)

logger = logging.getLogger(__name__)

# FIXED 2026-09-03 (SEC/XBRL missing-data sweep): mirrors utils/loaders/helpers.py's
# get_active_symbols(exclude_etfs=True) inline SQL - the canonical, heavily-refined "is this
# symbol a real operating company, not an ETF/CEF/BDC/ETN/trust-preferred/SPAC shell" test (name
# regex uses `\y` not `\b` - `\b` is a literal backspace in PostgreSQL regex, not a word boundary;
# sic_code/entity_type check added 2026-08-20 after CEFs like BCAT/HQL/GBAB slipped past the name
# regex; OZK force-include and TVC/TVE/SCE$L force-exclude added for cases the pattern can't
# generalize to - see that function's own inline history for the full live-evidence trail).
# Duplicated here rather than imported - a same-session sibling process was actively rewriting
# utils/loaders/helpers.py concurrently while this fix was being landed, wiping a shared-import
# version of this constant three times in a row (each landing then vanishing within seconds) -
# self-contained is the only way this specific fix could be gotten onto disk reliably today. If
# helpers.py's canonical version is ever refined again (a new OZK-shaped carve-out, etc.), this
# copy needs the same update - grep both files for NON_OPERATING_COMPANY_EXCLUSION_SQL to find
# both copies. Lives here (used only by _get_scores_coverage below) - scores.py re-exports the
# name (see its own NOTE comment) since tests reach it via that module.
_NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE = """
    (
        ({symbols_alias}.etf IS NULL OR {symbols_alias}.etf != 'true')
        AND {symbols_alias}.security_name !~* '\\y(Warrant|Unit|Contingent Value|ETNs?|Exchange[- ]Traded Notes?|Double Long|Double Short|Inverse|Leveraged|Acquisition Corp|SPAC|Crypto|Debenture|Subordinated|Preferred|Perpetual)\\y'
        AND NOT (
              COALESCE({company_info_alias}.sic_code, 0) = 0
              AND COALESCE({company_info_alias}.entity_type, 'operating') IN ('other', 'investment')
              AND {symbols_alias}.symbol != 'OZK'
        )
        AND {symbols_alias}.symbol NOT IN ('TVC', 'TVE', 'SCE$L')
        -- FIXED 2026-09-03: mirrors utils/loaders/helpers.py's
        -- _KNOWN_BDC_ENTITY_TYPE_OPERATING_SYMBOLS - see that constant's own module-level
        -- comment for the full live-evidence trail (30 real BDCs whose SEC entity_type is
        -- 'operating' despite sic_code=NULL, so they escape the sic_code/entity_type check
        -- above; CBC/AFCG deliberately excluded from this list, see that comment).
        AND {symbols_alias}.symbol NOT IN (
            'BBDC', 'BCSF', 'CCAP', 'CION', 'CSWC', 'EQS', 'FSK', 'GAIN', 'GSBD', 'HRZN',
            'HTGC', 'ICMB', 'KBDC', 'LIEN', 'MAIN', 'NCDL', 'NMFC', 'OBDC', 'OTF', 'PFLT',
            'PFX', 'PNNT', 'PSBD', 'RWAY', 'SAR', 'SCM', 'TPVG', 'TRIN', 'TSLX'
        )
    )
"""


def _get_scores_coverage(cur: cursor, group_filter: str | None = None, meta_only: bool = False) -> Any:
    """Factor-level data coverage report: which *_unavailable_reason columns are
    missing data across the universe, how much, and why - aggregated by root cause.

    Powers the ServiceHealth "Scores Data Coverage" tab. Read-only, ~100+ small
    grouped-count queries (one per *_unavailable_reason column found in the schema) -
    not meant to be polled on a tight interval, hence no data_freshness auto-refresh
    wiring; the frontend refetches on manual click only.

    `group_filter` scopes the (expensive) per-table loop below to a single
    `_TABLE_GROUP` value, so one HTTP call covers a handful of tables instead of all
    ~20 - see the 2026-09-01 fix note at this function's call site for why. `meta_only`
    short-circuits before any per-table query runs at all, returning just the group
    list the frontend chunks its requests by.
    """
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

        # FIXED 2026-08-19 (goal session continuation - "which factor inputs are missing the
        # most" audit): yfinance_snapshot.unavailable_reason was reporting 2,146 active-symbol
        # gaps (45.8% of the table, the #2 largest "Missing SEC/XBRL data" contributor after
        # dividend_data) as if it were an actionable loader gap. It isn't: yfinance_snapshot
        # has had NO active loader since Session 275 (see load_value_quality_growth_metrics.py's
        # and load_positioning_metrics.py's own "yfinance_snapshot is deprecated" comments -
        # every real consumer was migrated off it, nothing writes to it anymore, its rows are
        # frozen at whatever they were on 2026-07-16). No amount of "fixing loaders" can ever
        # change this number, so surfacing it here as a live gap actively misleads the exact
        # workflow ("find which factor inputs are missing the most, fix the loaders") this
        # report exists to support. Excludes any table with no entry in loader_registry.py's
        # LOADER_TABLES/PSEUDO_LOADER_TABLES (the canonical active-loader-output mapping) rather
        # than hardcoding "yfinance_snapshot" by name, so a future loader removal is excluded
        # automatically instead of silently reintroducing this same trap a second way.
        _tables_with_active_loader = {t for tables in LOADER_TABLES.values() for t in tables} | {
            t for tables in PSEUDO_LOADER_TABLES.values() for t in tables
        }
        reason_columns = [(t, c) for t, c in reason_columns if t in _tables_with_active_loader]

        # FIXED 2026-08-19 (goal: "no SEC data"/missing factor inputs audit, same-day
        # follow-up to the active-universe fix above): the "%unavailable_reason%" name
        # match above misses every table whose gap-reason column is just called "reason"
        # instead - live-confirmed this is a completely different, real blind spot, not
        # overlap: institutional_holdings_13f,
        # analyst_earnings_estimates, sec_segment_info/metrics, short_interest_finra, and
        # sec_valuations are all genuine per-symbol data SOURCES (not just downstream
        # computed factors) with a real, populated "reason" column - sec_segment_metrics
        # alone had 2,067 of 5,546 rows (37%) unavailable with real, specific reasons
        # (no_segment_dimension_contexts_in_xbrl_xml, no_segment_revenue_in_xbrl_xml, ...),
        # 100% invisible to this report the whole time. Scoped to this specific allowlist
        # (verified against the schema below, not a blanket "reason" scan) rather than
        # every bare "reason" column in the DB - most of those belong to internal
        # audit/log/algo-state tables (data_loader_status, circuit_breaker_log,
        # algo_orchestrator_state, ...) that aren't per-symbol factor data at all, and
        # quality_metrics/growth_metrics/value_metrics/positioning_metrics/
        # stability_metrics/institutional_holdings_13f-consumers already have their own
        # much more granular *_unavailable_reason columns covered above - their bare
        # "reason" is just a coarse whole-row fallback (live-confirmed quality_metrics:
        # only 151 rows, mostly a single generic "Insufficient SEC financial data"
        # message) that would only add noise, not information, if included too.
        # ADDED 2026-08-29 (goal session: "full data" audit continuation): signal_quality_scores
        # is exactly the same "genuine per-symbol data source with a real, populated bare
        # `reason` column" shape as the 6 tables above, but was missed when this allowlist was
        # built - live-confirmed 100% invisible to this report despite being the single
        # largest bare-reason population found this session (964,110 total reason rows,
        # ~899,000 active-universe). Two dynamic, per-symbol reason families
        # (`[SIGNAL_QUALITY] ... No buy/sell signals found` / `[VCP_NO_DATA] ... No VCP
        # patterns found`) embed the ticker/date range inline, so _categorize_reason's
        # `base = reason.split(":")[0]` never matches a set-literal key for either - see the
        # startswith checks added there for both patterns.
        bare_reason_tables = (
            "institutional_holdings_13f",
            "analyst_earnings_estimates",
            "sec_segment_info",
            "sec_segment_metrics",
            "short_interest_finra",
            "sec_valuations",
            "signal_quality_scores",
        )
        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE column_name = 'reason'
              AND table_schema = 'public'
              AND table_name = ANY(%s)
            ORDER BY table_name
            """,
            (list(bare_reason_tables),),
        )
        reason_columns.extend((r[0], r[1]) for r in cur.fetchall())

        if meta_only:
            groups = sorted({_TABLE_GROUP.get(t, t) for t, _ in reason_columns})
            return json_response(200, {"groups": groups, "factor_count": len(reason_columns)})

        if group_filter:
            reason_columns = [(t, c) for t, c in reason_columns if _TABLE_GROUP.get(t, t) == group_filter]

        denom_cache: dict[str, int | None] = {}
        table_cols_cache: dict[str, set[str]] = {}
        table_all_cols_cache: dict[str, set[str]] = {}
        # Per-table (not per-factor) source breakdown caches - `data_source`/`source_tracking`
        # are table-level columns shared by every *_unavailable_reason factor on that table, so
        # they're computed once per table and attached to each of that table's factor rows below,
        # not recomputed per factor.
        table_source_cache: dict[str, list[dict[str, Any]] | None] = {}
        table_source_tracking_cache: dict[str, dict[str, list[dict[str, Any]]] | None] = {}
        factors: list[dict[str, Any]] = []

        for table, column in reason_columns:
            if table not in table_cols_cache:
                cur.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=%s
                      AND column_name IN ('symbol','date','fiscal_year','updated_at','created_at',
                                           'data_source','source_tracking')
                    """,
                    (table,),
                )
                table_cols_cache[table] = {r[0] for r in cur.fetchall()}
            cols = table_cols_cache[table]
            has_symbol = "symbol" in cols
            order_col = _coverage_order_col(cur, table, cols)

            # FIXED 2026-09-01 (goal: "are these gaps real" audit, live-caught via
            # value_metrics.dividend_yield): this report used to infer "missing" purely from
            # the *_unavailable_reason column being non-NULL, on the unstated assumption that
            # every loader nulls the reason out the moment it fills the real value. That's true
            # almost everywhere but not universal - load_value_quality_growth_metrics.py
            # deliberately sets dividend_yield=0.0 (a real, correct value) for confirmed
            # non-payers while KEEPING dividend_yield_unavailable_reason='non_dividend_paying_stock'
            # "for transparency" (see that file's 2026-08-05 fix comment) - live-confirmed 2,771
            # rows carry a real non-NULL value alongside a non-NULL reason, inflating
            # dividend_yield's reported gap from a real ~5.6% to a shown 59.6%. Resolving the
            # matching value column (same name as the factor, e.g. "dividend_yield" for
            # "dividend_yield_unavailable_reason") and requiring it be NULL too closes this for
            # every factor at once rather than special-casing dividend_yield - live-audited via a
            # full-schema scan and found only 3 other, negligible (1-8 row) instances of the same
            # pattern (company_info_sec.shares_outstanding, quality_metrics.
            # estimate_momentum_60d/90d), so this generalizes cleanly. Falls back to the old
            # reason-only behavior when no matching value column exists (the bare_reason_tables
            # case, where "reason" describes the whole row rather than one specific field).
            factor_name_candidate, value_col = _resolve_factor_value_col(cur, table, column, table_all_cols_cache)

            # FIXED 2026-08-19 (goal: "no SEC data"/missing factor inputs audit): every
            # query below used to scan {table} directly with no active-universe filter, so
            # a symbol delisted/failed-SPAC/dropped from stock_symbols.active but never
            # pruned from a metrics table (live-confirmed: 6-9% of rows in quality_metrics/
            # growth_metrics/value_metrics/positioning_metrics/stability_metrics/
            # dividend_data belong to symbols no longer active) counted as a live "gap in
            # the real, scored universe" here - inflating every factor's numerator AND
            # denominator, and inactive symbols are disproportionately gap-heavy (delisted
            # shells, failed SPACs), so this wasn't just proportional noise. The actual
            # user-facing /api/algo/scores query already joins stock_scores -> stock_symbols
            # (stock_scores itself is 99.7% clean of inactive symbols - the scoring loader
            # already scopes to the active universe), so this report was measuring a
            # DIFFERENT, larger, stale-inflated population than what real users ever see.
            # Joining to stock_symbols and filtering active=true here makes this report
            # match that same real, live-scored universe.
            #
            # FIXED 2026-09-03 (SEC/XBRL missing-data sweep): active=true alone still let through
            # closed-end funds/BDCs/ETNs (BCAT, HQL, GBAB, BDJ, EVF, JHI, BMN, FTF, GAM, PIM, ... -
            # live-confirmed 88 active symbols matching this exact signature) - these are
            # active=true in stock_symbols but structurally never real operating companies (no
            # SIC classification, entity_type='other'/'investment'), the SAME population
            # loaders/*.py's get_active_symbols(exclude_etfs=True) already excludes from every
            # real scoring loader (quality_metrics/growth_metrics/value_metrics never even
            # attempt to fetch data for them going forward) - see that function's own extensive
            # inline history for why each piece of this filter exists. This report was still
            # counting their permanent, structural "no free_cash_flow/operating_cash_flow/
            # interest_coverage/..." gaps as real "Missing SEC/XBRL data" on top of the real
            # scored universe's gaps - the same "measuring a population nobody actually scores"
            # bug class as the active=true fix above, just for entity type instead of listing
            # status. See _NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE's own module-level
            # comment above for why this duplicates (rather than imports) utils/loaders/
            # helpers.py's canonical filter.
            active_join = (
                (
                    f" LEFT JOIN company_info_sec _cis ON _cis.symbol = {table}.symbol"
                    f" JOIN stock_symbols _su ON _su.symbol = {table}.symbol AND _su.active = true"
                    # FIXED 2026-09-03 (SEC/XBRL missing-data sweep, drift check against the
                    # canonical filter): utils/loaders/helpers.py's get_active_symbols(
                    # exclude_etfs=True) - the actual real-scoring population this report is
                    # trying to match - also requires `data_unavailable IS NOT TRUE` as a
                    # sibling condition to `active = true` (a symbol can be active=true in the
                    # roster yet separately flagged permanently data_unavailable, e.g. after a
                    # confirmed-dead-data investigation), but this join never carried that
                    # second condition. Live-confirmed only 3 active-universe symbols currently
                    # match (ISSC/BNRG/AVB) and none currently contribute a live
                    # missing_sec_data row, so this has zero headline impact today, but it's the
                    # same "measuring a population nobody actually scores" bug class as the two
                    # fixes just above/below this comment and would silently reopen the moment
                    # any such symbol picks up a real gap.
                    f" AND _su.data_unavailable IS NOT TRUE"
                    f" AND {_NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias='_su', company_info_alias='_cis')}"
                )
                if has_symbol
                else ""
            )

            if table not in denom_cache:
                if has_symbol:
                    try:
                        cur.execute(f"SELECT COUNT(DISTINCT {table}.symbol) FROM {table}{active_join}")
                        denom_cache[table] = cur.fetchone()[0]
                    except Exception:
                        denom_cache[table] = None
                else:
                    denom_cache[table] = None

            # Data source breakdown (goal 2026-08-21: "which sources - SEC/yfinance/etc - and
            # what % from each, per input"). Table-level, not column-level - computed once per
            # table (same latest-row-per-symbol population as denom_cache above) and attached to
            # every factor row from that table below. `source_tracking` (positioning_metrics only
            # today) gives a finer per-field breakdown when the factor name matches one of its
            # keys (short_interest/institutional/insider); everything else uses the table-wide
            # `data_source` column. Split into helpers above to keep this loop's own complexity
            # in check.
            if table not in table_source_cache:
                table_source_cache[table] = _fetch_table_source_breakdown(cur, table, cols, has_symbol, order_col)
                table_source_tracking_cache[table] = _fetch_table_source_tracking(
                    cur, table, cols, has_symbol, order_col
                )

            try:
                if has_symbol and order_col:
                    # {table}-qualify column/order_col (not just symbol) - active_join's _su
                    # alias is another copy of the SAME table for the stock_symbols.
                    # data_unavailable_reason case (self-join), and stock_symbols also has
                    # updated_at/created_at, either of which order_col can pick as the
                    # ordering column for OTHER tables too - both would otherwise be
                    # ambiguous between {table} and the joined _su copy.
                    #
                    # FIXED (goal session, "so many from yfinance still" data-accuracy audit):
                    # a plain `ORDER BY {order_col} DESC` picks the row with the highest
                    # fiscal_year/date even when THAT row is an unavailable placeholder (e.g.
                    # annual_income_statement writes a data_unavailable=TRUE marker row for the
                    # current, not-yet-filed fiscal year) while an older row for the same symbol
                    # has real, usable data - live-confirmed on annual_income_statement (3,076
                    # symbols) via stocks.py's identical bug in the deep-value screener CTEs,
                    # fixed alongside this. A symbol only counts as "missing" here if it has
                    # NEVER once had a row where this factor was available, regardless of
                    # fiscal_year/date - same "once real, always real" rule
                    # load_value_quality_growth_metrics.py's own "latest row" helpers already
                    # apply when computing ratios from these same tables.
                    #
                    # REWRITTEN 2026-09-01 (goal session: "this one timing out") - the original
                    # form of this query (`DISTINCT ON (symbol) ... ORDER BY symbol, (reason_val
                    # IS NULL) DESC, order_col DESC`) computed the exact same "once real, always
                    # real" result but by sorting EVERY row of the table per symbol, which is
                    # what a plain per-symbol DISTINCT ON always costs regardless of how rare the
                    # non-null reason values actually are - live-confirmed price_daily.
                    # data_unavailable_reason (26.2M rows, only 15 ever non-null) alone cost
                    # ~27s this way, the dominant cost in the whole report and enough on its own
                    # to exceed the frontend's 28s client timeout even after the per-group
                    # chunking added alongside this (ScoresDataCoverage.jsx's header comment).
                    # This form is mathematically the same computation, just reordered to do the
                    # cheap, selective part first: `candidates` finds the (usually tiny) set of
                    # symbols that have EVER had a non-null reason row - a single filtered scan,
                    # not a per-symbol sort - and `never_available` then keeps only the ones that
                    # NEVER had a null-reason row either, which is exactly "missing" under the
                    # same rule as before. Only that (typically tiny) survivor set ever reaches
                    # the DISTINCT ON, so its per-symbol sort is now bounded by how many symbols
                    # are actually missing, not by the table's total size - live-verified to
                    # return byte-identical results to the original query on every table tested
                    # (quality_metrics, growth_metrics, stability_metrics, value_metrics,
                    # price_weekly, price_daily), 12-25x faster on the two price_* tables and
                    # indistinguishable on the smaller ones.
                    # value_col cross-check (see this loop's own 2026-09-01 comment above): a
                    # symbol only belongs in `candidates`/`never_available` when the real value
                    # column is ALSO null, not just the reason column - otherwise a factor like
                    # dividend_yield (real 0.0 kept alongside its reason "for transparency")
                    # gets double-counted as missing on top of its genuinely-null rows.
                    value_is_null = f" AND {table}.{value_col} IS NULL" if value_col else ""
                    never_exists_clause = f"t2.{value_col} IS NOT NULL" if value_col else f"t2.{column} IS NULL"
                    query = f"""
                        WITH candidates AS (
                            SELECT DISTINCT {table}.symbol FROM {table}{active_join}
                            WHERE {table}.{column} IS NOT NULL{value_is_null}
                        ),
                        never_available AS (
                            SELECT c.symbol FROM candidates c
                            WHERE NOT EXISTS (
                                SELECT 1 FROM {table} t2 WHERE t2.symbol = c.symbol AND {never_exists_clause}
                            )
                        )
                        SELECT reason_val, COUNT(*) FROM (
                            SELECT DISTINCT ON ({table}.symbol) {table}.symbol, {table}.{column} AS reason_val
                            FROM {table}
                            JOIN never_available na ON na.symbol = {table}.symbol
                            ORDER BY {table}.symbol, {table}.{order_col} DESC
                        ) latest
                        WHERE reason_val IS NOT NULL
                        GROUP BY reason_val
                        ORDER BY COUNT(*) DESC
                    """
                else:
                    # Same active-universe scoping as the has_symbol branch above, for the
                    # rarer has_symbol-but-no-order_col case (a market-wide/no-symbol table
                    # skips the join entirely since active_join is "" when not has_symbol).
                    # Same value_col cross-check as the branch above.
                    value_is_null = f" AND {table}.{value_col} IS NULL" if value_col else ""
                    query = f"""
                        SELECT {table}.{column} AS reason_val, COUNT(*)
                        FROM {table}{active_join}
                        WHERE {table}.{column} IS NOT NULL{value_is_null}
                        GROUP BY {table}.{column}
                        ORDER BY COUNT(*) DESC
                    """
                cur.execute(query)
                rows = cur.fetchall()
            except Exception as col_err:
                logger.warning(f"[SCORES_COVERAGE] Skipping {table}.{column}: {col_err}")
                continue

            if not rows:
                continue

            total_missing = sum(int(r[1]) for r in rows)
            denom = denom_cache[table]
            pct_missing = round(100 * total_missing / denom, 1) if denom else None

            categories: dict[str, int] = {}
            reasons_out = []
            for reason_val, count in rows:
                cat = _categorize_reason(str(reason_val))
                categories[cat] = categories.get(cat, 0) + int(count)
                reasons_out.append({"reason": str(reason_val), "count": int(count), "category": cat})

            factor_name = factor_name_candidate
            # A bare "reason" column (the bare_reason_tables case above) doesn't match the
            # unavailable_reason suffix at all and would otherwise show the unhelpful
            # literal "reason" as the factor name - same fallback as the "data"/empty case.
            if not factor_name or factor_name in ("data", "reason"):
                factor_name = table

            factors.append(
                {
                    "table": table,
                    "group": _TABLE_GROUP.get(table, table),
                    "factor": factor_name,
                    "column": column,
                    "total_missing": total_missing,
                    "denom": denom,
                    "pct_missing": pct_missing,
                    "reasons": reasons_out,
                    "categories": categories,
                    "sources": _resolve_factor_sources(
                        table_source_cache, table_source_tracking_cache, table, factor_name
                    ),
                    # ADDED 2026-09-02: see _UNSCORED_FACTORS/_UNSCORED_TABLES's own comments
                    # above - a gap here can never move stock_scores, unlike every other
                    # factor on this page.
                    "scored": table not in _UNSCORED_TABLES and (table, factor_name) not in _UNSCORED_FACTORS,
                }
            )

        factors.sort(key=lambda f: -1 if f["pct_missing"] is None else -f["pct_missing"])

        category_totals = dict.fromkeys(_COVERAGE_CATEGORY_ORDER, 0)
        for f in factors:
            for c, v in f["categories"].items():
                category_totals[c] = category_totals.get(c, 0) + v

        # Table-wide source rollup for the summary KPI/chart - one table's data_source
        # breakdown counted once (not once per factor column on that table), same dedup
        # reasoning as table_source_cache being keyed by table above.
        #
        # FIXED 2026-08-23 (goal: data-source accuracy review): keyed by s["label"], not
        # s["source"]. Different tables write different literal data_source strings that
        # _prettify_source() maps to the SAME human label - e.g. "finra" (short_interest_finra)
        # and "finra_query_api" (positioning_metrics) both -> "FINRA". Keying by the raw string
        # left them as two separate same-labeled bars/legend entries in the summary chart
        # (e.g. "FINRA 5,192" and "FINRA 4,918" shown side by side) instead of one merged
        # ~10,110-count bar. Per-factor source breakdowns (_resolve_factor_sources) are
        # unaffected - only this table-wide rollup used the raw string as its dict key.
        source_totals: dict[str, int] = {}
        source_labels: dict[str, str] = {}
        _seen_source_tables: set[str] = set()
        for f in factors:
            t = f["table"]
            if t in _seen_source_tables:
                continue
            _seen_source_tables.add(t)
            # BUG FOUND 2026-08-24 (goal session data-source audit): a table with
            # source_tracking (positioning_metrics today) has MULTIPLE independently-sourced
            # fields (short_interest/institutional/insider) but only ONE flat table-wide
            # data_source column, which picks a single winning field per row (see
            # load_positioning_metrics.py: short_interest_source wins over
            # institutional/insider whenever short-interest data exists, true for ~95% of
            # symbols). Summing table_source_cache here counted every row as "FINRA" even
            # for symbols whose institutional_ownership_pct/insider_ownership_pct came from
            # SEC 13F/Form 4-5 - live-confirmed this collapsed ~4,100 real SEC-sourced rows
            # for each of those two fields into the FINRA bucket, undercounting SEC Form
            # 13F/Form 4-5 in this summary by >99% versus their true per-factor breakdown
            # (_resolve_factor_sources, unaffected by this bug). Sum each of the table's
            # source_tracking fields separately when present - each field is a real,
            # independent source population - falling back to the flat data_source rollup
            # only for tables with no source_tracking column at all.
            st_detail = table_source_tracking_cache.get(t)
            per_table_sources = (
                [s for field_breakdown in st_detail.values() for s in field_breakdown]
                if st_detail
                else (table_source_cache.get(t) or [])
            )
            for s in per_table_sources:
                label = s["label"]
                source_totals[label] = source_totals.get(label, 0) + s["count"]
                source_labels[label] = label
        source_order = sorted(source_totals, key=lambda s: -source_totals[s])

        # stock_symbols is the actual universe registry - prefer it over other tables'
        # denom counts, since a table like price_weekly can carry more distinct symbols
        # than the live universe (delisted/historical rows never pruned), which would
        # otherwise overstate "universe_estimate" via a naive max().
        universe_estimate = denom_cache.get("stock_symbols") or max((d for d in denom_cache.values() if d), default=0)

        result = {
            "summary": {
                "universe_estimate": universe_estimate,
                "factor_count": len(factors),
                "category_order": _COVERAGE_CATEGORY_ORDER,
                "category_totals": category_totals,
                "source_order": source_order,
                "source_totals": source_totals,
                "source_labels": source_labels,
            },
            "factors": factors,
        }
        return json_response(200, result)

    except Exception as e:
        code, error_type, message = handle_db_error(e, "get scores coverage")
        return error_response(code, error_type, message)
