"""Algo metrics route handlers - one module per handler function (mostly).

Split 2026-09-05 (file-size-ratchet compliance split of the original 1246-line
algo_handlers/metrics.py - see loaders/stock_scores/ and
lambda/api/routes/algo_handlers/dashboard/ for the established precedent this
follows). 10 of the 11 handlers that used to live in one flat module now live in
their own sibling module (algo_metrics.py, performance.py, portfolio.py,
daily_return_histogram.py, holding_period_distribution.py, performance_analytics.py,
performance_metrics_endpoint.py, risk_metrics.py, stage_distribution.py,
trade_distribution.py); `_compute_data_age_seconds` (shared by performance.py and
performance_analytics.py) lives in `_shared.py`, and `_ensure_portfolio_fields`
(used only by `_get_algo_portfolio`) stays in portfolio.py.

`_get_portfolio_summary` is the one handler that stays defined directly in THIS file
rather than moving to its own sibling module. Reason: tests/unit/test_api_portfolio_
summary.py does `patch.object(metrics_module, "safe_dict_convert", ...)` (patching
the module attribute) and then calls `metrics_module._get_portfolio_summary(...)`
directly - Python binds a function's free variables to whatever module it is
*physically defined in*, not to the module a caller happens to import it from. Had
`_get_portfolio_summary` moved to a sibling module, that patch would either raise
AttributeError (if safe_dict_convert isn't re-exported here) or silently no-op (if it
is re-exported here but the function's own globals still point at the sibling
module) - the exact same failure class that stopped an earlier split attempt on
scripts/local_loader_scheduler.py today. Keeping the function's physical definition
in this __init__.py (which already imports safe_dict_convert etc. below) keeps that
test's patch hitting the same module the function's globals actually resolve
against, unmodified.

This file re-exports all 11 handler names so existing callers - notably
routes/algo.py's `from .algo_handlers.metrics import (_get_algo_metrics, ...)` -
require zero changes. Pure move for the 10 relocated handlers, no logic changed
anywhere; each function's body is byte-for-byte identical to the pre-split version
(only the import header at the top of each new module differs, trimmed to that
function's actual dependencies).

`_compute_data_age_seconds` is also re-exported here (though not imported by
routes/algo.py) because tests/unit/test_algo_performance_data_age_seconds.py reaches
it via `metrics_module._compute_data_age_seconds` on the flat pre-split module.
"""

from __future__ import annotations

# mypy: disable-error-code=no-any-return
import logging
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import db_route_handler, error_response, json_response, safe_dict_convert

from ._shared import _compute_data_age_seconds
from .algo_metrics import _get_algo_metrics
from .daily_return_histogram import _get_daily_return_histogram
from .holding_period_distribution import _get_holding_period_distribution
from .performance import _get_algo_performance
from .performance_analytics import _get_performance_analytics
from .performance_metrics_endpoint import _get_performance_metrics_endpoint
from .portfolio import _get_algo_portfolio
from .risk_metrics import _get_risk_metrics
from .stage_distribution import _get_stage_distribution
from .trade_distribution import _get_trade_distribution

logger = logging.getLogger(__name__)


@db_route_handler("get portfolio summary")
# NOTE: not @validate_api_response("port") - "port" is the schema for the separate
# /api/algo/portfolio endpoint (_get_algo_portfolio below), whose required fields
# (total_portfolio_value, total_cash, position_count) don't match this endpoint's
# response shape (total_value, cash, invested, positions). Validating against it
# made every call to /api/algo/portfolio-summary fail contract validation and
# return a 500, regardless of the underlying data.
def _get_portfolio_summary(cur: cursor) -> Any:
    cur.execute("""
        SELECT total_portfolio_value, total_cash, total_equity, position_count, daily_return_pct
        FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC
        LIMIT 1
    """)
    row = cur.fetchone()

    if not row:
        return error_response(503, "no_data", "Portfolio snapshot not yet available")

    row = safe_dict_convert(row)

    # Validate critical fields (fail-fast: check for None, not falsiness - 0.0 is valid)
    total_value_raw = row.get("total_portfolio_value")
    if total_value_raw is None:
        return error_response(503, "incomplete_data", "Portfolio snapshot missing total_portfolio_value")

    try:
        total_value = float(total_value_raw)
        cash = float(row["total_cash"])
        invested = float(row["total_equity"])
        positions = int(row["position_count"])
        daily_return_pct = float(row["daily_return_pct"])
    except (ValueError, TypeError) as e:
        logger.error(f"Cannot convert portfolio fields to numeric types: {e}")
        return error_response(503, "incomplete_data", "Portfolio snapshot has invalid numeric fields")

    daily_change_dollars = (
        (daily_return_pct / 100 * total_value) if total_value is not None and daily_return_pct is not None else None
    )

    # Check `is not None`, not falsiness (see comment above): cash=$0.00 (fully invested),
    # invested=$0.00 (all cash), and daily_return_pct=0.00% (flat day) are all valid, common
    # portfolio states, not missing data - `if x else None` was silently reporting each of
    # them as unavailable ("N/A") on the portfolio summary, one of the most visible numbers
    # in the dashboard.
    if positions is None:
        return json_response(
            200,
            {
                "total_value": round(total_value, 2) if total_value is not None else None,
                "cash": round(cash, 2) if cash is not None else None,
                "invested": round(invested, 2) if invested is not None else None,
                "positions": None,
                "_warning": "positions count unavailable",
                "daily_change": (round(daily_change_dollars, 2) if daily_change_dollars is not None else None),
                "daily_change_percent": (round(daily_return_pct, 2) if daily_return_pct is not None else None),
            },
        )

    return json_response(
        200,
        {
            "total_value": round(total_value, 2) if total_value is not None else None,
            "cash": round(cash, 2) if cash is not None else None,
            "invested": round(invested, 2) if invested is not None else None,
            "positions": positions,
            "daily_change": (round(daily_change_dollars, 2) if daily_change_dollars is not None else None),
            "daily_change_percent": (round(daily_return_pct, 2) if daily_return_pct is not None else None),
        },
    )


__all__ = [
    "_compute_data_age_seconds",
    "_get_algo_metrics",
    "_get_algo_performance",
    "_get_algo_portfolio",
    "_get_daily_return_histogram",
    "_get_holding_period_distribution",
    "_get_performance_analytics",
    "_get_performance_metrics_endpoint",
    "_get_portfolio_summary",
    "_get_risk_metrics",
    "_get_stage_distribution",
    "_get_trade_distribution",
]
