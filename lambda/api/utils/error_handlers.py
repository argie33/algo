"""Error handlers for Lambda API - delegates to shared utils.error_handlers.

Consolidates duplicate implementations into single source of truth to prevent
divergence (especially critical for sanitize_error_message PII handling).
"""

# Import from root utils package by path manipulation
import sys
from pathlib import Path

_root = Path(__file__).parent.parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Remove local utils from path to avoid shadowing
_local_utils = Path(__file__).parent
if str(_local_utils) in sys.path:
    sys.path.remove(str(_local_utils))

# Now import from root utils (not from local utils)
import utils.error_handlers as _root_error_handlers

classify_exception = _root_error_handlers.classify_exception
extract_error_context = _root_error_handlers.extract_error_context
log_error_with_context = _root_error_handlers.log_error_with_context
log_sanitizer = _root_error_handlers.log_sanitizer
make_error_response = _root_error_handlers.make_error_response
retry_with_backoff = _root_error_handlers.retry_with_backoff
sanitize_error_message = _root_error_handlers.sanitize_error_message

__all__ = [
    "classify_exception",
    "extract_error_context",
    "log_error_with_context",
    "log_sanitizer",
    "make_error_response",
    "retry_with_backoff",
    "sanitize_error_message",
]
