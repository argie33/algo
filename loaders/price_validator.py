#!/usr/bin/env python3
"""PriceValidator specialist - handles validation rules and data quality checks.

Extracted from PriceLoader to eliminate God Object code smell.
Responsibility: Validate price data quality, schema, and constraints.
"""

import logging
from typing import Any


logger = logging.getLogger(__name__)


class PriceValidator:
    """Specialist for validating price data.

    Handles:
    - Price tick validation (OHLCV correctness)
    - Schema validation
    - Unique constraint checking
    - Data quality assertions
    """

    def __init__(self):
        """Initialize PriceValidator."""
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
