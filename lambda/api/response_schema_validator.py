#!/usr/bin/env python3
"""Response Schema Validator - Runtime schema validation."""

from typing import Any


class SchemaValidator:
    """Runtime schema validation for API responses."""

    SCHEMAS = {
        "market/status": {
            "required": ["date", "market_trend", "market_stage", "vix_level"],
            "types": {"date": str, "vix_level": float, "market_stage": int}
        },
        "portfolio": {
            "required": ["value", "cash", "positions", "unrealized_pnl"],
            "types": {"value": float, "cash": float, "positions": int}
        },
    }

    @staticmethod
    def validate(endpoint: str, data: dict[str, Any]) -> tuple[bool, str]:
        """Validate response against schema."""
        schema = SchemaValidator.SCHEMAS.get(endpoint)
        if not schema:
            return True, ""

        required = schema.get("required", [])
        missing = set(required) - set(data.keys())

        if missing:
            return False, f"Missing fields: {missing}"
        return True, ""
