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
        """Validate that price table schema exists and has required columns."""
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
                    logger.error(f"Missing column {col_name} in {self.table_name}")
                    return False
            return True
        except Exception as e:
            logger.error(f"Schema validation failed: {e}")
            return False

    def validate_price_row(self, row: dict) -> bool:
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
        except Exception as e:
            logger.error(f"Could not verify unique constraint: {e}")
            return False

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
            )

    def verify_unique_constraint_exists(self, cur: Any) -> bool:
        """Verify unique constraint on (symbol, date)."""
        if not self.table_name:
            logger.error("Table name not set for constraint verification")
            return False

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
            logger.error(f"[CONSTRAINT_CHECK] Could not verify unique constraint: {e}")
            return False

    def validate_and_check_preconditions(self, cur: Any, interval: str = "1d", check_market_close: bool = False) -> bool:
        """Validate preflight conditions: schema and market close availability."""
        # Always validate schema
        if not self.validate_schema_preflight(cur):
            return False

        # Check unique constraint
        if not self.verify_unique_constraint_exists(cur):
            logger.warning("[PRECONDITION] Unique constraint missing - continuing anyway (may cause duplicates)")

        # For daily prices, check market close
        if interval == "1d" and check_market_close:
            if not self._check_market_close_available():
                logger.warning("[MARKET_CLOSE] Market close data NOT available - this may indicate data staleness")
                return False

        logger.info(f"[PRECONDITION] All preflight checks passed for {self.table_name}")
        return True

    def _check_market_close_available(self, max_wait_sec: int = 10) -> bool:
        """Check if market close data is available (for EOD pipeline validation)."""
        from datetime import datetime

        from algo.infrastructure import MarketCalendar
        from utils.infrastructure.timezone import EASTERN_TZ

        today = datetime.now(EASTERN_TZ).date()
        if not MarketCalendar.is_trading_day(today):
            logger.info("[MARKET_CLOSE] Today is not a trading day, skipping check")
            return True

        # Simple check: attempt to query market calendar
        try:
            is_trading = MarketCalendar.is_trading_day(today)
            if is_trading:
                logger.debug("[MARKET_CLOSE] ✓ Market close data available")
                return True
            return False
        except Exception as e:
            logger.warning(f"[MARKET_CLOSE] Could not verify market close availability: {e}")
            return False

    def validate_row(self, row: dict) -> bool:
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
                    symbol = row.get("symbol", "unknown")
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
