"""DEPRECATED: Use lambda/api/utils/response_validation_unified.py instead.

This module is kept for backward compatibility only.
All new code should import from response_validation_unified.
"""

from ..utils.response_validation_unified import (
    ResponseValidationError,
    ResponseValidator,
)

__all__ = [
    "ResponseValidator",
    "ResponseValidationError",
]
