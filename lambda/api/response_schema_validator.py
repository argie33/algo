"""DEPRECATED: Use lambda/api/utils/response_validators.py instead.

This module is kept for backward compatibility only.
All new code should import from response_validators.
"""

from utils.response_validators import ResponseValidator

# Re-export for backward compatibility
__all__ = ["ResponseValidator", "SchemaValidator"]


class SchemaValidator:
    """Deprecated: Use ResponseValidator.validate_schema() instead."""

    SCHEMAS = ResponseValidator.SCHEMAS

    @staticmethod
    def validate(endpoint: str, data: dict):
        """Deprecated: Use ResponseValidator.validate_schema()."""
        return ResponseValidator.validate_schema(endpoint, data)
