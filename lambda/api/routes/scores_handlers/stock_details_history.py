"""Score route handlers: 12-1 momentum derivation and the per-symbol score-history endpoint.

Split out of stock_details.py (2026-09) purely to keep that file under the file-size
ratchet's new-file cap - no behavior change from the code's prior location there.
"""

from __future__ import annotations

import logging
import math
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

logger = logging.getLogger(__name__)


def _derive_mom_12_1(momentum_12m: float | None, momentum_1m: float | None) -> float | None:
    """12-1 skip-month momentum (Jegadeesh 1990 standard construction) - the actual quantity
    loaders/load_stock_scores.py's _score_momentum weights at 35% since 2026-08-25 (see that
    function's docstring RESOLVED note), replacing raw momentum_6m/momentum_12m. Not a stored
    field - derived here the identical way, so this page shows the real number driving the
    score instead of the raw momentum_12m value that no longer is the score input (same
    "computed but invisible" bug class this codebase has fixed before for
    vol_managed_multiplier/active_policy_tier - a scored quantity must be visible somewhere,
    not just its stale predecessor). Cumulative return from 12mo-ago to 1mo-ago is
    algebraically (1+momentum_12m/100)/(1+momentum_1m/100) - 1, converted back to the
    percentage-number convention this page's other momentum fields use.
    """
    if momentum_12m is None or momentum_1m is None:
        return None
    denom = 1.0 + float(momentum_1m) / 100.0
    if abs(denom) <= 1e-6:
        return None
    result = ((1.0 + float(momentum_12m) / 100.0) / denom - 1.0) * 100.0
    return result if math.isfinite(result) else None


def _get_score_history(cur: cursor, symbol: str, days: int) -> Any:
    """Historical composite score / rank movement for one symbol.

    Sourced from stock_scores_history - one snapshot per trading day, written by
    load_stock_scores.py's post_run() after RS percentiles are finalized for that run.
    A symbol new to scoring, or one that only recently started passing the completeness
    gate, will simply have fewer points than `days` - not an error.
    """
    try:
        query = """
            SELECT
                score_date, composite_score, composite_rank, rs_percentile,
                momentum_score, quality_score, growth_score, value_score,
                risk_score, data_completeness
            FROM stock_scores_history
            WHERE symbol = %s AND score_date >= CURRENT_DATE - %s::int
            ORDER BY score_date ASC
        """
        rows = execute_with_timeout(cur, query, [symbol, days], timeout_sec=20, max_attempts=1)

        points = [dict(row) for row in rows]
        for p in points:
            if p.get("score_date") is not None:
                p["score_date"] = p["score_date"].isoformat()

        movement: dict[str, Any] = {
            "score_change": None,
            "rank_change": None,
            "rs_percentile_change": None,
            "start_date": None,
            "end_date": None,
        }
        if len(points) >= 2:
            first, last = points[0], points[-1]
            movement["start_date"] = first["score_date"]
            movement["end_date"] = last["score_date"]
            if first.get("composite_score") is not None and last.get("composite_score") is not None:
                movement["score_change"] = round(float(last["composite_score"]) - float(first["composite_score"]), 2)
            if first.get("composite_rank") is not None and last.get("composite_rank") is not None:
                # Negative rank_change = improved (moved toward rank 1)
                movement["rank_change"] = int(first["composite_rank"]) - int(last["composite_rank"])
            if first.get("rs_percentile") is not None and last.get("rs_percentile") is not None:
                movement["rs_percentile_change"] = round(
                    float(last["rs_percentile"]) - float(first["rs_percentile"]), 2
                )

        result = {
            "symbol": symbol,
            "days": days,
            "points": points,
            "movement": movement,
        }

        freshness = check_data_freshness(cur, "stock_scores_history", "updated_at", warning_days=3)
        return json_response(200, result, data_freshness=freshness, preserve_arrays=True)

    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "get score history")
        return error_response(code, error_type, message)
