"""Route: financials"""

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
    list_response,
    safe_json_serialize,
    safe_limit,
)

from shared_contracts.response_validator import ResponseValidator

logger = logging.getLogger(__name__)


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        parts = path.split("/")
        symbol = parts[3] if len(parts) > 3 else None
        endpoint = parts[4] if len(parts) > 4 else None

        if not symbol:
            return cast(dict[str, Any], error_response(400, "bad_request", "Symbol required"))

        sym = symbol.upper()
        period = (params.get("period", [None])[0] if params else None) or "annual"
        limit = safe_limit(params.get("limit", [None])[0] if params else None, max_val=40, default=8)

        if endpoint == "key-metrics":
            rows = execute_with_timeout(
                cur,
                """
                SELECT
                    vm.symbol,
                    CURRENT_DATE AS date,
                    vm.pe_ratio,
                    vm.pb_ratio AS price_to_book,
                    vm.ps_ratio AS price_to_sales,
                    vm.peg_ratio,
                    vm.dividend_yield,
                    vm.fcf_yield,
                    qm.debt_to_equity,
                    qm.roe AS return_on_equity,
                    qm.roa AS return_on_assets,
                    qm.net_margin AS profit_margin,
                    qm.current_ratio,
                    qm.quick_ratio,
                    vm.market_cap,
                    pm.insider_ownership AS held_percent_insiders,
                    pm.institutional_ownership AS held_percent_institutions
                FROM value_metrics vm
                LEFT JOIN quality_metrics qm ON vm.symbol = qm.symbol
                LEFT JOIN company_profile cp ON vm.symbol = cp.ticker
                LEFT JOIN positioning_metrics pm ON vm.symbol = pm.symbol
                WHERE vm.symbol = %s AND vm.symbol IS NOT NULL
                ORDER BY vm.symbol DESC
                LIMIT %s
            """,
                params=(sym, limit),
                timeout_sec=5,
            )
            freshness = check_data_freshness(cur, "value_metrics", "created_at", warning_days=7)
            result = list_response(
                [safe_json_serialize(dict(r)) for r in rows] if rows else [],
                data_freshness=freshness,
            )
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("financials/key-metrics", result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return cast(dict[str, Any], error_response(500, "response_validation_error", error_msg))
            return result

        if endpoint == "income-statement":
            if period == "quarterly":
                income_query = """
                    SELECT * FROM quarterly_income_statement
                    WHERE symbol = %s ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT %s
                """
            else:
                income_query = """
                    SELECT * FROM annual_income_statement
                    WHERE symbol = %s ORDER BY fiscal_year DESC LIMIT %s
                """
            rows = execute_with_timeout(cur, income_query, params=(sym, limit), timeout_sec=5)
            table_name = "quarterly_income_statement" if period == "quarterly" else "annual_income_statement"
            freshness = check_data_freshness(cur, table_name, "fiscal_year", warning_days=30)
            result = list_response(
                [safe_json_serialize(dict(r)) for r in rows] if rows else [],
                data_freshness=freshness,
            )
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("financials/income-statement", result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return cast(dict[str, Any], error_response(500, "response_validation_error", error_msg))
            return result

        if endpoint == "balance-sheet":
            if period == "quarterly":
                balance_query = """
                    SELECT * FROM quarterly_balance_sheet
                    WHERE symbol = %s ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT %s
                """
            else:
                balance_query = """
                    SELECT * FROM annual_balance_sheet
                    WHERE symbol = %s ORDER BY fiscal_year DESC LIMIT %s
                """
            rows = execute_with_timeout(cur, balance_query, params=(sym, limit), timeout_sec=5)
            table_name = "quarterly_balance_sheet" if period == "quarterly" else "annual_balance_sheet"
            freshness = check_data_freshness(cur, table_name, "fiscal_year", warning_days=30)
            result = list_response(
                [safe_json_serialize(dict(r)) for r in rows] if rows else [],
                data_freshness=freshness,
            )
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("financials/balance-sheet", result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return cast(dict[str, Any], error_response(500, "response_validation_error", error_msg))
            return result

        if endpoint == "cash-flow":
            if period == "quarterly":
                rows = execute_with_timeout(
                    cur,
                    """
                    SELECT * FROM quarterly_cash_flow
                    WHERE symbol = %s ORDER BY fiscal_year DESC, fiscal_quarter DESC LIMIT %s
                """,
                    (sym, limit),
                    timeout_sec=5,
                )
            else:
                rows = execute_with_timeout(
                    cur,
                    """
                    SELECT * FROM annual_cash_flow
                    WHERE symbol = %s ORDER BY fiscal_year DESC LIMIT %s
                """,
                    (sym, limit),
                    timeout_sec=5,
                )
            table_name = "quarterly_cash_flow" if period == "quarterly" else "annual_cash_flow"
            freshness = check_data_freshness(cur, table_name, "fiscal_year", warning_days=30)
            result = list_response(
                [safe_json_serialize(dict(r)) for r in rows] if rows else [],
                data_freshness=freshness,
            )
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("financials/cash-flow", result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return cast(dict[str, Any], error_response(500, "response_validation_error", error_msg))
            return result

        return cast(dict[str, Any], error_response(404, "not_found", f"No financials handler for {path}"))
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle financials")
        return cast(dict[str, Any], error_response(code, error_type, message))
