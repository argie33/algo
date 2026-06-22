#!/usr/bin/env python3
"""Trade Field Validator - Consolidate trade field handling and validation."""

from typing import Any


class TradeFieldValidator:
    """Validates and consolidates trade field handling."""

    REQUIRED_FIELDS = {
        "symbol",
        "entry_price",
        "shares",
        "stop_loss",
        "entry_time",
        "status",
        "trade_id",
    }

    OPTIONAL_FIELDS = {
        "exit_price",
        "exit_time",
        "pnl",
        "exit_shares",
        "stop_adjusted_at",
        "max_profit",
        "reason",
    }

    @classmethod
    def validate_trade_entry(cls, trade_data: dict[str, Any]) -> tuple[bool, str]:
        """Validate trade entry fields.

        Returns:
            (is_valid, error_message)
        """
        missing = cls.REQUIRED_FIELDS - set(trade_data.keys())
        if missing:
            return False, f"Missing required fields: {missing}"

        # Validate field types
        if not isinstance(trade_data.get("symbol"), str):
            return False, "symbol must be string"
        if not isinstance(trade_data.get("shares"), int) or trade_data["shares"] <= 0:
            return False, "shares must be positive integer"

        return True, ""

    @classmethod
    def validate_trade_exit(cls, trade_data: dict[str, Any]) -> tuple[bool, str]:
        """Validate trade exit fields."""
        if "exit_price" not in trade_data:
            return False, "exit_price required"
        if trade_data["exit_price"] <= 0:
            return False, "exit_price must be positive"

        return True, ""

    @classmethod
    def normalize_fields(cls, trade_data: dict[str, Any]) -> dict[str, Any]:
        """Normalize trade fields to standard format."""
        normalized = {}
        for field in cls.REQUIRED_FIELDS | cls.OPTIONAL_FIELDS:
            if field in trade_data:
                normalized[field] = trade_data[field]
        return normalized
