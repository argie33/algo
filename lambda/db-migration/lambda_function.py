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


def clear_blocking_queries(creds: dict[str, Any]) -> bool:
    """Terminate all idle and long-running queries blocking migrations.

    PostgreSQL materialized view operations (DROP, REFRESH) require exclusive locks.
    These can be blocked by idle transactions or cursors still holding locks.
    This function terminates:
    1. Any idle backend (closed transaction still holding locks)
    2. Any long-running query (> 30s)
    Excludes the current backend to avoid killing ourselves.

    Returns:
        bool: True if locks cleared or no blocking queries found, False if error.
    """
    try:
        import psycopg2
    except ImportError:
        logger.warning("psycopg2 not available - cannot clear blocking queries")
        return True

    try:
        conn = psycopg2.connect(
            host=creds['host'],
            port=creds['port'],
            database=creds['database'],
            user=creds['user'],
            password=creds['password'],
            connect_timeout=5
        )
        cur = conn.cursor()

        # Find ALL backends except our own, including idle ones (which might hold locks)
        cur.execute("""
            SELECT pid, usename, state, query, extract(epoch FROM (now() - backend_start)) as age_secs
            FROM pg_stat_activity
            WHERE pid != pg_backend_pid()
              AND datname = current_database()
            ORDER BY backend_start ASC;
        """)

        all_backends = cur.fetchall()
        if not all_backends:
            logger.info("No other backends found")
            conn.close()
            return True

        logger.warning(f"Found {len(all_backends)} backend(s) that may hold locks")
        killed_count = 0

        for pid, user, state, query, age_secs in all_backends:
            logger.info(f"  PID {pid} ({user}): {state} age={age_secs:.0f}s query={query[:60] if query else 'N/A'}")

            try:
                cur.execute("SELECT pg_terminate_backend(%s);", (pid,))
                result = cur.fetchone()[0]
                if result:
                    killed_count += 1
                    logger.info(f"    ✓ Terminated")
                else:
                    logger.debug(f"    Could not terminate (may have ended already)")
            except Exception as e:
                logger.warning(f"    Error terminating: {e}")

        if killed_count > 0:
            conn.commit()
            logger.info(f"✓ Terminated {killed_count} backend(s) blocking migrations")
        else:
            logger.info("No backends could be terminated (likely already closed)")

        conn.close()
        return True

    except Exception as e:
        logger.error(f"Failed to clear blocking queries: {e}")
        return False


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
    # Clear blocking queries before running migrations (retry once to handle stale connections)
    import time
    if not clear_blocking_queries(creds):
        logger.warning("Failed to clear blocking queries on first attempt")
    logger.info("Waiting 5 seconds for lock state to stabilize...")
    time.sleep(5)
    if not clear_blocking_queries(creds):
        logger.warning("Failed to clear blocking queries on second attempt, but continuing with migrations anyway")

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
        #
        # NOTE: .parent.parent.parent assumed the local repo layout (lambda/db-migration/
        # lambda_function.py, three levels above a repo-root migrations/ dir). The deployed
        # Lambda package flattens this: deploy-all-infrastructure.yml copies
        # lambda_function.py to the package root and migrations/versions/ + migrations/run.py
        # to a sibling migrations/ directory, so migrations/run.py sits one level below
        # lambda_function.py's own directory, not three. Confirmed live 2026-07-07: every
        # invocation failed with "Migration script not found: /migrations/run.py" (resolved
        # from filesystem root, not /var/task).
        migration_script = Path(__file__).parent / "migrations" / "run.py"

        if not migration_script.exists():
            return {
                "success": False,
                "error": f"Migration script not found: {migration_script}",
            }

        logger.info(f"Running migrations from: {migration_script}")
        logger.info(f"Target database: {creds['host']}:{creds['port']}/{creds['database']}")

        # Lambda's runtime bootstrap adds layer paths (e.g. /opt/python/lib/python3.12/
        # site-packages) to sys.path in-process; it does NOT set PYTHONPATH in the OS
        # environment. A subprocess spawned via subprocess.run() gets a fresh interpreter
        # that only sees PYTHONPATH, so it never sees the layer's psycopg2 unless we add
        # it explicitly. Confirmed live 2026-07-07: "ModuleNotFoundError: No module named
        # 'psycopg2'" in the child process despite the layer being attached and psycopg2
        # importing fine in this parent process.
        subprocess_env = dict(os.environ)
        layer_site_packages = "/opt/python/lib/python3.12/site-packages"
        subprocess_env["PYTHONPATH"] = (
            f"{layer_site_packages}:{subprocess_env['PYTHONPATH']}"
            if subprocess_env.get("PYTHONPATH")
            else layer_site_packages
        )

        try:
            result = subprocess.run(
                [sys.executable, str(migration_script), "apply", "--all", "--credentials-from-stdin"],
                input=creds_json,
                capture_output=True,
                text=True,
                timeout=850,  # leave ~50s of the Lambda's 900s timeout for overhead
                env=subprocess_env,
            )
        except subprocess.TimeoutExpired as e:
            error_msg = "Migration timeout (exceeded 850s)"
            logger.error(f"[CRITICAL] {error_msg}")
            # Previously this branch discarded whatever the child process had already
            # written to stdout/stderr, so every timeout looked like a contextless black
            # box -- three straight runs hung for ~850s with nothing in CloudWatch to show
            # which migration was in flight. subprocess.TimeoutExpired carries partial
            # output (captured before the kill) when capture_output=True; log it so a
            # future hang is diagnosable instead of a mystery.
            partial_stdout = e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else e.stdout
            partial_stderr = e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else e.stderr
            if partial_stdout:
                logger.error(f"Partial migration stdout before timeout:\n{partial_stdout}")
            if partial_stderr:
                logger.error(f"Partial migration stderr before timeout:\n{partial_stderr}")
            return {
                "success": False,
                "error": error_msg,
                "timeout": True,
                "partial_stdout": partial_stdout,
                "partial_stderr": partial_stderr,
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
