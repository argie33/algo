"""Algo metrics handler: /api/algo/stage-distribution.

Split 2026-09-05 (file-size-ratchet compliance split of the original 1246-line
algo_handlers/metrics.py into a package, one module per top-level handler function -
same pattern as loaders/stock_scores/ and lambda/api/routes/algo_handlers/dashboard/).
This module holds only `_get_stage_distribution`; the other handlers live in their
own sibling modules (or, for `_get_portfolio_summary`, directly in `__init__.py` -
see that file's docstring for why). All names are re-exported from
`algo_handlers/metrics/__init__.py` so existing callers (e.g. routes/algo.py's
`from .algo_handlers.metrics import (...)`) require zero changes. Pure move, no
logic changed - body is byte-for-byte identical to the pre-split version (only the
import header differs, trimmed to that function's actual dependencies).
"""

from __future__ import annotations

# mypy: disable-error-code=no-any-return
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import db_route_handler, list_response


@db_route_handler("get stage distribution")
def _get_stage_distribution(cur: cursor) -> Any:
    cur.execute("""
        SELECT
            COUNT(*) as count,
            CASE
                WHEN weinstein_stage = 1 THEN 'Stage 1 (base)'
                WHEN weinstein_stage = 2 THEN
                    CASE
                        WHEN minervini_trend_score < 4 THEN 'Early Stage-2'
                        WHEN minervini_trend_score >= 6 THEN 'Late Stage-2'
                        ELSE 'Mid Stage-2'
                    END
                WHEN weinstein_stage = 3 THEN 'Stage 3 (top)'
                WHEN weinstein_stage = 4 THEN 'Stage 4 (down)'
                ELSE 'Unknown'
            END as phase
        FROM algo_positions_with_risk
        GROUP BY phase, weinstein_stage
        ORDER BY weinstein_stage ASC
    """)
    rows = cur.fetchall()

    if not rows:
        return list_response([], total=0, limit=None, offset=None)

    distribution = [{"phase": r["phase"], "count": int(r["count"])} for r in rows]

    return list_response(distribution, total=len(distribution), limit=None, offset=None)
