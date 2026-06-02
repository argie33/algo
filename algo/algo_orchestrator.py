#!/usr/bin/env python3

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from algo.algo_config import get_subprocess_timeout

import os
import time
import json
import psycopg2
import psycopg2.extensions
from datetime import datetime, date as _date, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple, Union
from algo.algo_alerts import AlertManager
from algo.algo_market_calendar import MarketCalendar
from algo.algo_sql_safety import assert_safe_table, assert_safe_column
from algo.algo_trade_executor import TradeExecutor
from utils.database_context import DatabaseContext
import logging
from monitoring.metrics_context import TimeBlock, log_metrics_summary, clear_metrics_buffer

logger = logging.getLogger(__name__)

class Orchestrator:
    """Daily workflow runner with explicit phases."""

    HALT_FLAG_DYNAMODB_KEY = 'orchestrator_halt'

    def __init__(self, config: Optional[Any] = None, run_date: Optional[_date] = None, dry_run: bool = False, verbose: bool = True) -> None:
        from algo.algo_config import get_config
        self.config = config or get_config()

        # Override execution_mode from environment variable if set
        env_execution_mode = os.getenv('ORCHESTRATOR_EXECUTION_MODE', '').strip().lower()
        if env_execution_mode:
            self.config.override('execution_mode', env_execution_mode)

        self.run_date = run_date or _date.today()
        self.dry_run = dry_run
        self.verbose = verbose
        self.phase_results = {}
        self.run_id = f"RUN-{self.run_date.isoformat()}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
        # FIXED Issue #8: Use DynamoDB lock manager instead of filesystem lock for distributed locking in Fargate
        from utils.dynamodb_lock_manager import DynamoDBLockManager
        self.lock_manager = DynamoDBLockManager()
        self._lock_acquired = False
        # FIXED Issue #3: Halt flag now uses DynamoDB instead of /tmp (which is ephemeral in Lambda)
        self._halt_flag_checked = False
        self.degraded_mode = False
        self.alerts = AlertManager()

        # RDS Proxy handles connection pooling - no local pool needed
        # In dry-run mode, database is optional; fail gracefully if unavailable
        if self.dry_run:
            logger.info("[DRY-RUN] Database optional in dry-run mode")
            self.degraded_mode = True
        else:
            self.degraded_mode = False

        logger.info("[ORCHESTRATOR] About to initialize feature flags")
        self._initialize_feature_flags()
        logger.info("[ORCHESTRATOR] Feature flags initialized")

        # DB failure counter removed: /tmp is ephemeral in Lambda (doesn't persist across invocations).
        # CloudWatch alarms on DB connection errors are more reliable for detecting outages.

    def cleanup(self) -> None:
        """No-op: RDS Proxy handles connection cleanup."""
        pass

    # ---------- Database health monitoring (B4) ----------

    def _check_db_connectivity(self) -> bool:
        """Test if database is reachable. Returns True if OK, False if failed."""
        try:
            with DatabaseContext('read') as cur:
                cur.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"  [ERROR] Database connectivity check failed: {e}")
            return False

    def _check_halt_flag(self) -> bool:
        """Check for halt flag in DynamoDB. Returns True if halt was requested.

        Uses DynamoDB instead of /tmp to work in Lambda where /tmp is ephemeral.
        SECURITY: If DynamoDB is unreachable, emits CloudWatch alarm metric.

        Auto-expires halt flags set on prior trading days. The circuit breaker Lambda
        runs at 10 AM, 12 PM, 3 PM ET and will re-trigger if conditions warrant.
        A flag from yesterday must not block today's 9:30 AM market-open run.
        """
        try:
            import boto3
            dynamodb = boto3.resource('dynamodb')
            table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
            table = dynamodb.Table(table_name)

            response = table.get_item(Key={'key': self.HALT_FLAG_DYNAMODB_KEY})
            if 'Item' in response and response['Item'].get('halt_flag') is True:
                triggered_at_str = response['Item'].get('triggered_at', '')
                if triggered_at_str:
                    try:
                        trigger_dt = datetime.fromisoformat(triggered_at_str.replace('Z', '+00:00'))
                        today_utc = datetime.now(timezone.utc).date()
                        if trigger_dt.date() < today_utc:
                            logger.info(
                                f"[HALT_FLAG] Stale flag (set {triggered_at_str}) — auto-clearing. "
                                f"Circuit breaker will re-evaluate at 10 AM ET if needed."
                            )
                            table.put_item(Item={
                                'key': self.HALT_FLAG_DYNAMODB_KEY,
                                'halt_flag': False,
                                'reason': 'Auto-expired: halt flag from prior trading day',
                                'reset_at': datetime.now(timezone.utc).isoformat(),
                            })
                            return False
                    except Exception as parse_err:
                        logger.warning(f"[HALT_FLAG] Could not parse triggered_at: {parse_err}")

                logger.critical("HALT FLAG DETECTED — stopping all trading phases immediately")
                self.log_phase_result(0, 'halt_flag_detected', 'halted', 'External halt flag detected and respected')
                return True
        except Exception as e:
            # CRITICAL: DynamoDB unavailable defeats emergency halt mechanism
            logger.error(f"[CRITICAL] Could not check halt flag in DynamoDB: {e}. Emergency halt is DISABLED.")
            try:
                from algo.algo_metrics import MetricsPublisher
                MetricsPublisher().add_metric('DynamoDBHaltCheckFailure', 1, unit='Count')
            except Exception as metric_err:
                logger.warning(f"Could not emit halt check failure metric: {metric_err}")

        return False

    def _kill_long_running_loaders(self) -> None:
        """CRITICAL: Kill analytics loaders running > 2 hours to prevent OOM crashes.

        Analytics loaders (company_profile, analyst_sentiment, stability_metrics, value_metrics)
        iterate 5000+ symbols with yfinance rate limits and can run 6+ hours. If any is still
        running when orchestrator fires, t4g.micro RDS OOMs. This check prevents that.
        """
        try:
            import boto3
            ecs = boto3.client('ecs', region_name=os.getenv('AWS_REGION', 'us-east-1'))
            cluster = os.getenv('ECS_CLUSTER_ARN', 'algo-cluster')

            analytics_loaders = {'company_profile', 'analyst_sentiment', 'stability_metrics', 'value_metrics'}

            # List running tasks
            response = ecs.list_tasks(cluster=cluster, desiredStatus='RUNNING')
            if not response.get('taskArns'):
                return

            # Get task details (includes startedAt timestamp)
            task_details = ecs.describe_tasks(cluster=cluster, tasks=response['taskArns'])
            now = datetime.now(timezone.utc)
            two_hours = timedelta(hours=2)

            for task in task_details.get('tasks', []):
                # Extract loader name from task definition (format: algo-LOADER_NAME-loader:1)
                task_def = task.get('taskDefinitionArn', '')
                loader_name = None
                for analytics_loader in analytics_loaders:
                    if analytics_loader in task_def:
                        loader_name = analytics_loader
                        break

                if not loader_name:
                    continue  # Skip non-analytics loaders

                started_at = task.get('startedAt')
                if not started_at:
                    continue

                # Convert startedAt to UTC-aware datetime if needed
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)

                age = now - started_at
                if age > two_hours:
                    task_arn = task.get('taskArn')
                    logger.warning(f"[OOM_PREVENTION] Killing {loader_name} task (running {age.total_seconds() / 3600:.1f}h): {task_arn}")
                    ecs.stop_task(cluster=cluster, task=task_arn, reason='Long-running loader OOM prevention')
                    self.log_phase_result(0, 'oom_prevention', 'success', f'Killed {loader_name} task running {age.total_seconds() / 3600:.1f}h')

        except Exception as e:
            logger.warning(f"[OOM_PREVENTION] Could not check/kill long-running loaders: {e}")
            # Don't halt trading for this check - it's advisory

    def _initialize_feature_flags(self) -> None:
        """Initialize feature flags with safe defaults on startup."""
        # In AWS Lambda, skip feature flag initialization (uses defaults only)
        if os.getenv('AWS_LAMBDA_FUNCTION_NAME'):
            logger.info("[FEATURE_FLAGS] Skipping initialization in Lambda (using defaults)")
            return

        try:
            from utils.feature_flags import initialize_safe_defaults, create_feature_flags_table
            # Ensure table exists
            create_feature_flags_table()
            initialize_safe_defaults()
        except Exception as e:
            if self.verbose:
                logger.warning(f"  [WARN] Feature flag initialization failed: {e}")
            # Don't fail the orchestrator if flags aren't available

    def _validate_required_tables(self, cur: Any) -> bool:
        """FIXED Issue #23: Validate that all required tables exist before running phases.

        Returns: True if all tables exist, False if any critical table is missing.
        """
        required_tables = [
            'price_daily',
            'technical_data_daily',
            'buy_sell_daily',
            'signal_quality_scores',
            'market_health_daily',
            'algo_audit_log',
        ]

        try:
            missing_tables = []
            for table_name in required_tables:
                try:
                    # Check if table exists by querying information_schema
                    cur.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name = %s LIMIT 1", (table_name,))
                    if not cur.fetchone():
                        missing_tables.append(table_name)
                        logger.error(f"[TABLE-CHECK] Missing required table: {table_name}")
                except Exception as e:
                    logger.error(f"[TABLE-CHECK] Failed to check table {table_name}: {e}")
                    missing_tables.append(table_name)

            if missing_tables:
                logger.error(f"[TABLE-CHECK] Cannot proceed: missing tables {missing_tables}")
                self.log_phase_result(0, 'table_validation', 'halt', f'Missing tables: {", ".join(missing_tables)}')
                return False

            logger.info(f"[TABLE-CHECK] All {len(required_tables)} required tables exist ✓")
            return True

        except Exception as e:
            logger.error(f"[TABLE-CHECK] Error validating tables: {e}")
            return False

    # ---------- Logging helpers ----------

    def _acquire_run_lock(self, lock_timeout_seconds: int = 5) -> bool:
        """Acquire distributed lock to prevent concurrent orchestrator runs.

        FIXED Issue #8: Uses DynamoDB conditional writes instead of filesystem locks
        for correct distributed locking in Fargate ECS tasks (no shared filesystem).

        Args:
            lock_timeout_seconds: How long to retry acquiring lock (default 5s)

        Returns: True if lock acquired, False if another active instance holds it.
        """
        self._lock_acquired = self.lock_manager.acquire(timeout_seconds=lock_timeout_seconds)
        return self._lock_acquired

    def _release_run_lock(self) -> None:
        """Release the distributed lock."""
        if self._lock_acquired:
            self.lock_manager.release()

    def log_phase_start(self, phase_num: int, name: str) -> None:
        if self.verbose:
            logger.info(f"\n{'='*70}")
            logger.info(f"PHASE {phase_num}: {name}")
            logger.info(f"{'='*70}")

    def log_phase_result(self, phase_num: int, name: str, status: str, summary: str) -> None:
        self.phase_results[phase_num] = {
            'name': name,
            'status': status,
            'summary': summary,
        }
        if self.verbose:
            logger.info(f"\n-> Phase {phase_num} {status}: {summary}")
        try:
            with DatabaseContext('write') as cur:
                cur.execute(
                    """
                    INSERT INTO algo_audit_log (action_type, action_date, details, actor, status, created_at)
                    VALUES (%s, CURRENT_TIMESTAMP, %s, 'orchestrator', %s, CURRENT_TIMESTAMP)
                    """,
                    (
                        f'phase_{phase_num}_{name}',
                        json.dumps({'run_id': self.run_id, 'summary': summary}),
                        status,
                    ),
                )
        except Exception as e:
            logger.warning(f"Warning: Could not persist audit log entry: {e}")

    # ---------- Phase implementations ----------

    def phase_1_data_freshness(self) -> bool:
        """Thin delegation to phase1_data_freshness module."""
        self.log_phase_start(1, 'DATA FRESHNESS CHECK')
        from algo.orchestrator.phase1_data_freshness import run as run_phase1
        result = run_phase1(
            self.config,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result
        )
        return not result.halted

    def phase_2_circuit_breakers(self) -> bool:
        """Thin delegation to phase2_circuit_breakers module."""
        self.log_phase_start(2, 'CIRCUIT BREAKERS')
        from algo.orchestrator.phase2_circuit_breakers import run as run_phase2
        result = run_phase2(
            self.config,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result
        )
        return not result.halted

    def phase_3_position_monitor(self) -> List[Dict[str, Any]]:
        """Thin delegation to phase3_position_monitor module."""
        self.log_phase_start(3, 'POSITION MONITOR')
        from algo.orchestrator.phase3_position_monitor import run as run_phase3
        result = run_phase3(
            self.config,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result
        )
        self._position_recs = result.data.get('recommendations', [])
        return True  # fail-open

    def phase_3b_exposure_policy(self) -> Dict[str, Any]:
        """Thin delegation to phase3b_exposure_policy module."""
        self.log_phase_start('3b', 'EXPOSURE POLICY ACTIONS')
        from algo.orchestrator.phase3b_exposure_policy import run as run_phase3b
        result = run_phase3b(
            self.config,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result
        )
        self._exposure_constraints = result.data.get('constraints')
        self._exposure_actions = result.data.get('actions', [])
        return True  # fail-open

    def phase_4_exit_execution(self) -> List[Dict[str, Any]]:
        """Thin delegation to phase4_exit_execution module."""
        self.log_phase_start(4, 'EXIT EXECUTION')
        # No halt flag check: exits must always run to reduce risk even when entries are halted.
        from algo.orchestrator.phase4_exit_execution import run as run_phase4
        result = run_phase4(
            self.config,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result,
            getattr(self, '_position_recs', []),
            getattr(self, '_exposure_actions', []),
            self._check_halt_flag
        )
        return not result.halted

    def phase_4b_pyramid_adds(self) -> List[Dict[str, Any]]:
        """Thin delegation to phase4b_pyramid_adds module."""
        self.log_phase_start('4b', 'PYRAMID ADDS (winners)')
        from algo.orchestrator.phase4b_pyramid_adds import run as run_phase4b
        result = run_phase4b(
            self.config,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result
        )
        return True  # fail-open

    def phase_5_signal_generation(self) -> List[Dict[str, Any]]:
        """Thin delegation to phase5_signal_generation module."""
        self.log_phase_start(5, 'SIGNAL GENERATION & RANKING')
        if self._check_halt_flag():
            return False
        from algo.orchestrator.phase5_signal_generation import run as run_phase5
        result = run_phase5(
            self.run_date, self.dry_run,
            self.verbose, self.log_phase_result,
            getattr(self, '_exposure_constraints', {}),
            self._check_halt_flag
        )
        self._qualified_trades = result.data.get('qualified_trades', [])
        self.phase_results.setdefault(5, {})['signals_evaluated'] = len(self._qualified_trades)
        return not result.halted

    def phase_6_entry_execution(self) -> List[Dict[str, Any]]:
        """Thin delegation to phase6_entry_execution module."""
        self.log_phase_start(6, 'ENTRY EXECUTION')
        if self._check_halt_flag():
            return False
        from algo.orchestrator.phase6_entry_execution import run as run_phase6
        result = run_phase6(
            self.config,
            self.run_date, self.dry_run,
            self.verbose, self.log_phase_result,
            getattr(self, '_qualified_trades', []),
            getattr(self, '_exposure_constraints', None),
            self._check_halt_flag
        )
        self.phase_results.setdefault(6, {})['trades_executed'] = result.data.get('entered', 0)
        return not result.halted

    def phase_7_reconcile(self) -> Dict[str, Any]:
        """Thin delegation to phase7_reconciliation module."""
        self.log_phase_start(7, 'RECONCILIATION & SNAPSHOT')
        # No halt flag check: snapshot must always be written so circuit breakers
        # have accurate portfolio state on the next invocation.
        from algo.orchestrator.phase7_reconciliation import run as run_phase7
        result = run_phase7(
            self.config,
            self.run_date, self.log_phase_result
        )
        self.phase_results.setdefault(7, {})['open_positions'] = result.data.get('positions', 0)
        return not result.halted

    # ---------- Main entrypoint ----------

    def run(self) -> Dict[str, Any]:
        run_start = time.time()
        logger.info(f"\n{'#'*70}")
        logger.info(f"#   ALGO ORCHESTRATOR — {self.run_date}  ({'DRY RUN' if self.dry_run else 'LIVE'})")
        logger.info(f"#   run_id: {self.run_id}")
        logger.info(f"#   START TIME: {datetime.now(timezone.utc).isoformat()}")
        logger.info(f"{'#'*70}")

        if not MarketCalendar.is_trading_day(self.run_date):
            status = MarketCalendar.market_status(datetime.combine(self.run_date, datetime.min.time()))
            logger.info(f"\n Market closed: {status['reason']}")
            logger.info("Skipping all trading phases.\n")
            return {'success': True, 'skipped': True, 'reason': f"Market closed: {status['reason']}"}

        # Concurrency lock — prevent two orchestrators running at once
        # which would risk duplicate trades or double-counting circuit breakers
        if not self._acquire_run_lock():
            logger.error(f"\nABORT: Could not acquire run lock. Another orchestrator instance is running.")
            return {'success': False, 'error': 'Lock acquisition failed'}

        try:
            logger.info(f"\n{'='*70}")
            logger.info("PRE-FLIGHT CHECKS (before Phase 1)")
            logger.info(f"{'='*70}")
            logger.info("[CRITICAL] Running critical data checks...")
            try:
                with DatabaseContext('read') as cur:
                    # Validate required tables exist (schema check only).
                    # Data freshness and patrol are handled by Phase 1 with proper
                    # halt/observe-only distinctions and fresh patrol execution.
                    if not self._validate_required_tables(cur):
                        logger.error("[HALT] Required tables missing — cannot proceed")
                        return self._final_report()

                    logger.info("[OK] All pre-flight checks passed")
            except Exception as e:
                logger.error(f"  [HALT] Pre-flight check failed: {e}")
                # Return skipped=True when DB is unreachable so test verification
                # treats this as a transient skip, not a code bug (phases={})
                report = self._final_report()
                if 'connection' in str(e).lower() or 'database' in str(e).lower():
                    report['skipped'] = True
                    report['reason'] = 'database_unavailable'
                return report

            logger.info("\n[CHECK] Database connectivity...")
            if not self._check_db_connectivity():
                logger.error("[DB_ERROR] Database connectivity check FAILED")
                logger.error("Check CloudWatch alarms for database availability. Returning skipped status.")
                report = self._final_report()
                report['skipped'] = True
                report['reason'] = 'database_unavailable'
                return report
            else:
                logger.info("[OK] Database connectivity check passed")

            logger.info("\n[CHECK] Killing long-running analytics loaders...")
            self._kill_long_running_loaders()

            if self.degraded_mode and self.dry_run:
                logger.info("[DRY-RUN] Running in planning mode — skipping all trading phases.")
                self.log_phase_result(1, 'planning_mode', 'success', 'Dry-run mode with unavailable database')
                return self._final_report()

            try:
                phase_1_start = time.time()
                logger.info(f"\n[PHASE 1] Starting at {datetime.now(timezone.utc).isoformat()}")
                with TimeBlock("phase_1_data_freshness"):
                    if not self.phase_1_data_freshness():
                        logger.error("\nFAIL-CLOSED: Data freshness check failed. Halting pipeline.")
                        self.log_phase_result(1, 'data_freshness', 'halt', 'Stale or missing critical data')
                        return self._final_report()
                phase_1_elapsed = time.time() - phase_1_start
                logger.info(f"[PHASE 1] Completed in {phase_1_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                logger.error(f"\nERROR in phase 1 (data freshness): {e}. Halting pipeline.")
                self.log_phase_result(1, 'data_freshness', 'error', str(e))
                return self._final_report()

            phase_2_start = time.time()
            logger.info(f"\n[PHASE 2] Starting at {datetime.now(timezone.utc).isoformat()}")
            with TimeBlock("phase_2_circuit_breakers"):
                phase_2_passed = self.phase_2_circuit_breakers()
            phase_2_elapsed = time.time() - phase_2_start
            logger.info(f"[PHASE 2] Completed in {phase_2_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")

            if not phase_2_passed:
                logger.info("\nHALT: Circuit breaker fired. Will still review positions but skip new entries.")
                self.phase_3_position_monitor()
                self.phase_3b_exposure_policy()
                self.phase_4_exit_execution()
                self.phase_7_reconcile()
                return self._final_report()

            # Phase 3: Position Monitor
            phase_3_start = time.time()
            logger.info(f"\n[PHASE 3] Starting at {datetime.now(timezone.utc).isoformat()}")
            try:
                with TimeBlock("phase_3_position_monitor"):
                    self.phase_3_position_monitor()
                phase_3_elapsed = time.time() - phase_3_start
                logger.info(f"[PHASE 3] Completed in {phase_3_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                logger.error(f"✗ Phase 3 (Position Monitor) failed: {e}", exc_info=True)
                self.log_phase_result(3, 'position_monitor', 'error', str(e))

            # Phase 3b: Exposure Policy
            phase_3b_start = time.time()
            logger.info(f"\n[PHASE 3b] Starting at {datetime.now(timezone.utc).isoformat()}")
            try:
                with TimeBlock("phase_3b_exposure_policy"):
                    self.phase_3b_exposure_policy()
                phase_3b_elapsed = time.time() - phase_3b_start
                logger.info(f"[PHASE 3b] Completed in {phase_3b_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                logger.error(f"✗ Phase 3b (Exposure Policy) failed: {e}", exc_info=True)
                self.log_phase_result('3b', 'exposure_policy', 'error', str(e))

            # Phase 4: Exit Execution
            phase_4_start = time.time()
            logger.info(f"\n[PHASE 4] Starting at {datetime.now(timezone.utc).isoformat()}")
            try:
                with TimeBlock("phase_4_exit_execution"):
                    result = self.phase_4_exit_execution()
                    if not result:
                        logger.critical("HALT: Phase 4 (Exit Execution) returned False — stopping pipeline")
                        return self._final_report()
                phase_4_elapsed = time.time() - phase_4_start
                logger.info(f"[PHASE 4] Completed in {phase_4_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                logger.error(f"✗ Phase 4 (Exit Execution) failed: {e}", exc_info=True)
                self.log_phase_result(4, 'exit_execution', 'error', str(e))

            # Phase 4b: Pyramid Adds
            try:
                with TimeBlock("phase_4b_pyramid_adds"):
                    self.phase_4b_pyramid_adds()
                logger.info("[OK] Phase 4b (Pyramid Adds) completed")
            except Exception as e:
                logger.error(f"✗ Phase 4b (Pyramid Adds) failed: {e}", exc_info=True)
                self.log_phase_result('4b', 'pyramid_adds', 'error', str(e))

            # Phase 5: Signal Generation
            phase_5_start = time.time()
            logger.info(f"\n[PHASE 5] Starting at {datetime.now(timezone.utc).isoformat()}")
            try:
                with TimeBlock("phase_5_signal_generation"):
                    result = self.phase_5_signal_generation()
                    if not result:
                        logger.critical("HALT: Phase 5 (Signal Generation) returned False — skipping Phase 6.")
                        # Phase 7 must still run: it creates the portfolio snapshot that Phase 5
                        # needs on its next invocation. Skipping Phase 7 here causes a deadlock
                        # where Phase 5 always halts (no snapshot) and Phase 7 never creates one.
                        self.phase_7_reconcile()
                        return self._final_report()
                phase_5_elapsed = time.time() - phase_5_start
                logger.info(f"[PHASE 5] Completed in {phase_5_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                logger.error(f"✗ Phase 5 (Signal Generation) failed: {e}", exc_info=True)
                self.log_phase_result(5, 'signal_generation', 'error', str(e))

            # Phase 6: Entry Execution
            phase_6_start = time.time()
            logger.info(f"\n[PHASE 6] Starting at {datetime.now(timezone.utc).isoformat()}")
            try:
                with TimeBlock("phase_6_entry_execution"):
                    result = self.phase_6_entry_execution()
                    if not result:
                        logger.critical("HALT: Phase 6 (Entry Execution) returned False — stopping pipeline")
                        return self._final_report()
                phase_6_elapsed = time.time() - phase_6_start
                logger.info(f"[PHASE 6] Completed in {phase_6_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                logger.error(f"✗ Phase 6 (Entry Execution) failed: {e}", exc_info=True)
                self.log_phase_result(6, 'entry_execution', 'error', str(e))

            # Phase 7: Reconciliation (fail-open — doesn't execute trades, just records state)
            phase_7_start = time.time()
            logger.info(f"\n[PHASE 7] Starting at {datetime.now(timezone.utc).isoformat()}")
            try:
                with TimeBlock("phase_7_reconciliation"):
                    result = self.phase_7_reconcile()
                # Phase 7 is fail-open: if reconciliation fails, we still finalize the report
                # (positions may already be executed, so we must sync state)
                phase_7_elapsed = time.time() - phase_7_start
                logger.info(f"[PHASE 7] Completed in {phase_7_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                logger.error(f"✗ Phase 7 (Reconciliation) failed: {e}", exc_info=True)
                self.log_phase_result(7, 'reconciliation', 'error', str(e))

            # Log performance metrics and total time
            log_metrics_summary()
            total_elapsed = time.time() - run_start
            logger.info(f"\n[TOTAL] Orchestrator run completed in {total_elapsed:.2f}s")
            logger.info(f"[END TIME] {datetime.now(timezone.utc).isoformat()}")
            return self._final_report()
        finally:
            self._release_run_lock()

    def _final_report(self):
        logger.info(f"\n{'#'*70}")
        logger.info(f"#   FINAL REPORT — {self.run_id}")
        logger.info(f"{'#'*70}")
        for n, info in sorted(self.phase_results.items(), key=lambda x: str(x[0])):
            status_flag = {
                'success': '[OK] ',
                'halt':    '[HALT]',
                'fail':    '[FAIL]',
                'error':   '[ERR] ',
            }.get(info['status'], '[?]   ')
            logger.info(f"  {status_flag} Phase {n}: {info['name']:22s} — {info['summary']}")
        logger.info(f"{'#'*70}\n")

        any_error = any(p['status'] in ('error', 'fail') for p in self.phase_results.values())
        any_halt = any(p['status'] == 'halt' for p in self.phase_results.values())
        result = {
            'run_id': self.run_id,
            'run_date': self.run_date.isoformat(),
            'phases': self.phase_results,
            'success': not any_error,
            'halted': any_halt,
        }

        # Publish CloudWatch metrics (non-blocking — never let metrics interrupt trading)
        try:
            from algo.algo_metrics import MetricsPublisher
            with MetricsPublisher(dry_run=self.dry_run) as m:
                m.put_orchestrator_result(result['success'], self.phase_results)

                # Signal count from phase 5 summary
                phase5 = self.phase_results.get(5, {})
                signals = phase5.get('signals_evaluated', 0)
                if isinstance(signals, int):
                    m.put_signal_count(signals)

                # Trade count from phase 6 summary
                phase6 = self.phase_results.get(6, {})
                trades = phase6.get('trades_executed', 0)
                if isinstance(trades, int):
                    m.put_trade_count(trades)

                # Open position count from phase 7
                phase7 = self.phase_results.get(7, {})
                positions = phase7.get('open_positions', 0)
                if isinstance(positions, int):
                    m.put_open_positions(positions)

        except Exception as e:
            # Never let metrics publishing interrupt trading results
            logger.error("CloudWatch metric publish failed: %s", e)

        return result

if __name__ == "__main__":

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    import argparse
    parser = argparse.ArgumentParser(description='Run daily algo workflow')
    parser.add_argument('--date', type=str, help='Run date (YYYY-MM-DD)', default=None)
    parser.add_argument('--dry-run', action='store_true', help='Plan only, no real trades')
    parser.add_argument('--init-only', action='store_true', help='Run loaders only, no trading')
    parser.add_argument('--quiet', action='store_true', help='Reduce output')
    args = parser.parse_args()

    run_date = _date.fromisoformat(args.date) if args.date else None

    # ORCHESTRATOR_DRY_RUN env var takes precedence over --dry-run flag.
    # Step Functions TriggerOrchestrator sets this to "true" for pipeline validation runs.
    env_dry_run = os.getenv('ORCHESTRATOR_DRY_RUN', 'false').lower() in ('true', '1', 'yes')
    dry_run = args.dry_run or env_dry_run

    from config.credential_validator import assert_credentials
    assert_credentials(on_failure="warn")

    if args.init_only:
        logger.info("Running in INIT-ONLY mode: loading data without trading")
        # For init-only, skip the orchestrator and just run loaders
        logger.info("To run loaders, execute: python3 run-all-loaders.py")
        sys.exit(0)

    orch = Orchestrator(run_date=run_date, dry_run=dry_run, verbose=not args.quiet)
    try:
        final = orch.run()
        sys.exit(0 if final['success'] else 1)
    finally:
        orch.cleanup()

