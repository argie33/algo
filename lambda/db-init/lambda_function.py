# DEPLOY_TRIGGER: 2026-07-04 074457
#!/usr/bin/env python3
"""
Database schema initialization Lambda for RDS PostgreSQL.
Uses Secrets Manager for credentials via credential_manager. Must run in VPC.
Deployed: May 24, 2026 21:56 - Triggering auto database initialization
"""

import json
import logging
import os
import re
import sys
from pathlib import Path

import psycopg2
import psycopg2.sql

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_DB_PORT = 5432

# Add project root to path for importing config module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def get_credentials():
    """Get DB credentials from Secrets Manager or env vars via credential_manager."""
    try:
        from config.credential_manager import get_db_credentials

        return get_db_credentials()
    except ImportError:
        logger.warning("Could not import credential_manager, falling back to manual boto3 fetch")
        # Fallback if config module not available
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
                    raise ValueError("Database host not found in secrets or DB_ENDPOINT environment variable")
                host = raw_host.split(":")[0] if ":" in raw_host else raw_host

                db_port = secret.get("port")
                if not db_port:
                    raise ValueError("Database port not found in secrets")

                db_name = os.environ.get("DB_NAME")
                if not db_name:
                    db_name = secret.get("dbname")
                if not db_name:
                    raise ValueError("Database name not found in environment or secrets")

                db_user = secret.get("username")
                if not db_user:
                    raise ValueError("Database username not found in secrets")

                db_password = secret.get("password")
                if not db_password:
                    raise ValueError("Database password not found in secrets")

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
            raise ValueError("DB_HOST not set in environment") from None

        db_port_str = os.environ.get("DB_PORT")
        if not db_port_str:
            raise ValueError("DB_PORT not set in environment") from None

        db_name = os.environ.get("DB_NAME")
        if not db_name:
            raise ValueError("DB_NAME not set in environment") from None

        db_user = os.environ.get("DB_USER")
        if not db_user:
            raise ValueError("DB_USER not set in environment") from None

        db_password = os.environ.get("DB_PASSWORD")
        if not db_password:
            raise ValueError("DB_PASSWORD not set in environment") from None

        return {
            "host": db_host,
            "port": int(db_port_str),
            "database": db_name,
            "user": db_user,
            "password": db_password,
        }


def split_sql_statements(sql):
    """Split SQL into statements, respecting dollar-quoted blocks (DO $$ ... $$).

    A naive split(';') breaks DO $$ BEGIN ... ; END $$; blocks.
    This parser tracks dollar-quoting depth so inner semicolons are preserved.
    """
    statements = []
    current = []
    dollar_tag = None
    i = 0
    while i < len(sql):
        ch = sql[i]

        # Detect start/end of dollar-quoted string
        if ch == "$" and dollar_tag is None:
            match = re.match(r"\$([^$]*)\$", sql[i:])
            if match:
                dollar_tag = match.group(0)
                current.append(dollar_tag)
                i += len(dollar_tag)
                continue

        if dollar_tag and sql[i : i + len(dollar_tag)] == dollar_tag:
            current.append(dollar_tag)
            i += len(dollar_tag)
            dollar_tag = None
            continue

        if ch == ";" and dollar_tag is None:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    # Flush any remaining
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)

    return statements


def lambda_handler(event, context):  # noqa: C901
    """Initialize RDS database schema and ensure stocks user exists."""
    try:
        creds = get_credentials()

        if not all([creds["host"], creds["user"], creds["password"]]):
            logger.error("Missing required database credentials")
            return {
                "statusCode": 400,
                "body": json.dumps("Missing required database credentials"),
            }

        # Fast DB availability check: if DB doesn't respond in 3s, return success
        # so Terraform doesn't block for 600s on db-init invocation during loader load.
        # Schema and seeds are idempotent — safe to skip when DB is temporarily busy.
        try:
            _probe = psycopg2.connect(
                host=creds["host"],
                port=creds["port"],
                database=creds["database"],
                user=creds["user"],
                password=creds["password"],
                connect_timeout=3,
            )
            _probe.autocommit = True
            _pc = _probe.cursor()
            _pc.execute("SET statement_timeout TO '2000'")  # 2 seconds
            _pc.execute("SELECT 1")
            _pc.close()
            _probe.close()
            logger.info("[DB_PROBE] Database responsive — proceeding with schema init")
        except Exception as _probe_err:
            logger.warning(
                f"[DB_PROBE] Database unresponsive ({_probe_err}) — skipping schema init this deploy. "
                "Schema is idempotent; will apply on next successful deploy."
            )
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "status": "skipped",
                        "reason": "Database temporarily busy (ECS loaders under heavy write load)",
                        "message": "Schema init skipped — idempotent, will apply on next successful deploy",
                    }
                ),
            }

        # Support unlock action: terminates idle connections holding advisory locks.
        # Invoke with {"action": "unlock_advisory_locks"} to clear stuck pg_advisory_lock sessions.
        if isinstance(event, dict) and event.get("action") == "unlock_advisory_locks":
            conn = psycopg2.connect(
                host=creds["host"],
                port=creds["port"],
                database=creds["database"],
                user=creds["user"],
                password=creds["password"],
                connect_timeout=15,
            )
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("""
                SELECT count(pg_terminate_backend(pid))
                FROM pg_stat_activity
                WHERE pid != pg_backend_pid()
                  AND state IN ('idle', 'idle in transaction', 'idle in transaction (aborted)')
                  AND state_change < NOW() - INTERVAL '5 minutes'
            """)
            row = cur.fetchone()
            if row is None or row[0] is None:
                raise RuntimeError("Terminate backend query failed")
            terminated = row[0]
            cur.close()
            conn.close()
            logger.info(f"Terminated {terminated} idle connections (advisory lock cleanup)")
            return {
                "statusCode": 200,
                "body": json.dumps(f"Terminated {terminated} idle connections"),
            }

        # Step 0: Release stale advisory locks from crashed/stuck ECS loader tasks.
        # OptimalLoader uses pg_try_advisory_lock() — if a task crashes mid-run, the
        # lock hangs in idle connections in the RDS Proxy pool and blocks all subsequent
        # runs. Clearing these at deploy time is safe: they belong to loader tasks
        # that are no longer running (idle > 60 minutes).
        try:
            _conn = psycopg2.connect(
                host=creds["host"],
                port=creds["port"],
                database=creds["database"],
                user=creds["user"],
                password=creds["password"],
                connect_timeout=10,
            )
            _conn.autocommit = True
            _cur = _conn.cursor()
            _cur.execute("""
                SELECT count(pg_terminate_backend(pid))
                FROM pg_stat_activity
                WHERE pid != pg_backend_pid()
                  AND state IN ('idle', 'idle in transaction', 'idle in transaction (aborted)')
                  AND state_change < NOW() - INTERVAL '5 minutes'
            """)
            row = _cur.fetchone()
            if row is None or row[0] is None:
                raise RuntimeError("Terminate backend query failed")
            terminated = row[0]
            _cur.close()
            _conn.close()
            if terminated:
                logger.info(f"Step 0: Released {terminated} stale idle connections (advisory lock cleanup)")
            else:
                logger.info("Step 0: No stale connections found (advisory locks clean)")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as _e:
            logger.warning(f"Step 0: Advisory lock cleanup failed (non-fatal): {_e}")

        # Step 1: Ensure stocks user exists (as master user)
        logger.info("Step 1: Ensuring stocks user exists with correct password...")

        master_user = os.environ.get("DB_MASTER_USER", "postgres")
        master_password = os.environ.get("DB_MASTER_PASSWORD")

        if master_user and master_password:
            try:
                logger.info(f"Connecting as master user ({master_user}) to create/update stocks user...")
                master_conn = psycopg2.connect(
                    host=creds["host"],
                    port=creds["port"],
                    database=creds["database"],
                    user=master_user,
                    password=master_password,
                    connect_timeout=15,
                )
                master_conn.autocommit = True
                master_cursor = master_conn.cursor()

                # Create or update stocks user with password from Secrets Manager
                try:
                    master_cursor.execute(
                        psycopg2.sql.SQL("ALTER USER {} WITH PASSWORD %s").format(
                            psycopg2.sql.Identifier(creds["user"])
                        ),
                        (creds["password"],),
                    )
                    logger.info(f"Updated existing {creds['user']} user password")
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.info(f"User update failed, creating new user: {e}")
                    try:
                        master_cursor.execute(
                            psycopg2.sql.SQL("CREATE USER {} WITH PASSWORD %s").format(
                                psycopg2.sql.Identifier(creds["user"])
                            ),
                            (creds["password"],),
                        )
                        logger.info(f"Created new {creds['user']} user")
                        # Grant permissions
                        master_cursor.execute(
                            psycopg2.sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                                psycopg2.sql.Identifier(creds["database"]),
                                psycopg2.sql.Identifier(creds["user"]),
                            )
                        )
                        master_cursor.execute(
                            psycopg2.sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                                psycopg2.sql.Identifier(creds["user"])
                            )
                        )
                        master_cursor.execute(
                            psycopg2.sql.SQL("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {}").format(
                                psycopg2.sql.Identifier(creds["user"])
                            )
                        )
                        master_cursor.execute(
                            psycopg2.sql.SQL("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {}").format(
                                psycopg2.sql.Identifier(creds["user"])
                            )
                        )
                        logger.info(f"Granted permissions to {creds['user']}")
                    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e2:
                        logger.error(f"Failed to create/update user: {e2}")

                master_cursor.close()
                master_conn.close()
                logger.info("✅ Stocks user setup complete")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(f"Could not connect as master user to create stocks user: {e}")
        else:
            logger.info("Master user credentials not provided, skipping user creation")

        # Step 2: Initialize schema as stocks user
        logger.info("Step 2: Initializing database schema")
        conn = psycopg2.connect(
            host=creds["host"],
            port=creds["port"],
            database=creds["database"],
            user=creds["user"],
            password=creds["password"],
            connect_timeout=15,
        )
        conn.autocommit = True

        # Add MACD columns if needed (idempotent)
        cursor = conn.cursor()
        for table in ["buy_sell_daily", "buy_sell_weekly", "buy_sell_monthly"]:
            try:
                cursor.execute(
                    psycopg2.sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS macd DECIMAL(10, 2)").format(
                        psycopg2.sql.Identifier(table)
                    )
                )
                cursor.execute(
                    psycopg2.sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS macd_signal DECIMAL(10, 2)").format(
                        psycopg2.sql.Identifier(table)
                    )
                )
                logger.info(f"Added MACD columns to {table}")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.info(f"MACD columns may already exist on {table}: {e}")

        # Add historical rank columns to industry_ranking (idempotent)
        try:
            cursor.execute("ALTER TABLE industry_ranking ADD COLUMN IF NOT EXISTS rank_1w_ago INTEGER")
            cursor.execute("ALTER TABLE industry_ranking ADD COLUMN IF NOT EXISTS rank_4w_ago INTEGER")
            cursor.execute("ALTER TABLE industry_ranking ADD COLUMN IF NOT EXISTS rank_12w_ago INTEGER")
            logger.info("Added historical rank columns to industry_ranking")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.info(f"industry_ranking history columns may already exist: {e}")

        # Add data_unavailable columns to score tables for explicit marker support (idempotent)
        try:
            cursor.execute("ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE")
            cursor.execute("ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS reason VARCHAR(500)")
            logger.info("Added data_unavailable columns to stock_scores")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.info(f"stock_scores data_unavailable columns may already exist: {e}")

        try:
            cursor.execute(
                "ALTER TABLE swing_trader_scores ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE"
            )
            cursor.execute(
                "ALTER TABLE swing_trader_scores ADD COLUMN IF NOT EXISTS unavailability_reason VARCHAR(500)"
            )
            logger.info("Added data_unavailable columns to swing_trader_scores")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.info(f"swing_trader_scores data_unavailable columns may already exist: {e}")

        # Create indexes for faster data_unavailable filtering (idempotent)
        try:
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_stock_scores_data_unavailable ON stock_scores(data_unavailable, symbol)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_swing_trader_scores_data_unavailable ON swing_trader_scores(data_unavailable, symbol, date)"
            )
            logger.info("Created data_unavailable indexes")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.info(f"data_unavailable indexes may already exist: {e}")

        # Add R-metrics columns to algo_performance_metrics for perf_anl API (idempotent)
        # Migration 113: Missing columns cause perf_anl endpoint to fail with 500 error
        try:
            cursor.execute("ALTER TABLE algo_performance_metrics ADD COLUMN IF NOT EXISTS avg_win_r NUMERIC(8, 4)")
            cursor.execute("ALTER TABLE algo_performance_metrics ADD COLUMN IF NOT EXISTS avg_loss_r NUMERIC(8, 4)")
            cursor.execute("ALTER TABLE algo_performance_metrics ADD COLUMN IF NOT EXISTS expectancy NUMERIC(8, 4)")
            logger.info("Added R-metrics columns (avg_win_r, avg_loss_r, expectancy) to algo_performance_metrics")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.info(f"R-metrics columns may already exist on algo_performance_metrics: {e}")

        sql_script = ""
        try:
            # SECURITY FIX S-07: Use absolute path to prevent path traversal
            schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
            with open(schema_path) as f:
                sql_script = f.read()
            logger.info(f"Using schema from {schema_path}")
        except FileNotFoundError:
            logger.warning("schema.sql not found")

        if not sql_script.strip():
            cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
            row = cursor.fetchone()
            if row is None or row[0] is None:
                raise RuntimeError("Table count query failed")
            table_count = row[0]
            cursor.close()
            conn.close()
            return {
                "statusCode": 200,
                "body": json.dumps(f"DB connected, {table_count} tables exist (MACD columns added)"),
            }

        statements = split_sql_statements(sql_script)
        ok_count = 0
        skip_count = 0

        for statement in statements:
            if not statement:
                continue
            try:
                cursor.execute(statement)
                ok_count += 1
            except (json.JSONDecodeError, ValueError) as e:
                err = str(e)
                if "already exists" in err or "does not exist" in err:
                    skip_count += 1
                else:
                    logger.warning(f"Statement failed: {statement[:100]}... -> {err[:120]}")
                    skip_count += 1

        cursor.close()
        conn.close()

        logger.info(f"Schema init done: {ok_count} ok, {skip_count} skipped/errored of {len(statements)} total")
        return {
            "statusCode": 200,
            "body": json.dumps(f"Database schema initialized ({ok_count}/{len(statements)} statements)"),
        }

    except psycopg2.OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return {"statusCode": 503, "body": json.dumps(f"DB connection failed: {e}")}
    except psycopg2.DatabaseError as e:
        logger.error(f"Init failed: {e}", exc_info=True)
        return {"statusCode": 500, "body": json.dumps(f"Init failed: {e}")}
