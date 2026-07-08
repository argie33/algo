"""Route: prices"""

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
    json_response,
    list_response,
    raise_api_error,
    safe_json_serialize,
    safe_limit,
)

from shared_contracts.response_validator import ResponseValidator
from utils.validation import DatabaseResultValidator

logger = logging.getLogger(__name__)

_TABLE_MAP = {
    "daily": "price_daily",
    "weekly": "price_weekly",
    "monthly": "price_monthly",
}
_ETF_TABLE_MAP = {
    "daily": "etf_price_daily",
    "weekly": "etf_price_weekly",
    "monthly": "etf_price_monthly",
}


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

        # /api/prices?symbols=AAPL,MSFT (simple query format - redirect to batch-history)
        if len(parts) == 3 and parts[2] in ["prices", "prices?symbols"]:
            symbols_raw = extract_param(params, "symbols", required=False, default="")
            if symbols_raw:
                # Delegate to batch-history handler logic
                symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
                if not symbols:
                    return error_response(400, "bad_request", "symbols parameter required")
                if len(symbols) > 20:
                    return error_response(400, "bad_request", "maximum 20 symbols per batch")
                for sym in symbols:
                    if not all(c.isalnum() or c in ("-", ".", "^") for c in sym):
                        return error_response(400, "bad_request", f"Invalid symbol: {sym}")

                limit = safe_limit(
                    extract_param(params, "limit", required=False),
                    max_val=252,
                    default=30,
                )
                timeframe = extract_param(params, "timeframe", required=False, default="daily")
                table_name = _TABLE_MAP.get(timeframe or "daily", "price_daily")
                etf_table_name = _ETF_TABLE_MAP.get(timeframe or "daily", "etf_price_daily")

                result: dict[str, Any] = {sym: [] for sym in symbols}

                batch_query = psycopg2.sql.SQL("""
                    WITH ranked AS (
                        SELECT symbol, date, open, high, low, close, volume,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                        FROM {}
                        WHERE symbol = ANY(%s)
                    )
                    SELECT symbol, date, open, high, low, close, volume
                    FROM ranked
                    WHERE rn <= %s
                    ORDER BY symbol, date DESC
                """).format(psycopg2.sql.Identifier(table_name))
                rows = execute_with_timeout(cur, batch_query, [symbols, limit], timeout_sec=20)

                # Validate rows is not None and not empty — fail fast if validation fails
                if not DatabaseResultValidator.validate_rows_not_empty(rows, "prices batch query"):
                    raise_api_error(
                        503,
                        "ServiceUnavailable",
                        "Price data validation failed; prices batch query returned invalid data",
                    )

                found_symbols = set()
                skipped_rows = []
                for row in rows:
                    # Validate row is not None before accessing
                    if row is None:
                        logger.error("NULL row in prices batch query result")
                        skipped_rows.append({"reason": "null_row"})
                        continue

                    # Safely extract symbol
                    sym = row.get("symbol")
                    if not sym:
                        logger.error("Row missing symbol in prices batch query")
                        skipped_rows.append({"reason": "missing_symbol"})
                        continue

                    result[sym].append(safe_json_serialize(dict(row)))
                    found_symbols.add(sym)

                # Calculate data completeness
                total_rows = len(rows) + len(skipped_rows)
                data_completeness_pct = round((len(rows) / total_rows * 100) if total_rows > 0 else 0, 1)
                if data_completeness_pct < 100:
                    logger.warning(
                        f"[PRICE DATA] Data completeness: {data_completeness_pct}% "
                        f"({len(rows)}/{total_rows} rows valid, {len(skipped_rows)} skipped)"
                    )

                missing = [s for s in symbols if s not in found_symbols]
                if missing:
                    etf_query = psycopg2.sql.SQL("""
                        WITH ranked AS (
                            SELECT symbol, date, open, high, low, close, volume,
                                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                            FROM {}
                            WHERE symbol = ANY(%s)
                        )
                        SELECT symbol, date, open, high, low, close, volume
                        FROM ranked
                        WHERE rn <= %s
                        ORDER BY symbol, date DESC
                    """).format(psycopg2.sql.Identifier(etf_table_name))
                    etf_rows = execute_with_timeout(cur, etf_query, [missing, limit], timeout_sec=20)

                    # Validate ETF rows — fail fast if validation fails
                    if not DatabaseResultValidator.validate_rows_not_empty(etf_rows, "prices ETF query"):
                        raise_api_error(
                            503,
                            "ServiceUnavailable",
                            "ETF price data validation failed; prices ETF query returned invalid data",
                        )

                    null_count = 0
                    for row in etf_rows:
                        # CRITICAL: NULL rows indicate data corruption or query error
                        if row is None:
                            null_count += 1
                            continue

                        # Safely extract symbol
                        sym = row.get("symbol")
                        if not sym:
                            logger.warning("Row missing symbol in prices ETF query")
                            null_count += 1
                            continue

                        result[sym].append(safe_json_serialize(dict(row)))

                    # Validate data completeness - if we skipped rows, data is incomplete
                    if null_count > 0:
                        logger.critical(
                            f"[PRICES] ETF query returned {null_count} NULL/invalid rows. "
                            f"Data is incomplete and cannot be used for trading decisions."
                        )
                        raise_api_error(
                            503,
                            "incomplete_data",
                            f"ETF price data incomplete - {null_count} NULL rows in result",
                        )

                price_result = {"symbols": result, "limit": limit}

                # CRITICAL: Fail-fast on incomplete price data
                if "data_completeness_pct" in locals():
                    price_result["data_completeness_pct"] = data_completeness_pct
                    if data_completeness_pct < 100:
                        logger.error(f"[PRICES_API] Incomplete price data ({data_completeness_pct:.1f}%)")
                        return error_response(
                            503,
                            "incomplete_price_data",
                            f"Price data only {data_completeness_pct:.0f}% complete. Cannot use incomplete price history for position sizing.",
                        )

                is_valid, error_msg = ResponseValidator.validate_endpoint_response("prices", price_result)
                if not is_valid:
                    logger.error(f"Endpoint response validation failed: {error_msg}")
                    return error_response(500, "response_validation_error", error_msg)
                return json_response(200, price_result)
            else:
                return error_response(400, "bad_request", "symbols parameter required")

        # /api/prices/history/{symbol}
        if len(parts) >= 5 and parts[3] == "history":
            symbol = parts[4].upper()
            if not symbol or not all(c.isalnum() or c in ("-", ".", "^") for c in symbol):
                return error_response(400, "bad_request", "Invalid symbol")

            limit = safe_limit(
                extract_param(params, "limit", required=False),
                max_val=2000,
                default=252,
            )
            timeframe = extract_param(params, "timeframe", required=False, default="daily")
            days_str = extract_param(params, "days", required=False)

            table_name = _TABLE_MAP.get(timeframe or "daily", "price_daily")

            where_clause = "symbol = %s"
            qparams = [symbol]

            if days_str:
                try:
                    days_int = max(1, min(int(days_str), 3650))
                    where_clause += f" AND date >= CURRENT_DATE - INTERVAL '{days_int} days'"
                except ValueError:
                    logger.debug(f"Invalid days parameter: {days_str}, ignoring date filter")

            # Query stock price table first; fall back to ETF table if no results
            etf_table_name = _ETF_TABLE_MAP.get(timeframe or "daily", "etf_price_daily")
            query = psycopg2.sql.SQL("""
                SELECT date, open, high, low, close, volume
                FROM {}
                WHERE {}
                ORDER BY date DESC
                LIMIT %s
            """).format(psycopg2.sql.Identifier(table_name), psycopg2.sql.SQL(where_clause))
            rows = execute_with_timeout(cur, query, [*qparams, limit], timeout_sec=10)
            used_table = table_name
            asset_class_mismatch = False
            if not rows:
                # No data in stock table — try ETF table
                etf_query = psycopg2.sql.SQL("""
                    SELECT date, open, high, low, close, volume
                    FROM {}
                    WHERE {}
                    ORDER BY date DESC
                    LIMIT %s
                """).format(
                    psycopg2.sql.Identifier(etf_table_name),
                    psycopg2.sql.SQL(where_clause),
                )
                rows = execute_with_timeout(cur, etf_query, [*qparams, limit], timeout_sec=10)
                if rows:
                    # CRITICAL: We found ETF data but stock data was requested
                    asset_class_mismatch = True
                    logger.warning(
                        f"[PRICES_API] Fallback to ETF data for {symbol}: requested stock data unavailable. "
                        f"Returning ETF price history instead."
                    )
                used_table = etf_table_name

                if not rows:
                    # Symbol not found in either table OR no data for requested date range
                    # Check if symbol exists at all (distinguishes 'symbol not loaded' from 'no data for dates')
                    check_query = psycopg2.sql.SQL("SELECT COUNT(*) FROM {} WHERE symbol = %s").format(
                        psycopg2.sql.Identifier(table_name)
                    )
                    cur.execute(check_query, (symbol,))
                    stock_row = cur.fetchone()
                    stock_count = stock_row[0] if stock_row else 0

                    check_etf_query = psycopg2.sql.SQL("SELECT COUNT(*) FROM {} WHERE symbol = %s").format(
                        psycopg2.sql.Identifier(etf_table_name)
                    )
                    cur.execute(check_etf_query, (symbol,))
                    etf_row = cur.fetchone()
                    etf_count = etf_row[0] if etf_row else 0

                    symbol_exists = (stock_count + etf_count) > 0

                    if not symbol_exists:
                        # Symbol has never been loaded into price database
                        return error_response(
                            503,
                            "no_data_available",
                            f"Price data not available for {symbol}. Symbol may not be loaded yet or not covered.",
                        )
                    # Symbol exists but no data for this date range — valid empty result

            # CRITICAL: Fail-fast when asset class doesn't match (stock requested, ETF returned)
            if asset_class_mismatch:
                return error_response(
                    503,
                    "asset_class_mismatch",
                    f"Requested stock prices unavailable for {symbol}. ETF data available instead (different asset class). "
                    f"Cannot use ETF pricing for position sizing. Fail-fast: data type mismatch.",
                )

            freshness = check_data_freshness(cur, used_table, "date", warning_days=1)
            result = list_response(
                [safe_json_serialize(dict(r)) for r in rows] if rows else [],
                data_freshness=freshness,
            )
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("prices", result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return error_response(500, "response_validation_error", error_msg)
            return result

        # /api/prices/batch-history?symbols=SPY,QQQ,IWM&limit=30&timeframe=daily
        # Returns {symbols: {SYM: [{date, open, high, low, close, volume}, ...]}}
        # Replaces N concurrent per-symbol calls with one batch query.
        elif len(parts) >= 4 and parts[3] == "batch-history":
            # HIGH-007 FIX: Remove redundant OR fallback — extract_param already uses default=""
            symbols_raw = extract_param(params, "symbols", required=False, default="")
            assert isinstance(symbols_raw, str), f"Expected str, got {type(symbols_raw).__name__}"
            symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
            if not symbols:
                return error_response(400, "bad_request", "symbols parameter required")
            if len(symbols) > 20:
                return error_response(400, "bad_request", "maximum 20 symbols per batch")
            for sym in symbols:
                if not all(c.isalnum() or c in ("-", ".", "^") for c in sym):
                    return error_response(400, "bad_request", f"Invalid symbol: {sym}")

            limit = safe_limit(
                extract_param(params, "limit", required=False),
                max_val=252,
                default=30,
            )
            timeframe = extract_param(params, "timeframe", required=False, default="daily")
            table_name = _TABLE_MAP.get(timeframe or "daily", "price_daily")
            etf_table_name = _ETF_TABLE_MAP.get(timeframe or "daily", "etf_price_daily")

            result3: dict[str, Any] = {sym: [] for sym in symbols}

            batch_query = psycopg2.sql.SQL("""
                WITH ranked AS (
                    SELECT symbol, date, open, high, low, close, volume,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM {}
                    WHERE symbol = ANY(%s)
                )
                SELECT symbol, date, open, high, low, close, volume
                FROM ranked
                WHERE rn <= %s
                ORDER BY symbol, date DESC
            """).format(psycopg2.sql.Identifier(table_name))
            rows = execute_with_timeout(cur, batch_query, [symbols, limit], timeout_sec=20)
            if not DatabaseResultValidator.validate_rows_not_empty(rows, "prices batch-history query"):
                raise_api_error(
                    503,
                    "ServiceUnavailable",
                    "Price data validation failed; prices batch-history query returned invalid data",
                )
            # FAIL-FAST: Extract symbol with safe validation in batch processing
            found_symbols = set()
            for row in rows:
                sym_raw = DatabaseResultValidator.safe_get_str(row, "symbol", strict=True)
                if sym_raw is None:
                    raise RuntimeError(
                        "BUG: safe_get_str with strict=True returned None. "
                        "This indicates data corruption or validation bypass."
                    )
                # After above check, sym_raw is narrowed to str
                result3[sym_raw].append(safe_json_serialize(dict(row)))
                found_symbols.add(sym_raw)

            missing = [s for s in symbols if s not in found_symbols]
            if missing:
                etf_query = psycopg2.sql.SQL("""
                    WITH ranked AS (
                        SELECT symbol, date, open, high, low, close, volume,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                        FROM {}
                        WHERE symbol = ANY(%s)
                    )
                    SELECT symbol, date, open, high, low, close, volume
                    FROM ranked
                    WHERE rn <= %s
                    ORDER BY symbol, date DESC
                """).format(psycopg2.sql.Identifier(etf_table_name))
                etf_rows = execute_with_timeout(cur, etf_query, [missing, limit], timeout_sec=20)
                if etf_rows:
                    for row in etf_rows:
                        # FAIL-FAST: Extract symbol with safe validation in ETF batch processing
                        sym_raw = DatabaseResultValidator.safe_get_str(row, "symbol", strict=True)
                        if sym_raw is None:
                            raise RuntimeError(
                                "BUG: safe_get_str with strict=True returned None. "
                                "This indicates data corruption or validation bypass."
                            )
                        # After above check, sym_raw is narrowed to str
                        result3[sym_raw].append(safe_json_serialize(dict(row)))

            batch_result = {"symbols": result3, "limit": limit}
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("prices", batch_result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return error_response(500, "response_validation_error", error_msg)
            return json_response(200, batch_result)

        return error_response(404, "not_found", f"No prices handler for {path}")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle prices")
        return error_response(code, error_type, message)
