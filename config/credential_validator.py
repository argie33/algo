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

logger = logging.getLogger(__name__)

class CredentialValidationError(Exception):
    """Raised when required credentials are missing."""
    pass

def validate_credentials() -> Tuple[bool, List[str]]:
    """Validate that all required credentials are present and complete.

    CRITICAL ISSUE 4 FIX: Ensures credentials are complete (not partial),
    validates timeout settings, and detects missing required values early.
    """
    errors = []
    warnings = []

    # Detect environment
    is_aws = bool(os.getenv("AWS_EXECUTION_ENV") or os.getenv("AWS_REGION"))
    is_lambda = "AWS_LAMBDA_FUNCTION_NAME" in os.environ
    is_local_dev = os.getenv("ENVIRONMENT") in ("development", "local") or os.getenv("LOCAL_DEV") == "true"

    # === CRITICAL: Database Password ===
    # This is always required. No defaults allowed.
    # In AWS, can come from DB_SECRET_ARN (JSON blob in Secrets Manager)
    # or from DB_PASSWORD env var (legacy)
    db_password = os.getenv("DB_PASSWORD")
    database_secret_arn = os.getenv("DB_SECRET_ARN")

    if not db_password and not database_secret_arn:
        errors.append(
            "[ERROR] CRITICAL: DB_PASSWORD not set and DB_SECRET_ARN not set. "
            "Set DB_PASSWORD for local dev or DB_SECRET_ARN for AWS production."
        )
    elif db_password:
        # Validate password is not empty string
        if len(db_password.strip()) == 0:
            errors.append(
                "[ERROR] DB_PASSWORD is empty string. "
                "Check that password is properly loaded from environment."
            )
        # In production, require longer passwords; in dev, allow shorter ones (test fixtures)
        elif not is_local_dev and len(db_password.strip()) < 8:
            errors.append(
                "[ERROR] DB_PASSWORD is too short (min 8 characters in production). "
                "Check that password is properly loaded from environment."
            )

    # === CRITICAL: Database hostname ===
    # DB_HOST MUST be explicitly set - no defaults to localhost
    db_host = os.getenv("DB_HOST")
    if not db_host:
        errors.append(
            "[ERROR] DB_HOST not set. Set DB_HOST environment variable "
            "to your database hostname (e.g., localhost for local dev, RDS endpoint for prod)."
        )
    elif len(db_host.strip()) == 0:
        errors.append(
            "[ERROR] DB_HOST is empty string. Set to valid hostname."
        )

    db_user = os.getenv("DB_USER", "stocks")
    db_name = os.getenv("DB_NAME", "stocks")

    if db_user == "stocks" and not os.getenv("DB_USER"):
        warnings.append(
            "[WARN] DB_USER not set, using default 'stocks'. "
            "For security, consider explicit DB_USER."
        )

    # === IMPORTANT: Database Timeout Settings ===
    # CRITICAL ISSUE 4 FIX: Validate timeout is configured
    db_timeout = os.getenv("DB_CONNECT_TIMEOUT", "10")
    try:
        timeout_val = int(db_timeout)
        if timeout_val <= 0:
            errors.append(
                "[ERROR] DB_CONNECT_TIMEOUT must be positive. "
                f"Got: {db_timeout}"
            )
        elif timeout_val > 30:
            warnings.append(
                "[WARN] DB_CONNECT_TIMEOUT is very long ("
                f"{timeout_val}s). Consider shorter timeout (10-15s recommended)."
            )
    except ValueError:
        errors.append(
            "[ERROR] DB_CONNECT_TIMEOUT must be integer (seconds). "
            f"Got: {db_timeout}"
        )

    # === IMPORTANT: Alpaca Trading Credentials ===
    # These are optional for paper trading but should be set for live trading
    alpaca_key = os.getenv("APCA_API_KEY_ID")
    alpaca_secret = os.getenv("APCA_API_SECRET_KEY")

    if not alpaca_key or not alpaca_secret:
        warnings.append(
            "[WARN] Alpaca credentials (APCA_API_KEY_ID, APCA_API_SECRET_KEY) not set. "
            "Paper trading mode will work, but live trading disabled."
        )
    else:
        # Validate credentials are not empty strings
        if len(alpaca_key.strip()) == 0 or len(alpaca_secret.strip()) == 0:
            errors.append(
                "[ERROR] Alpaca credentials are empty strings. "
                "Check that credentials are properly loaded from environment."
            )

    # === OPTIONAL: Email/SMS Alerts ===
    if os.getenv("ALERT_ENABLED") == "true":
        smtp_password = os.getenv("ALERT_SMTP_PASSWORD")
        smtp_user = os.getenv("ALERT_SMTP_USER")
        if not smtp_password or not smtp_user:
            errors.append(
                "[ERROR] ALERT_ENABLED=true but ALERT_SMTP_PASSWORD or ALERT_SMTP_USER missing. "
                "Set these credentials or set ALERT_ENABLED=false."
            )
        elif not smtp_password or not smtp_user or len(smtp_password.strip()) == 0 or len(smtp_user.strip()) == 0:
            errors.append(
                "[ERROR] ALERT_SMTP_PASSWORD or ALERT_SMTP_USER is empty string. "
                "Check environment variable loading."
            )

    twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
    if os.getenv("ALERT_SMS_ENABLED") == "true" and not twilio_token:
        errors.append(
            "[ERROR] ALERT_SMS_ENABLED=true but TWILIO_AUTH_TOKEN missing. "
            "Set it or disable SMS alerts."
        )
    elif twilio_token and len(twilio_token.strip()) == 0:
        errors.append(
            "[ERROR] TWILIO_AUTH_TOKEN is empty string. "
            "Check environment variable loading."
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
        logger.info("[OK] All required credentials validated")
        return True

    # Print messages
    for msg in messages:
        if "[ERROR]" in msg:
            logger.error(msg)
        else:
            logger.warning(msg)

    if on_failure == "raise":
        raise CredentialValidationError(
            f"Credential validation failed. {len([m for m in messages if '[ERROR]' in m])} critical issues."
        )
    elif on_failure == "exit":
        sys.exit(1)
    elif on_failure == "warn":
        pass  # Just logged above
    elif on_failure == "return":
        return False

    return is_valid

if __name__ == "__main__":
    # Test the validator
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    logger.info("\nValidating credentials...")
    logger.info("-" * 60)
    is_valid, messages = validate_credentials()

    for msg in messages:
        logger.info(msg)

    logger.info("-" * 60)
    if is_valid:
        logger.info("[OK] All credentials valid")
        sys.exit(0)
    else:
        logger.info("[FAIL] Credential validation failed")
        sys.exit(1)
