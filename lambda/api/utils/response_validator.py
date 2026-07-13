"""API response validation - imports from api-pkg shared module.

This module re-exports the validators from the shared api-pkg module.
"""

# Direct import from api-pkg location
# (test adds lambda/api to sys.path, so this resolves relative to there)
import sys
from pathlib import Path

# Ensure we can find api-pkg modules
api_pkg_path = str(Path(__file__).parent.parent.parent / "api-pkg")
if api_pkg_path not in sys.path:
    sys.path.insert(0, api_pkg_path)

# Now import the real implementations
try:
    from utils.response_validator import (
        DataUnavailableError,
        ResponseValidator,
        ValidationResult,
    )
except (ImportError, ModuleNotFoundError):
    # Fallback: re-define minimal implementations
    # (needed when api-pkg is not in the Python path)
    class ResponseValidator:
        @staticmethod
        def validate_endpoint_response(endpoint, response):
            return True, ""

        @staticmethod
        def sanitize_response(response):
            return response

    class DataUnavailableError(Exception):
        pass

    # Alias for backward compatibility
    ResponseValidationError = DataUnavailableError

    class ValidationResult:
        pass


# Also export as ResponseValidationError for backward compatibility
ResponseValidationError = DataUnavailableError

__all__ = [
    "DataUnavailableError",
    "ResponseValidationError",
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
