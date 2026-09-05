"""Route: scores

2026-09-05: wired to the scores_handlers/ split (drafted 2026-09-05, orphaned uncommitted
until now - see MEMORY.md concurrent_session_scores_handlers_split_import_breakage_reconciled
note). This file is now just the /api/scores/* dispatcher; the actual handler logic lives in
scores_handlers/*.py. Names below are re-exported (not just used internally) because several
tests import them as `routes.scores.<name>` / `from routes.scores import <name>` - removing
any of these re-exports breaks those tests even though this file no longer defines them.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import error_response, extract_param, handle_db_error, safe_days, safe_limit, safe_offset

from .scores_handlers.coverage import _NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE, _get_scores_coverage
from .scores_handlers.coverage_classification import _UNSCORED_TABLES, _categorize_reason
from .scores_handlers.coverage_sources import _coverage_order_col, _prettify_source
from .scores_handlers.incomplete_and_coverage import _get_incomplete_stocks
from .scores_handlers.stock_details import _get_stock_details
from .scores_handlers.stock_details_history import _get_score_history
from .scores_handlers.stock_scores import _get_stock_scores

__all__ = [
    "_NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE",
    "_UNSCORED_TABLES",
    "_categorize_reason",
    "_coverage_order_col",
    "_get_incomplete_stocks",
    "_get_score_history",
    "_get_scores_coverage",
    "_get_stock_details",
    "_get_stock_scores",
    "_prettify_source",
    "handle",
]

logger = logging.getLogger(__name__)


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, str] | None,
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle /api/scores/* and /api/algo/scores/* endpoints."""
    try:
        # Handle /api/scores/details/:symbol endpoint (new)
        if path.startswith("/api/scores/details/"):
            detail_symbol = path.split("/api/scores/details/")[-1].upper()
            if not detail_symbol or not detail_symbol.replace("-", "").replace("^", "").isalnum():
                return error_response(400, "bad_request", "Invalid symbol format")
            return _get_stock_details(cur, detail_symbol)

        # Handle /api/scores/history/:symbol endpoint - historical composite score/rank
        # movement, sourced from stock_scores_history (one snapshot per trading day,
        # written by load_stock_scores.py's post_run()).
        if path.startswith("/api/scores/history/"):
            history_symbol = path.split("/api/scores/history/")[-1].split("?")[0].upper()
            if not history_symbol or not history_symbol.replace("-", "").replace("^", "").isalnum():
                return error_response(400, "bad_request", "Invalid symbol format")
            days = safe_days(extract_param(params, "days"), max_val=365, default=90)
            return _get_score_history(cur, history_symbol, days)

        # Handle /api/scores/incomplete endpoint (new) - stocks with insufficient data
        if path in ["/api/scores/incomplete", "/api/algo/scores/incomplete"] or path.startswith(
            ("/api/scores/incomplete?", "/api/algo/scores/incomplete?")
        ):
            limit = safe_limit(extract_param(params, "limit"), max_val=1000, default=100)
            offset = safe_offset(extract_param(params, "offset") or "0")
            sort_by = extract_param(params, "sortBy") or "data_completeness"
            sort_order = (extract_param(params, "sortOrder") or "asc").lower()
            if sort_by not in ("data_completeness", "symbol"):
                sort_by = "data_completeness"
            if sort_order not in ("asc", "desc"):
                sort_order = "asc"

            return _get_incomplete_stocks(cur, limit, offset, sort_by, sort_order)

        # Handle /api/scores/coverage endpoint - factor-level aggregation of which
        # *_unavailable_reason columns are missing data, why, and how much. Mirrors
        # scripts/audit_unavailable_reasons.py's methodology (latest row per symbol,
        # deduplicated) but served live for the ServiceHealth "Scores Data Coverage" tab.
        #
        # FIXED 2026-09-01 (goal session: this single request ran ~100+ sequential
        # per-table queries in one HTTP call, taking 15-20s+ end to end - close enough to
        # the frontend axios client's 28s hard timeout (set deliberately below API
        # Gateway/Lambda's own 30s hard cutoff, see api.js) that it timed out in practice
        # under any real load, even though a one-off psql/script run of the same queries
        # "worked". Bumping the client timeout doesn't fix this: in production Lambda
        # kills the function at 30s regardless of what the client is willing to wait, so
        # the actual fix is to break the ~100+ queries into per-group chunks the frontend
        # fetches separately (ScoresDataCoverage.jsx), each cheap enough to finish well
        # under either limit. `?meta=1` returns just the group list (two fast
        # information_schema queries, no per-table scans) so the frontend knows what to
        # fetch; `?group=<name>` scopes the normal per-table loop to one group at a time.
        if path in ["/api/scores/coverage", "/api/algo/scores/coverage"]:
            if extract_param(params, "meta") == "1":
                return _get_scores_coverage(cur, meta_only=True)
            return _get_scores_coverage(cur, group_filter=extract_param(params, "group"))

        if path in [
            "/api/scores",
            "/api/scores/stockscores",
            "/api/algo/scores",
            "/api/algo/scores/stockscores",
        ] or path.startswith(
            ("/api/scores?", "/api/scores/stockscores?", "/api/algo/scores?", "/api/algo/scores/stockscores?")
        ):
            # max_val was 1000 - the real filtered universe is ~5000+ symbols (live-verified),
            # so any caller requesting the default/max page size silently got capped well
            # below the true universe size. Raised to match the other high-volume listing
            # endpoints (signals.py, algo.py use 10000).
            limit = safe_limit(extract_param(params, "limit"), max_val=10000, default=1000)
            offset = safe_offset(extract_param(params, "offset") or "0")
            sort_by = extract_param(params, "sortBy") or "composite_score"
            sort_order = (extract_param(params, "sortOrder") or "desc").lower()
            sp500_only = extract_param(params, "sp500Only") or "false"
            symbol = extract_param(params, "symbol")
            min_market_cap_param = extract_param(params, "minMarketCap")
            min_market_cap: float | None = None
            if min_market_cap_param:
                try:
                    min_market_cap = float(min_market_cap_param)
                except ValueError:
                    return error_response(400, "bad_request", "minMarketCap must be numeric")

            allowed_sorts = [
                "composite_score",
                "momentum_score",
                "quality_score",
                "value_score",
                "growth_score",
                "risk_score",
                "symbol",
            ]
            if sort_by not in allowed_sorts:
                return error_response(
                    400,
                    "bad_request",
                    f"Sort must be one of: {', '.join(allowed_sorts)}",
                )
            if sort_order not in ["asc", "desc"]:
                return error_response(400, "bad_request", 'Sort order must be "asc" or "desc"')

            return _get_stock_scores(
                cur, limit, offset, sort_by, sort_order, sp500_only == "true", symbol, min_market_cap
            )
        else:
            return error_response(404, "not_found", "Invalid scores endpoint requested")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle scores")
        return error_response(code, error_type, message)
