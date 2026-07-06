#!/usr/bin/env python3
"""
AWS RDS Database Credential Initialization for Dashboard

This module:
1. Fetches RDS credentials from AWS Secrets Manager
2. Sets AWS_RDS_HOST/USER/PASS environment variables
3. Validates the connection is active before dashboard starts

CRITICAL: This MUST be called before any DatabaseContext or database operations.

Usage:
    from dashboard.aws_rds_init import initialize_aws_rds_credentials

    # Call this at dashboard startup, BEFORE creating DatabaseContext
    initialize_aws_rds_credentials(force_aws=False)

    # Now use database as normal
    from utils.db import DatabaseContext
    with DatabaseContext('read') as cur:
        cur.execute("SELECT ...")
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)


class AWSRDSInitializationError(Exception):
    """Raised when RDS credential initialization fails."""

    pass


class RDSCredentialFetcher:
    """Fetches and validates RDS credentials from AWS Secrets Manager."""

    def __init__(self, aws_region: str | None = None, force_aws: bool = False) -> None:
        """Initialize credential fetcher.

        Args:
            aws_region: AWS region (defaults to us-east-1)
            force_aws: If True, force AWS Secrets Manager access even in local dev
        """
        self.aws_region = aws_region or os.getenv("AWS_REGION", "us-east-1")
        self.force_aws = force_aws
        self._is_aws = self._detect_aws_environment(force_aws)
        self._secrets_client = None

    def _detect_aws_environment(self, force_aws: bool) -> bool:
        """Detect if running in AWS Lambda/ECS or if forced.

        Returns:
            True if in AWS environment or FORCE_AWS is set
        """
        # Check if forced by env var (allows local dev to access AWS Secrets Manager)
        if force_aws or os.getenv("FORCE_AWS", "").lower() in ("true", "1", "yes"):
            return True
        # Check if running in AWS Lambda/ECS
        return bool(os.getenv("AWS_EXECUTION_ENV"))

    def _get_secrets_client(self) -> Any:
        """Get boto3 Secrets Manager client (lazy-loaded).

        Returns:
            boto3 SecretsManager client

        Raises:
            AWSRDSInitializationError: If boto3 unavailable and in AWS environment
        """
        if self._secrets_client is not None:
            return self._secrets_client

        try:
            import boto3
            import botocore.config

            # Fast timeouts for credential fetching
            config = botocore.config.Config(
                connect_timeout=3,
                read_timeout=5,
                retries={"max_attempts": 2},
            )
            self._secrets_client = boto3.client(
                "secretsmanager",
                region_name=self.aws_region,
                config=config,
            )
            logger.debug(f"[RDS_INIT] Secrets Manager client initialized (region={self.aws_region})")
            return self._secrets_client
        except ImportError as e:
            if self._is_aws:
                raise AWSRDSInitializationError(
                    "boto3 not available in AWS environment. "
                    "This is a critical deployment error. "
                    "Ensure boto3 is installed in Lambda layer or container image."
                ) from e
            logger.debug("boto3 not available; using environment variables only")
            return None

    def fetch_from_secrets_manager(self, secret_arn: str) -> dict[str, Any]:
        """Fetch RDS secret from AWS Secrets Manager.

        Args:
            secret_arn: ARN or name of the secret (e.g., 'algo/rds' or full ARN)

        Returns:
            Dictionary with keys: host, port, username, password, dbname

        Raises:
            AWSRDSInitializationError: If secret cannot be fetched or is invalid
        """
        try:
            client = self._get_secrets_client()
            if not client:
                raise AWSRDSInitializationError(
                    "Secrets Manager client unavailable. "
                    "Cannot fetch RDS credentials."
                )

            logger.info(f"[RDS_INIT] Fetching RDS secret: {secret_arn}")
            response = client.get_secret_value(SecretId=secret_arn)

            # Extract secret value (supports both SecretString and SecretBinary)
            secret_string = response.get("SecretString")
            if not secret_string:
                raise AWSRDSInitializationError(
                    f"Secret '{secret_arn}' exists but contains no SecretString"
                )

            secret_data = json.loads(secret_string)

            # Validate required fields
            required_fields = ["host", "port", "username", "password", "dbname"]
            missing_fields = [f for f in required_fields if not secret_data.get(f)]
            if missing_fields:
                raise AWSRDSInitializationError(
                    f"Secret '{secret_arn}' missing required fields: {missing_fields}. "
                    f"Found fields: {list(secret_data.keys())}"
                )

            # Validate port is numeric
            try:
                port = int(secret_data["port"])
            except (ValueError, TypeError) as e:
                raise AWSRDSInitializationError(
                    f"Invalid port in secret '{secret_arn}': {secret_data['port']}"
                ) from e

            result = {
                "host": str(secret_data["host"]),
                "port": port,
                "username": str(secret_data["username"]),
                "password": str(secret_data["password"]),
                "dbname": str(secret_data["dbname"]),
            }

            logger.info(
                f"[RDS_INIT] Successfully fetched RDS credentials "
                f"(host={result['host']}, port={result['port']}, user={result['username'][:8]}...)"
            )
            return result

        except json.JSONDecodeError as e:
            raise AWSRDSInitializationError(
                f"Failed to parse secret '{secret_arn}' as JSON: {e}"
            ) from e
        except Exception as e:
            # Sanitize error message to avoid leaking ARNs or secrets
            error_msg = str(e)
            if "arn:aws:" in error_msg:
                error_msg = "Secret ARN access denied (check IAM permissions)"
            elif "ResourceNotFoundException" in error_msg or "not found" in error_msg:
                error_msg = "Secret not found (check secret name/ARN)"
            raise AWSRDSInitializationError(
                f"Failed to fetch RDS credentials from Secrets Manager: {error_msg}"
            ) from e

    def get_credentials_from_env_or_secrets(
        self, secret_name: str | None = None
    ) -> dict[str, Any]:
        """Get RDS credentials from environment or AWS Secrets Manager.

        Priority:
        1. AWS Secrets Manager (if available and secret_name provided)
        2. Environment variables (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME)
        3. Alternative env names (DB_ENDPOINT for host)

        Args:
            secret_name: AWS Secrets Manager secret ARN/name (optional)

        Returns:
            Dictionary with host, port, user, password, database

        Raises:
            AWSRDSInitializationError: If credentials cannot be obtained
        """
        # Try Secrets Manager first if in AWS and secret name provided
        if self._is_aws and secret_name:
            try:
                return self.fetch_from_secrets_manager(secret_name)
            except AWSRDSInitializationError as e:
                logger.warning(
                    f"[RDS_INIT] Failed to fetch from Secrets Manager: {e}. "
                    f"Falling back to environment variables."
                )

        # Fall back to environment variables
        return self._get_credentials_from_env()

    def _get_credentials_from_env(self) -> dict[str, Any]:
        """Get RDS credentials from environment variables.

        Supported variable names:
        - Host: DB_HOST or DB_ENDPOINT
        - Port: DB_PORT (default 5432)
        - User: DB_USER
        - Password: DB_PASSWORD or db/password secret
        - Database: DB_NAME

        Returns:
            Dictionary with host, port, user, password, database

        Raises:
            AWSRDSInitializationError: If any required variable missing
        """
        # Get host (try DB_HOST first, then DB_ENDPOINT)
        host = os.getenv("DB_HOST")
        if not host:
            host = os.getenv("DB_ENDPOINT")
        if not host:
            raise AWSRDSInitializationError(
                "DB_HOST or DB_ENDPOINT environment variable not set. "
                "Cannot determine database host."
            )

        # Get port (default 5432 for PostgreSQL)
        port_str = os.getenv("DB_PORT", "5432")
        try:
            port = int(port_str)
        except ValueError as e:
            raise AWSRDSInitializationError(
                f"Invalid DB_PORT value: {port_str} (must be integer)"
            ) from e

        # Get user
        user = os.getenv("DB_USER")
        if not user:
            raise AWSRDSInitializationError("DB_USER environment variable not set.")

        # Get password
        password = os.getenv("DB_PASSWORD")
        if not password:
            raise AWSRDSInitializationError("DB_PASSWORD environment variable not set.")

        # Get database name
        database = os.getenv("DB_NAME")
        if not database:
            raise AWSRDSInitializationError("DB_NAME environment variable not set.")

        logger.info(
            f"[RDS_INIT] Using environment variables "
            f"(host={host}, port={port}, user={user[:8]}...)"
        )

        return {
            "host": host,
            "port": port,
            "username": user,
            "password": password,
            "dbname": database,
        }


def set_aws_rds_environment_variables(credentials: dict[str, Any]) -> None:
    """Set AWS RDS environment variables from credentials dict.

    This makes the credentials available to utils.db.connection.get_db_connection()
    which reads these environment variables.

    Args:
        credentials: Dictionary with host, port, username, password, dbname
    """
    os.environ["DB_HOST"] = str(credentials["host"])
    os.environ["DB_PORT"] = str(credentials["port"])
    os.environ["DB_USER"] = str(credentials["username"])
    os.environ["DB_PASSWORD"] = str(credentials["password"])
    os.environ["DB_NAME"] = str(credentials["dbname"])

    logger.info(
        f"[RDS_INIT] Environment variables set: "
        f"DB_HOST={credentials['host']}, "
        f"DB_PORT={credentials['port']}, "
        f"DB_USER={credentials['username'][:8]}..., "
        f"DB_NAME={credentials['dbname']}"
    )


def validate_aws_rds_connection(timeout: int = 10) -> bool:
    """Validate that database connection works before dashboard starts.

    This performs a simple SELECT 1 query to confirm connectivity before
    the dashboard begins rendering (prevents hanging dashboard on bad credentials).

    Args:
        timeout: Connection timeout in seconds

    Returns:
        True if connection successful

    Raises:
        AWSRDSInitializationError: If connection fails
    """
    try:
        import psycopg2

        logger.debug("[RDS_INIT] Validating database connection...")

        host = os.getenv("DB_HOST")
        port = os.getenv("DB_PORT", "5432")
        user = os.getenv("DB_USER")
        password = os.getenv("DB_PASSWORD")
        database = os.getenv("DB_NAME")

        if not all([host, user, password, database]):
            raise AWSRDSInitializationError(
                "Cannot validate connection: missing environment variables"
            )

        # Attempt connection with timeout
        conn = psycopg2.connect(
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=database,
            connect_timeout=timeout,
        )

        # Test query
        cur = conn.cursor()
        cur.execute("SELECT 1")
        result = cur.fetchone()
        cur.close()
        conn.close()

        if result:
            logger.info("[RDS_INIT] Database connection validated successfully")
            return True
        else:
            raise AWSRDSInitializationError("Database validation query returned no result")

    except ImportError as e:
        raise AWSRDSInitializationError("psycopg2 not available") from e
    except Exception as e:
        raise AWSRDSInitializationError(
            f"Database connection validation failed: {str(e)[:200]}"
        ) from e


def initialize_aws_rds_credentials(
    secret_name: str | None = None,
    aws_region: str | None = None,
    force_aws: bool = False,
    validate_connection: bool = True,
    verbose: bool = True,
) -> dict[str, Any]:
    """Initialize AWS RDS credentials and set environment variables.

    This is the main entry point for dashboard RDS initialization.

    CRITICAL: Call this BEFORE any DatabaseContext or database operations.

    Args:
        secret_name: AWS Secrets Manager secret name/ARN (optional, e.g., 'algo/rds' or full ARN).
                     If None, will use environment variables only.
        aws_region: AWS region (defaults to us-east-1)
        force_aws: If True, force AWS Secrets Manager access even in local dev
        validate_connection: If True, validate connection before returning
        verbose: If True, log initialization steps

    Returns:
        Dictionary with initialized credentials: host, port, user, password, database

    Raises:
        AWSRDSInitializationError: If initialization fails at any step
    """
    if verbose:
        logger.info(
            "[RDS_INIT] Initializing AWS RDS credentials for dashboard... "
            f"(secret_name={secret_name}, aws_region={aws_region}, force_aws={force_aws})"
        )

    try:
        # Step 1: Create credential fetcher
        fetcher = RDSCredentialFetcher(aws_region=aws_region, force_aws=force_aws)

        # Step 2: Fetch credentials
        credentials = fetcher.get_credentials_from_env_or_secrets(secret_name=secret_name)

        # Step 3: Set environment variables
        set_aws_rds_environment_variables(credentials)

        # Step 4: Validate connection (optional)
        if validate_connection:
            validate_aws_rds_connection()

        if verbose:
            logger.info(
                "[RDS_INIT] RDS initialization complete: "
                f"host={credentials['host']}, database={credentials['dbname']}"
            )

        return credentials

    except AWSRDSInitializationError as e:
        logger.error(f"[RDS_INIT] CRITICAL: {e}")
        raise
    except Exception as e:
        raise AWSRDSInitializationError(f"Unexpected error during RDS initialization: {e}") from e


if __name__ == "__main__":
    # Quick test script
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        # Test with Secrets Manager if available, otherwise use env vars
        creds = initialize_aws_rds_credentials(
            secret_name=os.getenv("DB_SECRET_ARN", "algo/rds"),
            force_aws=os.getenv("FORCE_AWS", "").lower() in ("true", "1"),
        )
        print(f"\nSuccess! Credentials loaded:")
        print(f"  Host: {creds['host']}")
        print(f"  Port: {creds['port']}")
        print(f"  User: {creds['username'][:8]}...")
        print(f"  Database: {creds['dbname']}")
    except AWSRDSInitializationError as e:
        print(f"\nFailed: {e}")
        sys.exit(1)
