"""Algo metrics handler: /api/algo/metrics.

Split 2026-09-05 (file-size-ratchet compliance split of the original 1246-line
algo_handlers/metrics.py into a package, one module per top-level handler function -
same pattern as loaders/stock_scores/ and lambda/api/routes/algo_handlers/dashboard/).
This module holds only `_get_algo_metrics`; the other handlers live in their own
sibling modules (or, for `_get_portfolio_summary`, directly in `__init__.py` - see
that file's docstring for why). All names are re-exported from
`algo_handlers/metrics/__init__.py` so existing callers (e.g. routes/algo.py's
`from .algo_handlers.metrics import (...)`) require zero changes. Pure move, no
logic changed - body is byte-for-byte identical to the pre-split version (only the
import header differs, trimmed to this function's actual dependencies).
"""

from __future__ import annotations

# mypy: disable-error-code=no-any-return
import logging
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import (
    db_route_handler,
    error_response,
    handle_db_error,
    safe_dict_convert,
    success_response,
)

logger = logging.getLogger(__name__)


@db_route_handler("get algo metrics")
def _get_algo_metrics(cur: cursor) -> Any:
    try:
        cur.execute("""
            SELECT date, total_actions, entries, exits, avg_signal_score
            FROM algo_metrics_daily
            ORDER BY date DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        # FAIL-FAST: Return error if metrics not yet available (no runs yet)
        if row is None:
            return error_response(
                503,
                "no_data",
                "Algo metrics not yet available - no daily runs have completed",
            )
        data = safe_dict_convert(row)

        # Validate critical fields
        date = data.get("date")
        total_actions = data.get("total_actions")
        entries = data.get("entries")
        exits = data.get("exits")

        if date is None:
            return error_response(503, "incomplete_data", "Algo metrics date missing")
        if total_actions is None or entries is None or exits is None:
            return error_response(
                503,
                "incomplete_data",
                "Algo metrics incomplete (missing actions/entries/exits)",
            )

        total_actions = int(total_actions)
        entries = int(entries)
        exits = int(exits)

        avg_signal_score_raw = data.get("avg_signal_score")
        avg_signal_score: float | None = None
        if avg_signal_score_raw is not None:
            try:
                avg_signal_score = float(avg_signal_score_raw)
            except (ValueError, TypeError) as e:
                logger.error(f"CRITICAL: avg_signal_score conversion failed: {avg_signal_score_raw} ({e})")
                return error_response(
                    503,
                    "data_corruption",
                    f"Algo metrics data corrupt: avg_signal_score is '{avg_signal_score_raw}' (expected float). "
                    "Check algo_metrics_daily table data type or calculation.",
                )

        return success_response(
            {
                "date": date,
                "total_actions": total_actions,
                "entries": entries,
                "exits": exits,
                "avg_signal_score": avg_signal_score,
            }
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch algo metrics")
        return error_response(code, error_type, message)
