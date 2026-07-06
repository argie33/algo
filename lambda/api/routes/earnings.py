"""Route: earnings"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
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
)

from shared_contracts.response_validator import ResponseValidator
from utils.validation import DatabaseResultValidator

logger = logging.getLogger(__name__)


def handle(
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

        if symbol:
            limit = safe_limit(
                extract_param(params, "limit"),
                max_val=200,
                default=20,
            )
            rows = execute_with_timeout(
                cur,
                """
                SELECT symbol,
                       earnings_date AS report_date,
                       CONCAT(fiscal_quarter, 'Q', fiscal_year) AS fiscal_period,
                       eps_actual, eps_estimate,
                       eps_surprise_pct AS eps_surprise,
                       revenue_actual, revenue_estimate,
                       revenue_surprise_pct AS revenue_surprise
                FROM earnings_history
                WHERE symbol = %s
                ORDER BY earnings_date DESC
                LIMIT %s
            """,
                (symbol.upper(), limit),
                timeout_sec=3,
            )

            # Validate rows — fail fast on validation failure
            if not DatabaseResultValidator.validate_rows_not_empty(rows, "earnings history query"):
                return error_response(
                    503,
                    "ServiceUnavailable",
                    "Earnings data validation failed; earnings history query returned invalid data",
                )

            freshness = check_data_freshness(cur, "earnings_history", "earnings_date", warning_days=7)
            result = list_response(
                [safe_json_serialize(dict(r)) for r in rows],
                data_freshness=freshness,
            )
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("earnings", result)
            if not is_valid:
                logger.error(f"Earnings response validation failed: {error_msg}")
                if error_msg:
                    return error_response(500, "response_validation_error", error_msg)
                else:
                    logger.error("[CRITICAL] Earnings validation failed but error_msg is None. Bug.")
                    return error_response(500, "response_validation_error", "Earnings validation failed (internal error: no message)")
            return result

        limit = safe_limit(
            extract_param(params, "limit"),
            max_val=1000,
            default=100,
        )
        rows = execute_with_timeout(
            cur,
            """
            SELECT symbol,
                   earnings_date AS report_date,
                   CONCAT(fiscal_quarter, 'Q', fiscal_year) AS fiscal_period,
                   eps_actual, eps_estimate,
                   eps_surprise_pct AS eps_surprise
            FROM earnings_history
            ORDER BY earnings_date DESC
            LIMIT %s
        """,
            (limit,),
            timeout_sec=5,
        )

        # Validate rows — fail fast on validation failure
        if not DatabaseResultValidator.validate_rows_not_empty(rows, "earnings all query"):
            return error_response(
                503,
                "ServiceUnavailable",
                "Earnings data validation failed; earnings all query returned invalid data",
            )

        freshness = check_data_freshness(cur, "earnings_history", "earnings_date", warning_days=7)
        result = list_response(
            [safe_json_serialize(dict(r)) for r in rows],
            data_freshness=freshness,
        )
        is_valid, error_msg = ResponseValidator.validate_endpoint_response("earnings", result)
        if not is_valid:
            logger.error(f"Earnings response validation failed: {error_msg}")
            if error_msg:
                return error_response(500, "response_validation_error", error_msg)
            else:
                logger.error("[CRITICAL] Earnings validation failed but error_msg is None. Bug.")
                return error_response(500, "response_validation_error", "Earnings validation failed (internal error: no message)")
        return result
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle earnings")
        return error_response(code, error_type, message)
