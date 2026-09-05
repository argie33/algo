"""Exception categorization helper for the API Lambda handler.

Split out of lambda_function.py (bloater decomposition, mechanical move, no behavior
change): maps caught exceptions to a client-facing error_type string.
"""

from __future__ import annotations


def categorize_error(e: Exception) -> str:
    """Categorize exception to return specific error_type for better debugging.

    Returns error_type string: 'database_error', 'auth_error', 'validation_error', 'import_error', or 'unknown_error'
    """
    error_class_name = type(e).__name__
    error_module = type(e).__module__ if hasattr(type(e), "__module__") else ""

    # Database errors
    if "psycopg2" in error_module or error_class_name in (
        "OperationalError",
        "DatabaseError",
    ):
        return "database_error"

    # Auth/JWT errors
    if "jwt" in error_module or error_class_name in (
        "ExpiredSignatureError",
        "InvalidTokenError",
    ):
        return "auth_error"

    # Validation errors
    if error_class_name == "ValueError":
        return "validation_error"

    # Import/initialization errors
    if error_class_name in ("ImportError", "ModuleNotFoundError", "AttributeError"):
        return "import_error"

    return "unknown_error"
