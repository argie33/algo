"""Algo metrics handler: /api/algo/trade-distribution.

Split 2026-09-05 (file-size-ratchet compliance split of the original 1246-line
algo_handlers/metrics.py into a package, one module per top-level handler function -
same pattern as loaders/stock_scores/ and lambda/api/routes/algo_handlers/dashboard/).
This module holds only `_get_trade_distribution`; the other handlers live in their
own sibling modules (or, for `_get_portfolio_summary`, directly in `__init__.py` -
see that file's docstring for why). All names are re-exported from
`algo_handlers/metrics/__init__.py` so existing callers (e.g. routes/algo.py's
`from .algo_handlers.metrics import (...)`) require zero changes. Pure move, no
logic changed - body is byte-for-byte identical to the pre-split version (only the
import header differs, trimmed to that function's actual dependencies).
"""

from __future__ import annotations

# mypy: disable-error-code=no-any-return
import logging
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import db_route_handler, list_response

logger = logging.getLogger(__name__)


@db_route_handler("get trade distribution")
def _get_trade_distribution(cur: cursor) -> Any:
    # No LIMIT: full-history R-multiple distribution across every closed trade - same
    # silent-truncation reasoning as the holding-period distribution above.
    cur.execute("""
        SELECT exit_r_multiple
        FROM algo_trades
        WHERE exit_r_multiple IS NOT NULL AND status = 'closed'
    """)
    rows = cur.fetchall()
    r_multiples = [float(r["exit_r_multiple"]) for r in rows if r.get("exit_r_multiple") is not None]

    if not r_multiples:
        return list_response([], total=0, limit=None, offset=None)

    buckets: list[dict[str, Any]] = [
        {"range": "<-2R", "count": 0, "min": -999},
        {"range": "-2R to -1R", "count": 0, "min": -2},
        {"range": "-1R to 0R", "count": 0, "min": -1},
        {"range": "0R to 1R", "count": 0, "min": 0},
        {"range": "1R to 2R", "count": 0, "min": 1},
        {"range": "2R to 3R", "count": 0, "min": 2},
        {"range": ">3R", "count": 0, "min": 3},
    ]

    for r in r_multiples:
        if r < -2:
            buckets[0]["count"] += 1
        elif r < -1:
            buckets[1]["count"] += 1
        elif r < 0:
            buckets[2]["count"] += 1
        elif r < 1:
            buckets[3]["count"] += 1
        elif r < 2:
            buckets[4]["count"] += 1
        elif r < 3:
            buckets[5]["count"] += 1
        else:
            buckets[6]["count"] += 1

    # Return ALL buckets including empty ones so caller can reconstruct full distribution
    # Track how many had zero data for completeness
    empty_bucket_count = sum(1 for b in buckets if b["count"] == 0)
    if empty_bucket_count > 0:
        logger.debug(f"[METRICS] R-multiple distribution: {empty_bucket_count}/{len(buckets)} ranges had zero trades")
    return list_response(buckets, total=len(buckets), limit=None, offset=None)
