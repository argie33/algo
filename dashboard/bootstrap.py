#!/usr/bin/env python3
"""
Dashboard Bootstrap - Initializes AWS RDS credentials before dashboard starts.

This module must be imported FIRST in the dashboard startup sequence, before
any database operations.

Usage in dashboard/__main__.py or dashboard/dashboard.py:

    # At the TOP of the file (before any imports of utils.db or DatabaseContext):
    from dashboard.bootstrap import bootstrap_dashboard_database

    # Call this in main() before creating any DatabaseContext:
    def main():
        bootstrap_dashboard_database()

        # Now use database as normal
        from utils.db import DatabaseContext
        with DatabaseContext('read') as cur:
            cur.execute("SELECT ...")
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _is_aws_environment() -> bool:
    """Check if running in AWS Lambda/ECS or forced via FORCE_AWS."""
    if os.getenv("FORCE_AWS", "").lower() in ("true", "1", "yes"):
        return True
    return bool(os.getenv("AWS_EXECUTION_ENV"))


def _get_rds_secret_name() -> str | None:
    """Get RDS secret name from environment variables.

    Checks in order:
    1. DB_SECRET_ARN (full ARN)
    2. DB_SECRET_NAME (simple name, e.g., 'algo/rds')
    3. Terraform output (if terraform installed)
    """
    # Check explicit ARN first
    secret_arn = os.getenv("DB_SECRET_ARN")
    if secret_arn:
        logger.debug(f"[BOOTSTRAP] Using DB_SECRET_ARN: {secret_arn}")
        return secret_arn

    # Check simple name
    secret_name = os.getenv("DB_SECRET_NAME", "algo/rds")
    if secret_name and secret_name != "":
        logger.debug(f"[BOOTSTRAP] Using DB_SECRET_NAME: {secret_name}")
        return secret_name

    return None


def bootstrap_dashboard_database(
    aws_region: str | None = None,
    secret_name: str | None = None,
    force_aws: bool = False,
    skip_validation: bool = False,
    verbose: bool = True,
) -> None:
    """Bootstrap dashboard database connection to AWS RDS.

    This function:
    1. Fetches RDS credentials from AWS Secrets Manager (if available)
    2. Falls back to environment variables (DB_HOST, DB_USER, etc.)
    3. Sets environment variables for utils.db.connection to use
    4. Validates connection before dashboard starts (optional)

    CRITICAL: Call this BEFORE any imports of DatabaseContext or database operations.

    Args:
        aws_region: AWS region (defaults to us-east-1)
        secret_name: Explicit secret name/ARN to use (overrides auto-detection)
        force_aws: If True, force AWS Secrets Manager access even in local dev
        skip_validation: If True, skip database connection validation
        verbose: If True, log bootstrap steps

    Raises:
        RuntimeError: If bootstrap fails (database credentials missing, connection invalid, etc.)
    """
    if verbose:
        logger.info("[BOOTSTRAP] Starting dashboard database bootstrap...")

    try:
        # Check if already initialized (env vars set)
        if _is_already_initialized():
            if verbose:
                logger.info(
                    "[BOOTSTRAP] Database already initialized. "
                    f"Using: DB_HOST={os.getenv('DB_HOST')}, "
                    f"DB_NAME={os.getenv('DB_NAME')}"
                )
            return

        # Determine environment
        in_aws = _is_aws_environment() or force_aws
        if verbose:
            logger.info(f"[BOOTSTRAP] Environment: {'AWS' if in_aws else 'Local'}")

        # Auto-detect secret name if not provided
        if secret_name is None:
            secret_name = _get_rds_secret_name()

        # Import aws_rds_init module
        try:
            from dashboard.aws_rds_init import initialize_aws_rds_credentials
        except ImportError as e:
            raise RuntimeError("Failed to import aws_rds_init module. Ensure dashboard/aws_rds_init.py exists.") from e

        # Initialize credentials
        credentials = initialize_aws_rds_credentials(
            secret_name=secret_name,
            aws_region=aws_region,
            force_aws=force_aws,
            validate_connection=not skip_validation,
            verbose=verbose,
        )

        if verbose:
            logger.info(
                "[BOOTSTRAP] Database bootstrap complete. "
                f"Connected to {credentials['host']}:{credentials['port']}/{credentials['dbname']}"
            )

    except Exception as e:
        logger.error(f"[BOOTSTRAP] CRITICAL: Database bootstrap failed: {e}")
        raise RuntimeError(f"Failed to bootstrap dashboard database: {e}") from e


def _is_already_initialized() -> bool:
    """Check if database environment variables are already set.

    Returns True if DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME are all set.
    """
    required_vars = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]
    initialized = all(os.getenv(var) for var in required_vars)

    if initialized:
        db_user = os.getenv("DB_USER") or ""
        logger.debug(
            "[BOOTSTRAP] Found existing environment variables: "
            f"DB_HOST={os.getenv('DB_HOST')}, DB_PORT={os.getenv('DB_PORT')}, "
            f"DB_USER={db_user[:8]}..."
        )

    return initialized


def get_dashboard_database_config() -> dict[str, Any]:
    """Get current database configuration from environment variables.

    Returns:
        Dictionary with host, port, user, password, database, or empty dict if not initialized

    Raises:
        RuntimeError: If configuration is partially set (some vars missing)
    """
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME")

    # Check if partially configured (would cause connection errors)
    vars_set = [bool(v) for v in [host, port, user, password, database]]
    if any(vars_set) and not all(vars_set):
        missing = [
            name
            for name, val in [
                ("DB_HOST", host),
                ("DB_PORT", port),
                ("DB_USER", user),
                ("DB_PASSWORD", password),
                ("DB_NAME", database),
            ]
            if not val
        ]
        raise RuntimeError(
            f"Database configuration is incomplete. Missing: {missing}. "
            f"Call bootstrap_dashboard_database() to initialize."
        )

    # Return empty dict if not initialized at all
    if not any(vars_set):
        return {}

    return {
        "host": host,
        "port": int(port) if port else None,
        "user": user,
        "password": password,
        "database": database,
    }


def check_database_connectivity() -> bool:
    """Check if database connection is currently valid.

    Returns:
        True if connection works, False if no credentials set

    Raises:
        RuntimeError: If credentials set but connection fails
    """
    try:
        import psycopg2

        config = get_dashboard_database_config()
        if not config:
            logger.debug("[BOOTSTRAP] Database not initialized - skipping connectivity check")
            return False

        logger.debug("[BOOTSTRAP] Checking database connectivity...")
        conn = psycopg2.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            database=config["database"],
            connect_timeout=5,
        )

        cur = conn.cursor()
        cur.execute("SELECT 1")
        result = cur.fetchone()
        cur.close()
        conn.close()

        if result:
            logger.info("[BOOTSTRAP] Database connectivity check passed")
            return True
        else:
            raise RuntimeError("Database connectivity check returned no result")

    except Exception as e:
        logger.error(f"[BOOTSTRAP] Database connectivity check failed: {e}")
        raise RuntimeError(f"Database connection failed: {e}") from e


if __name__ == "__main__":
    # Quick test
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        bootstrap_dashboard_database(verbose=True)
        config = get_dashboard_database_config()
        print("\nDatabase Configuration:")
        print(f"  Host: {config.get('host')}")
        print(f"  Port: {config.get('port')}")
        print(f"  User: {config.get('user', 'N/A')[:8]}...")
        print(f"  Database: {config.get('database')}")
        print("\nConnectivity Check:")
        if check_database_connectivity():
            print("  ✓ Connection successful")
    except Exception as e:
        print(f"\nBootstrap failed: {e}")
        sys.exit(1)
