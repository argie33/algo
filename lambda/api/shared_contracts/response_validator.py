"""DEPRECATED: Use utils/response_validator.py instead.

This module is kept for backward compatibility only.
All new code should import from response_validator directly.
"""

# Handle both relative and absolute imports
try:
    # Try relative import first (when used as part of lambda.api package)
    from ..utils.response_validator import (
        ResponseValidationError,
        ResponseValidator,
    )
except (ImportError, ValueError):
    # Fall back to absolute import (when lambda/api is in sys.path)
    from utils.response_validator import (
        ResponseValidationError,
        ResponseValidator,
    )

__all__ = [
    "ResponseValidationError",
    "ResponseValidator",
]
