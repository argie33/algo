#!/usr/bin/env python3
"""Trade Field Validator - Consolidate trade field handling and validation."""

from typing import Any


class TradeFieldValidator:
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
        missing = cls.REQUIRED_FIELDS - set(trade_data.keys())
        if missing:
            return False, f"Missing required fields: {missing}"

        # Validate field types (safe to use direct access since required fields already checked)
        if not isinstance(trade_data["symbol"], str):
            return False, "symbol must be string"
        shares = trade_data["shares"]
        if not isinstance(shares, int) or shares <= 0:
            return False, "shares must be positive integer"

        return True, ""

    @classmethod
    def validate_trade_exit(cls, trade_data: dict[str, Any]) -> tuple[bool, str]:
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
