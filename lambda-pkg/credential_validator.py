#!/usr/bin/env python3
"""
Credential validation at startup.

Ensures all required credentials are present before the application runs.
Fails fast with clear error messages if anything is missing.

This module should be imported early in the application lifecycle
(e.g., in __main__.py or at the top of algo_config.py).
"""

import os
import sys
import logging
from typing import List, Tuple

log = logging.getLogger(__name__)


class CredentialValidationError(Exception):
    """Raised when required credentials are missing."""
    pass


def validate_credentials() -> Tuple[bool, List[str]]:
    """
    Validate all required credentials.

    Returns:
        (is_valid, error_messages)
        is_valid: True if all required credentials present
        error_messages: List of clear error messages for missing credentials
    """
    errors = []
    warnings = []

    # Detect environment
    is_aws = bool(os.getenv("AWS_EXECUTION_ENV") or os.getenv("AWS_REGION"))
    is_lambda = "AWS_LAMBDA_FUNCTION_NAME" in os.environ

    # === CRITICAL: Database Password ===
    # This is always required. No defaults allowed.
    db_password = os.getenv("DB_PASSWORD")
    if not db_password and not is_aws:
        # Local development: allow .env.local to provide it
        errors.append(
            "❌ DB_PASSWORD not set. Set in .env.local for local development or "
            "in AWS Secrets Manager for production."
        )
    elif not db_password and is_aws:
        # Production: must come from Secrets Manager
        errors.append(
            "❌ DB_PASSWORD not set. In AWS, use AWS Secrets Manager "
            "(db/password secret) or set DB_PASSWORD environment variable."
        )

    # === IMPORTANT: Database credentials ===
    db_host = os.getenv("DB_HOST", "localhost")
    db_user = os.getenv("DB_USER", "stocks")
    db_name = os.getenv("DB_NAME", "stocks")

    if not db_host or db_host == "localhost" and not os.getenv("DB_HOST"):
        warnings.append(
            "⚠️  DB_HOST not set, using 'localhost'. "
            "For production, set DB_HOST explicitly."
        )

    if db_user == "stocks" and not os.getenv("DB_USER"):
        warnings.append(
            "⚠️  DB_USER not set, using default 'stocks'. "
            "For security, consider explicit DB_USER."
        )

    # === IMPORTANT: Alpaca Trading Credentials ===
    # These are optional for paper trading but should be set for live trading
    alpaca_key = os.getenv("APCA_API_KEY_ID")
    alpaca_secret = os.getenv("APCA_API_SECRET_KEY")

    if not alpaca_key or not alpaca_secret:
        warnings.append(
            "⚠️  Alpaca credentials (APCA_API_KEY_ID, APCA_API_SECRET_KEY) not set. "
            "Paper trading mode will work, but live trading disabled."
        )

    # === OPTIONAL: Email/SMS Alerts ===
    if os.getenv("ALERT_ENABLED") == "true":
        smtp_password = os.getenv("ALERT_SMTP_PASSWORD")
        smtp_user = os.getenv("ALERT_SMTP_USER")
        if not smtp_password or not smtp_user:
            errors.append(
                "❌ ALERT_ENABLED=true but ALERT_SMTP_PASSWORD or ALERT_SMTP_USER missing. "
                "Set these credentials or set ALERT_ENABLED=false."
            )

    twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
    if os.getenv("ALERT_SMS_ENABLED") == "true" and not twilio_token:
        errors.append(
            "❌ ALERT_SMS_ENABLED=true but TWILIO_AUTH_TOKEN missing. "
            "Set it or disable SMS alerts."
        )

    return len(errors) == 0, errors + warnings


def assert_credentials(on_failure: str = "raise") -> bool:
    """
    Assert that all required credentials are present.

    Args:
        on_failure: What to do if validation fails:
            - "raise": Raise CredentialValidationError
            - "exit": Call sys.exit(1)
            - "warn": Log warnings only
            - "return": Return False

    Returns:
        True if validation passed, False otherwise

    Raises:
        CredentialValidationError: If on_failure="raise" and validation fails
    """
    is_valid, messages = validate_credentials()

    if is_valid:
        log.info("✓ All required credentials validated")
        return True

    # Print messages
    for msg in messages:
        if "❌" in msg:
            log.error(msg)
        else:
            log.warning(msg)

    if on_failure == "raise":
        raise CredentialValidationError(
            f"Credential validation failed. {len([m for m in messages if '❌' in m])} critical issues."
        )
    elif on_failure == "exit":
        sys.exit(1)
    elif on_failure == "warn":
        pass  # Just logged above
    elif on_failure == "return":
        return False

    return is_valid


def get_credential_issues() -> List[str]:
    """Get list of credential issues for display/logging."""
    _, messages = validate_credentials()
    return messages


if __name__ == "__main__":
    # Test the validator
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s: %(message)s"
    )

    print("\nValidating credentials...")
    print("-" * 60)
    is_valid, messages = validate_credentials()

    for msg in messages:
        print(msg)

    print("-" * 60)
    if is_valid:
        print("✓ All credentials valid")
        sys.exit(0)
    else:
        print("✗ Credential validation failed")
        sys.exit(1)
