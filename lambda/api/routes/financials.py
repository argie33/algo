"""Route: financials"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    error_response,
    execute_with_timeout,
    extract_param,
    handle_db_error,
    list_response,
    safe_json_serialize,
    safe_limit,
    success_response,
)

from shared_contracts.response_validator import ResponseValidator

logger = logging.getLogger(__name__)


def handle(  # noqa: C901
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    try:
        parts = path.split("/")
        symbol = parts[3] if len(parts) > 3 else None
        endpoint = parts[4] if len(parts) > 4 else None

        if not symbol:
            return error_response(400, "bad_request", "Symbol required")

        sym = symbol.upper()
        # Extract period from params list (default to "annual" if not provided)
        period = None
        if params and params.get("period"):
            period_list = params["period"]
            if period_list:
                period = period_list[0]
        if not period:
            period = "annual"
        limit = safe_limit(extract_param(params, "limit"), max_val=40, default=8)

        if endpoint == "key-metrics":
            rows = execute_with_timeout(
                cur,
                """
                SELECT
                    vm.symbol,
                    CURRENT_DATE AS date,
                    vm.market_cap,
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
                    pm.insider_ownership_pct AS held_percent_insiders,
                    pm.institutional_ownership_pct AS held_percent_institutions
                FROM value_metrics vm
                LEFT JOIN quality_metrics qm ON vm.symbol = qm.symbol
                LEFT JOIN company_profile cp ON vm.symbol = cp.symbol
                LEFT JOIN positioning_metrics pm ON vm.symbol = pm.symbol
                WHERE vm.symbol = %s AND vm.symbol IS NOT NULL
                ORDER BY vm.symbol DESC
                LIMIT %s
            """,
                params=(sym, limit),
                timeout_sec=5,
            )
            freshness = check_data_freshness(cur, "value_metrics", "created_at", warning_days=7)
            if not rows:
                return error_response(
                    503,
                    "data_unavailable",
                    f"Financial metrics not available for {sym}. "
                    f"value_metrics loader may not have run or data is stale. {freshness}",
                )
            result = list_response(
                [safe_json_serialize(dict(r)) for r in rows],
                data_freshness=freshness,
            )
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("financials/key-metrics", result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                if error_msg:
                    return error_response(500, "response_validation_error", error_msg)
                else:
                    logger.error("[CRITICAL] Key metrics validation failed but error_msg is None. Bug.")
                    return error_response(
                        500, "response_validation_error", "Key metrics validation failed (internal error: no message)"
                    )
            return result

        if endpoint == "ownership":
            # BUG FOUND 2026-08-10 (frontend/dashboard audit pass): StockDetail.jsx's
            # StatsTab has called this exact path since it was written, but this handler
            # never existed - every stock detail page load 404'd on it, permanently leaving
            # Insider Ownership/Insiders/Recent Buys/Segment Count/Concentration HHI/
            # Diversified blank ("--") site-wide, even though both source tables
            # (insider_holdings_sec, sec_segment_metrics) are populated and fresh.
            rows = execute_with_timeout(
                cur,
                """
                SELECT
                    ih.insider_ownership_pct,
                    ih.number_of_insiders,
                    ih.recent_buys,
                    ih.recent_sells,
                    ih.net_insider_transactions,
                    ih.latest_insider_filing_date,
                    sm.segment_count,
                    sm.largest_segment_revenue_pct,
                    sm.revenue_concentration_hhi,
                    sm.is_diversified
                FROM (SELECT %s::text AS symbol) req
                LEFT JOIN insider_holdings_sec ih ON ih.symbol = req.symbol AND ih.data_unavailable = false
                LEFT JOIN sec_segment_metrics sm ON sm.symbol = req.symbol AND sm.data_unavailable = false
                """,
                params=(sym,),
                timeout_sec=5,
            )
            # The constant-subquery LEFT JOIN always returns exactly 1 row (all-NULL fields
            # if neither source table has this symbol) - the frontend already renders "--"
            # for each null field individually, so there is no "no data" error case here.
            return success_response(safe_json_serialize(dict(rows[0])))

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
            if not rows:
                return error_response(
                    503,
                    "data_unavailable",
                    f"No {period} income statement found for {sym}. "
                    f"{table_name} loader may not have run or data is stale. {freshness}",
                )
            result = list_response(
                [safe_json_serialize(dict(r)) for r in rows],
                data_freshness=freshness,
            )
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("financials/income-statement", result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                if error_msg:
                    return error_response(500, "response_validation_error", error_msg)
                else:
                    logger.error("[CRITICAL] Income statement validation failed but error_msg is None. Bug.")
                    return error_response(
                        500,
                        "response_validation_error",
                        "Income statement validation failed (internal error: no message)",
                    )
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
            if not rows:
                return error_response(
                    503,
                    "data_unavailable",
                    f"No {period} balance sheet found for {sym}. "
                    f"{table_name} loader may not have run or data is stale. {freshness}",
                )
            result = list_response(
                [safe_json_serialize(dict(r)) for r in rows],
                data_freshness=freshness,
            )
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("financials/balance-sheet", result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                if error_msg:
                    return error_response(500, "response_validation_error", error_msg)
                else:
                    logger.error("[CRITICAL] Balance sheet validation failed but error_msg is None. Bug.")
                    return error_response(
                        500, "response_validation_error", "Balance sheet validation failed (internal error: no message)"
                    )
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
            if not rows:
                return error_response(
                    503,
                    "data_unavailable",
                    f"No {period} cash flow statement found for {sym}. "
                    f"{table_name} loader may not have run or data is stale. {freshness}",
                )
            result = list_response(
                [safe_json_serialize(dict(r)) for r in rows],
                data_freshness=freshness,
            )
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("financials/cash-flow", result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                if error_msg:
                    return error_response(500, "response_validation_error", error_msg)
                else:
                    logger.error("[CRITICAL] Cash flow validation failed but error_msg is None. Bug.")
                    return error_response(
                        500, "response_validation_error", "Cash flow validation failed (internal error: no message)"
                    )
            return result

        return error_response(404, "not_found", f"No financials handler for {path}")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle financials")
        return error_response(code, error_type, message)
