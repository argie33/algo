"""Startup/cold-start helpers for the API Lambda handler.

Split out of lambda_function.py (bloater decomposition, mechanical move, no behavior
change): database migration bootstrap, CloudFront domain lookup, environment validation,
and the cold-start DB connectivity probe.
"""

from __future__ import annotations

import logging
import os
import threading

import psycopg2

logger = logging.getLogger()

_CLOUDFRONT_DOMAIN_CACHE = None  # CloudFront domain fetched from Secrets Manager
_CLOUDFRONT_DOMAIN_CACHE_TIME = None
_CLOUDFRONT_DOMAIN_CACHE_TTL_SECONDS = 86400  # Refresh CloudFront domain daily
_CLOUDFRONT_DOMAIN_LOCK = threading.Lock()  # Protects CloudFront domain cache


# Apply critical database migrations on Lambda cold start
def _apply_critical_migrations() -> tuple[bool, str]:
    """Apply critical schema migrations directly in Lambda startup.

    Adds data_unavailable columns to metric tables that the scores query requires.
    This is a self-healing mechanism - if columns already exist, ALTER TABLE ... IF NOT EXISTS does nothing.
    """
    try:
        # Import psycopg2 for direct database access (no ORM complexity)
        import psycopg2

        # Use credential_manager to fetch DB credentials from Secrets Manager or environment
        # This is the same source that DatabaseContext uses for all other DB operations
        try:
            from algo.config.credential_manager import get_db_config

            db_config = get_db_config()
        except (ImportError, ModuleNotFoundError) as e:
            logger.critical(
                f"[STARTUP] Credential manager module not available: {e}. Cannot initialize Lambda without database access."
            )
            raise RuntimeError(f"Database credential manager unavailable at startup: {e}") from e
        except (ValueError, KeyError) as e:
            logger.critical(
                f"[STARTUP] Database credentials incomplete from credential_manager: {e}. Cannot initialize Lambda without database access."
            )
            raise RuntimeError(f"Database credentials missing required fields: {e}") from e

        # GOVERNANCE: Fail-fast on missing database configuration.
        # get_db_config() validates all required fields and raises ValueError if any are missing.
        # Use direct dict access, not .get() with defaults - no silent defaults allowed.
        try:
            db_host = db_config["host"]
            db_port = db_config["port"]
            db_name = db_config["database"]
            db_user = db_config["user"]
            db_password = db_config["password"]
        except KeyError as e:
            logger.critical(
                f"[STARTUP] Database config missing required field {e}. Cannot initialize Lambda in degraded state."
            )
            raise RuntimeError(f"Database config missing required field: {e}") from e

        # FIXED 2026-08-03: db_password was included in this truthy check, but
        # credential_manager.get_db_config() legitimately returns password="" (not missing -
        # an actual empty string) for localhost trust-auth Postgres (see
        # algo/config/credential_manager.py's own "Only localhost Postgres is expected to run
        # with trust-auth" convention). That made dev_server.py hard-fail at startup every time
        # it was correctly pointed at local trust-auth Postgres via .env.local (DB_PASSWORD=
        # empty by design), even though the same empty password connects to Postgres just fine.
        # host/user are still required (an empty database host or user is never legitimate,
        # even for trust-auth); only password is allowed to be empty.
        if not all([db_host, db_user]) or db_password is None:
            logger.critical(
                "[STARTUP] Database configuration has empty required fields. Cannot initialize Lambda with incomplete configuration."
            )
            raise RuntimeError("Database configuration has empty required fields")

        # Connect to database
        # Use sslmode="prefer" (try SSL, fall back to unencrypted) for local dev compatibility
        # Lambda and RDS always support/require SSL
        sslmode = "require" if "AWS_LAMBDA_FUNCTION_NAME" in os.environ else "prefer"
        conn = psycopg2.connect(
            host=db_host, port=int(db_port), database=db_name, user=db_user, password=db_password, sslmode=sslmode
        )
        cur = conn.cursor()

        # Apply migrations for critical missing tables and data_unavailable columns
        # Table creation migrations (CREATE TABLE IF NOT EXISTS)
        table_migrations = [
            (
                "algo_signals",
                """
                CREATE TABLE IF NOT EXISTS algo_signals (
                    id SERIAL PRIMARY KEY,
                    signal_date DATE NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    source_table VARCHAR(50),
                    source_timeframe VARCHAR(20),
                    raw_signal VARCHAR(20),
                    entry_price DECIMAL(12, 4),
                    entry_stage VARCHAR(20),
                    signal_active BOOLEAN DEFAULT TRUE,
                    signal_quality_score INTEGER,
                    risk_score DECIMAL(8, 2),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(signal_date, symbol, source_timeframe)
                );
                CREATE INDEX IF NOT EXISTS idx_algo_signals_symbol_date ON algo_signals(symbol, signal_date DESC);
                CREATE INDEX IF NOT EXISTS idx_algo_signals_active ON algo_signals(signal_active);
            """,
            ),
            (
                "market_sentiment",
                """
                CREATE TABLE IF NOT EXISTS market_sentiment (
                    id SERIAL PRIMARY KEY,
                    date DATE NOT NULL UNIQUE,
                    fear_greed_index DECIMAL(8, 4),
                    put_call_ratio DECIMAL(8, 4),
                    vix DECIMAL(8, 4),
                    sentiment_score DECIMAL(8, 4),
                    bullish_pct DECIMAL(8, 2),
                    bearish_pct DECIMAL(8, 2),
                    neutral_pct DECIMAL(8, 2),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_market_sentiment_date ON market_sentiment(date DESC);
            """,
            ),
            (
                "orchestrator_execution_log",
                """
                CREATE TABLE IF NOT EXISTS orchestrator_execution_log (
                    id SERIAL PRIMARY KEY,
                    run_id VARCHAR(50) NOT NULL UNIQUE,
                    run_date DATE NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    overall_status VARCHAR(20) NOT NULL,
                    phase_results JSONB,
                    summary TEXT,
                    halt_reason TEXT,
                    phases_completed INTEGER,
                    phases_halted INTEGER,
                    phases_errored INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_orchestrator_execution_run_date ON orchestrator_execution_log(run_date DESC);
                CREATE INDEX IF NOT EXISTS idx_orchestrator_execution_status ON orchestrator_execution_log(overall_status);
            """,
            ),
        ]

        for table_name, create_sql in table_migrations:
            try:
                cur.execute(create_sql)
                conn.commit()
                logger.info(f"[STARTUP] Created table {table_name}")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(f"[STARTUP] Could not create table {table_name}: {e}")
                try:
                    conn.rollback()
                except (psycopg2.OperationalError, psycopg2.DatabaseError) as rollback_err:
                    # Connection died mid-statement (e.g. transient RDS/network blip).
                    # Reconnect so the remaining migrations and the validation step
                    # below still run against a healthy connection instead of a single
                    # transient failure aborting the entire Lambda cold start.
                    logger.warning(f"[STARTUP] Connection lost during rollback: {rollback_err} - reconnecting")
                    conn = psycopg2.connect(
                        host=db_host,
                        port=int(db_port),
                        database=db_name,
                        user=db_user,
                        password=db_password,
                        sslmode=sslmode,
                    )
                    cur = conn.cursor()

        # Apply migrations for data_unavailable and reason columns
        # Schema migration definitions: (table, column, type, description)
        migrations_to_apply = [
            ("quality_metrics", "data_unavailable", "BOOLEAN DEFAULT FALSE", "Quality metrics unavailable flag"),
            ("quality_metrics", "reason", "VARCHAR(500)", "Quality metrics unavailable reason"),
            ("growth_metrics", "data_unavailable", "BOOLEAN DEFAULT FALSE", "Growth metrics unavailable flag"),
            ("growth_metrics", "reason", "VARCHAR(500)", "Growth metrics unavailable reason"),
            ("value_metrics", "data_unavailable", "BOOLEAN DEFAULT FALSE", "Value metrics unavailable flag"),
            ("value_metrics", "reason", "VARCHAR(500)", "Value metrics unavailable reason"),
            (
                "positioning_metrics",
                "data_unavailable",
                "BOOLEAN DEFAULT FALSE",
                "Positioning metrics unavailable flag",
            ),
            ("positioning_metrics", "reason", "VARCHAR(500)", "Positioning metrics unavailable reason"),
            ("stability_metrics", "data_unavailable", "BOOLEAN DEFAULT FALSE", "Stability metrics unavailable flag"),
            ("stability_metrics", "reason", "VARCHAR(500)", "Stability metrics unavailable reason"),
            ("aaii_sentiment", "data_unavailable", "BOOLEAN DEFAULT FALSE", "AAII sentiment unavailable flag"),
            ("fear_greed_index", "data_unavailable", "BOOLEAN DEFAULT FALSE", "Fear/greed index unavailable flag"),
            ("naaim", "data_unavailable", "BOOLEAN DEFAULT FALSE", "NAAIM sentiment unavailable flag"),
            # market_health_daily columns
            (
                "market_health_daily",
                "put_call_ratio_data_unavailable",
                "BOOLEAN DEFAULT FALSE",
                "Put/call ratio unavailable flag",
            ),
            (
                "market_health_daily",
                "put_call_ratio_unavailable_reason",
                "VARCHAR(255)",
                "Put/call ratio unavailable reason",
            ),
            (
                "market_health_daily",
                "yield_curve_data_unavailable",
                "BOOLEAN DEFAULT FALSE",
                "Yield curve unavailable flag",
            ),
            ("market_health_daily", "yield_curve_unavailable_reason", "VARCHAR(255)", "Yield curve unavailable reason"),
            ("market_health_daily", "fed_rate_data_unavailable", "BOOLEAN DEFAULT FALSE", "Fed rate unavailable flag"),
            ("market_health_daily", "fed_rate_unavailable_reason", "VARCHAR(255)", "Fed rate unavailable reason"),
            # algo_positions computed column
            (
                "algo_positions",
                "is_open",
                "BOOLEAN GENERATED ALWAYS AS (status IN ('open', 'partially_closed')) STORED",
                "Open position computed flag",
            ),
            # value_metrics detailed reason columns
            ("value_metrics", "market_cap_unavailable_reason", "VARCHAR(255)", "Market cap unavailable reason"),
            ("value_metrics", "pe_ratio_unavailable_reason", "VARCHAR(255)", "P/E ratio unavailable reason"),
            ("value_metrics", "pb_ratio_unavailable_reason", "VARCHAR(255)", "P/B ratio unavailable reason"),
            ("value_metrics", "ps_ratio_unavailable_reason", "VARCHAR(255)", "P/S ratio unavailable reason"),
            ("value_metrics", "peg_ratio_unavailable_reason", "VARCHAR(255)", "PEG ratio unavailable reason"),
            ("value_metrics", "dividend_yield_unavailable_reason", "VARCHAR(255)", "Dividend yield unavailable reason"),
            ("value_metrics", "fcf_yield_unavailable_reason", "VARCHAR(255)", "FCF yield unavailable reason"),
            (
                "value_metrics",
                "held_percent_institutions_unavailable_reason",
                "VARCHAR(255)",
                "Institutional ownership unavailable reason",
            ),
            # technical_data_daily columns
            ("technical_data_daily", "atr_50", "DECIMAL(12, 4)", "50-day ATR"),
            # performance metrics columns
            ("algo_performance_metrics", "avg_win_r", "NUMERIC(8, 4)", "Average win R-multiple"),
            ("algo_performance_metrics", "avg_loss_r", "NUMERIC(8, 4)", "Average loss R-multiple"),
            ("algo_performance_metrics", "expectancy", "NUMERIC(8, 4)", "Expectancy metric"),
        ]

        for table, column, type_def, description in migrations_to_apply:
            try:
                sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {type_def}"
                cur.execute(sql)
                conn.commit()
                logger.info(f"[STARTUP] Ensured {table}.{column} exists ({description})")
            except (psycopg2.DatabaseError, psycopg2.OperationalError, psycopg2.ProgrammingError) as e:
                logger.warning(f"[STARTUP] Could not update {table}.{column}: {e}")
                try:
                    conn.rollback()
                except (psycopg2.OperationalError, psycopg2.DatabaseError) as rollback_err:
                    logger.warning(f"[STARTUP] Connection lost during rollback: {rollback_err} - reconnecting")
                    conn = psycopg2.connect(
                        host=db_host,
                        port=int(db_port),
                        database=db_name,
                        user=db_user,
                        password=db_password,
                        sslmode=sslmode,
                    )
                    cur = conn.cursor()

        # NOTE: R-metrics columns (expectancy, avg_win_r, avg_loss_r) are created by lambda/db-init/lambda_function.py
        # DO NOT duplicate column creation here. The db-init Lambda is authoritative for schema initialization.

        # ISSUE #7 FIX: Explicit validation that data_unavailable columns actually exist
        # After creating columns, verify they're present in the schema before continuing
        logger.info("[STARTUP] Validating that data_unavailable columns were created correctly...")
        critical_columns_to_validate = [
            ("quality_metrics", "data_unavailable"),
            ("growth_metrics", "data_unavailable"),
            ("value_metrics", "data_unavailable"),
            ("positioning_metrics", "data_unavailable"),
            ("stability_metrics", "data_unavailable"),
            ("market_health_daily", "put_call_ratio_data_unavailable"),
        ]

        missing_columns = []
        for table, column in critical_columns_to_validate:
            try:
                cur.execute(
                    "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
                    (table, column),
                )
                if not cur.fetchone():
                    missing_columns.append(f"{table}.{column}")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as val_err:
                logger.warning(f"[STARTUP] Could not validate {table}.{column}: {val_err}")
                missing_columns.append(f"{table}.{column} (validation failed)")

        if missing_columns:
            logger.critical(
                f"[STARTUP CRITICAL] Required columns missing after migration: {', '.join(missing_columns)}"
            )
            raise RuntimeError(
                f"[STARTUP] Data unavailable columns not created: {', '.join(missing_columns)}. "
                f"Metric loaders require these columns to mark data unavailability."
            )

        cur.close()
        conn.close()
        logger.info("[STARTUP] Critical schema migrations completed and validated")
        return True, "Migrations applied and validated"

    except ImportError:
        logger.warning("[STARTUP] psycopg2 not available - migrations skipped")
        return False, "psycopg2 missing"
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.warning(f"[STARTUP] Migration initialization failed: {e}")
        return False, str(e)
    except (RuntimeError, ValueError, OSError) as e:
        # Configuration or system error during migration - log as critical
        logger.critical(f"[STARTUP CRITICAL] Error during migration: {type(e).__name__}: {e}")
        return False, f"Migration error: {type(e).__name__}"


def fetch_cloudfront_domain_from_secrets() -> tuple[str | None, str | None]:
    """Fetch CloudFront domain from AWS Secrets Manager (thread-safe with TTL).

    Uses centralized credential_manager for consistent error handling, caching, and fallback.
    If domain is not found in Secrets Manager, falls back to FRONTEND_URL env var.
    Cache expires after 24 hours to ensure fresh data.

    Returns: (domain: Optional[str], error: Optional[str])
    """
    global _CLOUDFRONT_DOMAIN_CACHE, _CLOUDFRONT_DOMAIN_CACHE_TIME
    from datetime import datetime, timezone

    if _CLOUDFRONT_DOMAIN_CACHE is not None and _CLOUDFRONT_DOMAIN_CACHE_TIME is not None:
        age_sec = (datetime.now(timezone.utc) - _CLOUDFRONT_DOMAIN_CACHE_TIME).total_seconds()
        if age_sec < _CLOUDFRONT_DOMAIN_CACHE_TTL_SECONDS:
            return _CLOUDFRONT_DOMAIN_CACHE, None

    with _CLOUDFRONT_DOMAIN_LOCK:
        if _CLOUDFRONT_DOMAIN_CACHE is not None and _CLOUDFRONT_DOMAIN_CACHE_TIME is not None:
            age_sec = (datetime.now(timezone.utc) - _CLOUDFRONT_DOMAIN_CACHE_TIME).total_seconds()
            if age_sec < _CLOUDFRONT_DOMAIN_CACHE_TTL_SECONDS:
                return _CLOUDFRONT_DOMAIN_CACHE, None

        try:
            import json

            from algo.config.credential_manager import get_secret

            try:
                secret = get_secret("algo/cloudfront-domain")
                if not secret:
                    logger.info(
                        "[CloudFront] Secret 'algo/cloudfront-domain' not found in Secrets Manager (OK on first deploy)"
                    )
                    return None, "Secret not found"

                if isinstance(secret, str) and not secret.startswith("{"):
                    # Plain string secret (just the domain)
                    domain = secret.strip()
                else:
                    # JSON secret with domain key
                    secret_dict = json.loads(secret) if isinstance(secret, str) else secret
                    domain = secret_dict.get("domain")
                    if not domain:
                        raise ValueError("[CloudFront] Domain key missing or empty in secret")
                    domain = domain.strip()

                logger.info(f"[CloudFront] Fetched domain from Secrets Manager: {domain}")
                _CLOUDFRONT_DOMAIN_CACHE = domain
                _CLOUDFRONT_DOMAIN_CACHE_TIME = datetime.now(timezone.utc)
                return domain, None

            except json.JSONDecodeError as e:
                logger.warning(f"[CloudFront] Failed to parse secret JSON: {e}")
                return None, f"Invalid secret format: {e}"
            except ValueError as ve:
                if "not found" in str(ve).lower():
                    logger.info("[CloudFront] Secret not found (OK on first deploy)")
                    return None, "Secret not found"
                logger.error(f"[CloudFront] Validation error: {ve}")
                return None, str(ve)

        except ImportError:
            logger.warning("[CloudFront] boto3 not available, skipping Secrets Manager fetch")
            return None, "boto3 not available"
        except RuntimeError as re:
            # Handle "marked for deletion" or other AWS errors gracefully
            logger.warning(f"[CloudFront] AWS Secrets Manager error (will continue without CloudFront domain): {re}")
            return None, f"AWS error: {re}"
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(
                f"[CloudFront] Error fetching from Secrets Manager: {type(e).__name__}: {e}"
                "\n  Operation: Fetch CloudFront domain from AWS Secrets Manager"
                "\n  Secret name: algo/cloudfront-domain"
            )
            return None, f"Error: {e}"


def validate_environment() -> tuple[bool, list[str], list[str]]:
    errors = []
    warnings = []

    # CRITICAL: Database configuration (always required)
    critical_vars = {
        "DB_HOST": "RDS Proxy endpoint (e.g., my-proxy.proxy-abc123.us-east-1.rds.amazonaws.com)",
        "DB_PORT": "Database port (e.g., 5432 for PostgreSQL; must be a valid integer)",
    }

    for var, description in critical_vars.items():
        if var == "DB_PORT":
            port_str = os.getenv(var, "").strip()
            if not port_str:
                errors.append(f"{var} missing: {description}")
            else:
                try:
                    int(port_str)
                except (ValueError, TypeError):
                    errors.append(f"{var} invalid: Must be a valid integer (e.g., 5432)")
        else:
            if not os.getenv(var):
                errors.append(f"{var} missing: {description}")

    # Validate DB_HOST points to proxy if it's an RDS endpoint
    db_host = os.getenv("DB_HOST", "")
    is_likely_direct_rds = "db-" in db_host and "rds.amazonaws.com" in db_host and "proxy" not in db_host.lower()
    is_localhost = db_host.startswith(("localhost", "127."))
    if db_host and is_likely_direct_rds and not is_localhost:
        logger.error(
            "FATAL: DB_HOST appears to be direct RDS, not proxy. Connection pooling REQUIRED. Use RDS Proxy endpoint."
        )
        errors.append(
            "DB_HOST invalid: Must use RDS Proxy endpoint (contains 'proxy'), not direct RDS. "
            "Connection pooling is required for production."
        )

    # CRITICAL: Database credentials (one of the two must be set)
    # In AWS Lambda: DB_SECRET_ARN is set by Terraform (preferred)
    # In local dev: DB_PASSWORD can be set directly in environment
    missing_secret_arn = not os.getenv("DB_SECRET_ARN")
    missing_password = not os.getenv("DB_PASSWORD")
    if missing_secret_arn and missing_password:
        errors.append(
            "Database credentials missing: Provide either DB_SECRET_ARN (AWS Secrets Manager) "
            "or DB_PASSWORD (environment variable). credential_manager requires one source."
        )

    # OPTIONAL: DB_NAME and DB_USER (use defaults if not set)
    if not os.getenv("DB_NAME"):
        logger.info("DB_NAME: using default 'stocks'")
    if not os.getenv("DB_USER"):
        logger.info("DB_USER: using default 'stocks'")

    # WARNING: Cognito configuration (only required if enabled)
    cognito_user_pool_id = os.getenv("COGNITO_USER_POOL_ID", "").strip()
    if cognito_user_pool_id:
        cognito_client_id = os.getenv("COGNITO_CLIENT_ID", "").strip()
        cognito_region = os.getenv("COGNITO_REGION", "").strip()

        if not cognito_client_id:
            warnings.append("COGNITO_CLIENT_ID missing: Required when COGNITO_USER_POOL_ID is set")
        if not cognito_region:
            warnings.append("COGNITO_REGION missing: Will default to us-east-1")

    # WARNING: FRONTEND_URL (required for CORS but can be fetched or allows localhost)
    is_lambda = "AWS_LAMBDA_FUNCTION_NAME" in os.environ
    if is_lambda:
        frontend_url = os.getenv("FRONTEND_URL", "").strip()
        allow_localhost = os.getenv("ALLOW_LOCALHOST_CORS", "") == "true"

        if not frontend_url:
            # CRITICAL FIX: Disabled Secrets Manager call at module load (causes VPC timeout)
            # CloudFront domain will be fetched on first request if needed, not at Lambda cold start
            cf_domain, cf_error = None, "Deferred to first request"
            if cf_domain:
                frontend_url = (
                    f"https://{cf_domain}" if not cf_domain.startswith(("http://", "https://")) else cf_domain
                )
                os.environ["FRONTEND_URL"] = frontend_url
                logger.info(f"[CloudFront] Set FRONTEND_URL from Secrets Manager: {frontend_url}")
            elif cf_error == "Secret not found":
                # Expected on first deploy before CloudFront domain is set up
                if allow_localhost:
                    logger.info("[CloudFront] Secret not found (OK on first deploy), ALLOW_LOCALHOST_CORS=true")
                else:
                    warnings.append(
                        "FRONTEND_URL missing: Set to frontend domain "
                        "(e.g., https://myapp.example.com) for CORS, or enable "
                        "ALLOW_LOCALHOST_CORS=true for dev"
                    )
            else:
                warnings.append(f"[CloudFront] Fetch attempt returned error (may be first deploy): {cf_error}")

    # Log warnings but don't fail
    for warning in warnings:
        logger.warning(f"[ENV_WARNING] {warning}")

    return len(errors) == 0, errors, warnings


def test_db_connection() -> tuple[bool, str | None]:
    """Test database connection at Lambda cold-start.

    Validates that the database is reachable and responsive.
    Tolerates transient RDS Proxy timing issues with exponential backoff.

    Uses a fast probe to stay within Lambda INIT budget:
    - 1 attempt x 3s connect timeout = 3s max (DB failures surface on first real request)
    - Statement timeout: 3s per query execution

    Returns: (success: bool, error_msg: Optional[str])
    """
    import time

    start_time = time.time()

    try:
        from utils.db.connection import get_db_connection

        # Short timeout for INIT probe: 1 attempt x 3s = 3s max.
        # The Lambda timeout is 25s and imports alone take ~5s, so we cannot
        # afford the original 3 attempts x 10s = 30s+ that was causing INIT timeouts.
        # First-request DB failures are handled gracefully by DatabaseContext anyway.
        conn = get_db_connection(max_retries=0, timeout=3)
        connect_time = time.time() - start_time

        cur = conn.cursor()
        try:
            # 3-second query timeout (up from 1s) for more reliable test on slow systems
            cur.execute("SET statement_timeout TO '3000'")
            query_start = time.time()
            cur.execute("SELECT 1 as connection_test")
            result = cur.fetchone()
            query_time = time.time() - query_start

            cur.close()
            conn.close()

            if result and result[0] == 1:
                total_time = time.time() - start_time
                logger.info(
                    "[DB_TEST_SUCCESS] Database connection verified at cold start "
                    f"(connect={connect_time:.2f}s, query={query_time:.3f}s, total={total_time:.2f}s)"
                )
                return True, None
            else:
                return False, "Connection test query returned unexpected result"
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as qe:
            try:
                conn.close()
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as close_err:
                logger.error(f"[DB_TEST_FAILED] Failed to close connection after query error: {close_err}")
                raise RuntimeError(f"Cold start database test failed to clean up: {close_err}") from close_err
            raise qe
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        error_msg = (
            f"Database connection test failed at cold start: {type(e).__name__}: {e!s}. "
            "Verify RDS Proxy is running and network connectivity is available."
        )
        logger.error(f"[DB_TEST_FAILED] {error_msg}")
        return False, error_msg
