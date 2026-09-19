"""Score route handlers: the main multi-factor stock scores listing endpoint.

_get_stock_scores below delegates most of its work to stock_scores_helpers.py (2026-09
split, purely to keep this file under the file-size ratchet's new-file cap) - each helper
is a behavior-preserving, mechanical extraction of one phase of this function's body
(paginated-query construction, row/factor-input transformation, summary-metric
computation). No logic, computation, query, or control flow was changed in the process.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    error_response,
    execute_with_timeout,
    handle_db_error,
    json_response,
)

from algo.signals.investable_universe import investable_universe_conditions
from algo.signals.market_cap_tilt import compute_tilted_weights

from .stock_scores_helpers import (
    _build_stock_score_items,
    _build_stock_scores_query,
    _compute_stock_scores_completeness_health,
    _compute_stock_scores_summary,
    _log_stock_scores_price_quality,
)

logger = logging.getLogger(__name__)


def _get_stock_scores(
    cur: cursor,
    limit: int = 5000,
    offset: int = 0,
    sort_by: str = "composite_score",
    sort_order: str = "desc",
    sp500_only: bool = False,
    symbol: str | None = None,
    min_market_cap: float | None = None,
    weighting: str = "raw",
) -> Any:
    """Get stock scores with multi-factor ranking."""
    try:
        # WEIGHTING (default "raw", opt-in "tilted" - 2026-09-15): tilted weight exists to
        # make a ranking resemble a real cap-weighted fund's HOLDINGS composition (verified
        # vs LRGF/GSLC at 84%/80% top-25/bottom-25 overlap - see MEMORY.md
        # goal_top25_bottom25_achieved_production_verified_20260915). That is NOT what "who
        # scores best on this factor" callers want (SectorAnalysis.jsx's "Top Companies", any
        # per-pillar leaderboard) - defaulting every sort_by to tilted weight silently
        # market-cap-dominated every one of them. Raw score is the default; a caller that
        # specifically wants fund-holdings-style ordering passes ?weighting=tilted. "symbol"
        # sort is untouched either way (alphabetical has no tilted-weight analog).
        #
        # TILTED WEIGHT COMPUTED AT REQUEST TIME, NOT A STORED COLUMN (2026-09-17, migration
        # 1308 - see algo/signals/market_cap_tilt.py's module docstring for the full
        # rationale/formula). sort_col below is always a REAL stock_scores column now -
        # pillar_by_sort_by maps a sort_by value to which pillar's tilted-weight dict to rank
        # by when weighting="tilted" (population-relative, so it can't be an ORDER BY column
        # inside a LIMIT'd SQL query - see the ranking logic below).
        raw_sorts = {
            "composite_score": "composite_score",
            "momentum_score": "momentum_score",
            "quality_score": "quality_score",
            "value_score": "value_score",
            "growth_score": "growth_score",
            "risk_score": "risk_score",
            "symbol": "symbol",
        }
        pillar_by_sort_by = {
            "composite_score": "composite",
            "momentum_score": "momentum",
            "quality_score": "quality",
            "value_score": "value",
            "growth_score": "growth",
            "risk_score": "risk",
        }
        sort_col = raw_sorts.get(sort_by, "composite_score")
        sort_direction = "DESC" if sort_order == "desc" else "ASC"
        # TIE-BREAK BUG FIX (2026-09-19, /goal scores audit): this used to be
        # `sort_by if sort_by in raw_sorts else "composite_score"`, which for every
        # recognized sort_by (the overwhelmingly common case - it's only NOT recognized for a
        # malformed/unknown sort_by param) evaluates to the exact SAME column as sort_col
        # itself. _build_stock_scores_query's ORDER BY then reads
        # `sc.{sort_col} DESC, sc.{fallback_col} DESC` with both placeholders identical -
        # a no-op secondary sort key, not a real tiebreak. Live-confirmed via /goal audit:
        # momentum_score is z-score-winsorized at +/-3SD (Phi(3)*100 = 99.865, rounds to
        # 99.87), and 11 real symbols (CLMT/JAN/MGRT/MSBI/MXL/NINE/OPI/TTRX/TWST/TXG/VLO)
        # all clip to that exact same ceiling value - with no real secondary sort key,
        # Postgres' tie order among those 11 is plan-dependent/arbitrary (not derived from
        # any real ranking signal), so "top 10 by momentum_score" silently drops one of the
        # 11 tied names essentially at random, and can even reorder between requests. Same
        # defect applies to any other sort_by wherever ties occur (composite_score ties are
        # just rarer since it's a continuous weighted average, not a clipped z-score).
        # Fixed by always tiebreaking on `symbol` (unique, so page contents/order become
        # fully deterministic) instead of duplicating sort_col - this does not change the
        # true ranking of tied rows (there is no real data to rank them by additionally),
        # it only replaces "arbitrary" with "fixed and reproducible" so the same page/tie
        # group always renders the same way instead of silently dropping members between
        # requests.
        fallback_col = "symbol" if sort_col != "symbol" else "composite_score"
        pillar_key = pillar_by_sort_by.get(sort_by)

        # RAW, UNFILTERED TABLE ROWS (2026-09-18 user directive: "it should not filter it
        # should show the raw results from the table" - reapplied after a concurrent-session
        # git operation reverted this endpoint back to its pre-directive state, see this
        # file's own history for that incident). No default ETF/investable-universe exclusion,
        # no default data_unavailable gate: every stock_scores row is a candidate. A row that
        # fails any data-quality/investability check is still a REAL row in the table, and
        # hiding it here is exactly the "why don't I see this symbol" confusion the directive
        # was about. `sp500_only`, `symbol` lookup, and `min_market_cap` stay as explicit,
        # caller-requested filters (opt-in, not default).
        where_clause = "WHERE 1=1"
        params_list: list[Any] = []

        if sp500_only:
            where_clause += " AND ss.is_sp500 = TRUE"
        if symbol:
            # Validate symbol format (consistent with signals.py)
            import re

            if not re.match(r"^[A-Z0-9\-\^]{1,10}$", symbol.upper()):
                return error_response(400, "bad_request", "Invalid symbol format")
            where_clause += " AND sc.symbol = %s"
            params_list.append(symbol.upper())

        # MARKET-CAP ELIGIBILITY FLOOR - REMOVED as the default screen 2026-09-15 (user
        # directive, correcting the same-day change below that kept this floor "alongside, not
        # instead of" a new liquidity screen). This repo's own research already established
        # real IBD screens (IBD 50) span small/mid/large-cap by design and have NO market-cap
        # floor at all - see the IBD-STYLE LIQUIDITY SCREEN comment just below for the full
        # citation. Keeping a $300M cap floor "because it's not a large-cap gate" missed the
        # actual point: a cap floor of ANY size is the wrong tool for an IBD-style system, not
        # just the wrong number - IBD's own screens are entirely liquidity-based (min price,
        # min average dollar volume). `min_market_cap` is kept as an explicit OPT-IN
        # (`?minMarketCap=<n>`) for a caller that genuinely wants a large/mid-cap-only view (a
        # real, legitimate use case - just not this endpoint's default) - no longer applied by
        # default (the `is not None` gate below only ever fires when a caller explicitly
        # passes the param; nothing sets `min_market_cap` to a default value anymore).
        market_cap_join = ""
        if min_market_cap is not None and not symbol:
            market_cap_join = "JOIN value_metrics mcf ON mcf.symbol = sc.symbol"
            where_clause += " AND mcf.market_cap >= %s"
            params_list.append(min_market_cap)

        # IBD-STYLE LIQUIDITY SCREEN REMOVED as a default on the MAIN query 2026-09-18 (same
        # "raw, unfiltered table rows" directive as above) - previously applied unconditionally
        # (min price $5, min 20d avg dollar volume $500k) to every bulk request's where_clause.
        # A row failing this screen is still a real stock_scores row; gating it out of this
        # endpoint's default results is the same class of hidden filter the directive rejected.
        # liquidity_screen_active/min_stock_price/min_adv_dollars are still computed here
        # because the opt-in `?weighting=tilted` population query below deliberately restricts
        # its ranking population to investable names (see that query's own comment) - that's a
        # scoped, opt-in design choice for a fund-resemblance feature, not a default filter on
        # what rows this endpoint returns.
        liquidity_screen_active = min_market_cap != 0 and not symbol
        min_stock_price = 5.0
        min_adv_dollars = 500_000.0
        if liquidity_screen_active:
            cur.execute("SELECT key, value FROM algo_config WHERE key IN ('min_stock_price', 'min_adv_dollars')")
            liquidity_config = {row[0]: row[1] for row in cur.fetchall()}
            try:
                min_stock_price = float(liquidity_config["min_stock_price"])
            except (KeyError, TypeError, ValueError):
                min_stock_price = 5.0
            try:
                min_adv_dollars = float(liquidity_config["min_adv_dollars"])
            except (KeyError, TypeError, ValueError):
                min_adv_dollars = 500_000.0

        # Real universe count (goal: dashboard/API were reporting "only ~1000 stocks
        # screened" - traced to `estimated_total` below being a page-size heuristic instead
        # of an actual count, compounded by this endpoint's limit being capped at 1000. The
        # true filtered universe is ~5000+ symbols (live-verified). Run against the same
        # where_clause/params_list as the page query, before LIMIT/OFFSET are appended to
        # params_list below, so this reflects the full filtered result set, not one page.
        count_query = f"""
            SELECT COUNT(*)
            FROM stock_scores sc
            JOIN stock_symbols ss ON ss.symbol = sc.symbol
            {market_cap_join}
            {where_clause}
        """
        cur.execute(count_query, params_list)
        real_total = cur.fetchone()[0]

        # TILT WEIGHT POPULATION (2026-09-17, migration 1308 - see algo/signals/
        # market_cap_tilt.py's module docstring). Computed over the same eligible universe
        # this request's own default investability screen defines - investable_universe_
        # conditions + data_unavailable filter, plus the IBD-style liquidity screen IF this
        # request has it active (liquidity_screen_active, computed above - honors the exact
        # same min_market_cap=0/symbol-lookup opt-outs the main query respects, so
        # ?minMarketCap=0 or a symbol lookup really does mean "no liquidity screening
        # anywhere in this request", not just in the returned rows). Reuses min_stock_price/
        # min_adv_dollars already fetched above rather than a second algo_config round trip.
        _population_liquidity_cte = (
            """
            WITH liquidity AS (
                SELECT symbol, AVG(volume * close) AS avg_dollar_volume_20d,
                       (ARRAY_AGG(close ORDER BY date DESC))[1] AS latest_close
                FROM (
                    SELECT symbol, volume, close, date,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM price_daily
                    WHERE date >= CURRENT_DATE - INTERVAL '45 days'
                      AND COALESCE(data_unavailable, false) = false
                      AND volume IS NOT NULL AND close IS NOT NULL
                ) ranked
                WHERE rn <= 20
                GROUP BY symbol
            )
            """
            if liquidity_screen_active
            else ""
        )
        _population_liquidity_join = (
            "LEFT JOIN liquidity liq ON liq.symbol = sc.symbol" if liquidity_screen_active else ""
        )
        _population_liquidity_filter = (
            "AND liq.latest_close >= %s AND liq.avg_dollar_volume_20d >= %s" if liquidity_screen_active else ""
        )
        cur.execute(
            _population_liquidity_cte
            + f"""
            SELECT sc.symbol, sc.composite_score, sc.momentum_score, sc.quality_score,
                   sc.value_score, sc.growth_score, sc.risk_score, vm.market_cap
            FROM stock_scores sc
            JOIN stock_symbols ss ON ss.symbol = sc.symbol
            LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
            {_population_liquidity_join}
            WHERE """
            + investable_universe_conditions("sc", "ss")
            + f"""
              AND (sc.data_unavailable = false OR sc.data_unavailable IS NULL)
              {_population_liquidity_filter}
            """,
            (min_stock_price, min_adv_dollars) if liquidity_screen_active else (),
        )
        population_rows = cur.fetchall()
        market_cap_by_symbol = {r[0]: float(r[7]) for r in population_rows if r[7] is not None}
        pillar_score_idx = {"composite": 1, "momentum": 2, "quality": 3, "value": 4, "growth": 5, "risk": 6}
        tilted_weights_by_pillar: dict[str, dict[str, float]] = {}
        for pillar, idx in pillar_score_idx.items():
            score_by_symbol = {r[0]: float(r[idx]) for r in population_rows if r[idx] is not None}
            tilted_weights_by_pillar[pillar] = compute_tilted_weights(score_by_symbol, market_cap_by_symbol)

        # PERFORMANCE: filter/sort/limit to the target page FIRST in a CTE, then run the
        # per-symbol LATERAL lookups (price_daily/technical_data_daily) only against that
        # small row set. Previously the LATERAL joins ran against every row of stock_scores
        # BEFORE the WHERE clause was applied, so a page of 50 rows still paid for thousands
        # of per-symbol index scans - this was the root cause of the endpoint's 7+ second
        # latency (and the dashboard's 3s client timeout hiding it as "no data"). Query
        # construction itself lives in stock_scores_helpers.py (_build_stock_scores_query) -
        # see that function's docstring for the same detail.
        #
        # weighting="tilted" ranks in Python off the population computed above (tilted
        # weight can't be an ORDER BY column inside a LIMIT'd SQL query any more - see
        # pillar_by_sort_by comment above) and passes the resulting page's symbols to
        # _build_stock_scores_query's page_symbols filter instead of SQL ORDER BY/LIMIT/
        # OFFSET. A symbol lookup (single row) or weighting="raw" both use the plain SQL
        # sort path unchanged - sort_col is always a real column either way.
        page_symbols: list[str] | None = None
        if weighting == "tilted" and pillar_key is not None and not symbol:
            tilted_dict = tilted_weights_by_pillar[pillar_key]
            raw_score_by_symbol = {
                r[0]: float(r[pillar_score_idx[pillar_key]])
                for r in population_rows
                if r[pillar_score_idx[pillar_key]] is not None
            }
            ranked_symbols = sorted(
                raw_score_by_symbol.keys(),
                key=lambda sym: (tilted_dict.get(sym, -1.0), raw_score_by_symbol[sym]),
                reverse=(sort_direction == "DESC"),
            )
            page_symbols = ranked_symbols[offset : offset + limit]
            query = _build_stock_scores_query(
                where_clause, market_cap_join, sort_col, sort_direction, fallback_col, page_symbols=page_symbols
            )
            params_list.append(page_symbols)
        else:
            query = _build_stock_scores_query(where_clause, market_cap_join, sort_col, sort_direction, fallback_col)
            params_list.extend([limit, offset])

        # Try with data_unavailable columns first (preferred)
        # timeout_sec=20 ensures DB cancels before Lambda's 25s timeout, allowing proper error response
        try:
            scores = execute_with_timeout(cur, query, params_list, timeout_sec=20, max_attempts=1)
        except psycopg2.errors.UndefinedColumn as e:
            # CRITICAL: Schema mismatch on data_unavailable columns indicates migration incomplete
            # FAIL-FAST: Do not silently degrade query validation
            if "data_unavailable" in str(e):
                logger.critical(
                    f"[SCORES_API] Schema validation failed: data_unavailable columns missing from metrics tables. "
                    f"This indicates database migration (0046) has not been applied. Cannot validate score completeness. "
                    f"Error: {e}"
                )
                return error_response(
                    503,
                    "schema_mismatch",
                    "Score validation unavailable: database schema missing required data_unavailable columns. "
                    "Database migration may not have completed.",
                )
            else:
                raise

        if page_symbols is not None:
            # ANY(%s) doesn't preserve order - reindex to match the Python-side ranking.
            _rows_by_symbol = {row["symbol"]: row for row in scores}
            scores = [_rows_by_symbol[sym] for sym in page_symbols if sym in _rows_by_symbol]

        # Row/factor-input transformation (data_unavailable-driven score nulling, factor
        # input objects, current_price data-quality flag) - see
        # stock_scores_helpers._build_stock_score_items's docstring.
        items = _build_stock_score_items(scores, tilted_weights_by_pillar)

        # Check data freshness
        freshness = check_data_freshness(cur, "stock_scores", "updated_at", warning_days=7)

        _log_stock_scores_price_quality(items)

        # CRITICAL FIX: Return scores in standard paginated format
        # Dashboard/responseNormalizer expects {statusCode: 200, items: [...], pagination: {...}} format
        # This matches other paginated endpoints and works with frontend schema validation
        # real_total comes from the COUNT(*) query above (same where_clause), not a
        # page-size estimate - see comment there for why the old estimate was wrong.
        estimated_total = real_total

        # Compute summary metrics over ALL scores (not just this page) - dashboard summary
        # line needs these metrics for the full universe.
        avg_composite, grades_summary = _compute_stock_scores_summary(items)

        # TRANSPARENCY ENHANCEMENT (2026-08-05): Data health metrics for the summary -
        # shows traders overall data quality of the scores being returned.
        avg_completeness, completeness_threshold_pct = _compute_stock_scores_completeness_health(items)

        result = {
            "items": items,
            "pagination": {
                "total": estimated_total,
                "limit": limit,
                "offset": offset,
                "page": (offset // limit) + 1 if limit > 0 else 1,
                "totalPages": ((estimated_total - 1) // limit) + 1 if limit > 0 else 1,
            },
            "avg_composite": avg_composite,
            "grades": grades_summary if grades_summary else None,
            "data_health": {
                "avg_completeness": round(avg_completeness, 2) if avg_completeness is not None else None,
                "meeting_trading_gate": f"{completeness_threshold_pct:.0f}%"
                if completeness_threshold_pct is not None
                else None,
                "note": "Completeness >= 70% passes trading entry gate; < 70% filtered per GOVERNANCE",
            },
        }
        return json_response(200, result, data_freshness=freshness)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle scores")
        return error_response(code, error_type, message)
