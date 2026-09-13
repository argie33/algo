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
) -> Any:
    """Get stock scores with multi-factor ranking."""
    try:
        allowed_sorts = {
            "composite_score": "composite_score",
            "momentum_score": "momentum_score",
            "quality_score": "quality_score",
            "value_score": "value_score",
            "growth_score": "growth_score",
            "risk_score": "risk_score",
            "symbol": "symbol",
        }
        sort_col = allowed_sorts.get(sort_by, "composite_score")
        sort_direction = "DESC" if sort_order == "desc" else "ASC"

        # ETF FILTERING (GOVERNANCE compliance): Stock scores are for equity trading signals.
        # Exclude ETFs per GOVERNANCE.md: "financial data loaders and trading signals are stocks only".
        # Use etf_symbols table (definitive source). Note: ss.etf column does not exist in stock_scores.
        # This pattern is mirrored in /api/market/breadth and Phase 7 signal generation.
        #
        # EXTRACTED 2026-09-13 to algo/signals/investable_universe.py, along with every
        # filter's own detailed rationale (SPAC/royalty-trust/structured-note/CEF/gold-trust/
        # ETN/active-universe history) - loaders/load_sector_industry_daily.py needed the
        # identical definition for its sector/industry rankings and was silently missing all
        # of it (414 non-tradeable symbols, live-counted, were skewing those averages). Only
        # this endpoint's own request-specific conditions (sp500_only, symbol lookup,
        # data_unavailable, market_cap floor) stay inline below.
        where_clause = "WHERE " + investable_universe_conditions("sc", "ss")
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
        else:
            # Bulk queries: filter by data availability status computed by loader.
            # Loader marks data_unavailable=false for scores with 4+/6 metrics (sufficient diversity).
            # Loader marks data_unavailable=true for scores with <4/6 metrics or data_completeness < 70%.
            # API: Return all scores where loader marked available; dashboard filters on completeness %.
            # This gives traders full visibility: completeness % shown for all scores >= 50%.
            where_clause += " AND (sc.data_unavailable = false OR sc.data_unavailable IS NULL)"

        # MARKET-CAP ELIGIBILITY FLOOR (added 2026-08-31, /goal session - "make sure the
        # results make sense" investigation). This endpoint's default sort is composite_score
        # DESC with no investability screen of any kind - live-verified the top of that
        # ranking was dominated by nano/micro-caps (SOGP $37.6M mkt cap, COHN $19.6M, CPBI
        # $79.5M, several under $200K/day dollar volume), because Size was deliberately
        # retired as a scoring PILLAR (size_pillar_retired_entirely_20260828 in memory - not
        # being re-litigated here) with nothing left to offset small-cap-favoring percentile
        # scoring. A liquidity gate already exists for real trade EXECUTION
        # (algo/risk/liquidity_checks.py, min_adv_shares/min_adv_dollars config) but only
        # fires at Phase 8 entry time - invisible to anyone just browsing this "top stocks"
        # list, so untradeable names surface as if they were the best picks. Opt-in
        # (min_market_cap query param, no default) rather than a silent behavior change for
        # existing callers/tests - single-symbol lookups are deliberately exempt (you should
        # always be able to look up any specific symbol regardless of its size). Standard
        # index-provider practice (Russell/S&P/MSCI) applies exactly this kind of investability
        # screen separately from the factor scores themselves.
        market_cap_join = ""
        if min_market_cap is not None and not symbol:
            market_cap_join = "JOIN value_metrics mcf ON mcf.symbol = sc.symbol"
            where_clause += " AND mcf.market_cap >= %s"
            params_list.append(min_market_cap)

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

        # PERFORMANCE: filter/sort/limit to the target page FIRST in a CTE, then run the
        # per-symbol LATERAL lookups (price_daily/technical_data_daily) only against that
        # small row set. Previously the LATERAL joins ran against every row of stock_scores
        # BEFORE the WHERE clause was applied, so a page of 50 rows still paid for thousands
        # of per-symbol index scans - this was the root cause of the endpoint's 7+ second
        # latency (and the dashboard's 3s client timeout hiding it as "no data"). Query
        # construction itself lives in stock_scores_helpers.py (_build_stock_scores_query) -
        # see that function's docstring for the same detail.
        query = _build_stock_scores_query(where_clause, market_cap_join, sort_col, sort_direction)
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

        # Row/factor-input transformation (data_unavailable-driven score nulling, factor
        # input objects, current_price data-quality flag) - see
        # stock_scores_helpers._build_stock_score_items's docstring.
        items = _build_stock_score_items(scores)

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
