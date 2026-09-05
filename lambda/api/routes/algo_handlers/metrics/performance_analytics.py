"""Algo metrics handler: /api/algo/performance-analytics.

Split 2026-09-05 (file-size-ratchet compliance split of the original 1246-line
algo_handlers/metrics.py into a package, one module per top-level handler function -
same pattern as loaders/stock_scores/ and lambda/api/routes/algo_handlers/dashboard/).
This module holds only `_get_performance_analytics`; `_compute_data_age_seconds`
(shared with `performance.py`) lives in `_shared.py`. The other handlers live in
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
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import db_route_handler, safe_dict_convert, success_response, validate_api_response

from utils.validation import APIResponseValidator

from ._shared import _compute_data_age_seconds

logger = logging.getLogger(__name__)


@db_route_handler("get performance analytics")
@validate_api_response("perf_anl")
def _get_performance_analytics(cur: cursor) -> Any:
    """Rolling performance analytics (Sharpe/Sortino/Calmar/expectancy).

    Reads algo_performance_daily, not algo_performance_metrics - the latter has had no
    writer since 2026-06-30 (see _get_algo_performance's docstring above for the full
    story) and was silently serving 3-week-stale numbers here too.
    """
    try:
        cur.execute("SAVEPOINT perf_analytics")
        cur.execute("""
            SELECT report_date AS metric_date, rolling_sharpe_252d AS sharpe_ratio,
                   rolling_sortino_252d AS sortino_ratio, calmar_ratio,
                   win_rate_50t AS win_rate_pct, max_drawdown_pct,
                   avg_win_r_50t AS avg_win_r, avg_loss_r_50t AS avg_loss_r, expectancy,
                   updated_at
            FROM algo_performance_daily
            ORDER BY report_date DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if row is None:
            logger.error(
                "Performance analytics unavailable: algo_performance_daily table empty. "
                "Phase 9 (LivePerformance.generate_daily_report) should populate it every orchestrator run."
            )
            raise RuntimeError("Performance metrics data unavailable - table is empty")
        # CRITICAL: Convert row to dict BEFORE releasing savepoint (RELEASE clears cursor.description)
        data = safe_dict_convert(row)
        cur.execute("RELEASE SAVEPOINT perf_analytics")
        sharpe: Any = data.get("sharpe_ratio")
        sortino: Any = data.get("sortino_ratio")
        calmar: Any = data.get("calmar_ratio")
        wr_pct: Any = data.get("win_rate_pct")
        max_dd: Any = data.get("max_drawdown_pct")
        avg_win_r: Any = data.get("avg_win_r")
        avg_loss_r: Any = data.get("avg_loss_r")
        expectancy_val: Any = data.get("expectancy")

        # FAIL-FAST only for sharpe_ratio - generate_daily_report guarantees it's non-null
        # whenever a row exists at all (see algo/reporting/performance.py).
        # Everything else is honestly nullable by documented design (win_rate_50t/sortino/
        # calmar need enough snapshot history; avg_win_r/avg_loss_r/expectancy need both
        # a winning AND a losing trade in the lookback window - expected early-sample
        # states, not pipeline failures) and must be passed through as None.
        if sharpe is None:
            logger.error("Performance analytics unavailable: sharpe_ratio missing from database")
            raise RuntimeError("Performance data incomplete: sharpe_ratio is missing")

        report_date = data.get("metric_date")
        data_age_seconds = _compute_data_age_seconds(cur, data.get("updated_at"), "algo_performance_daily")

        response_dict_final: dict[str, Any] = {
            "rolling_sharpe_252d": float(sharpe),
            "rolling_sortino_252d": float(sortino) if sortino is not None else None,
            "calmar_ratio": float(calmar) if calmar is not None else None,
            "win_rate_50t": float(wr_pct) if wr_pct is not None else None,
            "avg_win_r_50t": float(avg_win_r) if avg_win_r is not None else None,
            "avg_loss_r_50t": float(avg_loss_r) if avg_loss_r is not None else None,
            "expectancy": float(expectancy_val) if expectancy_val is not None else None,
            "max_drawdown_pct": float(max_dd) if max_dd is not None else None,
            "report_date": report_date.isoformat() if report_date is not None else None,
            "data_age_seconds": data_age_seconds,
        }

        # Validate perf_anl response matches contract schema
        sanitized = APIResponseValidator.sanitize_response(response_dict_final)

        return success_response(sanitized)
    except psycopg2.errors.UndefinedColumn as col_err:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT perf_analytics")
        except (psycopg2.DatabaseError, psycopg2.OperationalError):
            pass

        logger.error(f"R-metrics columns missing from performance_metrics table: {col_err}")
        raise RuntimeError(f"Performance metrics schema incomplete: {col_err}") from col_err
    except psycopg2.errors.UndefinedTable as table_err:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT perf_analytics")
        except (psycopg2.DatabaseError, psycopg2.OperationalError):
            pass

        logger.error(f"Performance metrics table missing: {table_err}")
        raise RuntimeError("Performance metrics table does not exist") from table_err
    except (
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        ValueError,
        KeyError,
    ) as e:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT perf_analytics")
        except (psycopg2.DatabaseError, psycopg2.OperationalError):
            pass

        logger.error(f"Performance analytics database error: {type(e).__name__}: {e}")
        raise RuntimeError(f"Failed to fetch performance analytics: {type(e).__name__}") from e
