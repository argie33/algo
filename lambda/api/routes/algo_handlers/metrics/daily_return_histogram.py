"""Algo metrics handler: /api/algo/daily-return-histogram.

Split 2026-09-05 (file-size-ratchet compliance split of the original 1246-line
algo_handlers/metrics.py into a package, one module per top-level handler function -
same pattern as loaders/stock_scores/ and lambda/api/routes/algo_handlers/dashboard/).
This module holds only `_get_daily_return_histogram`; the other handlers live in
their own sibling modules (or, for `_get_portfolio_summary`, directly in
`__init__.py` - see that file's docstring for why). All names are re-exported from
`algo_handlers/metrics/__init__.py` so existing callers (e.g. routes/algo.py's
`from .algo_handlers.metrics import (...)`) require zero changes. Pure move, no
logic changed - body is byte-for-byte identical to the pre-split version (only the
import header differs, trimmed to this function's actual dependencies).
"""

from __future__ import annotations

# mypy: disable-error-code=no-any-return
import logging
import math
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import db_route_handler, error_response

from utils.validation import format_decimal_string

logger = logging.getLogger(__name__)


@db_route_handler("get daily return histogram")
def _get_daily_return_histogram(cur: cursor) -> Any:
    try:
        # No LIMIT: this feeds the mean/std (volatility) stats on the histogram panel. A
        # hardcoded LIMIT 250 here would silently drop everything before the most recent
        # ~250 daily snapshots with no signal to the caller once history grows past that
        # (currently well under it - only rows with non-NULL daily_return_pct qualify -
        # but the cap was arbitrary and would bite silently later). Full history is cheap
        # here (one float column, no per-row work) so there's no performance reason to cap it.
        cur.execute("""
            SELECT daily_return_pct
            FROM algo_portfolio_snapshots
            WHERE daily_return_pct IS NOT NULL
        """)
        rows = cur.fetchall()
        returns = [float(r["daily_return_pct"]) for r in rows if r.get("daily_return_pct") is not None]

        if not returns:
            return {"statusCode": 200, "data": {"items": [], "total": 0, "stats": None}}

        bucket_width = 0.5
        min_ret = min(returns)
        max_ret = max(returns)
        min_bucket = math.floor(min_ret / bucket_width) * bucket_width
        max_bucket = math.ceil(max_ret / bucket_width) * bucket_width

        buckets_dict = {}
        mid = min_bucket
        while mid <= max_bucket:
            buckets_dict[mid] = 0
            mid += bucket_width

        for ret in returns:
            bucket_mid = round(ret / bucket_width) * bucket_width
            if bucket_mid in buckets_dict:
                buckets_dict[bucket_mid] += 1

        buckets = [
            {"mid": format_decimal_string(mid, precision=2), "count": count}
            for mid, count in sorted(buckets_dict.items())
        ]

        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        std_ret = math.sqrt(variance)
        stats = {
            "count": len(returns),
            "mean": format_decimal_string(mean_ret, precision=2),
            "std": format_decimal_string(std_ret, precision=2),
        }

        return {"statusCode": 200, "data": {"items": buckets, "total": len(buckets), "stats": stats}}
    except Exception as e:
        logger.error(f"Error in daily return histogram: {e}")
        return error_response(500, "internal_error", "Failed to generate histogram")
