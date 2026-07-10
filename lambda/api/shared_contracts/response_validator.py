"""DEPRECATED: Use lambda/api/utils/response_validators.py instead.

This module is kept for backward compatibility only.
All new code should import from response_validators.
"""

from ..utils.response_validators import (
    ResponseValidationError,
    ResponseValidator,
)

__all__ = [
    "ResponseValidator",
    "ResponseValidationError",
]
