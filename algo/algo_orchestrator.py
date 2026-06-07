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
from zoneinfo import ZoneInfo
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

        # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
        self.run_date = run_date or datetime.now(ZoneInfo("America/New_York")).date()
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

        ISSUE #8 FIX: Halt flag persists through entire trading day (9:30 AM - 4:00 PM ET)
        to prevent Phase 5 from generating signals with stale data set by early morning
        Phase 1. Auto-expires only at market open of next trading day (9:30 AM ET).

        Timeline example:
        - 2:30 AM: Loaders detect stale data → Phase 1 sets halt_flag with triggered_at=2:30 AM
        - 9:30 AM, 1 PM, 3 PM, 5:30 PM: Orchestrator runs check halt_flag → still active (same day)
        - 9:30 AM NEXT DAY: Auto-clears halt_flag at market open (new trading day)
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
                        now_utc = datetime.now(timezone.utc)

                        # Convert to ET for trading hour comparison
                        trigger_et = trigger_dt.astimezone(ZoneInfo("America/New_York"))
                        now_et = now_utc.astimezone(ZoneInfo("America/New_York"))

                        trigger_date = trigger_et.date()
                        now_date_et = now_et.date()

                        MARKET_OPEN_HOUR = 9
                        MARKET_OPEN_MINUTE = 30

                        # Check if halt is from a previous trading day
                        if trigger_date < now_date_et:
                            # Halt flag from previous day: auto-clear only if we've passed
                            # market open (9:30 AM) of current trading day
                            now_trading_day = now_date_et
                            market_open_et = now_et.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0)
                            market_open_et = market_open_et.replace(tzinfo=ZoneInfo("America/New_York"))

                            if now_et >= market_open_et:
                                logger.info(
                                    f"[HALT_FLAG] Halt from {trigger_date} past market open ({MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} ET) "
                                    f"on {now_date_et} — auto-clearing"
                                )
                                table.put_item(Item={
                                    'key': self.HALT_FLAG_DYNAMODB_KEY,
                                    'halt_flag': False,
                                    'reason': 'Auto-expired: halt flag from prior trading day after market open',
                                    'reset_at': now_utc.isoformat(),
                                })
                                return False
                            else:
                                # Pre-market on current day, keep halt from previous day active
                                # (e.g., stale data from night loaders should halt all-day trading)
                                logger.info(
                                    f"[HALT_FLAG] Halt from {trigger_date} still active before market open today"
                                )
                                return True

                        # Same trading day: halt persists throughout entire day
                        # (early morning Phase 1 sets flag to protect all-day trading)
                        if trigger_date == now_date_et:
                            logger.critical("HALT FLAG DETECTED — stopping all trading phases immediately")
                            self.log_phase_result(0, 'halt_flag_detected', 'halted', 'External halt flag detected and respected')
                            return True

                    except Exception as parse_err:
                        logger.warning(f"[HALT_FLAG] Could not parse triggered_at: {parse_err}")

                logger.critical("HALT FLAG DETECTED — stopping all trading phases immediately")
                self.log_phase_result(0, 'halt_flag_detected', 'halted', 'External halt flag detected and respected')
                return True
        except Exception as e:
            # CRITICAL SAFETY: DynamoDB unavailable means we cannot verify halt flag status
            # MUST FAIL-CLOSED: Assume halt is set if we can't verify the flag
            # Better to stop trading unnecessarily than to trade when halt was set
            logger.critical(f"[CRITICAL] Could not check halt flag in DynamoDB: {e}")
            logger.critical("[CRITICAL] FAILING CLOSED: Treating DynamoDB unavailability as halt condition for safety")

            # Emit alert to operations team
            try:
                from algo.algo_alerts import AlertManager
                alerts = AlertManager()
                alerts.send_position_alert(
                    'DYNAMODB',
                    'HALT_CHECK_UNAVAILABLE',
                    f'DynamoDB halt flag check failed. Emergency halt mechanism DISABLED. Trading halted as fail-safe. '
                    f'Error: {str(e)[:200]}',
                    {'error': str(e)[:200], 'action': 'manual_intervention_required'}
                )
            except Exception as alert_err:
                logger.warning(f"Could not send DynamoDB unavailability alert: {alert_err}")

            # Emit metric for monitoring
            try:
                from algo.algo_metrics import MetricsPublisher
                MetricsPublisher().add_metric('DynamoDBHaltCheckFailure', 1, unit='Count')
            except Exception as metric_err:
                logger.warning(f"Could not emit halt check failure metric: {metric_err}")

            # Return True (halt condition) to fail-closed
            return True

    def _set_halt_flag(self, reason: str = '') -> bool:
        """Set halt flag in DynamoDB. Returns True if successfully set.

        ISSUE #8 FIX: When Phase 1 detects stale data, set halt flag to stop
        Phase 5 from generating full-intensity signals during degradation.
        """
        try:
            import boto3
            dynamodb = boto3.resource('dynamodb')
            table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
            table = dynamodb.Table(table_name)

            now_utc = datetime.now(timezone.utc)
            table.put_item(Item={
                'key': self.HALT_FLAG_DYNAMODB_KEY,
                'halt_flag': True,
                'triggered_at': now_utc.isoformat(),
                'reason': reason or 'Phase 1 degraded: stale data detected',
            })
            logger.critical(f"[HALT_FLAG_SET] {reason or 'Phase 1 degraded: halt flag activated'}")
            return True
        except Exception as e:
            logger.error(f"[ERROR] Failed to set halt flag: {e}")
            return False

    def _clear_halt_flag(self, reason: str = '') -> bool:
        """Clear halt flag in DynamoDB. Returns True if successfully cleared.

        ISSUE #8 FIX: When Phase 1 verifies data is fresh, explicitly clear the
        halt flag to allow Phase 5 to generate signals normally.

        Args:
            reason: Optional explanation for why halt was cleared

        Returns: True if successfully cleared, False on error
        """
        try:
            import boto3
            dynamodb = boto3.resource('dynamodb')
            table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
            table = dynamodb.Table(table_name)

            now_utc = datetime.now(timezone.utc)
            table.put_item(Item={
                'key': self.HALT_FLAG_DYNAMODB_KEY,
                'halt_flag': False,
                'cleared_at': now_utc.isoformat(),
                'reason': reason or 'Phase 1 verified: data is fresh',
                'reset_at': now_utc.isoformat(),
            })
            logger.info(f"[HALT_FLAG_CLEARED] {reason or 'Phase 1 verified: data is fresh, resuming normal trading'}")
            return True
        except Exception as e:
            logger.error(f"[ERROR] Failed to clear halt flag: {e}")
            return False

    def _check_connection_pool_health(self) -> None:
        """Monitor RDS connection pool and alert if approaching limits."""
        try:
            from algo.algo_connection_monitor import get_pool_status, check_stuck_connections
            status = get_pool_status()
            logger.debug(f"[RDS_POOL] Status: {status['active_connections']}/{status['max_connections']} "
                        f"({status['usage_pct']:.0f}%)")

            # Alert on stuck connections (held >5min)
            if status['stuck_connections_count'] > 0:
                logger.warning(f"[RDS_POOL] Found {status['stuck_connections_count']} stuck connections")
                check_stuck_connections()
        except Exception as e:
            logger.debug(f"Could not check connection pool health: {e}")

    def _health_check_diagnostics(self) -> None:
        """Log system health status: what's working, what's not, what's stale."""
        try:
            with DatabaseContext('read') as cur:
                cur.execute("SET statement_timeout = 10000")  # 10s timeout

                # Check key table freshness
                tables_to_check = [
                    ('price_daily', 'SPY prices'),
                    ('market_health_daily', 'Market health'),
                    ('technical_data_daily', 'Technicals'),
                    ('buy_sell_daily', 'Buy/sell signals'),
                    ('signal_quality_scores', 'Signal quality'),
                    ('swing_trader_scores', 'Swing scores'),
                    ('trend_template_data', 'Trend template'),
                ]

                logger.info("  Table Freshness Status:")
                for table, desc in tables_to_check:
                    try:
                        cur.execute(f"SELECT MAX(date) FROM {table} LIMIT 1")
                        row = cur.fetchone()
                        latest_date = row[0] if row and row[0] else None
                        if latest_date:
                            from datetime import datetime as dt, date as date_type
                            if isinstance(latest_date, date_type) and not isinstance(latest_date, datetime):
                                latest_dt = dt.combine(latest_date, dt.min.time()).replace(tzinfo=timezone.utc)
                            elif isinstance(latest_date, datetime) and latest_date.tzinfo is None:
                                latest_dt = latest_date.replace(tzinfo=timezone.utc)
                            else:
                                latest_dt = latest_date if isinstance(latest_date, datetime) else dt.fromisoformat(str(latest_date)).replace(tzinfo=timezone.utc)
                            age = (datetime.now(timezone.utc) - latest_dt).days
                            logger.info(f"    [{age}d old] {desc:20s}: {latest_date}")
                        else:
                            logger.info(f"    [EMPTY] {desc:20s}: no data")
                    except Exception as t_err:
                        logger.warning(f"    [ERROR] {desc:20s}: {t_err}")

                # Check loader status
                try:
                    cur.execute("""
                        SELECT table_name, status, last_updated
                        FROM data_loader_status
                        WHERE table_name IN ('price_daily', 'swing_trader_scores', 'signal_quality_scores')
                        ORDER BY table_name
                    """)
                    logger.info("  Loader Status:")
                    for row in cur.fetchall():
                        logger.info(f"    {row[0]:25s}: {row[1]:10s} (updated {row[2]})")
                except Exception as loader_err:
                    logger.debug(f"    Could not check loader status: {loader_err}")

        except Exception as e:
            logger.debug(f"  Health check failed: {e}")

    def _verify_task_stopped(self, ecs, cluster: str, task_arn: str, loader_name: str, max_retries: int = 3, retry_delay_sec: float = 1.0) -> bool:
        """Verify that a task actually stopped. Returns True if verified STOPPED, False if verification failed.

        ISSUE #5 FIX: Prevents hung tasks consuming RDS connections by verifying termination.
        Retries with escalating delays because ECS stop_task is async and may fail silently.
        """
        for attempt in range(1, max_retries + 1):
            try:
                response = ecs.describe_tasks(cluster=cluster, tasks=[task_arn])
                if not response.get('tasks'):
                    logger.error(f"[TASK_TERMINATION] Attempt {attempt}: Task {task_arn} not found in describe_tasks response")
                    if attempt < max_retries:
                        time.sleep(retry_delay_sec)
                        retry_delay_sec *= 1.5  # Exponential backoff
                    continue

                task_status = response['tasks'][0].get('lastStatus', 'UNKNOWN')
                desired_status = response['tasks'][0].get('desiredStatus', 'UNKNOWN')

                logger.debug(f"[TASK_TERMINATION] Attempt {attempt}: {loader_name} lastStatus={task_status}, desiredStatus={desired_status}")

                # Task is confirmed stopped
                if task_status == 'STOPPED':
                    logger.info(f"[TASK_TERMINATION] ✓ {loader_name} task {task_arn} verified STOPPED")
                    return True

                # Task still running but stop was requested
                if desired_status == 'STOPPED' and task_status in ('RUNNING', 'DEPROVISIONING'):
                    if attempt < max_retries:
                        logger.debug(f"[TASK_TERMINATION] Attempt {attempt}: Stop requested, waiting for status transition...")
                        time.sleep(retry_delay_sec)
                        retry_delay_sec *= 1.5
                        continue

                # Task didn't receive stop signal
                logger.error(f"[TASK_TERMINATION] Attempt {attempt}: Task status {task_status}/{desired_status} — stop not acknowledged")
                if attempt < max_retries:
                    time.sleep(retry_delay_sec)
                    retry_delay_sec *= 1.5

            except Exception as e:
                logger.error(f"[TASK_TERMINATION] Attempt {attempt}: Failed to verify task status: {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay_sec)
                    retry_delay_sec *= 1.5

        # All retries exhausted — termination verification failed
        logger.critical(f"[TASK_TERMINATION] FAILED: {loader_name} task {task_arn} did not transition to STOPPED after {max_retries} attempts. "
                       f"RDS connection may not be released. Manual intervention required.")
        return False

    def _kill_long_running_loaders(self) -> None:
        """CRITICAL: Kill analytics loaders if approaching next orchestrator run.

        Analytics loaders (company_profile, analyst_sentiment, stability_metrics, value_metrics)
        iterate 5000+ symbols with yfinance rate limits and can run 6+ hours. If any is still
        running when orchestrator fires, t4g.micro RDS OOMs. This check prevents that.

        Dynamic timeout: calculate time until next orchestrator run, subtract 15 min buffer.
        Orchestrator runs at: 9:30 AM, 1 PM, 3 PM, 5:30 PM ET (Mon-Fri only)

        ISSUE #5 FIX: Verifies task termination to prevent hung tasks consuming RDS connections.
        """
        try:
            import boto3
            ecs = boto3.client('ecs', region_name=os.getenv('AWS_REGION', 'us-east-1'))
            cluster = os.getenv('ECS_CLUSTER_ARN', 'algo-cluster')

            analytics_loaders = {'company_profile', 'analyst_sentiment', 'stability_metrics', 'value_metrics'}

            # Calculate time until next orchestrator run (in ET)
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(ZoneInfo("America/New_York"))

            ORCHESTRATOR_TIMES = [
                (9, 30),    # 9:30 AM
                (13, 0),    # 1 PM
                (15, 0),    # 3 PM
                (17, 30),   # 5:30 PM
            ]
            BUFFER_MINUTES = 15

            # Find next orchestrator run
            next_orch_et = None
            for orch_hour, orch_minute in ORCHESTRATOR_TIMES:
                orch_time = now_et.replace(hour=orch_hour, minute=orch_minute, second=0, microsecond=0)
                if orch_time > now_et:
                    next_orch_et = orch_time
                    break

            # If no more runs today, next is tomorrow morning
            if next_orch_et is None:
                next_orch_et = (now_et + timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0)
                # Skip non-trading days
                while not MarketCalendar.is_trading_day(next_orch_et.date()):
                    next_orch_et += timedelta(days=1)

            # Calculate kill threshold: next_orch - 15 minutes buffer
            kill_threshold_et = next_orch_et - timedelta(minutes=BUFFER_MINUTES)
            max_runtime = kill_threshold_et - now_et

            if max_runtime.total_seconds() <= 0:
                logger.debug("[OOM_PREVENTION] Next orchestrator run is imminent, using 5 min max runtime")
                max_runtime = timedelta(minutes=5)

            logger.debug(f"[OOM_PREVENTION] Next orchestrator run at {next_orch_et.strftime('%H:%M')} ET. "
                        f"Kill timeout: {max_runtime.total_seconds()/60:.0f} minutes")

            # List running tasks
            response = ecs.list_tasks(cluster=cluster, desiredStatus='RUNNING')
            if not response.get('taskArns'):
                return

            # Get task details (includes startedAt timestamp)
            task_details = ecs.describe_tasks(cluster=cluster, tasks=response['taskArns'])
            now = datetime.now(timezone.utc)

            failed_terminations = []
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
                if age > max_runtime:
                    task_arn = task.get('taskArn')
                    logger.warning(f"[OOM_PREVENTION] Killing {loader_name} task (running {age.total_seconds() / 3600:.1f}h, "
                                 f"max {max_runtime.total_seconds()/3600:.1f}h before next orch run): {task_arn}")

                    # ISSUE #5: Issue stop request
                    try:
                        ecs.stop_task(cluster=cluster, task=task_arn, reason=f'Analytics loader killing before next orchestrator run')
                    except Exception as stop_err:
                        logger.error(f"[TASK_TERMINATION] stop_task() call failed: {stop_err}")
                        failed_terminations.append((loader_name, task_arn, str(stop_err)))
                        continue

                    # ISSUE #5: Verify task actually stopped (with retries)
                    if self._verify_task_stopped(ecs, cluster, task_arn, loader_name):
                        self.log_phase_result(0, 'oom_prevention', 'success',
                                             f'Killed {loader_name} task running {age.total_seconds() / 3600:.1f}h')
                    else:
                        failed_terminations.append((loader_name, task_arn, 'verification timeout'))

            # ISSUE #5: Alert if any terminations failed
            if failed_terminations:
                error_details = '; '.join([f"{name}: {err}" for name, arn, err in failed_terminations])
                logger.critical(f"[TASK_TERMINATION] ESCALATION: {len(failed_terminations)} task termination(s) failed. "
                              f"{error_details}")
                try:
                    self.alerts.send_position_alert(
                        'TASK_TERMINATION',
                        'HUNG_LOADER_TERMINATION_FAILED',
                        f'Failed to terminate {len(failed_terminations)} hung analytics loaders. RDS connections may not be released. '
                        f'Check CloudWatch logs and manually stop: {", ".join([arn.split("/")[-1] for _, arn, _ in failed_terminations])}',
                        {'failed_tasks': [{'loader': name, 'task_arn': arn, 'error': err} for name, arn, err in failed_terminations]}
                    )
                except Exception as alert_err:
                    logger.error(f"[TASK_TERMINATION] Could not send escalation alert: {alert_err}")

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

    def phase_1_data_freshness(self):
        """Thin delegation to phase1_data_freshness module.

        ISSUE #11 FIX: Returns full PhaseResult instead of boolean to capture degradation status
        """
        self.log_phase_start(1, 'DATA FRESHNESS CHECK')
        from algo.orchestrator.phase1_data_freshness import run as run_phase1
        result = run_phase1(
            self.config,
            self.run_date, self.dry_run, self.alerts,
            self.verbose, self.log_phase_result
        )
        # Store result for Phase 5 to check degradation status
        self._phase1_result = result

        # ISSUE #9 FIX: Write Phase 1 degraded mode status to DynamoDB for health endpoint visibility
        # ISSUE #8 FIX: Manage halt flag lifecycle based on data freshness status
        try:
            import boto3
            dynamodb = boto3.resource('dynamodb')
            table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
            table = dynamodb.Table(table_name)

            degraded_status = result.status == 'degraded'
            table.put_item(Item={
                'key': 'phase1_degraded_mode',
                'degraded': degraded_status,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'reason': result.summary if degraded_status else None,
                'ttl': int(time.time()) + 3600,  # 1-hour TTL
            })

            if degraded_status:
                logger.info(f"[DEGRADED_MODE] Phase 1 returned degraded status: {result.summary}")
                # ISSUE #8 FIX: Set halt flag to stop Phase 5 from generating full-intensity signals
                self._set_halt_flag(f"Phase 1 degraded: {result.summary}")
            elif result.status == 'ok':
                # ISSUE #8 FIX: Clear halt flag when Phase 1 verifies data is fresh
                # This allows Phase 5 to resume normal signal generation
                self._clear_halt_flag(f"Phase 1 verified data is fresh at {datetime.now(timezone.utc).isoformat()}")
        except Exception as e:
            logger.debug(f"Failed to write Phase 1 degraded status to DynamoDB: {e}")

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
        """Thin delegation to phase5_signal_generation module.

        ISSUE #11 FIX: Pass Phase 1 degradation status so Phase 5 can apply conservative filters
        """
        self.log_phase_start(5, 'SIGNAL GENERATION & RANKING')
        if self._check_halt_flag():
            return False
        from algo.orchestrator.phase5_signal_generation import run as run_phase5
        # Check if Phase 1 returned degraded status (stale data with failsafe in progress)
        phase1_degraded = getattr(self, '_phase1_result', None) and self._phase1_result.status == 'degraded'
        result = run_phase5(
            self.run_date, self.dry_run,
            self.verbose, self.log_phase_result,
            getattr(self, '_exposure_constraints', {}),
            self._check_halt_flag,
            phase1_degraded=phase1_degraded  # Signal Phase 5 to use conservative filters
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
        # Skip lock check in dry-run mode (no actual trades) or when DynamoDB unavailable
        if not self.dry_run:
            lock_acquired = self._acquire_run_lock()
            if not lock_acquired:
                if self.lock_manager.is_available:
                    # DynamoDB is available but lock couldn't be acquired (another instance running)
                    logger.error(f"\nABORT: Could not acquire run lock. Another orchestrator instance is running.")
                    return {'success': False, 'error': 'Lock acquisition failed'}
                else:
                    # DynamoDB unavailable (no permissions, network issue, etc.) - allow to continue with warning
                    logger.warning("[DEGRADED MODE] DynamoDB lock unavailable - running without distributed lock protection")
        else:
            logger.info("[DRY-RUN] Skipping distributed lock check (dry-run mode)")

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

            logger.info("\n[CHECK] Monitoring RDS connection pool...")
            self._check_connection_pool_health()

            logger.info("\n[CHECK] Killing long-running analytics loaders...")
            self._kill_long_running_loaders()

            logger.info("\n[HEALTH CHECK] System diagnostics before Phase 1:")
            self._health_check_diagnostics()

            if self.degraded_mode and self.dry_run:
                logger.info("[DRY-RUN] Running in planning mode — skipping all trading phases.")
                self.log_phase_result(1, 'planning_mode', 'success', 'Dry-run mode with unavailable database')
                return self._final_report()

            try:
                phase_1_start = time.time()
                logger.info(f"\n[PHASE 1] Starting at {datetime.now(timezone.utc).isoformat()}")
                with TimeBlock("phase_1_data_freshness"):
                    # ISSUE #11 FIX: Capture Phase 1 result to check for degradation
                    from algo.orchestrator.phase1_data_freshness import run as run_phase1
                    self.config
                    phase1_result = run_phase1(
                        self.config,
                        self.run_date, self.dry_run, self.alerts,
                        self.verbose, self.log_phase_result
                    )
                    self._phase1_result = phase1_result  # Store for Phase 5 to check degradation
                    if phase1_result.halted:
                        logger.error("\nFAIL-CLOSED: Data freshness check failed. Running Phase 7 (reconciliation) before halting.")
                        self.log_phase_result(1, 'data_freshness', 'halt', 'Stale or missing critical data')
                        self.phase_7_reconcile()
                        return self._final_report()
                phase_1_elapsed = time.time() - phase_1_start
                logger.info(f"[PHASE 1] Completed in {phase_1_elapsed:.2f}s at {datetime.now(timezone.utc).isoformat()}")
            except Exception as e:
                logger.error(f"\nERROR in phase 1 (data freshness): {e}. Running Phase 7 (reconciliation) before halting.")
                self.log_phase_result(1, 'data_freshness', 'error', str(e))
                self.phase_7_reconcile()
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

