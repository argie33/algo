"""Route: research"""

import logging
from typing import Any, cast

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    error_response,
    execute_with_timeout,
    handle_db_error,
    json_response,
    list_response,
    safe_json_serialize,
    safe_limit,
    safe_offset,
)

logger = logging.getLogger(__name__)


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Handle /api/research/* endpoints."""
    try:
        if path == "/api/research/backtests" or path.startswith("/api/research/backtests?"):
            limit_str = params.get("limit", [None])[0] if params else None
            limit = safe_limit(limit_str or "50000", max_val=50000)
            backtests = execute_with_timeout(
                cur,
                """
                    SELECT run_id, strategy_name, start_date AS date_start, end_date AS date_end,
                           total_return AS total_return_pct, sharpe_ratio AS sharpe,
                           max_drawdown AS max_drawdown_pct, win_rate, num_trades AS total_trades
                    FROM backtest_runs
                    ORDER BY created_at DESC
                    LIMIT %s
                """,
                (limit,),
                timeout_sec=10,
            )
            freshness = check_data_freshness(cur, "backtest_runs", "created_at", warning_days=7)
            return cast(dict[str, Any], list_response(
                [safe_json_serialize(dict(b)) for b in backtests] if backtests else [],
                data_freshness=freshness,
            ))
        elif path.startswith("/api/research/backtests/"):
            run_id = path.split("/api/research/backtests/")[-1]
            try:
                run_id_int = int(run_id)
            except ValueError:
                return cast(dict[str, Any], error_response(400, "bad_request", "Run ID must be numeric"))

            backtest_rows = execute_with_timeout(
                cur,
                """
                    SELECT run_id, strategy_name, start_date AS date_start, end_date AS date_end,
                           total_return AS total_return_pct, sharpe_ratio AS sharpe_annualized,
                           max_drawdown AS max_drawdown_pct, win_rate,
                           num_trades AS total_trades,
                           NULL AS best_trade_pct, NULL AS worst_trade_pct, NULL AS avg_trade_pct,
                           NULL AS consecutive_wins, NULL AS consecutive_losses,
                           created_at, NULL AS notes
                    FROM backtest_runs
                    WHERE run_id = %s
                """,
                (run_id_int,),
                timeout_sec=8,
            )
            backtest = backtest_rows[0] if backtest_rows else None
            if not backtest:
                return cast(dict[str, Any], error_response(404, "not_found", f"Backtest run {run_id} not found"))

            limit_str = params.get("limit", [None])[0] if params else None
            offset_str = params.get("offset", [None])[0] if params else None
            limit = safe_limit(limit_str or "50000", max_val=50000)
            offset = safe_offset(offset_str or "0")

            trades = execute_with_timeout(
                cur,
                """
                    SELECT trade_id, symbol, NULL AS signal_date, entry_date, entry_price,
                           quantity AS entry_quantity, exit_date, exit_price,
                           profit_loss_percent AS profit_loss_pct,
                           NULL AS mfe_pct, NULL AS mae_pct
                    FROM backtest_trades
                    WHERE run_id = %s
                    ORDER BY entry_date DESC
                    LIMIT %s OFFSET %s
                """,
                (run_id_int, limit, offset),
                timeout_sec=6,
            )

            count_rows = execute_with_timeout(
                cur,
                """
                    SELECT COUNT(*) FROM backtest_trades WHERE run_id = %s
                """,
                (run_id_int,),
                timeout_sec=3,
            )
            total_trades_count = (
                next(iter(safe_json_serialize(dict(count_rows[0]).values())), 0) if count_rows and count_rows[0] else 0
            )

            # Build response
            run_dict = safe_json_serialize(dict(backtest))
            freshness = check_data_freshness(cur, "backtest_runs", "created_at", warning_days=7)
            return cast(dict[str, Any], json_response(
                200,
                {
                    "run": run_dict,
                    "trades": ([safe_json_serialize(dict(t)) for t in trades] if trades else []),
                    "trade_pagination": {"total": total_trades_count},
                    "data_freshness": freshness,
                },
            ))
        return cast(dict[str, Any], error_response(404, "not_found", f"No research handler for {path}"))
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle research")
        return cast(dict[str, Any], error_response(code, error_type, message))
