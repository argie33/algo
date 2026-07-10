"""DEPRECATED: Use response_validators.py instead.

This module is kept for backward compatibility only.
All new code should import from response_validators.
"""

from response_validators import (
    DataUnavailableError,
    ResponseValidator,
    ValidationResult,
)

__all__ = [
    "DataUnavailableError",
    "ResponseValidator",
    "ValidationResult",
    "validate_critical_data",
    "validate_required_fields",
]


# Re-export for backward compatibility
def validate_critical_data(data, field_name):
    """Deprecated: Use ResponseValidator.validate_critical_data()."""
    return ResponseValidator.validate_critical_data(data, field_name)


def validate_required_fields(data, required_fields, context):
    """Deprecated: Use ResponseValidator.validate_required_fields()."""
    return ResponseValidator.validate_required_fields(data, required_fields, context)
