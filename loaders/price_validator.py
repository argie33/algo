#!/usr/bin/env python3
"""PriceValidator specialist - handles validation rules and data quality checks.

Extracted from PriceLoader to eliminate God Object code smell.
Responsibility: Validate price data quality, schema, and constraints.
"""

import logging
from typing import Any

import psycopg2

logger = logging.getLogger(__name__)


class PriceValidator:
    """Specialist for validating price data.

    Handles:
    - Price tick validation (OHLCV correctness)
    - Schema validation
    - Unique constraint checking
    - Data quality assertions
    """

    def __init__(self, table_name: str = "", asset_class: str = "stock"):
        """Initialize PriceValidator."""
        self.table_name = table_name
        self.asset_class = asset_class
        self.validation_rules = {
            "close_required": True,
            "date_required": True,
            "symbol_required": True,
            "volume_non_negative": True,
            "ohlc_reasonable": True,  # High >= Low, Close between them
        }

    def validate_schema(self, cur: Any) -> bool:
        """Validate that price table schema exists and has required columns.

        CRITICAL: Raises RuntimeError on schema validation failure (fail-fast).
        Missing schema columns indicate incomplete database setup and will corrupt
        all downstream price processing (technical indicators, P&L calculations).
        """
        required_columns = {
            "symbol": "text",
            "date": "date",
            "open": "numeric",
            "high": "numeric",
            "low": "numeric",
            "close": "numeric",
            "volume": "bigint",
        }

        try:
            for col_name in required_columns:
                query = "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s"
                cur.execute(query, (self.table_name, col_name))
                if not cur.fetchone():
                    msg = (
                        f"[SCHEMA_VALIDATION] Missing column {col_name} in {self.table_name}. "
                        "Cannot load prices without complete schema. "
                        "Verify database schema creation and migration status."
                    )
                    logger.error(msg)
                    raise RuntimeError(msg)
            return True
        except psycopg2.Error as e:
            msg = (
                f"[SCHEMA_VALIDATION] Schema validation failed for {self.table_name}: {e}. "
                "Cannot proceed with data load until database is accessible."
            )
            logger.error(msg)
            raise RuntimeError(msg) from e

    def validate_price_row(self, row: dict[str, Any]) -> bool:
        """Validate a single price row."""
        # Check required fields
        if self.validation_rules.get("close_required") and row.get("close") is None:
            return False
        if self.validation_rules.get("date_required") and row.get("date") is None:
            return False
        if self.validation_rules.get("symbol_required") and row.get("symbol") is None:
            return False

        # Check OHLC reasonableness
        if self.validation_rules.get("ohlc_reasonable"):
            close = row.get("close")
            high = row.get("high")
            low = row.get("low")

            if close is not None and high is not None and low is not None:
                if not (low <= close <= high):
                    logger.warning(f"Price out of range for {row.get('symbol')}: close={close}, high={high}, low={low}")
                    return False
                if not (high >= low):
                    return False

        # Check volume non-negative
        if self.validation_rules.get("volume_non_negative"):
            volume = row.get("volume")
            if volume is not None and volume < 0:
                return False

        return True

    def verify_unique_constraint(self, cur: Any, table_name: str) -> bool:
        """Verify unique constraint on (symbol, date)."""
        try:
            constraint_query = """
                SELECT constraint_name FROM information_schema.constraint_column_usage
                WHERE table_name = %s AND column_name IN ('symbol', 'date')
                AND constraint_type = 'UNIQUE'
            """
            cur.execute(constraint_query, (table_name,))
            return bool(cur.fetchone())
        except psycopg2.Error as e:
            msg = f"[CONSTRAINT_CHECK] Failed to verify unique constraint on {table_name}: {e}. Cannot proceed without knowing constraints exist."
            logger.error(msg)
            raise RuntimeError(msg) from e

    def set_table_name(self, table_name: str) -> None:
        """Set the table name for schema validation."""
        self.table_name = table_name

    def validate_schema_preflight(self, cur: Any) -> bool:
        """Validate that price table schema exists and has required columns."""
        if not self.table_name:
            logger.error("Table name not set for schema validation")
            return False

        required_columns = {
            "symbol": "text",
            "date": "date",
            "open": "numeric",
            "high": "numeric",
            "low": "numeric",
            "close": "numeric",
            "volume": "bigint",
        }

        try:
            for col_name in required_columns:
                query = "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s"
                cur.execute(query, (self.table_name, col_name))
                if not cur.fetchone():
                    logger.error(f"[SCHEMA_VALIDATION] Missing column {col_name} in {self.table_name}")
                    raise RuntimeError(
                        f"[SCHEMA_VALIDATION] Table {self.table_name} missing required column {col_name}. "
                        "Cannot load prices without proper schema."
                    )
            logger.debug(f"[SCHEMA_VALIDATION] ✓ Schema validation passed for {self.table_name}")
            return True
        except psycopg2.Error as e:
            logger.error(f"[SCHEMA_VALIDATION] Schema validation failed: {e}")
            raise RuntimeError(
                f"[SCHEMA_VALIDATION] Failed to validate schema for {self.table_name}: {e}. "
                "Cannot proceed with data load."
            ) from e

    def verify_unique_constraint_exists(self, cur: Any) -> bool:
        """Verify unique constraint on (symbol, date).

        CRITICAL: Raises RuntimeError on database errors (fail-fast).
        Returns False only if schema check shows constraint is actually missing.
        Database errors are NOT the same as missing constraints.
        """
        if not self.table_name:
            msg = "Table name not set for constraint verification"
            logger.error(msg)
            raise RuntimeError(msg)

        try:
            constraint_query = """
                SELECT constraint_name FROM information_schema.constraint_column_usage
                WHERE table_name = %s AND column_name IN ('symbol', 'date')
                AND constraint_type = 'UNIQUE'
            """
            cur.execute(constraint_query, (self.table_name,))
            constraint_exists = bool(cur.fetchone())
            if not constraint_exists:
                logger.warning(f"[CONSTRAINT_CHECK] No unique constraint found on {self.table_name}(symbol, date)")
            return constraint_exists
        except psycopg2.Error as e:
            msg = (
                f"[CONSTRAINT_CHECK] Failed to verify constraint on {self.table_name}: {e}. "
                "Database error (not missing constraint). Check database connectivity and permissions."
            )
            logger.error(msg)
            raise RuntimeError(msg) from e

    def validate_and_check_preconditions(
        self, cur: Any, interval: str = "1d", check_market_close: bool = False
    ) -> bool:
        """Validate preflight conditions: schema and market close availability."""
        # Always validate schema
        if not self.validate_schema_preflight(cur):
            return False

        # Check unique constraint - CRITICAL: must exist to prevent duplicate prices
        if not self.verify_unique_constraint_exists(cur):
            raise RuntimeError(
                f"[PRECONDITION FAILED] Unique constraint missing on {self.table_name}. "
                "Cannot load prices without uniqueness guarantee. "
                "Duplicate prices would corrupt all technical indicators and P&L calculations. "
                "Verify database schema and constraint creation."
            )

        # For daily prices, market close data is mandatory (fail-fast on stale data)
        if interval == "1d" and check_market_close:
            if not self._check_market_close_available():
                msg = (
                    "[MARKET_CLOSE] Daily price loader requires market close data. Data appears stale. Cannot proceed."
                )
                logger.error(msg)
                raise RuntimeError(msg)

        logger.info(f"[PRECONDITION] All preflight checks passed for {self.table_name}")
        return True

    def _check_market_close_available(self, max_wait_sec: int = 10) -> bool:
        from datetime import datetime

        from algo.infrastructure import MarketCalendar
        from utils.infrastructure.timezone import EASTERN_TZ

        today = datetime.now(EASTERN_TZ).date()
        if not MarketCalendar.is_trading_day(today):
            logger.info("[MARKET_CLOSE] Today is not a trading day, skipping check")
            return True

        try:
            is_trading = MarketCalendar.is_trading_day(today)
            if is_trading:
                logger.debug("[MARKET_CLOSE] ✓ Market close data available")
                return True
            return False
        except (ValueError, AttributeError, TypeError) as e:
            logger.warning(f"[MARKET_CLOSE] Market calendar lookup failed (expected for non-trading days): {e}")
            return False
        except Exception as e:
            msg = f"[MARKET_CLOSE] Unexpected error checking market calendar: {e}. Cannot proceed without calendar access."
            logger.error(msg)
            raise RuntimeError(msg) from e

    def validate_row(self, row: dict[str, Any]) -> bool:
        """Validate a single price row for quality."""
        if not row:
            return False

        # Check required fields
        if self.validation_rules.get("symbol_required") and not row.get("symbol"):
            return False
        if self.validation_rules.get("date_required") and not row.get("date"):
            return False
        if self.validation_rules.get("close_required") and row.get("close") is None:
            return False

        # Check OHLC reasonableness
        if self.validation_rules.get("ohlc_reasonable"):
            close = row.get("close")
            high = row.get("high")
            low = row.get("low")

            if close is not None and high is not None and low is not None:
                if not (low <= close <= high):
                    # CRITICAL: Validate symbol field exists for audit (fail-fast if missing)
                    symbol = row.get("symbol")
                    if symbol is None:
                        raise ValueError(
                            f"[VALIDATOR] Row with out-of-range prices missing required 'symbol' field. "
                            f"Cannot identify which symbol had validation failure. Row: {row}"
                        )
                    logger.debug(f"[{symbol}] Price out of range: close={close}, high={high}, low={low}")
                    return False
                if not (high >= low):
                    return False

        # Check volume non-negative
        if self.validation_rules.get("volume_non_negative"):
            volume = row.get("volume")
            if volume is not None and volume < 0:
                return False

        return True
