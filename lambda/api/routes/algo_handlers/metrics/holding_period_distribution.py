"""Algo metrics handler: /api/algo/holding-period-distribution.

Split 2026-09-05 (file-size-ratchet compliance split of the original 1246-line
algo_handlers/metrics.py into a package, one module per top-level handler function -
same pattern as loaders/stock_scores/ and lambda/api/routes/algo_handlers/dashboard/).
This module holds only `_get_holding_period_distribution`; the other handlers live
in their own sibling modules (or, for `_get_portfolio_summary`, directly in
`__init__.py` - see that file's docstring for why). All names are re-exported from
`algo_handlers/metrics/__init__.py` so existing callers (e.g. routes/algo.py's
`from .algo_handlers.metrics import (...)`) require zero changes. Pure move, no
logic changed - body is byte-for-byte identical to the pre-split version (only the
import header differs, trimmed to this function's actual dependencies).
"""

from __future__ import annotations

# mypy: disable-error-code=no-any-return
import logging
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import db_route_handler, list_response

logger = logging.getLogger(__name__)


@db_route_handler("get holding period distribution")
def _get_holding_period_distribution(cur: cursor) -> Any:
    # No LIMIT: this is a full-history distribution of every closed trade's holding
    # period, not a recent-activity feed. A hardcoded LIMIT 500 here would silently
    # exclude older trades from the bucket counts once total closed trades passes 500 -
    # same silent-truncation pattern fixed on the daily-return histogram above.
    cur.execute("""
        SELECT CASE
            WHEN trade_duration_days IS NOT NULL AND trade_duration_days > 0 THEN trade_duration_days
            ELSE (exit_date - trade_date)::int
        END AS trade_duration_days
        FROM algo_trades
        WHERE status = 'closed' AND exit_date IS NOT NULL
    """)
    rows = cur.fetchall()
    durations = [int(r["trade_duration_days"]) for r in rows if r.get("trade_duration_days") is not None]

    if not durations:
        return list_response([], total=0, limit=None, offset=None)

    buckets: list[dict[str, Any]] = [
        {"range": "0-3 days", "count": 0},
        {"range": "4-7 days", "count": 0},
        {"range": "8-14 days", "count": 0},
        {"range": "15-30 days", "count": 0},
        {"range": "31-60 days", "count": 0},
        {"range": "61-90 days", "count": 0},
        {"range": "91-180 days", "count": 0},
        {"range": ">180 days", "count": 0},
    ]

    for d in durations:
        if d <= 3:
            buckets[0]["count"] += 1
        elif d <= 7:
            buckets[1]["count"] += 1
        elif d <= 14:
            buckets[2]["count"] += 1
        elif d <= 30:
            buckets[3]["count"] += 1
        elif d <= 60:
            buckets[4]["count"] += 1
        elif d <= 90:
            buckets[5]["count"] += 1
        elif d <= 180:
            buckets[6]["count"] += 1
        else:
            buckets[7]["count"] += 1

    # Return ALL buckets including empty ones so caller can reconstruct full distribution
    # Track how many had zero data for completeness
    empty_bucket_count = sum(1 for b in buckets if b["count"] == 0)
    if empty_bucket_count > 0:
        logger.debug(
            f"[METRICS] Holding period distribution: {empty_bucket_count}/{len(buckets)} ranges had zero trades"
        )
    return list_response(buckets, total=len(buckets), limit=None, offset=None)
