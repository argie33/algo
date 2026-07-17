#!/usr/bin/env python3
"""
Lambda handler for the Algo Orchestrator.

Wraps the 7-phase orchestrator in a Lambda-compatible handler.
Supports both scheduled execution (EventBridge) and manual invocation (test-and-debug.yml).
"""

import json
import logging
import os
import sys
from datetime import date as _date
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2

# Setup logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

# Add Lambda layer path and project root to sys.path
# In Lambda: code is in /var/task, layers are in /opt/python
# In local dev: code is in project root
if os.path.exists("/opt/python"):
    sys.path.insert(0, "/opt/python")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import the orchestrator
from algo.orchestration import Orchestrator  # noqa: E402


def _load_alpaca_credentials_from_secrets() -> None:
    """Load Alpaca API credentials from AWS Secrets Manager into environment.

    CRITICAL: Must be called before orchestrator initialization to ensure
    credentials are available for live trading validation in phase 1.

    The algo/alpaca secret contains (Terraform-managed, see config/credential_manager.py):
    - APCA_API_KEY_ID: Alpaca API key
    - APCA_API_SECRET_KEY: Alpaca API secret

    These are loaded into environment variables:
    - APCA_API_KEY_ID
    - APCA_API_SECRET_KEY
    """
    import json

    # Skip if already loaded (e.g., local development)
    if os.environ.get("APCA_API_KEY_ID"):
        logger.debug("Alpaca credentials already in environment, skipping AWS Secrets load")
        return

    try:
        import boto3

        sm = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION", "us-east-1"))

        # Try both secret names: algo-algo-secrets-dev (current) and algo/alpaca (future Terraform)
        secret = None
        tried_secrets = []
        for secret_id in ["algo-algo-secrets-dev", "algo/alpaca"]:
            tried_secrets.append(secret_id)
            try:
                secret = sm.get_secret_value(SecretId=secret_id)
                logger.debug(f"[CREDENTIALS] Found credentials in {secret_id}")
                break
            except Exception:
                continue

        if not secret:
            raise ValueError(f"Alpaca credentials not found in any secret: {tried_secrets}")

        data = json.loads(secret["SecretString"])
        os.environ["APCA_API_KEY_ID"] = data["APCA_API_KEY_ID"]
        os.environ["APCA_API_SECRET_KEY"] = data["APCA_API_SECRET_KEY"]
        logger.info("[CREDENTIALS] Loaded Alpaca API credentials from AWS Secrets Manager")
    except Exception as e:
        logger.warning(
            f"[CREDENTIALS] Could not load Alpaca credentials from AWS Secrets Manager: {type(e).__name__}. "
            f"Will fall back to environment variables or paper trading mode. Error: {e}"
        )


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    """
    Lambda entry point for Algo Orchestrator.

    Event payload (optional):
    {
        "source": "test-live-execution",
        "test": "true",
        "timeout": 120,
        "dry_run": false,
        "date": "2026-05-23"
    }

    Returns:
        {
            "statusCode": 200 | 500,
            "body": {
                "status": "success" | "error",
                "message": "...",
                "run_id": "...",
                "phases": {...},
                "source": "..."
            }
        }
    """

    # CRITICAL: Load Alpaca credentials from AWS Secrets Manager FIRST
    # Must happen BEFORE environment validation, so credentials are available
    _load_alpaca_credentials_from_secrets()

    source = "unknown"
    try:
        # Load environment variables

        # FIXED Issue #8: Validate incoming event structure for EventBridge
        if not event:
            event = {}
        if not isinstance(event, dict):
            logger.error(f"Invalid event type: {type(event)}. Expected dict.")
            return {
                "statusCode": 400,
                "body": json.dumps({"status": "error", "message": "Event must be a JSON object"}),
            }

        # FIXED Issue #1: Parse event execution_mode BEFORE validation
        # EventBridge scheduler passes execution_mode in payload, not as Lambda env var
        event_execution_mode = event.get("execution_mode", "").strip().lower()
        if event_execution_mode and event_execution_mode in ("paper", "live", "auto"):
            # Set environment variable from event so validator will pass
            os.environ["ORCHESTRATOR_EXECUTION_MODE"] = event_execution_mode
            logger.info(f"[EXECUTION_MODE] Set from event payload: {event_execution_mode}")

        # PHASE 3 FIX: Validate environment variables AFTER setting from event
        # This catches missing config but allows EventBridge scheduler to inject via payload
        from algo.config.environment_validation import EnvironmentValidator

        EnvironmentValidator.require_valid_or_halt("lambda_handler")

        # Reset config singleton on invocation to load fresh DB config
        from algo.infrastructure import reset_config

        reset_config()

        # Price seeding moved to separate test Lambda: algo-test-seed-prices-dev
        # Production orchestrator Lambda should not accept seed_prices
        if event.get("seed_prices"):
            raise RuntimeError(
                "[SEED_PRICES_REJECTED] Price seeding has been moved to a separate test Lambda function. "
                "Use 'algo-test-seed-prices-dev' for price seeding in development. "
                "The production orchestrator Lambda no longer accepts seed_prices in events. "
                "This change improves separation of concerns and prevents accidental data injection."
            )

        # Parse event payload
        source = event.get("source", "eventbridge")
        # CRITICAL FIX: Explicit check for test flag instead of silent conversion
        is_test = event.get("test")
        if is_test is None:
            is_test = False
        elif not isinstance(is_test, bool):
            raise ValueError(
                f"CRITICAL: Event 'test' field must be boolean, got {type(is_test).__name__}: {is_test!r}. "
                f"Orchestrator mode (test/production) must be explicitly specified as boolean. "
                f"Silent conversion of {is_test!r} to bool could hide configuration errors."
            )

        # ORCHESTRATOR_DRY_RUN env var (set by Terraform) is the baseline.
        # Event payload 'dry_run' key overrides it for manual invocations.
        env_dry_run = os.getenv("ORCHESTRATOR_DRY_RUN", "false").strip().lower() in (
            "true",
            "1",
            "yes",
        )
        dry_run = event["dry_run"] if "dry_run" in event else env_dry_run

        # Support both 'date' and 'run_date' fields from EventBridge; treat 'now'/'today' as None (use today's date)
        run_date_str = event.get("date")
        if run_date_str is None:
            run_date_str = event.get("run_date")

        # Parse run_identifier from EventBridge Scheduler to determine run purpose
        # Issue #15: dry_run should be explicit; default based on run_identifier only if not specified
        run_identifier = event.get("run_identifier")
        dry_run_raw = event.get("dry_run")

        # Determine dry_run: explicit event value takes priority over run_identifier defaults
        if dry_run_raw is not None:
            # Explicit value provided - use it; run_identifier optional (used for logging only)
            dry_run = bool(dry_run_raw)
            if not run_identifier:
                run_identifier = "manual"
        else:
            # No explicit dry_run - run_identifier is required to determine trading mode
            if not run_identifier:
                logger.error("run_identifier is required when dry_run is not explicitly set")
                return {
                    "statusCode": 400,
                    "body": json.dumps({"error": "run_identifier required (or set dry_run explicitly)"}),
                }
            # Validate run_identifier for traceability
            if not isinstance(run_identifier, str) or not run_identifier.strip():
                raise ValueError(
                    "[CRITICAL] Invalid 'run_identifier' in orchestration event. "
                    "Must be a non-empty string for traceability. "
                    f"Got: {run_identifier!r}"
                )
            # Map run_identifier to dry_run mode:
            # Live-trading runs execute real orders (paper or live per execution_mode)
            # Dry-run/monitor runs generate signals for review but do not submit orders
            live_trading_ids = {"morning", "afternoon", "preclose", "premarket"}
            monitor_ids = {"evening", "default", "prewarm", "manual"}
            if run_identifier in live_trading_ids:
                dry_run = False
            elif run_identifier in monitor_ids:
                dry_run = True
            else:
                # Unknown identifier - fail safe: observe-only, no trades
                logger.warning(
                    f"Unknown run_identifier: '{run_identifier}' - defaulting to dry_run=True (safe mode). "
                    "Add it to _LIVE_TRADING_IDS or _MONITOR_IDS to suppress this warning."
                )
                dry_run = True

        # ISSUE #5 FIX: Explicit execution mode validation and enforcement
        # Execution mode determines whether trades are paper (test) or live (real money)
        # At this point, ORCHESTRATOR_EXECUTION_MODE is already set (from event or Lambda env)
        execution_mode = os.getenv("ORCHESTRATOR_EXECUTION_MODE", "").strip().lower()
        if not execution_mode:
            logger.critical(
                "[EXECUTION_MODE_MISSING] ORCHESTRATOR_EXECUTION_MODE environment variable is not set. "
                "This should not happen - EnvironmentValidator should have caught this."
            )
            raise ValueError(
                "[CONFIG] ORCHESTRATOR_EXECUTION_MODE environment variable is required and must be set to 'paper', 'live', or 'auto'. "
                "Refusing to proceed without explicit execution mode configuration."
            )

        # FIXED: Allow "auto" mode like orchestrator does (in addition to paper/live)
        if execution_mode not in ("paper", "live", "auto"):
            logger.critical(f"[EXECUTION_MODE_VALIDATION_FAILED] Final execution_mode invalid: {execution_mode}")
            raise ValueError(
                f"[CONFIG] Execution mode validation failed - final mode '{execution_mode}' is invalid. "
                "This should never happen if environment variable is set correctly."
            )

        logger.info(f"[EXECUTION_MODE] Running in {execution_mode} mode")

        # ISSUE #2 FIX: Explicit DynamoDB halt flag check at Lambda entry point
        # Fail-fast before orchestrator initialization if emergency halt flag is set
        # This ensures no trades occur when halt flag is active, regardless of orchestrator logic
        if not dry_run:
            try:
                import boto3

                dynamodb = boto3.resource("dynamodb")
                table = dynamodb.Table(os.environ.get("HALT_FLAG_TABLE", "algo_orchestrator_state"))
                response = table.get_item(Key={"key": "orchestrator_halt"})

                if "Item" in response:
                    item = response["Item"]
                    if item.get("halt_flag") is True:
                        # PROACTIVE CLEAR: Auto-clear halt flag if from prior trading day
                        # Prevents deadlock where data staleness is fixed but halt remains
                        # This mirrors halt_flag_manager.py logic that orchestrator.py uses
                        from datetime import date as dt_date
                        triggered_at_str = item.get("triggered_at", "")
                        try:
                            if triggered_at_str:
                                # Parse ISO format timestamp with timezone handling
                                if triggered_at_str.endswith("Z"):
                                    triggered_dt = datetime.fromisoformat(triggered_at_str[:-1] + "+00:00")
                                else:
                                    triggered_dt = datetime.fromisoformat(triggered_at_str)
                                # Convert to ET for comparison
                                from zoneinfo import ZoneInfo
                                triggered_et_date = triggered_dt.astimezone(ZoneInfo("America/New_York")).date()
                                current_et_date = dt_date.today()

                                if triggered_et_date < current_et_date:
                                    # Halt is from prior trading day - clear it and continue
                                    try:
                                        table.delete_item(Key={"key": "orchestrator_halt"})
                                        logger.info(
                                            f"[PROACTIVE_CLEAR] Halt from {triggered_et_date} (today: {current_et_date}) "
                                            f"- cleared stale halt flag"
                                        )
                                        # Don't halt - continue with orchestrator execution
                                    except Exception as clear_err:
                                        logger.warning(f"[PROACTIVE_CLEAR_FAILED] Could not clear stale halt: {clear_err}")
                                        # If we can't clear, proceed anyway since it's stale
                                        logger.info("[PROACTIVE_CLEAR] Proceeding despite clear failure (halt is stale)")
                                else:
                                    # Halt is from today - respect it
                                    halt_reason = item.get("reason", "Emergency halt flag set in DynamoDB")
                                    logger.critical(f"[HALT_FLAG_DETECTED] Trading halted: {halt_reason}")
                                    return {
                                        "statusCode": 503,
                                        "body": json.dumps(
                                            {
                                                "status": "halted",
                                                "message": f"Trading halted by emergency halt flag: {halt_reason}",
                                                "source": source,
                                                "halt_timestamp": item.get("triggered_at"),
                                            }
                                        ),
                                    }
                            else:
                                halt_reason = item.get("reason", "Emergency halt flag set in DynamoDB")
                                logger.critical(f"[HALT_FLAG_DETECTED] Trading halted: {halt_reason}")
                                return {
                                    "statusCode": 503,
                                    "body": json.dumps(
                                        {
                                            "status": "halted",
                                            "message": f"Trading halted by emergency halt flag: {halt_reason}",
                                            "source": source,
                                            "halt_timestamp": item.get("triggered_at"),
                                        }
                                    ),
                                }
                        except Exception as parse_err:
                            logger.warning(f"[PROACTIVE_CLEAR] Could not parse halt timestamp: {parse_err}")
                            # If we can't parse, respect the halt for safety
                            halt_reason = item.get("reason", "Emergency halt flag set in DynamoDB")
                            logger.critical(f"[HALT_FLAG_DETECTED] Trading halted: {halt_reason}")
                            return {
                                "statusCode": 503,
                                "body": json.dumps(
                                    {
                                        "status": "halted",
                                        "message": f"Trading halted by emergency halt flag: {halt_reason}",
                                        "source": source,
                                        "halt_timestamp": item.get("triggered_at"),
                                    }
                                ),
                            }
            except Exception as halt_err:
                logger.critical(f"[HALT_CHECK_FAILED] Could not verify halt flag in DynamoDB: {halt_err}")
                # Fail-closed: if we can't verify halt status, assume halt for safety
                return {
                    "statusCode": 503,
                    "body": json.dumps(
                        {
                            "status": "halted",
                            "message": f"Could not verify halt status - assuming halt for safety: {halt_err!s}",
                            "source": source,
                        }
                    ),
                }

        # CONSOLIDATED: Single halt flag system using DynamoDB (managed by orchestrator.py)
        # Removed redundant Secrets Manager halt check - orchestrator.py already handles circuit breaker
        # state via DynamoDB algo_orchestrator_state table. This prevents dual-system confusion.

        logger.info(
            f"Orchestrator invoked: source={source}, is_test={is_test}, dry_run={dry_run}, execution_mode={execution_mode}, run_identifier={run_identifier}"
        )
        # Track startup success status for metrics
        if not is_test:
            logger.debug("[LAMBDA_STATUS] Orchestrator startup: statusCode will reflect success state")
        # Startup diagnostic: surface critical config state in every CloudWatch log
        logger.info(
            f"[CONFIG] ORCHESTRATOR_DRY_RUN={os.getenv('ORCHESTRATOR_DRY_RUN', '<unset>')} "
            f"ORCHESTRATOR_EXECUTION_MODE={os.getenv('ORCHESTRATOR_EXECUTION_MODE', '<unset>')} "
            f"ALPACA_PAPER_TRADING={os.getenv('ALPACA_PAPER_TRADING', '<unset>')} "
            f"APCA_API_BASE_URL={os.getenv('APCA_API_BASE_URL', '<unset>')} "
            f"ALGO_LIVE_TRADING={'SET' if os.getenv('ALGO_LIVE_TRADING') else 'NOT SET'}"
        )

        # Ensure database tables exist and have required columns (idempotent - safe on every startup)
        try:
            from utils.db.context import DatabaseContext as DBContext_Init

            with DBContext_Init("write") as init_cur:
                # Create algo_config table if missing
                init_cur.execute(
                    "CREATE TABLE IF NOT EXISTS algo_config "
                    "(key VARCHAR(255) PRIMARY KEY, value TEXT, type VARCHAR(50), description TEXT)"
                )
                # Create orchestrator_execution_log if missing
                init_cur.execute(
                    "CREATE TABLE IF NOT EXISTS orchestrator_execution_log "
                    "(run_id VARCHAR(255) PRIMARY KEY, run_date DATE, started_at TIMESTAMP, "
                    "completed_at TIMESTAMP, overall_status VARCHAR(50), summary TEXT, halt_reason TEXT, phase_results JSONB)"
                )
                # Create algo_orchestrator_runs if missing (actual table orchestrator.py writes run history to -
                # distinct from orchestrator_execution_log above, confirmed via live UndefinedTable error)
                init_cur.execute(
                    "CREATE TABLE IF NOT EXISTS algo_orchestrator_runs "
                    "(run_id VARCHAR(255) PRIMARY KEY, run_date DATE, overall_status VARCHAR(50), "
                    "started_at TIMESTAMP, completed_at TIMESTAMP, execution_time_seconds NUMERIC, halt_reason TEXT)"
                )
                # Add missing updated_at column to algo_portfolio_snapshots (Phase 9's
                # ON CONFLICT ... DO UPDATE SET updated_at = NOW() references it; confirmed
                # UndefinedColumn error live - table predates this column being added)
                try:
                    init_cur.execute(
                        "ALTER TABLE algo_portfolio_snapshots ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()"
                    )
                except Exception:
                    pass
                # Add missing columns to metric tables (critical - loaders write these)
                metric_tables = [
                    "quality_metrics",
                    "growth_metrics",
                    "value_metrics",
                    "positioning_metrics",
                    "stability_metrics",
                ]
                for table in metric_tables:
                    try:
                        init_cur.execute(
                            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE"
                        )
                        init_cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS reason VARCHAR(500)")
                    except Exception:
                        pass
                # Add missing columns to stock_scores
                try:
                    init_cur.execute(
                        "ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS data_unavailable BOOLEAN DEFAULT FALSE"
                    )
                    init_cur.execute("ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS reason VARCHAR(500)")
                    init_cur.execute("ALTER TABLE stock_scores ADD COLUMN IF NOT EXISTS data_completeness NUMERIC(4,2)")
                except Exception:
                    pass
                # Create yfinance_snapshot if missing (migrations/versions/1006_create_yfinance_snapshot.sql
                # sat only in the db-migration Lambda pipeline, which cannot reach RDS due to unresolved VPC
                # networking issues in that pipeline as of 2026-07-07; loaders/load_value_metrics.py (and
                # several others) fail on every symbol with 'relation "yfinance_snapshot" does not exist'
                # without it, confirmed live via ECS task logs. This Lambda's DB connectivity is already
                # proven working every ~5 minutes, so bootstrap the table here too.)
                try:
                    init_cur.execute(
                        "CREATE TABLE IF NOT EXISTS yfinance_snapshot ("
                        "symbol VARCHAR(10) PRIMARY KEY, "
                        "fetched_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                        "pe_ratio DECIMAL(10, 2), pb_ratio DECIMAL(10, 2), ps_ratio DECIMAL(10, 2), "
                        "peg_ratio DECIMAL(10, 2), dividend_yield DECIMAL(8, 6), fcf_yield DECIMAL(8, 6), "
                        "held_percent_insiders DECIMAL(5, 2), held_percent_institutions DECIMAL(5, 2), "
                        "short_interest DECIMAL(5, 2), beta DECIMAL(8, 4), fifty_two_week_high DECIMAL(12, 2), "
                        "fifty_two_week_low DECIMAL(12, 2), market_cap BIGINT, "
                        "data_available BOOLEAN DEFAULT TRUE, unavailable_reason VARCHAR(255), "
                        "CONSTRAINT yfinance_snapshot_symbol_fk FOREIGN KEY (symbol) "
                        "REFERENCES stock_symbols(symbol) ON DELETE CASCADE)"
                    )
                    init_cur.execute(
                        "CREATE INDEX IF NOT EXISTS idx_yfinance_snapshot_fetched_at ON yfinance_snapshot(fetched_at)"
                    )
                    init_cur.execute(
                        "CREATE INDEX IF NOT EXISTS idx_yfinance_snapshot_data_available "
                        "ON yfinance_snapshot(data_available)"
                    )
                except Exception:
                    pass
                init_cur.connection.commit()
            logger.info("[STARTUP] Database schema verified and fixed")
        except Exception as db_init_err:
            logger.warning(f"[STARTUP] Database init check failed (non-fatal): {type(db_init_err).__name__}")

        # FIXED Issue #18: Default Lambda timeout to 600s instead of 240s (close to Lambda max)
        lambda_timeout = context.get_remaining_time_in_millis() // 1000 if context else 600

        # Parse run date if provided (skip 'now'/'today' to use system date logic)
        run_date = None
        if run_date_str and run_date_str.lower() not in ("now", "today", ""):
            try:
                run_date = _date.fromisoformat(run_date_str)
            except (ValueError, TypeError):
                logger.error(f"Invalid date format: {run_date_str}. Cannot proceed with invalid execution date.")
                return {
                    "statusCode": 400,
                    "body": json.dumps(
                        {
                            "status": "error",
                            "message": f"Invalid date format: {run_date_str}. Expected ISO format (YYYY-MM-DD).",
                            "source": source,
                        }
                    ),
                }

        # Verify EventBridge schedules are enabled (auto-fix if disabled)
        # This addresses issue where loaders don't run because schedules become disabled
        try:
            import boto3

            scheduler = boto3.client("scheduler", region_name="us-east-1")
            schedules = scheduler.list_schedules(MaxResults=50)
            algo_schedules = [s["Name"] for s in schedules.get("Schedules", []) if "algo" in s["Name"].lower()]
            for sched_name in algo_schedules:
                try:
                    sched = scheduler.get_schedule(Name=sched_name)
                    if sched.get("State") == "DISABLED":
                        scheduler.update_schedule(Name=sched_name, State="ENABLED")
                        logger.info(f"[STARTUP] Re-enabled EventBridge schedule: {sched_name}")
                except Exception:
                    pass
        except Exception:
            logger.debug("[STARTUP] EventBridge schedule check skipped (non-critical)")

        # Set execution_mode in environment before creating orchestrator
        # (orchestrator.__init__ will pick it up from ORCHESTRATOR_EXECUTION_MODE)
        # Always write to env to override any Terraform-set residual value (e.g. "paper")
        os.environ["ORCHESTRATOR_EXECUTION_MODE"] = execution_mode
        os.environ["ORCHESTRATOR_DRY_RUN"] = "true" if dry_run else "false"
        logger.info(f"ORCHESTRATOR_EXECUTION_MODE={execution_mode}, ORCHESTRATOR_DRY_RUN={dry_run}")

        # Ensure sector_ranking schema is correct (has 'date' column, not 'date_recorded')
        # This is a failsafe for when migrations don't run properly
        try:
            from utils.db.context import DatabaseContext

            with DatabaseContext("write") as cur:
                # Check if date column exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='sector_ranking' AND column_name='date'
                    )
                """)
                row = cur.fetchone()
                if row is None or row[0] is None:
                    raise RuntimeError("Column existence check failed")
                has_date = row[0]

                if not has_date:
                    logger.warning("[SCHEMA FIX] Adding 'date' column to sector_ranking...")
                    # Check if date_recorded exists to migrate from
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='sector_ranking' AND column_name='date_recorded'
                        )
                    """)
                    row = cur.fetchone()
                    if row is None or row[0] is None:
                        raise RuntimeError("Column existence check failed")
                    has_date_recorded = row[0]

                    # Add date column
                    cur.execute("ALTER TABLE sector_ranking ADD COLUMN date DATE")

                    # Migrate data if needed
                    if has_date_recorded:
                        cur.execute("UPDATE sector_ranking SET date = date_recorded WHERE date IS NULL")
                        cur.execute("ALTER TABLE sector_ranking DROP COLUMN date_recorded")
                        logger.info("[SCHEMA FIX] Migrated date_recorded -> date")

                    # Add constraint and indexes
                    cur.execute("ALTER TABLE sector_ranking ALTER COLUMN date SET NOT NULL")
                    cur.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS idx_sector_ranking_unique ON sector_ranking(sector_name, date)"
                    )
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_sector_ranking_date ON sector_ranking(date DESC)")
                    logger.info("[SCHEMA FIX] sector_ranking schema fixed successfully")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[SCHEMA FIX] CRITICAL: Could not verify/fix sector_ranking schema: {e}")
            return {
                "statusCode": 500,
                "body": json.dumps(
                    {
                        "status": "error",
                        "message": f"Database schema verification failed: {e!s}. Cannot proceed with invalid schema.",
                        "source": source,
                    }
                ),
            }
        # Create orchestrator instance with explicit config dependency injection
        from algo.infrastructure import get_config

        config = get_config()

        # CRITICAL: Validate all required config keys exist BEFORE running orchestrator
        # Catches config issues at startup rather than deep in Phase 1
        required_config_keys = [
            "enable_algo",
            "execution_mode",
            "phase1_min_coverage_pct",
            "phase1_min_symbol_count",
            "max_position_size_pct",
            "max_positions",
            "base_risk_pct",
        ]
        missing_keys = [k for k in required_config_keys if k not in config]
        if missing_keys:
            logger.critical(
                f"[LAMBDA STARTUP] CRITICAL: Missing required config keys at orchestrator startup. "
                f"Missing: {missing_keys}. Database must have algo_config entries for these keys. "
                f"Cannot proceed without configuration."
            )
            return {
                "statusCode": 500,
                "body": json.dumps(
                    {
                        "status": "error",
                        "message": f"Missing required config keys: {', '.join(missing_keys)}. Cannot initialize orchestrator.",
                        "source": source,
                    }
                ),
            }
        logger.info(f"[LAMBDA STARTUP] Config validation passed - {len(required_config_keys)} required keys present")

        orchestrator = Orchestrator(
            config=config,
            run_date=run_date,
            dry_run=dry_run,
            verbose=not is_test,
        )

        # Apply event-level config overrides (for testing only - overrides AlgoConfig defaults)
        # E.g.: {"config_overrides": {"min_close_quality_pct": 0.0, "min_breakout_volume_ratio": 0.5}}
        config_overrides = event.get("config_overrides")
        if config_overrides and isinstance(config_overrides, dict):
            for k, v in config_overrides.items():
                orchestrator.config.override(k, v)

        # Run the orchestrator
        logger.info("Starting orchestrator run")
        try:
            result = orchestrator.run()

            # Validate orchestrator result structure
            if "success" not in result:
                raise ValueError(
                    f"Orchestrator result missing 'success' field. "
                    f"Available keys: {list(result.keys())}. "
                    f"Cannot determine if orchestrator run succeeded."
                )

            success = result["success"]

            # Orchestrator._handle_concurrency_lock() short-circuits with just
            # {"success": False, "error": "Lock acquisition failed"} when another
            # invocation is already running - a benign, expected outcome of concurrent
            # triggers (EventBridge schedule overlapping a manual/retry invoke), not a
            # bug. Report it as a skip rather than crashing on the missing 'run_id'.
            if "run_id" not in result:
                if result.get("error") == "Lock acquisition failed":
                    logger.info("Orchestrator run skipped: another instance is already running")
                    return {
                        "statusCode": 200,
                        "body": json.dumps(
                            {
                                "status": "skipped",
                                "message": "Another orchestrator instance is already running",
                                "source": "eventbridge",
                            }
                        ),
                    }
                raise ValueError(
                    f"Orchestrator result missing 'run_id' field. "
                    f"Available keys: {list(result.keys())}. "
                    f"Cannot track orchestrator execution."
                )

            run_id = result["run_id"]

            # CRITICAL: Validate all required response fields to catch contract changes
            # If orchestrator doesn't return these, it's either a code change or a runtime error
            required_fields = ["skipped", "reason", "phases"]
            for field in required_fields:
                if field not in result:
                    raise ValueError(
                        f"Orchestrator response missing required field '{field}'. "
                        f"Available fields: {list(result.keys())}. "
                        f"This indicates either: (1) orchestrator code changed, "
                        f"(2) orchestrator failed silently, or (3) response contract broken."
                    )
            # Validate phases is a list
            phases = result["phases"]
            if not isinstance(phases, list):
                raise ValueError(
                    f"Orchestrator response 'phases' must be a list, got {type(phases).__name__}. "
                    f"Data contract violation: phases field is required and must be a list."
                )

            skipped = result["skipped"]
            reason = result["reason"]

            # Return response
            response_status_code = 200 if success else 500
            if not success:
                logger.warning(
                    f"[LAMBDA_RESPONSE] Orchestrator failed - returning statusCode {response_status_code} with error status"
                )
            else:
                logger.info(f"[LAMBDA_RESPONSE] Orchestrator succeeded - returning statusCode {response_status_code}")
            return {
                "statusCode": response_status_code,
                "body": json.dumps(
                    {
                        "status": "success" if success else "error",
                        "message": (
                            "Orchestrator completed successfully" if success else "Orchestrator encountered errors"
                        ),
                        "run_id": run_id,
                        "phases": phases,
                        "skipped": skipped,
                        "reason": reason,
                        "source": source,
                        "lambda_timeout_seconds": lambda_timeout,
                    }
                ),
            }
        finally:
            orchestrator.cleanup()

    except Exception as e:
        logger.exception(f"Orchestrator Lambda handler error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "error",
                    "message": f"Orchestrator failed: {e!s}",
                    "source": source,
                }
            ),
        }
