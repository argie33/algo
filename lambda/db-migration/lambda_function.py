#!/usr/bin/env python3
"""
Database migration Lambda for RDS PostgreSQL.
Applies pending SQL migrations from migrations/versions/ directory.
Must run in VPC with DB access. Uses Secrets Manager for credentials.

This Lambda replaces the ECS migration task approach and runs directly
in the GitHub Actions deployment pipeline via Lambda invocation.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Add project root to path for importing config module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def get_credentials() -> dict[str, Any]:
    """Get DB credentials from Secrets Manager via credential_manager.

    Returns:
        dict[str, Any]: Always returns a dict with keys: host, port, database, user, password.
                       Never returns None. Raises ValueError if any required credential is missing.

    Raises:
        ValueError: If any required credential is missing or invalid.
        ImportError: If credential_manager cannot be imported and no fallback available.
    """
    try:
        from config.credential_manager import get_db_credentials

        return get_db_credentials()
    except ImportError:
        logger.warning("Could not import credential_manager, falling back to manual boto3 fetch")
        import boto3

        secret_arn = os.environ.get("DB_SECRET_ARN")
        if secret_arn:
            try:
                client = boto3.client(
                    "secretsmanager",
                    region_name=os.environ.get("AWS_REGION", "us-east-1"),
                )
                response = client.get_secret_value(SecretId=secret_arn)
                secret = json.loads(response["SecretString"])
                raw_host = os.environ.get("DB_ENDPOINT")
                if not raw_host:
                    raw_host = secret.get("host")
                if not raw_host:
                    raise ValueError(
                        "[CRITICAL] Database host not found in secrets or DB_ENDPOINT environment variable"
                    )
                host = raw_host.split(":")[0] if ":" in raw_host else raw_host

                db_port = secret.get("port")
                if not db_port:
                    raise ValueError("[CRITICAL] Database port not found in secrets")

                db_name = os.environ.get("DB_NAME")
                if not db_name:
                    db_name = secret.get("dbname")
                if not db_name:
                    raise ValueError("[CRITICAL] Database name not found in environment or secrets")

                db_user = secret.get("username")
                if not db_user:
                    raise ValueError("[CRITICAL] Database username not found in secrets")

                db_password = secret.get("password")
                if not db_password:
                    raise ValueError("[CRITICAL] Database password not found in secrets")

                return {
                    "host": host,
                    "port": int(db_port),
                    "database": db_name,
                    "user": db_user,
                    "password": db_password,
                }
            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
                logger.error(f"Failed to parse secrets: {e}")
                raise

        # Local dev mode: all credentials must be explicitly set
        db_host = os.environ.get("DB_HOST")
        if not db_host:
            raise ValueError("[CRITICAL] DB_HOST not set in environment") from None

        db_port_str = os.environ.get("DB_PORT")
        if not db_port_str:
            raise ValueError("[CRITICAL] DB_PORT not set in environment") from None

        db_name = os.environ.get("DB_NAME")
        if not db_name:
            raise ValueError("[CRITICAL] DB_NAME not set in environment") from None

        db_user = os.environ.get("DB_USER")
        if not db_user:
            raise ValueError("[CRITICAL] DB_USER not set in environment") from None

        db_password = os.environ.get("DB_PASSWORD")
        if not db_password:
            raise ValueError("[CRITICAL] DB_PASSWORD not set in environment") from None

        return {
            "host": db_host,
            "port": int(db_port_str),
            "database": db_name,
            "user": db_user,
            "password": db_password,
        }


def run_migrations(creds: dict[str, Any]) -> dict[str, Any]:
    """Execute migrations/run.py apply --all with credentials from Secrets Manager.

    Returns:
        dict[str, Any]: Always returns a dict with 'success' bool and either 'message' or 'error'.
                       Never returns None. Explicit error states for all failure modes.

    Error states:
        - Missing migration script: success=False, error message
        - Timeout (>5min): success=False, error message
        - Migration failure: success=False, error + exit code
        - Unexpected exception: success=False, error message
    """
    try:
        # Build credentials JSON to pass to run.py
        creds_json = json.dumps(
            {
                "host": creds["host"],
                "port": creds["port"],
                "username": creds["user"],
                "password": creds["password"],
                "dbname": creds["database"],
            }
        )

        # Run migrations/run.py with credentials from stdin
        # This avoids passing sensitive data as environment variables
        migration_script = Path(__file__).parent.parent.parent / "migrations" / "run.py"

        if not migration_script.exists():
            return {
                "success": False,
                "error": f"Migration script not found: {migration_script}",
            }

        logger.info(f"Running migrations from: {migration_script}")
        logger.info(f"Target database: {creds['host']}:{creds['port']}/{creds['database']}")

        try:
            result = subprocess.run(
                [sys.executable, str(migration_script), "apply", "--all", "--credentials-from-stdin"],
                input=creds_json,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
        except subprocess.TimeoutExpired:
            error_msg = "Migration timeout (exceeded 5 minutes)"
            logger.error(f"[CRITICAL] {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "timeout": True,
            }

        stdout = result.stdout
        stderr = result.stderr

        logger.info(f"Migration output:\n{stdout}")
        if stderr:
            logger.warning(f"Migration stderr:\n{stderr}")

        if result.returncode == 0:
            logger.info("[SUCCESS] All pending migrations applied successfully")
            return {
                "success": True,
                "message": "All pending migrations applied successfully",
                "output": stdout,
            }
        else:
            error_msg = f"Migration failed with exit code {result.returncode}"
            logger.error(f"[FAILURE] {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "exit_code": result.returncode,
                "output": stdout,
                "stderr": stderr,
            }

    except Exception as e:
        logger.error(f"[CRITICAL] Unexpected error running migrations: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Unexpected error: {e}",
            "exception_type": type(e).__name__,
        }


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    """Lambda entry point for database migrations.

    Returns:
        dict[str, Any]: HTTP response dict with statusCode (200/400/500) and JSON body.
                       Always returns explicit success/failure state. Never returns None.

    Status codes:
        - 200: Migrations succeeded
        - 400: Configuration error (missing credentials)
        - 500: Migration failure or unexpected error
    """
    try:
        logger.info("Starting database migrations")
        logger.info(f"Event: {json.dumps(event)}")

        # Get database credentials
        creds = get_credentials()
        logger.info(
            f"Successfully loaded credentials for database: {creds['host']}:{creds['port']}/{creds['database']}"
        )

        # Run migrations
        result = run_migrations(creds)

        if result.get("success"):
            logger.info("[SUCCESS] Migrations completed successfully")
            return {
                "statusCode": 200,
                "body": json.dumps(result),
            }
        else:
            error_msg = result.get("error", "Unknown migration failure")
            logger.error(f"[FAILURE] Migrations failed: {error_msg}")
            return {
                "statusCode": 500,
                "body": json.dumps(result),
            }

    except ValueError as e:
        error_msg = f"[CRITICAL] Configuration error: {e}"
        logger.error(error_msg)
        return {
            "statusCode": 400,
            "body": json.dumps({"success": False, "error": str(e), "config_error": True}),
        }
    except Exception as e:
        error_msg = f"[CRITICAL] Unexpected error in lambda_handler: {e}"
        logger.error(error_msg, exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"success": False, "error": str(e), "exception_type": type(e).__name__}),
        }
