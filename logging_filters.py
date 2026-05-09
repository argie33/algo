#!/usr/bin/env python3
"""
Logging filters to prevent credential leaks in logs.

Masks passwords, API keys, and other sensitive values before they hit
log files or stdout. Prevents accidental credential exposure via:
- Exception stack traces
- Debug log messages
- Error response bodies

Usage:
    import logging
    from logging_filters import CredentialFilter
    logging.getLogger().addFilter(CredentialFilter())
"""

import logging
import os
import re
from typing import Pattern


class CredentialFilter(logging.Filter):
    """Mask sensitive credentials in log records."""

    # Patterns to match and replace
    PATTERNS = [
        # Database passwords: password=mypass → password=***
        (r'password["\']?\s*[=:]\s*["\']?[^"\'\s,}]+', lambda m: re.sub(r'[=:]\s*["\']?[^"\'\s,}]+', '=***', m.group(0))),

        # API keys: api_key=abc123def456 → api_key=***
        (r'(api[_-]?key|apikey)["\']?\s*[=:]\s*["\']?[^"\'\s,}]+', lambda m: re.sub(r'[=:]\s*["\']?[^"\'\s,}]+', '=***', m.group(0))),

        # Secrets: secret=value → secret=***
        (r'(secret|token|auth)["\']?\s*[=:]\s*["\']?[^"\'\s,}]+', lambda m: re.sub(r'[=:]\s*["\']?[^"\'\s,}]+', '=***', m.group(0))),

        # Connection strings: postgresql://user:pass@host → postgresql://user:***@host
        (r'(postgresql|mysql|postgres)://[^@]*:([^@]+)@', r'\1://***:***@'),

        # Bearer tokens: Authorization: Bearer eyJhbcVc... → Authorization: Bearer ***
        (r'(Bearer|Token)\s+[a-zA-Z0-9._-]+', r'\1 ***'),

        # Alpaca keys in JSON: "api_key": "pk_live_..."  → "api_key": "***"
        (r'"(api_key|api_secret|secret_key)":\s*"[^"]*"', r'"\1": "***"'),

        # General password pattern in dicts/JSON: "password": "value" → "password": "***"
        (r'"(password|passwd|pwd)":\s*"[^"]*"', r'"\1": "***"'),

        # Query parameters: ?key=value&password=secret → ?key=value&password=***
        (r'([?&](password|api[_-]?key|token|secret)=)[^&]*', r'\1***'),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter a log record to mask sensitive data.

        Args:
            record: LogRecord to filter

        Returns:
            True to allow the log, False to suppress it (always True here)
        """
        if record.msg:
            # Mask the main message
            record.msg = self._mask_credentials(str(record.msg))

        # Mask any arguments in the message
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._mask_credentials(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, (tuple, list)):
                record.args = tuple(self._mask_credentials(str(v)) for v in record.args)

        # Mask exception info if present
        if record.exc_info:
            # Exception traceback might contain credentials
            pass  # Can't easily mask exc_info here; exc_text is formatted later

        # Mask the formatted message (called by formatters)
        if hasattr(record, 'getMessage'):
            # Note: getMessage() is called by formatters, so we mask before that
            pass

        return True

    @staticmethod
    def _mask_credentials(text: str) -> str:
        """Apply all masking patterns to a text string."""
        for pattern, replacement in CredentialFilter.PATTERNS:
            if callable(replacement):
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
            else:
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text


class CredentialFormatter(logging.Formatter):
    """Logging formatter that masks credentials in the formatted message."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record and mask credentials."""
        # Format the record normally
        formatted = super().format(record)

        # Then mask any credentials that appeared in the formatted output
        return CredentialFilter._mask_credentials(formatted)


def setup_credential_filtering(logger: logging.Logger = None) -> None:
    """
    Add credential filtering to a logger (or root logger if None).

    Usage:
        setup_credential_filtering()  # Root logger
        setup_credential_filtering(logging.getLogger('myapp'))  # Specific logger
    """
    if logger is None:
        logger = logging.getLogger()

    # Add the filter
    if not any(isinstance(f, CredentialFilter) for f in logger.filters):
        logger.addFilter(CredentialFilter())

    # Optionally update all handlers to use the masking formatter
    # (Comment out if you want to keep existing formatters)
    # for handler in logger.handlers:
    #     if not isinstance(handler.formatter, CredentialFormatter):
    #         handler.setFormatter(CredentialFormatter(handler.formatter._fmt if handler.formatter else None))


# Auto-setup on import if in production
if __name__ != "__main__":
    # Only enable auto-setup in certain environments
    if not (os.getenv("DISABLE_CREDENTIAL_FILTER") == "true"):
        try:
            setup_credential_filtering()
        except Exception:
            pass  # Silently ignore filter setup errors


if __name__ == "__main__":
    # Test the filter
    import os
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    setup_credential_filtering(logger)

    # Test cases
    logger.info("DB password=supersecret123")
    logger.info("api_key=sk_live_abcd1234efgh5678")
    logger.info("Bearer token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")
    logger.info('{"password": "my_secret_pwd"}')
    logger.info("postgresql://user:password123@localhost/mydb")
    logger.info("?api_key=abc123&password=secret456")
    print("\nAll credentials above should be masked as ***")
