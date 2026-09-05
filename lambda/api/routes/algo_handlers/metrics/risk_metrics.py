"""Algo metrics handler: /api/algo/risk-metrics.

Split 2026-09-05 (file-size-ratchet compliance split of the original 1246-line
algo_handlers/metrics.py into a package, one module per top-level handler function -
same pattern as loaders/stock_scores/ and lambda/api/routes/algo_handlers/dashboard/).
This module holds only `_get_risk_metrics`; the other handlers live in their own
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
    validate_api_response,
)

logger = logging.getLogger(__name__)


@db_route_handler("get risk metrics")
@validate_api_response("risk")
def _get_risk_metrics(cur: cursor) -> Any:
    try:
        cur.execute("SAVEPOINT risk_metrics")
        cur.execute("""
            SELECT report_date, var_pct_95, cvar_pct_95, stressed_var_pct,
                   portfolio_beta, top_5_concentration
            FROM algo_risk_daily
            ORDER BY report_date DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT risk_metrics")
        # FAIL-FAST: Return error if no risk metrics available
        if row is None:
            logger.warning(
                "Risk metrics unavailable: algo_risk_daily table empty. "
                "Check data loader health - should be populated daily."
            )
            return error_response(
                503,
                "data_unavailable",
                "Risk metrics not available. Check data loader health.",
            )
        # Check if there are any open positions first (needed to interpret beta/concentration values)
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
        position_count_row = cur.fetchone()
        has_positions = (position_count_row[0] > 0) if position_count_row else False

        data = safe_dict_convert(row)
        var_95 = data.get("var_pct_95")
        cvar_95 = data.get("cvar_pct_95")
        stressed_var = data.get("stressed_var_pct")
        portfolio_beta = data.get("portfolio_beta")
        concentration = data.get("top_5_concentration")

        # CRITICAL FIX: Beta and Concentration are OPTIONAL - use 0.0 default if missing
        # When positions = 0, NULL/0.0 is the correct value (zero market exposure/concentration)
        # When positions > 0 but beta/concentration NULL, data loader may still be running - use default instead of failing
        if portfolio_beta is None and has_positions:
            logger.warning(
                "Risk metrics missing portfolio_beta despite open positions. "
                "Portfolio has positions but beta not yet calculated - using default 0.0"
            )
        if concentration is None and has_positions:
            logger.warning(
                "Risk metrics missing top_5_concentration despite open positions. "
                "Portfolio has positions but concentration not yet calculated - using default 0.0"
            )

        return success_response(
            {
                "report_date": data.get("report_date"),
                "var_pct_95": float(var_95) if var_95 is not None else None,
                "cvar_pct_95": float(cvar_95) if cvar_95 is not None else None,
                "stressed_var_pct": (float(stressed_var) if stressed_var is not None else None),
                "portfolio_beta": (float(portfolio_beta) if portfolio_beta is not None else 0.0),
                "top_5_concentration": (float(concentration) if concentration is not None else 0.0),
                "has_positions": has_positions,
            }
        )
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        try:
            cur.execute("ROLLBACK TO SAVEPOINT risk_metrics")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Unexpected error: {e}") from e
        logger.error("Risk metrics table missing or schema changed")
        return error_response(503, "table_missing", "Risk metrics table not found")
    except (
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        ValueError,
        KeyError,
    ) as e:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT risk_metrics")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as save_err:
            raise RuntimeError(f"Unexpected error: {save_err}") from save_err
        code, error_type, message = handle_db_error(e, "fetch risk metrics")
        return error_response(code, error_type, message)
