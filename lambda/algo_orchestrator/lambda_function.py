#!/usr/bin/env python3
"""
Lambda handler for the Algo Orchestrator.

Wraps the 7-phase orchestrator in a Lambda-compatible handler.
Supports both scheduled execution (EventBridge) and manual invocation (test-and-debug.yml).
"""

import json
import os
import sys
import logging
from pathlib import Path
from datetime import date as _date

# Setup logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO').upper())

# Add Lambda layer path and project root to sys.path
# In Lambda: code is in /var/task, layers are in /opt/python
# In local dev: code is in project root
if os.path.exists('/opt/python'):
    sys.path.insert(0, '/opt/python')
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import the orchestrator
from algo.algo_orchestrator import Orchestrator

def lambda_handler(event, context):
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

    # Reset config singleton on invocation to load fresh DB config
    from algo.infrastructure import reset_config
    reset_config()

    source = "unknown"
    try:
        # Load environment variables

        # FIXED Issue #8: Validate incoming event structure for EventBridge
        if not event:
            event = {}
        if not isinstance(event, dict):
            logger.error(f"Invalid event type: {type(event)}. Expected dict.")
            return {
                'statusCode': 400,
                'body': json.dumps({'status': 'error', 'message': 'Event must be a JSON object'})
            }

        # Seed mode: insert price rows directly into price_daily so today's intraday
        # price is visible to circuit breakers before the EOD pipeline runs.
        # Usage: {"seed_prices": [{"symbol": "SPY", "date": "2026-06-08", "open": 743.35,
        #          "high": 745.18, "low": 744.99, "close": 745.16, "volume": 50000}]}
        if event.get('seed_prices'):
            from utils.db.context import DatabaseContext
            rows = event['seed_prices']
            inserted = []
            with DatabaseContext('write') as cur:
                for row in rows:
                    cur.execute(
                        """INSERT INTO price_daily (symbol, date, open, high, low, close, volume, adj_close)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (symbol, date) DO UPDATE
                             SET open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                                 close=EXCLUDED.close, volume=EXCLUDED.volume,
                                 adj_close=EXCLUDED.adj_close""",
                        (row['symbol'], row['date'], row.get('open'), row.get('high'),
                         row.get('low'), row['close'], row.get('volume'), row.get('adj_close', row['close']))
                    )
                    inserted.append(f"{row['symbol']}@{row['date']}={row['close']}")
            logger.info(f"[SEED] Inserted/updated prices: {inserted}")
            if not event.get('then_run_orchestrator'):
                return {'statusCode': 200, 'body': json.dumps({'status': 'seeded', 'rows': inserted})}
            # Continue to run orchestrator with fresh prices

        # Parse event payload
        source = event.get('source', 'eventbridge')
        is_test = event.get('test', False)

        # ORCHESTRATOR_DRY_RUN env var (set by Terraform) is the baseline.
        # Event payload 'dry_run' key overrides it for manual invocations.
        env_dry_run = os.getenv('ORCHESTRATOR_DRY_RUN', 'false').strip().lower() in ('true', '1', 'yes')
        dry_run = event['dry_run'] if 'dry_run' in event else env_dry_run

        # Support both 'date' and 'run_date' fields from EventBridge; treat 'now'/'today' as None (use today's date)
        run_date_str = event.get('date') or event.get('run_date')

        # Parse run_identifier from EventBridge Scheduler to determine run purpose
        # ONLY evening run (after market close) should skip trading by default
        # Preclose run (3 PM ET) should trade — it's the final opportunity before market close
        run_identifier = event.get('run_identifier', '')
        if run_identifier == 'evening':
            # Evening orchestrator runs AFTER market close (5:30 PM ET) — no trading allowed
            dry_run = event.get('dry_run', True)
        elif run_identifier == 'preclose':
            # Preclose orchestrator runs BEFORE market close (3 PM ET) — this MUST trade
            dry_run = event.get('dry_run', False)

        # FIXED Issue #12: Parse execution_mode from event (EventBridge Scheduler passes it)
        execution_mode = event.get('execution_mode', os.getenv('ORCHESTRATOR_EXECUTION_MODE', 'auto')).strip().lower()
        if execution_mode not in ('auto', 'paper', 'live'):
            logger.warning(f"Invalid execution_mode: {execution_mode}. Defaulting to 'auto'.")
            execution_mode = 'auto'

        # F-02: Check Secrets Manager for intraday circuit breaker halt flag.
        # Set by algo-circuit-breaker Lambda when portfolio drawdown exceeds threshold.
        # Fail-open: if Secrets Manager is unavailable, continue with current dry_run value.
        if not dry_run:
            try:
                import boto3, json as _json
                sm = boto3.client('secretsmanager', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                secret = sm.get_secret_value(SecretId='algo/orchestrator')
                orch_state = _json.loads(secret.get('SecretString', '{}'))
                if orch_state.get('orchestrator_dry_run', False) in (True, 'true', '1'):
                    logger.warning("[F-02] Circuit breaker halted trading — orchestrator_dry_run=true in Secrets Manager")
                    dry_run = True
            except Exception as _cb_err:
                logger.warning(f"[F-02] Could not check circuit breaker state: {_cb_err} — continuing with dry_run={dry_run}")

        logger.info(f"Orchestrator invoked: source={source}, is_test={is_test}, dry_run={dry_run}, execution_mode={execution_mode}, run_identifier={run_identifier}")
        # Startup diagnostic: surface critical config state in every CloudWatch log
        logger.info(
            f"[CONFIG] ORCHESTRATOR_DRY_RUN={os.getenv('ORCHESTRATOR_DRY_RUN','<unset>')} "
            f"ORCHESTRATOR_EXECUTION_MODE={os.getenv('ORCHESTRATOR_EXECUTION_MODE','<unset>')} "
            f"ALPACA_PAPER_TRADING={os.getenv('ALPACA_PAPER_TRADING','<unset>')} "
            f"APCA_API_BASE_URL={os.getenv('APCA_API_BASE_URL','<unset>')} "
            f"ALGO_LIVE_TRADING={'SET' if os.getenv('ALGO_LIVE_TRADING') else 'NOT SET'}"
        )

        # FIXED Issue #18: Default Lambda timeout to 600s instead of 240s (close to Lambda max)
        lambda_timeout = context.get_remaining_time_in_millis() // 1000 if context else 600

        # Parse run date if provided (skip 'now'/'today' to use system date logic)
        run_date = None
        if run_date_str and run_date_str.lower() not in ('now', 'today', ''):
            try:
                run_date = _date.fromisoformat(run_date_str)
            except (ValueError, TypeError):
                logger.warning(f"Invalid date format: {run_date_str}, using today")

        # Set execution_mode in environment before creating orchestrator
        # (orchestrator.__init__ will pick it up from ORCHESTRATOR_EXECUTION_MODE)
        if execution_mode != 'auto':
            os.environ['ORCHESTRATOR_EXECUTION_MODE'] = execution_mode
            logger.info(f"ORCHESTRATOR_EXECUTION_MODE set to {execution_mode} from event")

        # Ensure sector_ranking schema is correct (has 'date' column, not 'date_recorded')
        # This is a failsafe for when migrations don't run properly
        try:
            from utils.db.context import DatabaseContext
            with DatabaseContext('write') as cur:
                # Check if date column exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='sector_ranking' AND column_name='date'
                    )
                """)
                has_date = cur.fetchone()[0]

                if not has_date:
                    logger.warning("[SCHEMA FIX] Adding 'date' column to sector_ranking...")
                    # Check if date_recorded exists to migrate from
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name='sector_ranking' AND column_name='date_recorded'
                        )
                    """)
                    has_date_recorded = cur.fetchone()[0]

                    # Add date column
                    cur.execute("ALTER TABLE sector_ranking ADD COLUMN date DATE")

                    # Migrate data if needed
                    if has_date_recorded:
                        cur.execute("UPDATE sector_ranking SET date = date_recorded WHERE date IS NULL")
                        cur.execute("ALTER TABLE sector_ranking DROP COLUMN date_recorded")
                        logger.info("[SCHEMA FIX] Migrated date_recorded -> date")

                    # Add constraint and indexes
                    cur.execute("ALTER TABLE sector_ranking ALTER COLUMN date SET NOT NULL")
                    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sector_ranking_unique ON sector_ranking(sector_name, date)")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_sector_ranking_date ON sector_ranking(date DESC)")
                    logger.info("[SCHEMA FIX] sector_ranking schema fixed successfully")
        except Exception as e:
            logger.warning(f"[SCHEMA FIX] Could not verify/fix sector_ranking schema: {e}. Continuing anyway...")

        # Set bypass flags from event (Path B testing)
        # E.g.: {"bypass_flags": {"BYPASS_PHASE1_HALT": "true", "BYPASS_HALT_FLAG": "true"}}
        bypass_flags = event.get('bypass_flags', {})
        if bypass_flags and isinstance(bypass_flags, dict):
            for flag_name, flag_value in bypass_flags.items():
                os.environ[flag_name] = str(flag_value).lower()
                logger.info(f"[PATH_B] Set {flag_name}={flag_value}")

        # Create orchestrator instance
        orchestrator = Orchestrator(
            run_date=run_date,
            dry_run=dry_run,
            verbose=not is_test,
        )

        # Apply event-level config overrides (for testing only — overrides AlgoConfig defaults)
        # E.g.: {"config_overrides": {"min_close_quality_pct": 0.0, "min_breakout_volume_ratio": 0.5}}
        config_overrides = event.get('config_overrides', {})
        if config_overrides and isinstance(config_overrides, dict):
            for k, v in config_overrides.items():
                orchestrator.config.override(k, v)

        # Run the orchestrator
        logger.info(f"Starting orchestrator run")
        try:
            result = orchestrator.run()
            success = result.get('success', False)
            run_id = result.get('run_id', 'unknown')

            # Return response
            skipped = result.get('skipped', False)
            return {
                'statusCode': 200 if success else 500,
                'body': json.dumps({
                    'status': 'success' if success else 'error',
                    'message': 'Orchestrator completed successfully' if success else 'Orchestrator encountered errors',
                    'run_id': run_id,
                    'phases': result.get('phases', {}),
                    'skipped': skipped,
                    'reason': result.get('reason', ''),
                    'source': source,
                    'lambda_timeout_seconds': lambda_timeout,
                })
            }
        finally:
            orchestrator.cleanup()

    except Exception as e:
        logger.exception(f"Orchestrator Lambda handler error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'message': f'Orchestrator failed: {str(e)}',
                'source': source,
            })
        }
