"""Error handlers for Lambda API - delegates to shared utils.error_handlers.

Consolidates duplicate implementations into single source of truth to prevent
divergence (especially critical for sanitize_error_message PII handling).
"""

import sys
from pathlib import Path

# Add root directory to path to import shared utils
_root = str(Path(__file__).parent.parent.parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from utils.error_handlers import (
    classify_exception,
    extract_error_context,
    log_error_with_context,
    log_sanitizer,
    make_error_response,
    retry_with_backoff,
    sanitize_error_message,
)

__all__ = [
    "classify_exception",
    "extract_error_context",
    "log_error_with_context",
    "log_sanitizer",
    "make_error_response",
    "retry_with_backoff",
    "sanitize_error_message",
]
