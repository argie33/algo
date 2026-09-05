"""Algo metrics handler: /api/algo/performance-metrics.

Split 2026-09-05 (file-size-ratchet compliance split of the original 1246-line
algo_handlers/metrics.py into a package, one module per top-level handler function -
same pattern as loaders/stock_scores/ and lambda/api/routes/algo_handlers/dashboard/).
This module holds only `_get_performance_metrics_endpoint`; the other handlers live
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

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import (
    db_route_handler,
    error_response,
    handle_db_error,
    json_response,
    safe_dict_convert,
    validate_api_response,
)

logger = logging.getLogger(__name__)


@db_route_handler("get performance metrics endpoint")
@validate_api_response("perf")
def _get_performance_metrics_endpoint(cur: cursor) -> Any:
    """Reads algo_performance_daily - see _get_algo_performance's docstring above:
    algo_performance_metrics (the previous source) has had no writer since 2026-06-30.
    profit_factor isn't populated in algo_performance_daily either (nothing in the
    current pipeline writes it there); returned as None rather than a stale number.
    """
    try:
        cur.execute("""
            SELECT win_rate_50t AS win_rate_pct, profit_factor, expectancy,
                   rolling_sharpe_252d AS sharpe_ratio, max_drawdown_pct
            FROM algo_performance_daily
            ORDER BY report_date DESC
            LIMIT 1
        """)
        row = cur.fetchone()

        if not row:
            logger.error("Performance metrics unavailable: algo_performance_daily table empty.")
            raise RuntimeError("Performance metrics not yet available - table is empty")

        row = safe_dict_convert(row)

        return json_response(
            200,
            {
                "win_rate": (float(row["win_rate_pct"]) / 100 if row["win_rate_pct"] else None),
                "profit_factor": float(row["profit_factor"]) if row["profit_factor"] is not None else None,
                "expectancy": float(row["expectancy"]) if row["expectancy"] is not None else None,
                "sharpe_ratio": float(row["sharpe_ratio"]) if row["sharpe_ratio"] is not None else None,
                "max_drawdown": (float(row["max_drawdown_pct"]) / 100 if row["max_drawdown_pct"] else None),
            },
        )
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as col_err:
        logger.error(f"Performance metrics table/columns unavailable: {col_err}")
        raise RuntimeError(f"Performance metrics schema incomplete: {col_err}") from col_err
    except (psycopg2.OperationalError, psycopg2.DatabaseError) as db_err:
        code, error_type, message = handle_db_error(db_err, "fetch performance metrics")
        return error_response(code, error_type, message)
