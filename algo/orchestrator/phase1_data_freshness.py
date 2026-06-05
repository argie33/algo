#!/usr/bin/env python3

import os
import json
import logging
import time
from datetime import date as _date, datetime, timedelta, timezone
from typing import Any, Callable, Optional, Dict

from utils.database_context import DatabaseContext
from algo.algo_alerts import AlertManager
from algo.algo_sql_safety import assert_safe_table, assert_safe_column
from algo.orchestrator.phase_result import PhaseResult

logger = logging.getLogger(__name__)

def _trigger_loader_failsafe_with_verification(loader_name: str, verbose: bool = False, poll_timeout_sec: int = 120, retry_count: int = 1) -> bool:
    """
    Trigger ECS loader asynchronously and VERIFY it started before returning.

    CRITICAL FIX: Previous implementation triggered loader but never confirmed it started.
    If trigger failed (network error, Lambda down, wrong ARN), orchestrator would proceed
    with stale data silently.

    Now: Use EventBridge to trigger ECS task, monitor CloudWatch for task start.
    Only return True if ECS task confirmed running within poll_timeout_sec.
    Retries once with 10s backoff if initial trigger fails.

    ECS TIMING: Fargate tasks can take 45-120s to reach RUNNING state under load.
    Default 120s timeout allows for normal scheduling delays while catching hung tasks.

    Args:
        loader_name: Name of the loader to trigger
        verbose: Whether to log verbose output
        poll_timeout_sec: Max seconds to wait for loader task to start (default 120s)
        retry_count: Number of retry attempts after initial failure (default 1)

    Returns: True if loader task confirmed running, False if timeout/error
    """
    import boto3
    from utils.database_context import DatabaseContext

    # Map loader names to ECS task definitions (constructed from Terraform naming: {project}-{loader_name}-loader)
    task_defs = {
        'stock_prices_daily': 'algo-stock_prices_daily-loader',
        'technical_data_daily': 'algo-technical_data_daily-loader',
        'market_health_daily': 'algo-market_health_daily-loader',
    }

    task_def = task_defs.get(loader_name)
    if not task_def:
        logger.warning(f"[FAILSAFE] Unknown loader '{loader_name}', cannot trigger")
        return False

    ecs_client = boto3.client('ecs', region_name=os.getenv('AWS_REGION', 'us-east-1'))
    cluster_arn = os.getenv('ECS_CLUSTER_ARN', 'algo-cluster')

    # Retry loop: attempt trigger + polling up to retry_count + 1 times
    attempts = 0
    max_attempts = retry_count + 1

    while attempts < max_attempts:
        attempts += 1

        try:
            if verbose:
                logger.info(f"[FAILSAFE] Attempt {attempts}/{max_attempts}: Launching ECS task {task_def}...")

            response = ecs_client.run_task(
                cluster=cluster_arn,
                taskDefinition=task_def,
                launchType='FARGATE',
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': os.getenv('ECS_SUBNETS', '').split(','),
                        'securityGroups': os.getenv('ECS_SECURITY_GROUPS', '').split(','),
                        'assignPublicIp': 'DISABLED'
                    }
                },
                overrides={
                    'containerOverrides': [
                        {
                            'name': f"algo-{loader_name}",
                            'environment': [
                                {'name': 'FAILSAFE_TRIGGER', 'value': 'true'},
                                {'name': 'TRIGGER_TIME', 'value': datetime.now(timezone.utc).isoformat()},
                            ]
                        }
                    ]
                }
            )

            if not response.get('tasks'):
                logger.warning(f"[FAILSAFE] Attempt {attempts}: ECS RunTask returned no tasks")
                if attempts < max_attempts:
                    logger.info(f"[FAILSAFE] Waiting 10s before retry...")
                    time.sleep(10)
                    continue
                return False

            task_arn = response['tasks'][0]['taskArn']
            task_id = task_arn.split('/')[-1]

            if verbose:
                logger.info(f"[FAILSAFE] Attempt {attempts}: ✓ ECS task launched: {task_id}")

            # Step 2: Poll CloudWatch Container Insights for task to reach RUNNING state
            # Task states: PROVISIONING → PENDING → ACTIVATING → RUNNING
            poll_start = time.time()
            poll_interval = 1.0  # Check every 1 second

            # Query CloudWatch Logs for task state transitions
            logs_client = boto3.client('logs', region_name=os.getenv('AWS_REGION', 'us-east-1'))

            poll_success = False
            while time.time() - poll_start < poll_timeout_sec:
                try:
                    # Check ECS DescribeTasks for current state
                    desc_response = ecs_client.describe_tasks(
                        cluster=cluster_arn,
                        tasks=[task_arn]
                    )

                    if desc_response.get('tasks'):
                        task = desc_response['tasks'][0]
                        task_state = task.get('lastStatus', '')

                        if verbose:
                            logger.debug(f"[FAILSAFE] Task {task_id} state: {task_state}")

                        if task_state == 'RUNNING':
                            elapsed = time.time() - poll_start
                            logger.info(f"[FAILSAFE] ✓ Loader task {task_id} confirmed RUNNING after {elapsed:.1f}s")

                            # Store actual_running_at for grace period compensation (Issue 12)
                            # Grace period should start from when task actually runs, not from trigger time
                            try:
                                import boto3
                                dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                                state_table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
                                state_table = dynamodb.Table(state_table_name)

                                now = time.time()
                                state_table.update_item(
                                    Key={'state_key': 'failsafe_trigger_log'},
                                    UpdateExpression='SET actual_running_at = :running_at, scheduling_delay_seconds = :delay',
                                    ExpressionAttributeValues={
                                        ':running_at': now,
                                        ':delay': elapsed,
                                    }
                                )
                                if verbose:
                                    logger.debug(f"[FAILSAFE] Stored actual_running_at and scheduling_delay: {elapsed:.1f}s")
                            except Exception as state_err:
                                logger.debug(f"[FAILSAFE] Could not store actual_running_at: {state_err}")

                            # Emit CloudWatch metric for ECS scheduling delay (how long from trigger to RUNNING)
                            try:
                                from algo.algo_metrics import MetricsPublisher
                                metrics = MetricsPublisher()
                                metrics.add_metric(
                                    'LoaderSchedulingDelaySeconds',
                                    elapsed,
                                    unit='Seconds',
                                    dimensions={'LoaderName': loader_name}
                                )
                                metrics.flush()
                                if verbose:
                                    logger.debug(f"[FAILSAFE] Published scheduling delay metric: {elapsed:.1f}s for {loader_name}")
                            except Exception as metric_err:
                                logger.debug(f"[FAILSAFE] Could not emit scheduling delay metric: {metric_err}")

                            # Alert if delay exceeds 5 minutes (indicates ECS queue backlog or provisioning issues)
                            if elapsed > 300:
                                logger.warning(f"[FAILSAFE] ECS scheduling delay EXCESSIVE for {loader_name}: {elapsed/60:.1f} minutes")
                                try:
                                    from algo.algo_alerts import AlertManager
                                    alerts = AlertManager()
                                    alerts.send_position_alert(
                                        'ECS',
                                        'LONG_SCHEDULING_DELAY',
                                        f'ECS task {loader_name} took {elapsed/60:.1f} min to reach RUNNING state. '
                                        f'This may indicate ECS cluster congestion or provisioning delays.',
                                        {'loader': loader_name, 'delay_seconds': elapsed}
                                    )
                                except Exception as alert_err:
                                    logger.debug(f"[FAILSAFE] Could not send scheduling delay alert: {alert_err}")

                            # SECONDARY HEALTH CHECK: Verify task is still running 5 seconds later
                            # Catch tasks that immediately fail (out of memory, missing env vars, code errors)
                            if verbose:
                                logger.debug(f"[FAILSAFE] Performing secondary health check in 5s...")
                            time.sleep(5)
                            try:
                                desc_follow = ecs_client.describe_tasks(cluster=cluster_arn, tasks=[task_arn])
                                if desc_follow.get('tasks'):
                                    task_follow = desc_follow['tasks'][0]
                                    task_state_follow = task_follow.get('lastStatus', '')
                                    if task_state_follow == 'RUNNING':
                                        if verbose:
                                            logger.debug(f"[FAILSAFE] ✓ Secondary check: Task {task_id} still RUNNING")
                                        poll_success = True
                                        break
                                    elif task_state_follow in ('STOPPED', 'STOPPING'):
                                        logger.critical(f"[FAILSAFE] FAILED: Task {task_id} stopped unexpectedly after reaching RUNNING. "
                                                      f"Reason: {task_follow.get('stoppedReason', 'unknown')}")
                                        if attempts < max_attempts:
                                            logger.info(f"[FAILSAFE] Will retry in 10s...")
                                            time.sleep(10)
                                            continue
                                        return False
                                    else:
                                        if verbose:
                                            logger.debug(f"[FAILSAFE] Task {task_id} transitioned to: {task_state_follow}")
                                        poll_success = True
                                        break
                            except Exception as follow_err:
                                logger.debug(f"[FAILSAFE] Secondary health check failed: {follow_err}")
                                # If we can't verify, assume OK (network issue)
                                poll_success = True
                                break
                        elif task_state in ('DEPROVISIONING', 'STOPPING', 'DEACTIVATING', 'STOPPED', 'DELETED'):
                            logger.warning(f"[FAILSAFE] Task {task_id} stopped prematurely: {task_state}")
                            if task.get('stoppedReason'):
                                logger.warning(f"  Reason: {task['stoppedReason']}")
                            break

                except Exception as desc_err:
                    logger.debug(f"[FAILSAFE] DescribeTasks failed: {desc_err}")

                time.sleep(poll_interval)

            if poll_success:
                return True
            elif attempts < max_attempts:
                logger.warning(f"[FAILSAFE] Attempt {attempts}: Task did not reach RUNNING within {poll_timeout_sec}s. "
                              f"Retrying in 10s...")
                time.sleep(10)
                continue
            else:
                logger.warning(f"[FAILSAFE] All {max_attempts} attempt(s) failed. "
                              "Task did not reach RUNNING state. Check ECS task definition and CloudWatch logs.")
                return False

        except Exception as ecs_err:
            if attempts < max_attempts:
                logger.warning(f"[FAILSAFE] Attempt {attempts} failed with error: {ecs_err}. Retrying in 10s...")
                time.sleep(10)
                continue
            else:
                logger.error(f"[FAILSAFE] All {max_attempts} attempt(s) failed. Last error: {ecs_err}")
                return False

    return False


def _check_failsafe_completion(state_table: Any, verbose: bool = False, timeout_sec: int = 7200) -> Optional[Dict[str, Any]]:
    """Check if a previous failsafe trigger has completed or timed out.

    Returns:
        None: No failsafe trigger in progress
        {'status': 'running', 'age_minutes': X}: Failsafe still running (age from trigger)
        {'status': 'timed_out', 'age_minutes': X}: Failsafe timed out (exceeded timeout_sec)
    """
    try:
        response = state_table.get_item(Key={'state_key': 'failsafe_trigger_log'})
        if 'Item' not in response:
            return None

        triggered_at = response['Item'].get('triggered_at', 0)
        completed_at = response['Item'].get('completed_at')
        current_time = time.time()
        age_minutes = (current_time - triggered_at) / 60

        # If completed_at is set, failsafe finished successfully
        if completed_at:
            if verbose:
                logger.debug(f"[FAILSAFE_TIMEOUT] Previous failsafe completed {(current_time - completed_at) / 60:.1f}m ago")
            return None

        # If timeout_sec exceeded and not completed, failsafe timed out
        if age_minutes > timeout_sec / 60:
            logger.warning(f"[FAILSAFE_TIMEOUT] Previous failsafe triggered {age_minutes:.1f}m ago ({timeout_sec/60:.0f}m timeout) but NOT COMPLETED")
            return {'status': 'timed_out', 'age_minutes': age_minutes}

        # Still within timeout window - failsafe still running
        if verbose:
            logger.debug(f"[FAILSAFE_TIMEOUT] Previous failsafe running {age_minutes:.1f}m ({timeout_sec/60:.0f}m timeout)")
        return {'status': 'running', 'age_minutes': age_minutes}

    except Exception as err:
        logger.debug(f"[FAILSAFE_TIMEOUT] Could not check failsafe timeout: {err}")
        return None

def _detect_hung_loader_task(loader_name: str, timeout_minutes: int = None) -> bool:
    """Detect if loader task has hung by checking heartbeat.

    Returns True if loader is marked RUNNING but hasn't updated heartbeat in > timeout_minutes.
    This allows Phase 1 to trigger a new loader when the old one is stuck.

    Timeout is configurable via algo_config (heartbeat_hung_timeout_minutes), defaults to 5 minutes.
    This is more responsive than the previous 10-minute default: if a task hangs at minute 4,
    it will be detected by minute 9 instead of minute 14.

    Args:
        loader_name: Name of loader table (e.g., 'price_daily', 'technical_data_daily')
        timeout_minutes: Override heartbeat timeout (reads from algo_config if not specified)

    Returns:
        True if task appears hung, False otherwise
    """
    try:
        from utils.database_context import DatabaseContext
        from datetime import datetime, timezone, timedelta

        # Use provided timeout or load from algo_config, default to 5 minutes (reduced from 10)
        if timeout_minutes is None:
            try:
                with DatabaseContext("read") as config_cur:
                    config_cur.execute(
                        "SELECT value FROM algo_config WHERE key = %s",
                        ('heartbeat_hung_timeout_minutes',)
                    )
                    config_result = config_cur.fetchone()
                    timeout_minutes = int(config_result[0]) if config_result else 5
            except Exception:
                timeout_minutes = 5  # Default to 5 minutes

        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT status, last_updated FROM data_loader_status WHERE table_name = %s",
                (loader_name,),
            )
            result = cur.fetchone()
            if not result:
                # No status record = task never started
                return False

            status, last_updated = result[0], result[1]

            # Only check for hung if marked as RUNNING
            if status != 'RUNNING':
                return False

            # Check if heartbeat is stale
            if not last_updated:
                # No last_updated timestamp = task just started, not stuck yet
                return False

            now = datetime.now(timezone.utc)
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)

            elapsed_minutes = (now - last_updated).total_seconds() / 60
            is_hung = elapsed_minutes > timeout_minutes

            if is_hung:
                logger.warning(
                    f"[HUNG_TASK] Loader {loader_name} marked RUNNING but no heartbeat for {elapsed_minutes:.0f} min (timeout: {timeout_minutes} min). "
                    f"Considering task hung and triggering failsafe."
                )
            else:
                logger.debug(
                    f"[HEARTBEAT] Loader {loader_name} healthy: last update {elapsed_minutes:.1f} min ago (timeout {timeout_minutes}m)"
                )

            return is_hung
    except Exception as e:
        logger.debug(f"[HUNG_TASK] Could not check loader heartbeat: {e}")
        return False

def _trigger_loader_failsafe(loader_name: str, verbose: bool = False, wait_timeout: int = 600) -> bool:
    """
    DEPRECATED: Use _trigger_loader_failsafe_with_verification instead.
    This function kept for backward compatibility only.
    """
    return _trigger_loader_failsafe_with_verification(loader_name, verbose, poll_timeout_sec=240)

def _check_failsafe_grace_period(state_table: Any, verbose: bool = False, loader_name: str = 'stock_prices_daily') -> Optional[float]:
    """Check if a previously-triggered failsafe is within grace period window.

    Now checks actual loader status (RUNNING/COMPLETED) instead of just timestamps.
    If loader is still RUNNING in database, grace period extends dynamically.
    If loader is COMPLETED, grace period is short-circuited (no redundant trigger needed).

    Returns:
        - Minutes since trigger if loader RUNNING or grace period not expired
        - None if loader COMPLETED or grace period expired

    Args:
        state_table: DynamoDB state table for trigger logs
        verbose: Whether to log verbose output
        loader_name: Name of loader to check status for (default: stock_prices_daily)
    """
    try:
        from utils.database_context import DatabaseContext

        # First check: is the loader actually running or completed?
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT status, last_updated FROM data_loader_status WHERE table_name = %s",
                    (loader_name.replace('_daily', ''),),  # Map loader name to table name
                )
                result = cur.fetchone()
                if result:
                    status, last_updated = result[0], result[1]
                    if status == 'COMPLETED':
                        logger.info(f"[FAILSAFE] Loader {loader_name} already COMPLETED, no need for failsafe trigger")
                        return None  # No need to trigger failsafe, loader already done
                    elif status == 'RUNNING':
                        logger.debug(f"[FAILSAFE] Loader {loader_name} still RUNNING (updated {last_updated}), within grace period")
                        # Extend grace period since loader is actively running
                        return 0.5  # Mark as "in grace period" but near expiry for next check
        except Exception as db_err:
            logger.debug(f"[FAILSAFE] Could not check loader status: {db_err}, falling back to time-based grace period")

        # Fallback: check DynamoDB timestamp-based grace period
        # FIXED Issue 12: Use actual_running_at if available (when loader actually started),
        # otherwise fall back to triggered_at (when trigger was initiated).
        # This ensures grace period is counted from when ECS task actually runs, not from trigger time.
        response = state_table.get_item(Key={'state_key': 'failsafe_trigger_log'})
        if 'Item' not in response:
            return None

        triggered_at = response['Item'].get('triggered_at', 0)
        actual_running_at = response['Item'].get('actual_running_at')  # When task actually started RUNNING
        scheduling_delay = response['Item'].get('scheduling_delay_seconds', 0)  # ECS provisioning delay in seconds

        current_time = time.time()

        # Use actual_running_at for grace period if available (more accurate)
        # Otherwise fall back to triggered_at (for triggers that haven't reached RUNNING yet)
        if actual_running_at:
            age_minutes = (current_time - actual_running_at) / 60
            age_source = f"running_at (delay {scheduling_delay:.0f}s)"
        else:
            age_minutes = (current_time - triggered_at) / 60
            age_source = "triggered_at (no RUNNING confirmation yet)"

        # Dynamic grace period (configurable via algo_config):
        # Read from database if available, default to 150 minutes
        # - stock_prices_daily can take up to 2h with yfinance lag
        # - Grace period starts from actual_running_at, so no need to add ECS delay anymore
        # - Total: 150 minutes (2.5 hours) as hard limit
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SELECT value FROM algo_config WHERE key = %s", ('failsafe_grace_period_minutes',))
                result = cur.fetchone()
                max_grace_period = int(result[0]) if result and result[0] else 150
        except Exception as config_err:
            logger.debug(f"[FAILSAFE] Could not read grace period config: {config_err}, using default 150m")
            max_grace_period = 150

        if age_minutes < max_grace_period:
            if verbose:
                logger.debug(f"[FAILSAFE] Within grace period: {age_source} {age_minutes:.0f}m ago (max {max_grace_period}m)")
            return age_minutes
        else:
            logger.info(f"[FAILSAFE] Grace period expired: {age_source} {age_minutes:.0f}m ago (>{max_grace_period}m)")
            return None

    except Exception as err:
        logger.debug(f"[FAILSAFE] Could not check grace period: {err}")
        return None

def _get_most_recent_trading_day(from_date: _date = None, trading_days_back: int = 1) -> _date:
    """Get the Nth most recent trading day from a given date.

    Args:
        from_date: Start date (default: today)
        trading_days_back: How many trading days to go back (1 = most recent trading day)

    Returns:
        The most recent trading day N days back
    """
    from algo.algo_market_calendar import MarketCalendar

    if from_date is None:
        from_date = _date.today()

    result = from_date
    count = 0
    max_iterations = 30  # prevent infinite loop

    while count < trading_days_back and max_iterations > 0:
        result -= timedelta(days=1)
        if MarketCalendar.is_trading_day(result):
            count += 1
        max_iterations -= 1

    return result if count == trading_days_back else from_date

def _check_data_patrol(cur: Any, run_date: _date, verbose: bool, log_phase_result_fn: Callable) -> bool:
    """Check data patrol results. Fail-closed if critical/error findings.

    Only checks FRESH patrol runs (completed in last 3 hours).
    Returns: True if patrol OK, False if critical/error issues found.
    """
    try:
        cur.execute("""
            SELECT patrol_run_id, MAX(created_at) AS run_at FROM data_patrol_log
            GROUP BY patrol_run_id
            ORDER BY MAX(created_at) DESC LIMIT 1
        """)
        latest_run = cur.fetchone()
        if not latest_run:
            if verbose:
                logger.info("No patrol data available — skipping patrol check")
            return True

        latest_run_id, latest_run_at = latest_run

        # Check if patrol is fresh (within last 3 hours).
        # This prevents checking stale results while a fresh patrol is running.
        from datetime import datetime as dt
        now = dt.now(timezone.utc)
        if isinstance(latest_run_at, str):
            latest_run_at = dt.fromisoformat(latest_run_at.replace('Z', '+00:00'))

        age_seconds = (now - latest_run_at).total_seconds()
        if age_seconds > 10800:  # 3 hours
            logger.warning(
                f"[PATROL] Latest patrol ({latest_run_id}) is {age_seconds/3600:.1f}h old. "
                f"Too stale to check. Skipping patrol validation (triggering fresh patrol asynchronously)."
            )

            # Check if a patrol trigger was already attempted recently (within last 1 hour)
            # CRITICAL FIX: Distinguish between "patrol running" vs "patrol failed"
            # Only apply grace period if patrol COMPLETED successfully, not just if it was triggered
            # ENHANCED: Graceful degradation if DynamoDB is unavailable
            patrol_trigger_already_attempted = False
            patrol_trigger_age_minutes = None
            try:
                import boto3
                dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                state_table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
                state_table = dynamodb.Table(state_table_name)

                response = state_table.get_item(Key={'state_key': 'patrol_trigger_log'})
                if 'Item' in response:
                    last_trigger_time = response['Item'].get('triggered_at', 0)
                    last_success_time = response['Item'].get('last_success_at', 0)  # When patrol last COMPLETED
                    current_time = time.time()
                    patrol_trigger_age_minutes = (current_time - last_trigger_time) / 60
                    patrol_success_age_minutes = (current_time - last_success_time) / 60 if last_success_time else float('inf')

                    # Only apply grace period if patrol COMPLETED successfully in last hour
                    # If patrol was triggered but never completed, OR if last success was >1 hour ago, trigger fresh patrol
                    if patrol_trigger_age_minutes < 60 and patrol_success_age_minutes < 60:
                        patrol_trigger_already_attempted = True
                        logger.info(f"[PATROL] Grace period: Patrol trigger already attempted {patrol_trigger_age_minutes:.0f}m ago "
                                   f"and COMPLETED successfully {patrol_success_age_minutes:.0f}m ago. "
                                   f"Skipping redundant trigger, allowing in-flight patrol to complete.")
                    elif patrol_success_age_minutes >= 60:
                        logger.warning(f"[PATROL] Last successful patrol was {patrol_success_age_minutes:.0f}m ago (>1h). "
                                      f"Triggering fresh patrol to ensure current data freshness.")
                    else:
                        logger.warning(f"[PATROL] Patrol was triggered {patrol_trigger_age_minutes:.0f}m ago but never completed successfully. "
                                      f"Triggering fresh patrol.")
            except Exception as state_err:
                logger.debug(f"[PATROL] DynamoDB unavailable: {state_err}. Falling back to database check...")
                # Graceful degradation: if DynamoDB is down, check patrol timestamp directly from database
                try:
                    cur.execute("""
                        SELECT MAX(created_at) FROM data_patrol_log
                        LIMIT 1
                    """)
                    result = cur.fetchone()
                    if result and result[0]:
                        last_patrol_time = result[0]
                        if isinstance(last_patrol_time, str):
                            from datetime import datetime as dt
                            last_patrol_time = dt.fromisoformat(last_patrol_time.replace('Z', '+00:00'))

                        current_time = datetime.now(timezone.utc)
                        if isinstance(last_patrol_time, str):
                            last_patrol_time = datetime.fromisoformat(last_patrol_time.replace('Z', '+00:00'))
                        else:
                            # Convert naive datetime to aware
                            if last_patrol_time.tzinfo is None:
                                last_patrol_time = last_patrol_time.replace(tzinfo=timezone.utc)

                        patrol_age = (current_time - last_patrol_time).total_seconds() / 60

                        if patrol_age < 60:
                            patrol_trigger_already_attempted = True
                            logger.info(f"[PATROL] Grace period (DynamoDB fallback): Last patrol {patrol_age:.0f}m ago (<1h). "
                                       f"Skipping redundant trigger. (DynamoDB unavailable, using DB as source)")
                        else:
                            logger.warning(f"[PATROL] Last patrol was {patrol_age:.0f}m ago (>1h, no DynamoDB). "
                                          f"Triggering fresh patrol. (DynamoDB unavailable, using DB as source)")
                except Exception as db_err:
                    logger.debug(f"[PATROL] Database fallback also failed: {db_err}. Proceeding with fresh trigger.")

            # Trigger fresh patrol asynchronously if not already attempted recently
            if not patrol_trigger_already_attempted:
                try:
                    import boto3
                    ecs_client = boto3.client('ecs', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                    cluster_arn = os.getenv('ECS_CLUSTER_ARN', 'algo-cluster')
                    logger.info("[PATROL] Triggering fresh data patrol via ECS...")

                    response = ecs_client.run_task(
                        cluster=cluster_arn,
                        taskDefinition='algo-data-patrol',
                        launchType='FARGATE',
                        networkConfiguration={
                            'awsvpcConfiguration': {
                                'subnets': os.getenv('ECS_SUBNETS', '').split(','),
                                'securityGroups': os.getenv('ECS_SECURITY_GROUPS', '').split(','),
                                'assignPublicIp': 'DISABLED'
                            }
                        }
                    )

                    if response.get('tasks'):
                        task_arn = response['tasks'][0]['taskArn']
                        task_id = task_arn.split('/')[-1]
                        logger.info(f"[PATROL] ✓ Fresh patrol task triggered: {task_id}")

                        # Verify task reaches RUNNING state (quick check, 5s timeout)
                        poll_start = time.time()
                        while time.time() - poll_start < 5:
                            try:
                                desc = ecs_client.describe_tasks(cluster=cluster_arn, tasks=[task_arn])
                                if desc.get('tasks'):
                                    task = desc['tasks'][0]
                                    if task.get('lastStatus') in ('RUNNING', 'PROVISIONING', 'PENDING'):
                                        logger.debug(f"[PATROL] Task {task_id} state: {task.get('lastStatus')}")
                                        break
                                    elif task.get('lastStatus') in ('STOPPED', 'STOPPING'):
                                        logger.warning(f"[PATROL] Task {task_id} stopped: {task.get('stoppedReason', 'unknown')}")
                                        break
                            except Exception:
                                pass
                            time.sleep(0.5)

                        # Log trigger timestamp for grace period check in future runs
                        # CRITICAL: Initialize last_success_at = triggered_at so grace period logic works
                        # If we only set triggered_at, next run sees last_success_at=0 (default) and triggers redundant patrol
                        try:
                            now = time.time()
                            state_table.put_item(Item={
                                'state_key': 'patrol_trigger_log',
                                'triggered_at': now,
                                'last_success_at': now,  # Initialize to trigger time; will update when patrol completes
                                'ttl': int(now) + 3600,  # 1-hour TTL
                            })
                            logger.debug("[PATROL] Logged patrol trigger timestamp for grace period")
                        except Exception as log_err:
                            logger.debug(f"[PATROL] Could not log trigger timestamp: {log_err}")
                    else:
                        logger.warning("[PATROL] ECS RunTask returned no tasks")
                except Exception as patrol_trigger_err:
                    logger.warning(f"[PATROL] Could not trigger fresh patrol: {patrol_trigger_err}")

            return True  # Stale patrol: don't block, fresh patrol running

        # Now get results for only this run
        cur.execute("""
            SELECT MAX(severity) as worst_severity,
                   COUNT(*) as total_findings,
                   COUNT(CASE WHEN severity = 'critical' THEN 1 END) as critical_count,
                   COUNT(CASE WHEN severity = 'error' THEN 1 END) as error_count,
                   COUNT(CASE WHEN severity = 'warn' THEN 1 END) as warn_count,
                   COUNT(CASE WHEN severity = 'info' THEN 1 END) as info_count
            FROM data_patrol_log
            WHERE patrol_run_id = %s
        """, (latest_run_id,))
        row = cur.fetchone()

        if not row or not row[0]:
            if verbose:
                logger.info("No findings in latest patrol")
            return True

        worst_severity, total_findings, critical_count, error_count, warn_count, info_count = row

        if verbose:
            logger.info(f"Patrol {latest_run_id}: {total_findings} findings "
                        f"(critical={critical_count}, error={error_count}, warn={warn_count})")

        # Fetch flagged findings for alerting
        cur.execute("""
            SELECT check_name, severity, target_table, message
            FROM data_patrol_log
            WHERE patrol_run_id = %s AND severity IN ('critical', 'error')
            ORDER BY severity DESC
        """, (latest_run_id,))
        flagged = [{'check': r[0], 'severity': r[1], 'target': r[2], 'message': r[3]}
                   for r in cur.fetchall()]

        if flagged:
            logger.warning(f"Patrol found {len(flagged)} critical/error findings")
            for f in flagged:
                logger.warning(f"  {f['severity'].upper()}: {f['check']} on {f['target']}: {f['message'][:100]}")

        # Send alerts on CRITICAL or ERROR
        if critical_count > 0 or error_count > 0:
            alerts = AlertManager()
            alerts.send_patrol_alert(
                latest_run_id,
                {'critical': critical_count, 'error': error_count, 'warn': warn_count, 'info': info_count},
                flagged
            )

        # Graduated alerting thresholds for data quality issues
        # CRITICAL: 3+ errors or 1+ critical → halt trading
        # MEDIUM: 2+ errors or 10+ warnings → alert but continue (observable)
        # INFO: 5+ warnings → warn but continue (background degradation)

        alerts = AlertManager()

        # FAIL-CLOSED: critical findings always block
        if critical_count >= 1:
            logger.critical(f"[HALT] Data patrol found {critical_count} CRITICAL issue(s) - BLOCKING ORCHESTRATOR")
            if verbose:
                logger.info(f"  [HALT] Data patrol found {critical_count} CRITICAL issue(s)")
            log_phase_result_fn(1, 'data_patrol', 'halt',
                               f'Critical data quality issues: {critical_count} critical finding(s)')
            try:
                alerts.send_position_alert(
                    'DATA_QUALITY',
                    'PATROL_CRITICAL',
                    f'Data patrol found {critical_count} CRITICAL issue(s). Orchestrator halted. '
                    f'Recent findings: {", ".join([f["check"] for f in flagged[:3]])}',
                    {'critical_count': critical_count, 'findings': flagged}
                )
            except Exception as alert_err:
                logger.debug(f"Could not send critical alert: {alert_err}")
            return False

        # FAIL-CLOSED: too many errors block
        if error_count >= 3:
            logger.error(f"[HALT] Data patrol found {error_count} ERROR issues - BLOCKING ORCHESTRATOR")
            if verbose:
                logger.error(f"  [HALT] Data patrol found {error_count} error(s)")
            log_phase_result_fn(1, 'data_patrol', 'halt',
                               f'Data quality errors: {error_count} finding(s) — too many to continue safely')
            try:
                alerts.send_position_alert(
                    'DATA_QUALITY',
                    'PATROL_ERRORS',
                    f'Data patrol found {error_count} ERROR issue(s). Orchestrator halted to prevent bad trades. '
                    f'Recent errors: {", ".join([f["check"] for f in flagged[:3]])}',
                    {'error_count': error_count, 'findings': flagged}
                )
            except Exception as alert_err:
                logger.debug(f"Could not send error alert: {alert_err}")
            return False

        # MEDIUM: 2+ errors or 10+ warnings → observable issue, alert but continue
        if error_count >= 2 or warn_count >= 10:
            logger.warning(
                f"[MEDIUM] Data patrol found {error_count} errors, {warn_count} warnings. "
                f"Issues detected but continuing with caution."
            )
            log_phase_result_fn(1, 'data_patrol', 'warn',
                               f'Data quality issues: {error_count} error(s), {warn_count} warning(s) — continuing with caution')
            try:
                alerts.send_position_alert(
                    'DATA_QUALITY',
                    'PATROL_MEDIUM',
                    f'Data patrol found {error_count} ERROR(s) and {warn_count} WARNING(s). '
                    f'Continuing but monitor closely. Examples: {", ".join([f["check"] for f in flagged[:3]])}',
                    {'error_count': error_count, 'warn_count': warn_count}
                )
            except Exception as alert_err:
                logger.debug(f"Could not send medium alert: {alert_err}")

        # INFO: 5+ warnings → background degradation, just warn
        elif warn_count >= 5:
            logger.warning(f"[INFO] Data patrol found {warn_count} warnings (early degradation signs)")
            log_phase_result_fn(1, 'data_patrol', 'info',
                               f'Data quality warnings: {warn_count} warning(s) — watch for trends')

        # Emit CloudWatch metrics for patrol findings
        try:
            from algo.algo_metrics import MetricsPublisher
            metrics = MetricsPublisher()
            metrics.add_metric('PatrolCriticalFindings', critical_count, unit='Count')
            metrics.add_metric('PatrolErrorFindings', error_count, unit='Count')
            metrics.add_metric('PatrolWarningFindings', warn_count, unit='Count')
            metrics.add_metric('PatrolInfoFindings', info_count, unit='Count')
            metrics.add_metric('PatrolTotalFindings', total_findings, unit='Count')
            metrics.flush()
        except Exception as metric_err:
            logger.debug(f"Could not emit patrol metrics: {metric_err}")

        return True

    except Exception as e:
        # If patrol check fails, fail-closed (don't trade on uncertain data)
        logger.error(f"  [HALT] Data patrol check failed: {e}")
        log_phase_result_fn(1, 'data_patrol', 'halt',
                           f'Patrol execution error: {str(e)[:100]}')
        return False

def _check_pipeline_health(cur: Any, run_date: _date, verbose: bool) -> None:
    """Check that all required tables have recent data for signal processing."""
    try:
        # Count recent rows (from last 5 days) in each critical table
        required_tables = {
            'price_daily': 'price_daily (OHLCV)',
            'buy_sell_daily': 'buy_sell_daily (entry signals)',
            'trend_template_data': 'trend_template_data (Minervini/Weinstein scores)',
            'technical_data_daily': 'technical_data_daily (MA/RSI/ATR)',
            'signal_quality_scores': 'signal_quality_scores (SQS >= 40 gate)',
            'swing_trader_scores': 'swing_trader_scores (final ranking)',
            'market_health_daily': 'market_health_daily (Tier 2 gate)',
            'sector_ranking': 'sector_ranking (Tier 6 context)',
            'industry_ranking': 'industry_ranking (Tier 6 context)',
            'stock_scores': 'stock_scores (Tier 6 scoring)',
        }

        five_days_ago = run_date - timedelta(days=5)
        status = {}

        for table, description in required_tables.items():
            try:
                # Count rows added in the last 5 days
                if table == 'price_daily':
                    assert_safe_table(table)
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE date >= %s", (five_days_ago,))
                elif table in ('buy_sell_daily', 'trend_template_data', 'technical_data_daily',
                              'signal_quality_scores', 'swing_trader_scores', 'market_health_daily',
                              'sector_ranking', 'industry_ranking', 'stock_scores'):
                    # Different tables use different date column names
                    if table == 'stock_scores':
                        col = 'updated_at'
                    elif table == 'industry_ranking':
                        col = 'date_recorded'
                    else:
                        col = 'date'
                    assert_safe_table(table)
                    assert_safe_column(col)
                    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} >= %s", (five_days_ago,))
                else:
                    assert_safe_table(table)
                    cur.execute(f"SELECT COUNT(*) FROM {table} LIMIT 1")

                row = cur.fetchone()
                count = row[0] if row else 0
                status[table] = count
                flag = '[OK]' if count > 0 else '[EMPTY]'
                if verbose:
                    logger.info(f"    {flag} {description:50s}: {count:,} rows (5d)")
            except Exception as e:
                status[table] = 0
                if verbose:
                    logger.warning(f"    [ERROR] {description}: {e}")

        # Alert if any critical table is empty
        empty_tables = [t for t, c in status.items() if c == 0]
        if empty_tables:
            empty_desc = ', '.join([required_tables[t] for t in empty_tables])
            logger.error(f"  [ALERT] Pipeline missing data in: {empty_desc}")
            logger.error(f"  Run the loaders to populate: {', '.join(empty_tables)}")
            alerts = AlertManager()
            alerts.critical(
                f"Pipeline data gap: {empty_desc}. No signals can pass filters until data is loaded."
            )

    except Exception as e:
        logger.warning(f"Pipeline health check failed: {e}")

def _validate_required_schema_columns(cur: Any, verbose: bool = False) -> bool:
    """Pre-flight validation: ensure all required schema columns exist with correct types and indexes.

    Checks:
    1. Column existence (critical columns must exist)
    2. Column types (must match expected data types)
    3. Index existence (performance-critical indexes must exist)

    If columns don't exist or have wrong types, migration may have failed or database is out of sync.

    Returns: True if all validations pass, False if any issues found (fail-closed)
    """
    required_columns = {
        'signal_quality_scores': [
            ('buy_sell_daily_age_days', 'integer'),
            ('technical_data_age_days', 'integer'),
            ('trend_template_age_days', 'integer'),
        ],
        'price_daily': [
            ('symbol', 'text'),
            ('date', 'text'),  # Stored as ISO string
            ('close', 'numeric'),
        ],
        'market_health_daily': [
            ('date', 'text'),
            ('spy_close', 'numeric'),
        ],
    }

    required_indexes = {
        'signal_quality_scores': [
            'idx_signal_quality_scores_symbol_date',  # Critical for Phase 5 lookups
        ],
        'price_daily': [
            'idx_price_daily_symbol_date',  # Critical for Phase 3 position monitor
        ],
    }

    issues = []

    # Check column existence and types
    for table, columns in required_columns.items():
        for col, expected_type in columns:
            try:
                # Check if column exists and get its data type
                cur.execute(f"""
                    SELECT data_type FROM information_schema.columns
                    WHERE table_name = %s AND column_name = %s
                """, (table, col))
                result = cur.fetchone()

                if not result:
                    issues.append(f"MISSING_COLUMN: {table}.{col}")
                else:
                    actual_type = result[0].lower()
                    # Allow numeric types to be flexible (int, bigint, smallint all OK for integer)
                    if expected_type == 'integer' and actual_type not in ('integer', 'bigint', 'smallint', 'int2', 'int4', 'int8'):
                        issues.append(f"WRONG_TYPE: {table}.{col} is {actual_type}, expected {expected_type}")
                    elif expected_type == 'text' and actual_type not in ('text', 'character varying', 'varchar'):
                        issues.append(f"WRONG_TYPE: {table}.{col} is {actual_type}, expected {expected_type}")

                    if verbose:
                        logger.debug(f"[SCHEMA] ✓ {table}.{col} exists ({actual_type})")

            except Exception as e:
                logger.warning(f"[SCHEMA] Could not verify column {table}.{col}: {e}")
                issues.append(f"VERIFY_ERROR: {table}.{col} ({str(e)[:50]})")

    # Check index existence (performance validation)
    for table, indexes in required_indexes.items():
        for index_name in indexes:
            try:
                cur.execute(f"""
                    SELECT 1 FROM pg_indexes
                    WHERE tablename = %s AND indexname = %s
                    LIMIT 1
                """, (table, index_name))
                result = cur.fetchone()

                if not result:
                    logger.warning(f"[SCHEMA] INDEX MISSING: {index_name} on {table}. "
                                 f"Performance may degrade. Performance queries will be slower.")
                    # Don't fail on missing indexes - they improve performance but aren't critical for correctness
                else:
                    if verbose:
                        logger.debug(f"[SCHEMA] ✓ Index {index_name} exists")

            except Exception as e:
                logger.debug(f"[SCHEMA] Could not verify index {index_name}: {e}")
                # Don't fail on index check errors - they're non-blocking

    # Report all issues found
    if issues:
        critical_issues = [i for i in issues if i.startswith(('MISSING_COLUMN', 'WRONG_TYPE'))]
        warning_issues = [i for i in issues if i.startswith('VERIFY_ERROR')]

        if critical_issues:
            logger.critical(f"[SCHEMA] Critical schema issues found:")
            for issue in critical_issues:
                logger.critical(f"  - {issue}")
            logger.critical("[SCHEMA] Database schema migration may have failed. Check RDS for errors.")
            return False

        if warning_issues:
            logger.warning(f"[SCHEMA] Schema verification warnings:")
            for issue in warning_issues:
                logger.warning(f"  - {issue}")

    if verbose:
        logger.info("[SCHEMA] ✓ All required columns present with correct types")
    return True

def _check_rds_connection_pool_health(cur: Any, verbose: bool = False, fail_closed_at: int = 80) -> bool:
    """Pre-flight validation: check RDS connection pool health.

    Queries active connections, kills hung connections, warns if pool is under heavy load.
    Emits metrics for monitoring.

    Args:
        cur: Database cursor
        verbose: Whether to log verbose output
        fail_closed_at: Halt if active connections exceed this threshold (default 80)

    Returns: True if pool OK (<80 connections), False if circuit breaker triggered (>80)
    """
    try:
        # STEP 1: Kill hung connections idle >15 minutes (900s)
        try:
            cur.execute("""
                SELECT pid, usename, application_name,
                       EXTRACT(EPOCH FROM (now() - state_change)) as idle_seconds
                FROM pg_stat_activity
                WHERE state = 'idle' AND query_start < now() - interval '15 minutes'
                LIMIT 10  -- Kill max 10 connections at a time to avoid disruption
            """)
            hung_connections = cur.fetchall()
            if hung_connections:
                killed_count = 0
                for pid, usename, app_name, idle_secs in hung_connections:
                    try:
                        cur.execute("SELECT pg_terminate_backend(%s)", (pid,))
                        killed_count += 1
                        logger.info(f"[RDS-POOL] Killed idle connection pid={pid} ({usename}/{app_name}, idle {idle_secs:.0f}s)")
                    except Exception as kill_err:
                        logger.debug(f"[RDS-POOL] Could not kill connection {pid}: {kill_err}")
                if killed_count > 0:
                    logger.warning(f"[RDS-POOL] Terminated {killed_count} hung connections (idle >15min)")
        except Exception as hung_err:
            logger.debug(f"[RDS-POOL] Could not check for hung connections: {hung_err}")

        # STEP 2: Query active connections
        cur.execute("""
            SELECT count(*) as active_connections,
                   max(EXTRACT(EPOCH FROM (now() - state_change))) as max_idle_seconds
            FROM pg_stat_activity
            WHERE state != 'idle'
        """)
        result = cur.fetchone()
        if result:
            active_conn, max_idle = result
            active_conn = active_conn or 0
            max_idle = max_idle or 0

            if verbose:
                logger.info(f"[RDS-POOL] Active connections: {active_conn}, Max idle: {max_idle:.0f}s")

            # Emit metrics for CloudWatch monitoring
            try:
                from algo.algo_metrics import MetricsPublisher
                metrics = MetricsPublisher()
                metrics.add_metric(
                    'RDSActiveConnections',
                    active_conn,
                    unit='Count',
                    dimensions={'DBInstance': os.getenv('DB_HOST', 'algo-db')}
                )
                if max_idle > 0:
                    metrics.add_metric(
                        'RDSMaxIdleSeconds',
                        max_idle,
                        unit='Seconds',
                        dimensions={'DBInstance': os.getenv('DB_HOST', 'algo-db')}
                    )
                metrics.flush()
            except Exception as metric_err:
                logger.debug(f"[RDS-POOL] Could not emit connection pool metrics: {metric_err}")

            # Circuit breaker: fail-closed if connections exceed threshold
            if active_conn >= fail_closed_at:
                logger.critical(
                    f"[RDS-POOL] CIRCUIT BREAKER TRIGGERED: {active_conn} active connections (>={fail_closed_at} threshold). "
                    f"RDS pool exhaustion risk. Halting Phase 1 to prevent cascade failures."
                )
                try:
                    alerts = AlertManager()
                    alerts.send_position_alert(
                        'RDS',
                        'CONNECTION_POOL_EXHAUSTION',
                        f'RDS connection pool critically high: {active_conn} active connections (>={fail_closed_at}). '
                        f'Circuit breaker triggered - Phase 1 halted to prevent cascade failures.',
                        {'active_connections': active_conn, 'max_idle_seconds': max_idle}
                    )
                except Exception as alert_err:
                    logger.debug(f"[RDS-POOL] Could not send alert: {alert_err}")
                return False  # FAIL-CLOSED: halt orchestrator

            # Warn if pool is getting full
            if active_conn >= 60:
                logger.warning(f"[RDS-POOL] ⚠️ High connection load: {active_conn} active connections (pool 75% full)")
            elif active_conn >= 40:
                logger.info(f"[RDS-POOL] Connection pool at 50% capacity ({active_conn} active). Monitor for growth.")

    except Exception as e:
        logger.debug(f"[RDS-POOL] Could not check connection pool health: {e}. Proceeding normally.")

    return True  # Continue if pool OK

def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable,
) -> PhaseResult:
    """Execute Phase 1: Data Freshness Check.

    Args:
        config: Configuration object
        run_date: Date for this run
        dry_run: Whether running in dry-run mode
        alerts: AlertManager instance
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results

    Returns:
        PhaseResult with status and data
    """
    logger.debug(f"Phase 1: Starting data freshness check for run_date={run_date}")

    try:
        # Pre-flight: validate schema and RDS connection pool before proceeding
        try:
            with DatabaseContext('read') as cur:
                if not _validate_required_schema_columns(cur, verbose):
                    logger.critical("[SCHEMA] Pre-flight validation failed - halting orchestrator")
                    log_phase_result_fn(1, 'schema_validation', 'halt',
                                       'Required schema columns missing - database schema migration incomplete')
                    return PhaseResult(1, 'schema_validation', 'halted', {}, True,
                                     'Schema validation failed: missing required columns')

                # Check RDS connection pool health (circuit breaker if >80 connections)
                try:
                    pool_ok = _check_rds_connection_pool_health(cur, verbose)
                    if not pool_ok:
                        log_phase_result_fn(1, 'rds_connection_pool', 'halt',
                                           'RDS connection pool exhaustion (>80 connections)')
                        return PhaseResult(1, 'rds_connection_pool', 'halted', {}, True,
                                         'RDS connection pool circuit breaker triggered: >80 active connections')
                except Exception as pool_err:
                    logger.debug(f"[RDS-POOL] Skipping connection pool check: {pool_err}")

        except Exception as e:
            logger.error(f"[SCHEMA] Pre-flight validation error: {e}")
            log_phase_result_fn(1, 'schema_validation', 'halt',
                               f'Schema validation error: {str(e)[:100]}')
            return PhaseResult(1, 'schema_validation', 'halted', {}, True,
                             f'Schema validation failed: {str(e)[:100]}')

        try:
            from algo.algo_pipeline_health import PipelineHealth
            health = PipelineHealth()
            status = health.get_pipeline_status()
            # log_health_check writes to data_loader_status — skip in Lambda to
            # avoid an extra DB round-trip on every Phase 1 run.
            if not os.getenv('AWS_LAMBDA_FUNCTION_NAME'):
                health.log_health_check(status)
            logger.debug(f"Phase 1: Pipeline health check complete - {status.healthy_count}/{status.total_count} healthy")

            if verbose:
                logger.info(f"  [HEALTH] Pipeline: {status.healthy_count}/{status.total_count} tables healthy "
                           f"({status.coverage_pct:.0f}%)")

            # Log any critical alerts
            for alert in status.critical_alerts:
                logger.error(f"  [CRITICAL] {alert}")
                log_phase_result_fn(1, 'pipeline_health', 'halt', alert)
                return PhaseResult(1, 'pipeline_health', 'halted', {}, True, alert)

            # Log warnings but don't fail
            for warning in status.warnings:
                logger.warning(f"  [WARNING] {warning}")

        except Exception as e:
            logger.warning(f"  [WARN] Pipeline health check failed: {e}")
            # Don't fail-close on health check error, let other checks handle it

        # NOTE: ANALYZE moved to morning prep pipeline (4:30 AM ET) to run once daily instead of 4x.
        # Previously: ANALYZE took ~7.8s and ran at 9:30 AM, 1 PM, 3 PM, 5:30 PM = 31.2s/day wasted
        # Now: ANALYZE runs once in morning prep, statistics fresh for all 4 daily Phase 1 runs.
        # If statistics become stale during day (unlikely), cached data_loader_status avoids slow scans.

        # Use data_loader_status (tiny, always fast) as primary source.
        # Scanning price_daily directly takes 130s+ when the EOD pipeline is writing
        # millions of rows concurrently — data_loader_status is a single-row-per-table
        # lookup that returns in milliseconds regardless of write load.
        # Cache results in DynamoDB to avoid repeated queries during same day (run at 9:30, 1, 3, 5:30 PM).
        dates = {}
        cache_key = f"data_loader_status-{run_date.isoformat()}"

        # Step 1: Try DynamoDB cache first (5-minute TTL)
        try:
            import boto3
            dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
            cache_table_name = os.getenv('CACHE_TABLE', 'algo_phase1_cache')
            cache_table = dynamodb.Table(cache_table_name)

            response = cache_table.get_item(Key={'cache_key': cache_key})
            if 'Item' in response:
                cached_dates = response['Item'].get('dates', {})
                cache_age = datetime.now(timezone.utc).timestamp() - response['Item'].get('created_at', 0)
                if cache_age < 300:  # 5-minute TTL
                    dates = cached_dates
                    logger.info(f"Phase 1: Using cached data_loader_status (age={cache_age:.0f}s)")
        except Exception as cache_err:
            logger.debug(f"Phase 1: Cache lookup failed ({cache_err}), will try database")

        # Step 2: If cache miss, query database
        if not dates:
            try:
                with DatabaseContext('read') as cur:
                    cur.execute("SET statement_timeout = 15000")  # 15s — should be instant
                    cur.execute("""
                        SELECT table_name, latest_date
                        FROM data_loader_status
                        WHERE table_name IN (
                            'price_daily', 'etf_price_daily',
                            'market_health_daily', 'trend_template_data',
                            'signal_quality_scores', 'buy_sell_daily'
                        )
                    """)
                    for r in cur.fetchall():
                        dates[r['table_name']] = r['latest_date']

                    # Cache the results for future runs today
                    if dates:
                        try:
                            cache_table.put_item(Item={
                                'cache_key': cache_key,
                                'dates': dates,
                                'created_at': datetime.now(timezone.utc).timestamp(),
                                'ttl': int(time.time()) + 300,  # 5-minute TTL
                            })
                            logger.debug(f"Phase 1: Cached {len(dates)} table dates")
                        except Exception as cache_write_err:
                            logger.debug(f"Phase 1: Cache write failed ({cache_write_err}), continuing")

            except Exception as e:
                logger.warning(f"Phase 1: data_loader_status query failed ({e}), trying direct table scan")

        # Fall back to direct scan only for tables missing from data_loader_status.
        # Use ORDER BY date DESC LIMIT 1 instead of MAX(date) — forces an index scan
        # regardless of stale PostgreSQL statistics (avoids sequential scan on t4g.micro).
        # Use ONE connection for ALL missing tables — DB connection establishment takes
        # 30-95s under heavy load; opening a separate connection per table would take
        # 3× as long. Single connection with per-query 30s timeouts via SAVEPOINTs.
        missing = [t for t in ('price_daily', 'market_health_daily', 'trend_template_data') if t not in dates]
        if missing:
            try:
                with DatabaseContext('read') as cur:
                    cur.execute("SET statement_timeout = 30000")  # 30s per query
                    for table in missing:
                        try:
                            cur.execute("SAVEPOINT scan")
                            if table == 'price_daily':
                                cur.execute(
                                    "SELECT date FROM price_daily WHERE symbol='SPY' ORDER BY date DESC LIMIT 1"
                                )
                                row = cur.fetchone()
                                if not row:
                                    cur.execute(
                                        "SELECT date FROM etf_price_daily WHERE symbol='SPY' ORDER BY date DESC LIMIT 1"
                                    )
                                    row = cur.fetchone()
                            else:
                                cur.execute(f"SELECT date FROM {table} ORDER BY date DESC LIMIT 1")
                                row = cur.fetchone()
                            cur.execute("RELEASE SAVEPOINT scan")
                            if row:
                                dates[table] = row[0]
                                logger.info(f"Phase 1: direct scan found {table} latest={row[0]}")
                        except Exception as e:
                            try:
                                cur.execute("ROLLBACK TO SAVEPOINT scan")
                                cur.execute("RELEASE SAVEPOINT scan")
                            except Exception:
                                pass
                            logger.warning(f"Phase 1: direct scan for {table} failed ({e})")
            except Exception as e:
                logger.warning(f"Phase 1: direct scan connection failed ({e})")

        spy_date = dates.get('price_daily') or dates.get('etf_price_daily')
        mh_date = dates.get('market_health_daily')
        tt_date = dates.get('trend_template_data')
        sqs_date = dates.get('signal_quality_scores')
        buys_date = dates.get('buy_sell_daily')

        # buy_sell_daily and signal_quality_scores are populated by the Step Functions morning
        # pipeline, which completes after the Lambda orchestrator fires at 9:30 AM ET. Halting on
        # their staleness creates a deadlock: Phase 1 blocks before Phase 5 can populate them.
        # They are logged for observability but excluded from the halt decision.
        halt_checks = {
            'SPY price data': spy_date,
            'Market health': mh_date,
            'Trend template': tt_date,
        }
        observe_checks = {
            'Signal quality scores': sqs_date,
            'Buy/sell signals': buys_date,
        }
        checks = {**halt_checks, **observe_checks}
        table_keys = {
            'SPY price data': 'price_daily',
            'Market health': 'market_health_daily',
            'Trend template': 'trend_template_data',
            'Signal quality scores': 'signal_quality_scores',
            'Buy/sell signals': 'buy_sell_daily',
        }
        stale_items = []

        # SIMPLIFIED DATA FRESHNESS LOGIC (2026-06-05 fix)
        # RULE: Data must be no older than 1 trading day. Period.
        # RATIONALE: Every run (9:30 AM, 1 PM, 3 PM, 5:30 PM) should have yesterday's EOD data.
        # If missing, trigger failsafe immediately (no grace period delays).
        # Exception: First run of system (no data ever loaded) — allow empty tables, log info only.

        from algo.algo_market_calendar import MarketCalendar

        # Get most recent trading day before today
        max_acceptable_age_days = 1
        expected_date = run_date - timedelta(days=1)
        while not MarketCalendar.is_trading_day(expected_date):
            expected_date -= timedelta(days=1)

        min_acceptable_date = expected_date  # No tolerance — must be from expected trading day

        logger.info(f"[DATA FRESHNESS] Simplified rule: data must be from {expected_date} (today is {run_date}, most recent trading day)")
        logger.info(f"[DATA FRESHNESS] Tolerance: {max_acceptable_age_days} trading day(s). Will trigger failsafe if older.")

        try:
            from algo.algo_metrics import MetricsPublisher
            _metrics = MetricsPublisher(dry_run=dry_run)
        except Exception as mp_e:
            logger.debug(f"MetricsPublisher unavailable: {mp_e}")
            _metrics = None

        # Get expected symbol count for completeness checks
        expected_symbols = 4500  # Default, will be overridden below
        try:
            with DatabaseContext('read') as _count_cur:
                _count_cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active=true")
                count_result = _count_cur.fetchone()
                if count_result:
                    expected_symbols = count_result[0]
        except Exception as e:
            logger.debug(f"Could not get active symbol count: {e}")

        for name, d in checks.items():
            is_halt_check = name in halt_checks
            if d is None:
                if is_halt_check:
                    stale_items.append(f"{name}: missing")
                else:
                    logger.warning(f"  [WARN] {name}: missing (observe-only, not blocking)")
                if _metrics:
                    _metrics.put_data_freshness(table_keys[name], 999)
            elif d is not None:
                # Calculate TRADING day age, not calendar day age
                # This correctly handles long weekends/holidays (Friday after Thanksgiving is still 1 trading day old on Monday)
                from algo.algo_market_calendar import MarketCalendar
                trading_day_age = 0
                check_date = run_date - timedelta(days=1)
                while check_date >= d and trading_day_age < 30:  # Stop at 30 to prevent infinite loops
                    if MarketCalendar.is_trading_day(check_date):
                        trading_day_age += 1
                    check_date -= timedelta(days=1)

                calendar_day_age = (run_date - d).days
                if _metrics:
                    _metrics.put_data_freshness(table_keys[name], trading_day_age)

                is_stale = d < min_acceptable_date
                if is_stale and is_halt_check:
                    stale_items.append(f"{name}: {trading_day_age}d stale ({calendar_day_age}cal, need within {expected_date} to {min_acceptable_date})")
                if verbose:
                    is_ideal = d >= expected_date
                    flag = '[OK]' if is_ideal else '[WARN]' if (not is_stale) else '[STALE]'
                    logger.info(f"  {flag} {name:25s}: latest {d} ({trading_day_age}d trading old/{calendar_day_age}d calendar, acceptable until {min_acceptable_date})")

        # ISSUE #9 FIX: Validate data COMPLETENESS (symbol coverage %) for critical tables
        # Freshness alone isn't enough — if 500/5000 symbols failed to load, data is incomplete
        completeness_warnings = []
        try:
            with DatabaseContext('read') as _comp_cur:
                _comp_cur.execute("SET statement_timeout = 10000")  # 10s for all checks

                # Check price_daily completeness
                _comp_cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date >= %s", (expected_date,))
                price_symbols = _comp_cur.fetchone()[0] if _comp_cur.fetchone() else 0
                price_coverage = (price_symbols / expected_symbols * 100) if expected_symbols > 0 else 0
                if price_coverage < 95:
                    completeness_warnings.append(
                        f"price_daily: {price_symbols}/{expected_symbols} symbols ({price_coverage:.1f}%, expected >95%)"
                    )
                    logger.warning(f"  [COMPLETENESS] {completeness_warnings[-1]}")

                # Check technical_data_daily completeness
                _comp_cur.execute("SELECT COUNT(DISTINCT symbol) FROM technical_data_daily WHERE updated_at >= %s", (expected_date,))
                tech_symbols = _comp_cur.fetchone()[0] if _comp_cur.fetchone() else 0
                tech_coverage = (tech_symbols / expected_symbols * 100) if expected_symbols > 0 else 0
                if tech_coverage < 95:
                    completeness_warnings.append(
                        f"technical_data_daily: {tech_symbols}/{expected_symbols} symbols ({tech_coverage:.1f}%, expected >95%)"
                    )
                    logger.warning(f"  [COMPLETENESS] {completeness_warnings[-1]}")

                # Check buy_sell_daily completeness
                _comp_cur.execute("SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily WHERE updated_at >= %s", (expected_date,))
                buys_symbols = _comp_cur.fetchone()[0] if _comp_cur.fetchone() else 0
                buys_coverage = (buys_symbols / expected_symbols * 100) if expected_symbols > 0 else 0
                if buys_coverage < 95:
                    completeness_warnings.append(
                        f"buy_sell_daily: {buys_symbols}/{expected_symbols} symbols ({buys_coverage:.1f}%, expected >95%)"
                    )
                    logger.warning(f"  [COMPLETENESS] {completeness_warnings[-1]}")

                if completeness_warnings:
                    logger.warning(f"[DATA COMPLETENESS] {len(completeness_warnings)} incomplete tables detected")
                    alerts.send_position_alert(
                        'DATA',
                        'DATA_COMPLETENESS_LOW',
                        f"Data completeness below threshold (expected >95%). Details: {'; '.join(completeness_warnings)}. "
                        f"Loaders may have failed partially.",
                        {'completeness_warnings': completeness_warnings, 'coverage': {
                            'price': price_coverage, 'technical': tech_coverage, 'buys': buys_coverage
                        }}
                    )
                    log_phase_result_fn(1, 'data_completeness', 'warn',
                                       f"Coverage: price={price_coverage:.0f}%, tech={tech_coverage:.0f}%, buys={buys_coverage:.0f}%")
                else:
                    log_phase_result_fn(1, 'data_completeness', 'success',
                                       f"All critical tables >95% complete: price={price_coverage:.0f}%, tech={tech_coverage:.0f}%, buys={buys_coverage:.0f}%")

        except Exception as comp_err:
            logger.debug(f"[DATA COMPLETENESS] Check failed: {comp_err} (proceeding)")

        if _metrics:
            _metrics.flush()

        if stale_items:
            logger.warning(f"[FAILSAFE] Data stale detected, will trigger loader: {stale_items}")

            # SIMPLIFIED: Check if loader is currently RUNNING. If yes, use grace period.
            # If not, trigger immediately (no time-based grace period delays).
            # This prevents waiting 2.5 hours for a loader that already finished.
            failsafe_already_triggered = False
            loader_currently_running = False

            try:
                # Quick check: is stock_prices_daily actually RUNNING in database?
                with DatabaseContext('read') as _status_cur:
                    _status_cur.execute("SET statement_timeout = 3000")  # 3s max
                    _status_cur.execute(
                        "SELECT status FROM data_loader_status WHERE table_name = 'price_daily'"
                    )
                    result = _status_cur.fetchone()
                    if result and result[0] == 'RUNNING':
                        loader_currently_running = True
                        logger.info(f"[FAILSAFE] Loader status: RUNNING in background. Using grace period, no re-trigger needed.")
                        failsafe_already_triggered = True  # Skip trigger below
            except Exception as status_err:
                logger.debug(f"[FAILSAFE] Could not check loader status: {status_err}. Will trigger fresh loader.")

            if failsafe_already_triggered and loader_currently_running:
                # Loader is actively running — let it finish
                failsafe_ok = True
                logger.info(f"[FAILSAFE] ✓ Loader actively RUNNING. Proceeding to Phase 2 with in-flight loader.")
                alerts.send_position_alert(
                    'DATA',
                    'STALE_DATA_LOADER_ACTIVE',
                    f'Stale data detected but loader is actively running. Proceeding with in-flight loader.',
                    {'stale_items': stale_items, 'loader_status': 'RUNNING'}
                )
                log_phase_result_fn(1, 'data_freshness', 'warn',
                                   f'Stale, but loader actively running: {"; ".join(stale_items)}')
            else:
                # Loader not running, or check failed. Trigger fresh loader NOW (no grace period).
                logger.warning(f"[FAILSAFE] Loader not currently running. Attempting to trigger fresh loader: {stale_items}")

                # CLUSTER HEALTH PRECHECK: Verify cluster has capacity before triggering
                try:
                    import boto3
                    ecs_client = boto3.client('ecs', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                    cluster_arn = os.getenv('ECS_CLUSTER_ARN', 'algo-cluster')

                    cluster_response = ecs_client.describe_clusters(clusters=[cluster_arn])
                    if cluster_response and cluster_response.get('clusters'):
                        cluster_info = cluster_response['clusters'][0]
                        registered_container_instances = cluster_info.get('registeredContainerInstancesCount', 0)
                        running_tasks = cluster_info.get('runningCount', 0)
                        pending_tasks = cluster_info.get('pendingCount', 0)

                        logger.info(f"[CLUSTER HEALTH] Instances: {registered_container_instances}, "
                                   f"Running: {running_tasks}, Pending: {pending_tasks}")

                        # If more than 10 tasks are pending or cluster is oversubscribed, warn
                        if pending_tasks > 10 or running_tasks > registered_container_instances * 2:
                            logger.warning(f"[CLUSTER HEALTH] High cluster load detected. "
                                         f"Pending tasks: {pending_tasks}, may experience higher provisioning latency.")
                except Exception as cluster_check_err:
                    logger.debug(f"[CLUSTER HEALTH] Could not check cluster capacity: {cluster_check_err}")

                # Check if a previous failsafe timed out (is still running after 2 hours)
                # This would indicate a hung loader, cascading failures risk
                try:
                    failsafe_status = _check_failsafe_completion(state_table, verbose=verbose, timeout_sec=7200)
                    if failsafe_status and failsafe_status.get('status') == 'timed_out':
                        logger.critical(
                            f"[FAILSAFE_TIMEOUT] Previous failsafe triggered {failsafe_status.get('age_minutes', 0):.1f}m ago but never completed. "
                            f"Data is still {oldest_stale_trading_day_age}+ trading days old with no fresh load in progress. HALTING."
                        )
                        alerts.send_position_alert(
                            'DATA',
                            'FAILSAFE_TIMEOUT',
                            f'Previous async failsafe loader timed out ({failsafe_status.get("age_minutes", 0):.0f}m ago with 2h timeout). '
                            f'Data stale for {oldest_stale_trading_day_age}+ trading days. Cannot safely retry.',
                            {'failsafe_age_minutes': failsafe_status.get('age_minutes'), 'halt': True}
                        )
                        log_phase_result_fn(1, 'data_freshness', 'halt',
                                           f'CRITICAL: Previous failsafe timeout - async loader did not complete in 2 hours')
                        return PhaseResult(1, 'data_freshness', 'halted', {}, True,
                                         f'Failsafe loader timeout — loader hung >2 hours, data stale {oldest_stale_trading_day_age}+ days')
                except Exception as timeout_check_err:
                    logger.debug(f"[FAILSAFE_TIMEOUT] Could not check failsafe timeout: {timeout_check_err}")

                # Stock prices loader takes 1-2 hours to fetch 5000+ symbols. Lambda orchestrator has
                # 10min timeout total. Instead of waiting synchronously (exceeds timeout), trigger
                # asynchronously and verify it started before proceeding.

                # SIMPLIFIED FAILSAFE: Single attempt with 90s poll timeout
                # If it fails, halt only if data is VERY stale (2+ days). Otherwise proceed with warning.
                # This prevents waiting through 3 timeout loops (30+120+180s = 330s) when failsafe is dead.
                failsafe_ok = False
                poll_timeout = 90  # Wait up to 90s for ECS task to reach RUNNING state

                try:
                    logger.info(f"[FAILSAFE] Triggering loader with {poll_timeout}s poll timeout...")
                    failsafe_ok = _trigger_loader_failsafe_with_verification('stock_prices_daily', verbose=verbose, poll_timeout_sec=poll_timeout)
                    if failsafe_ok:
                        logger.info(f"[FAILSAFE] ✓ Loader trigger confirmed. Task is running.")
                    else:
                        logger.warning(f"[FAILSAFE] ✗ Loader trigger did not confirm within {poll_timeout}s. Will check data staleness.")
                except Exception as trigger_err:
                    logger.warning(f"[FAILSAFE] Loader trigger failed: {trigger_err}")

            if not failsafe_ok:
                # Failsafe failed or timeout - loader may not have started.
                # Check how stale the data actually is. If VERY stale (2+ trading days),
                # HALT instead of proceeding with risky old data.
                oldest_stale_trading_day_age = None
                for item in stale_items:
                    # Parse "name: 5d stale (3cal, need...)" to extract TRADING day age (first number)
                    if 'd stale' in item:
                        try:
                            age_str = item.split(': ')[1].split('d stale')[0]
                            age = int(age_str)
                            if oldest_stale_trading_day_age is None or age > oldest_stale_trading_day_age:
                                oldest_stale_trading_day_age = age
                        except (IndexError, ValueError):
                            pass

                # Decision: if data is >= configured threshold and failsafe failed, HALT (Issue #1)
                # This prevents silent failures in Phase 5 when signal gate kills trades.
                # Threshold is configurable via algo_config (default 2 trading days)
                halt_threshold = 2  # Default
                try:
                    with DatabaseContext('read') as _cfg_cur:
                        _cfg_cur.execute("SELECT value FROM algo_config WHERE key = %s", ('phase1_halt_stale_days_threshold',))
                        result = _cfg_cur.fetchone()
                        if result:
                            halt_threshold = int(result[0])
                except Exception:
                    pass

                if oldest_stale_trading_day_age is not None and oldest_stale_trading_day_age >= halt_threshold:
                    logger.critical(f"[HALT] Failsafe loader trigger failed AND data is {oldest_stale_trading_day_age}+ trading days stale. Too risky to proceed.")
                    logger.critical(f"  Stale items: {stale_items}")
                    logger.critical(f"  Loader failed to start. Halting orchestrator.")

                    alerts.send_position_alert(
                        'DATA',
                        'STALE_DATA_FAILSAFE_CRITICAL',
                        f'HALT: Failsafe loader trigger failed AND data is {oldest_stale_trading_day_age}+ trading days stale. '
                        f'Cannot safely proceed with this old data. Check loader ECS logs for startup errors. '
                        f'Stale items: {"; ".join(stale_items)}',
                        {'stale_items': stale_items, 'failsafe': 'failed', 'oldest_age': oldest_stale_trading_day_age, 'halt': True}
                    )
                    log_phase_result_fn(1, 'data_freshness', 'halt',
                                       f'CRITICAL: Failsafe failed and data is {oldest_stale_trading_day_age}+ trading days stale')
                    return PhaseResult(1, 'data_freshness', 'halted', {}, True,
                                     f'Failsafe failed with {oldest_stale_trading_day_age}+ trading day stale data — too risky to trade')

                # Failsafe failed but data is recent enough (1 trading day old) - proceed with caution
                logger.warning(f"[FAILSAFE] Loader did not confirm startup within 90s. Data is {oldest_stale_trading_day_age}d trading days old (acceptable window).")
                logger.warning(f"  Stale items: {stale_items}")
                logger.warning(f"  Proceeding to Phase 2 circuit breakers for additional safety checks.")
                logger.warning(f"  Check CloudWatch logs for ECS loader startup errors.")

                alerts.send_position_alert(
                    'DATA',
                    'STALE_DATA_FAILSAFE_FAILED',
                    f'Failsafe loader trigger did not confirm startup but data is recent ({oldest_stale_trading_day_age}d trading days old). '
                    f'Proceeding with caution — circuit breakers active. '
                    f'Stale items: {"; ".join(stale_items)}. Check CloudWatch for errors.',
                    {'stale_items': stale_items, 'expected_date': str(expected_date), 'failsafe': 'failed', 'age': oldest_stale_trading_day_age}
                )
                log_phase_result_fn(1, 'data_freshness', 'warn',
                                   f'Stale, failsafe unconfirmed ({oldest_stale_trading_day_age}d trading days): {"; ".join(stale_items)}')
                # Continue to Phase 2 circuit breakers
            else:
                # Failsafe confirmed - loader started successfully and will refresh data
                logger.info("[FAILSAFE] ✓ Loader confirmed startup. Data will be refreshed in parallel.")
                alerts.send_position_alert(
                    'DATA',
                    'STALE_DATA_FAILSAFE_TRIGGERED',
                    f'Stale data detected. Failsafe loader triggered successfully. '
                    f'stock_prices_daily now running in parallel. Data will refresh within 1-2 hours.',
                    {'stale_items': stale_items, 'expected_date': str(expected_date), 'failsafe': 'started'}
                )
                log_phase_result_fn(1, 'data_freshness', 'warn',
                                   f'Stale but failsafe triggered: {"; ".join(stale_items)}')

        # Check if this is a first-run (before any loaders have populated data).
        # On first deployment: signal_quality_scores and buy_sell_daily both empty
        # Don't halt, just log and skip to Phase 2+ (which will also be conservative)
        # CRITICAL: Verify that data actually exists before returning success.
        # Previous bug: system declared success with 0 rows because timestamp was "fresh enough".
        first_run_state = False
        try:
            with DatabaseContext('read') as _check_cur:
                _check_cur.execute("SET statement_timeout = 5000")
                # Check if both signal_quality_scores and buy_sell_daily are empty
                _check_cur.execute("SELECT COUNT(*) FROM signal_quality_scores")
                sqs_count = _check_cur.fetchone()[0] if _check_cur.fetchone() else 0

                _check_cur.execute("SELECT COUNT(*) FROM buy_sell_daily")
                bsd_count = _check_cur.fetchone()[0] if _check_cur.fetchone() else 0

                # Also check critical price table
                _check_cur.execute("SELECT COUNT(*) FROM price_daily WHERE symbol='SPY'")
                price_count = _check_cur.fetchone()[0] if _check_cur.fetchone() else 0

                if sqs_count == 0 and bsd_count == 0 and price_count == 0:
                    first_run_state = True
                    logger.warning(
                        "[FIRST_RUN] System has never run EOD pipeline. "
                        "signal_quality_scores, buy_sell_daily, and price_daily are all empty. "
                        "Waiting for EOD pipeline (4:05 PM) to populate data. "
                        "Next orchestrator run (9:30 AM tomorrow) will generate signals."
                    )
                    log_phase_result_fn(1, 'data_freshness', 'info',
                                       'First run detected: waiting for EOD pipeline to populate data')
                elif price_count == 0:
                    # Price data exists as a prerequisite for everything else
                    # If it's missing entirely, system cannot function
                    logger.critical(
                        "[HALT] price_daily table has no SPY data. "
                        "Stock loader must run before any analysis is possible."
                    )
                    log_phase_result_fn(1, 'data_freshness', 'halt',
                                       'price_daily table is empty - system not initialized')
                    return PhaseResult(1, 'data_freshness', 'halted', {}, True,
                                     'price_daily table is empty — no price data available for trading')

        except Exception as e:
            logger.debug(f"Could not check first-run state: {e}")

        # Check swing_trader_scores and source data freshness — WARNING-ONLY (no halt).
        # CRITICAL FIX (Issue #1, #5): Swing scores halting was false-positive.
        # Root cause: If buy_sell_daily/technical_data_daily incomplete, swing_trader_scores will be incomplete.
        # But system halted on scores themselves, not on SOURCE DATA completeness.
        # NEW RULE: Check source data (buy_sell_daily, technical_data_daily) for freshness and coverage.
        # If sources fresh + complete, Phase 5 will work even if scores are slightly older.
        # Move scores check to warning-only for observability.

        swing_data_health = {'status': 'ok', 'warnings': []}
        min_acceptable_swing_date = expected_date  # For reference only

        try:
            with DatabaseContext('read') as _sw_cur:
                _sw_cur.execute("SET statement_timeout = 5000")

                # Check swing_trader_scores freshness and size
                _sw_cur.execute("""
                    SELECT MAX(date), COUNT(*) as row_count, COUNT(DISTINCT symbol) as symbol_count
                    FROM swing_trader_scores
                """)
                sw_row = _sw_cur.fetchone()
                sw_latest = sw_row[0] if sw_row else None
                sw_row_count = sw_row[1] if sw_row and len(sw_row) > 1 else 0
                sw_symbol_count = sw_row[2] if sw_row and len(sw_row) > 2 else 0

                # Check source data: buy_sell_daily freshness and coverage
                _sw_cur.execute("""
                    SELECT MAX(updated_at) as latest_update, COUNT(DISTINCT symbol) as symbol_count
                    FROM buy_sell_daily
                """)
                bsd_row = _sw_cur.fetchone()
                bsd_latest = bsd_row[0] if bsd_row else None
                bsd_symbol_count = bsd_row[1] if bsd_row and len(bsd_row) > 1 else 0

                # Check technical_data_daily freshness
                _sw_cur.execute("""
                    SELECT MAX(updated_at) as latest_update, COUNT(DISTINCT symbol) as symbol_count
                    FROM technical_data_daily
                """)
                tech_row = _sw_cur.fetchone()
                tech_latest = tech_row[0] if tech_row else None
                tech_symbol_count = tech_row[1] if tech_row and len(tech_row) > 1 else 0

                # Get expected symbol count from stock_symbols table
                _sw_cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active=true")
                expected_symbol_count = _sw_cur.fetchone()[0] if _sw_cur.fetchone() else 4500

                # Thresholds for completeness (configurable)
                min_coverage_pct_warn = 0.90  # Warn if <90% coverage
                min_coverage_pct_error = 0.75  # Alert error if <75%

                # Check buy_sell_daily completeness
                bsd_coverage = (bsd_symbol_count / expected_symbol_count * 100) if expected_symbol_count > 0 else 0
                if bsd_coverage < min_coverage_pct_error:
                    swing_data_health['warnings'].append(
                        f"buy_sell_daily coverage LOW: {bsd_symbol_count}/{expected_symbol_count} symbols ({bsd_coverage:.1f}%). "
                        f"Phase 5 will have reduced trading opportunity."
                    )
                elif bsd_coverage < min_coverage_pct_warn:
                    swing_data_health['warnings'].append(
                        f"buy_sell_daily coverage suboptimal: {bsd_symbol_count}/{expected_symbol_count} symbols ({bsd_coverage:.1f}%)"
                    )

                # Check technical_data_daily completeness
                tech_coverage = (tech_symbol_count / expected_symbol_count * 100) if expected_symbol_count > 0 else 0
                if tech_coverage < min_coverage_pct_error:
                    swing_data_health['warnings'].append(
                        f"technical_data_daily coverage LOW: {tech_symbol_count}/{expected_symbol_count} symbols ({tech_coverage:.1f}%). "
                        f"Check if technical_data_daily loader completed successfully."
                    )
                elif tech_coverage < min_coverage_pct_warn:
                    swing_data_health['warnings'].append(
                        f"technical_data_daily coverage suboptimal: {tech_symbol_count}/{expected_symbol_count} symbols ({tech_coverage:.1f}%)"
                    )

                # Log swing scores status (observation only, no halt)
                if sw_latest is None or sw_row_count == 0:
                    if first_run_state:
                        logger.info("[SWING SCORES] Empty (first run): waiting for EOD pipeline")
                    else:
                        logger.warning(
                            f"[SWING SCORES] Empty or stale ({sw_row_count} rows). "
                            f"This is expected during first-run or if EOD pipeline failed. "
                            f"Phase 5 will execute with limited scoring capability."
                        )
                        swing_data_health['warnings'].append(
                            f"swing_trader_scores empty/stale: {sw_row_count} rows, {sw_symbol_count} symbols"
                        )
                else:
                    sw_coverage = (sw_symbol_count / expected_symbol_count * 100) if expected_symbol_count > 0 else 0
                    logger.info(
                        f"  [SWING SCORES] {sw_symbol_count}/{expected_symbol_count} symbols ({sw_coverage:.1f}%), "
                        f"latest={sw_latest}"
                    )

                # Log source data health
                if bsd_latest or tech_latest:
                    logger.info(
                        f"  [SOURCE DATA] buy_sell_daily={bsd_symbol_count}/{expected_symbol_count} ({bsd_coverage:.1f}%), "
                        f"technical={tech_symbol_count}/{expected_symbol_count} ({tech_coverage:.1f}%)"
                    )

                if swing_data_health['warnings']:
                    logger.warning(f"[DATA HEALTH] Warnings: {'; '.join(swing_data_health['warnings'])}")
                    alerts.send_position_alert(
                        'DATA',
                        'SWING_DATA_INCOMPLETE',
                        f"Swing/source data completeness below optimal. Details: {'; '.join(swing_data_health['warnings'])}. "
                        f"Phase 5 will execute but with reduced trading opportunity.",
                        {'coverage_warnings': swing_data_health['warnings']}
                    )
                    log_phase_result_fn(1, 'swing_trader_scores', 'warn',
                                       f"Source data completeness: {bsd_coverage:.0f}% buy_sell, {tech_coverage:.0f}% technical")
                else:
                    log_phase_result_fn(1, 'swing_trader_scores', 'success',
                                       f"Swing/source data: {sw_symbol_count}/{expected_symbol_count} symbols, "
                                       f"buy_sell={bsd_coverage:.0f}%, technical={tech_coverage:.0f}%")

        except Exception as _sw_err:
            logger.warning(f"[SWING SCORES] Could not check freshness: {_sw_err} (proceeding with caution)")
            log_phase_result_fn(1, 'swing_trader_scores', 'warn',
                               f'Freshness check failed: {_sw_err}')

        # ISSUE #10 FIX: Add sector_ranking health check (missing from verification)
        # Sector_ranking is used by Phase 3 (position monitor) and Phase 5 (position limits).
        # If stale, position tracking and sector limits may be incorrect.
        try:
            with DatabaseContext('read') as _sector_cur:
                _sector_cur.execute("SET statement_timeout = 5000")
                _sector_cur.execute("SELECT MAX(updated_at), COUNT(*) FROM sector_ranking")
                sector_row = _sector_cur.fetchone()
                sector_latest = sector_row[0] if sector_row else None
                sector_count = sector_row[1] if sector_row and len(sector_row) > 1 else 0

                if sector_latest is None or sector_count == 0:
                    logger.warning(
                        "[SECTOR_RANKING] Empty or missing. "
                        "Phase 3/5 will not enforce sector position limits. Check morning-prep-pipeline."
                    )
                    alerts.send_position_alert(
                        'DATA',
                        'SECTOR_RANKING_MISSING',
                        f'sector_ranking is empty ({sector_count} rows). Phase 3/5 position limits may not work. '
                        f'Check morning-prep-pipeline logs.',
                        {'sector_count': sector_count}
                    )
                    log_phase_result_fn(1, 'sector_ranking', 'warn', 'sector_ranking missing')
                elif sector_latest < expected_date:
                    logger.warning(
                        f"[SECTOR_RANKING] Stale (latest={sector_latest}, expected {expected_date}). "
                        f"Phase 3/5 position limits use outdated sector assignments."
                    )
                    log_phase_result_fn(1, 'sector_ranking', 'warn', f'sector_ranking stale: {sector_latest}')
                else:
                    logger.info(f"  [OK] sector_ranking: {sector_count} rows, latest {sector_latest}")
                    log_phase_result_fn(1, 'sector_ranking', 'success', f'sector_ranking fresh: {sector_count} rows')
        except Exception as sector_err:
            logger.debug(f"[SECTOR_RANKING] Check failed: {sector_err} (proceeding)")

        # MORNING PREP VISIBILITY: Check if morning pipeline (3:30 AM) actually ran today
        # If it's 9:30 AM+ and buy_sell_daily/signal_quality_scores haven't been updated since yesterday,
        # morning prep failed silently and we should halt or alert.
        try:
            now_et = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-5)))
            is_9am_or_later = now_et.hour >= 9

            if is_9am_or_later:
                # At 9:30 AM or later, check if morning pipeline ran (should have updated signals)
                morning_pipeline_cutoff = run_date.replace(hour=3, minute=30, second=0, microsecond=0)
                with DatabaseContext('read') as _morning_cur:
                    _morning_cur.execute("SET statement_timeout = 5000")

                    # Check if buy_sell_daily was updated since 3:30 AM this morning
                    _morning_cur.execute("""
                        SELECT MAX(updated_at) FROM buy_sell_daily
                        WHERE updated_at >= %s
                    """, (morning_pipeline_cutoff,))
                    buys_updated = _morning_cur.fetchone()[0]

                    if not buys_updated:
                        logger.warning(f"[MORNING PREP] buy_sell_daily was NOT updated since 3:30 AM (morning prep may have failed)")
                        logger.warning(f"  Check Step Functions: algo-morning-prep-pipeline or scheduled EventBridge trigger")
                        alerts.send_position_alert(
                            'PIPELINE',
                            'MORNING_PREP_POTENTIAL_FAILURE',
                            f'buy_sell_daily has not been refreshed since 3:30 AM. Morning prep pipeline may have failed. '
                            f'Check Step Functions logs.',
                            {'last_update': str(buys_updated), 'cutoff': str(morning_pipeline_cutoff)}
                        )
                    else:
                        logger.info(f"[MORNING PREP] ✓ buy_sell_daily updated at {buys_updated} (morning prep completed)")
        except Exception as morning_check_err:
            logger.debug(f"[MORNING PREP] Could not check morning pipeline status: {morning_check_err}")

        # Read cached data patrol results only — do NOT run a new patrol in-line.
        # The in-line patrol (via ThreadPoolExecutor) always times out after 45s, but
        # the background thread CONTINUES running after future.cancel() (Python threads
        # can't be force-killed). That background patrol opens 30+ DB connections with
        # slow MAX(date) queries, saturating the t4g.micro and causing "Connection refused"
        # for all subsequent DB operations in Phase 1 and beyond.
        # Solution: patrol runs as a pre-scheduled job; orchestrator only reads results.
        log_phase_result_fn(1, 'data_patrol', 'success', 'Using cached patrol results')

        with DatabaseContext('read') as _patrol_cur:
            patrol_ok = _check_data_patrol(_patrol_cur, run_date, verbose, log_phase_result_fn)

        if not patrol_ok:
            return PhaseResult(1, 'data_patrol', 'halted', {}, True, 'Data patrol check failed')

        # DATA COMPLETENESS CHECK: Verify critical tables have adequate symbol coverage
        # If a loader runs but completes only 90% of symbols, freshness check passes but we're
        # trading on incomplete data. This check catches that: verify price_daily, technical_data_daily,
        # and buy_sell_daily cover at least 75% of expected universe (3750/5000 symbols).
        completeness_ok = True
        try:
            with DatabaseContext('read') as _completeness_cur:
                _completeness_cur.execute("SET statement_timeout = 10000")

                # Get reference universe size (active S&P 500 + large-cap ETFs, ~5000 symbols)
                _completeness_cur.execute("""
                    SELECT COUNT(DISTINCT symbol) FROM price_daily
                    WHERE date = (SELECT MAX(date) FROM price_daily)
                """)
                price_coverage = _completeness_cur.fetchone()[0] or 0

                _completeness_cur.execute("""
                    SELECT COUNT(DISTINCT symbol) FROM technical_data_daily
                    WHERE date = (SELECT MAX(date) FROM technical_data_daily)
                """)
                technical_coverage = _completeness_cur.fetchone()[0] or 0

                _completeness_cur.execute("""
                    SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily
                    WHERE date = (SELECT MAX(date) FROM buy_sell_daily)
                """)
                buysell_coverage = _completeness_cur.fetchone()[0] or 0

                # Expected universe: assume 5000 active symbols (S&P 500 + large ETFs)
                # Min acceptable: configurable via algo_config (default 75% = 3750 symbols)
                min_coverage_pct = 75
                try:
                    with DatabaseContext('read') as _cfg_cur:
                        _cfg_cur.execute("SELECT value FROM algo_config WHERE key = %s", ('phase1_coverage_min_pct',))
                        result = _cfg_cur.fetchone()
                        if result:
                            min_coverage_pct = int(result[0])
                except Exception:
                    pass

                min_coverage = int(5000 * min_coverage_pct / 100)
                coverage_check_failed = False

                if price_coverage < min_coverage:
                    price_pct = 100 * price_coverage / 5000
                    logger.error(f"[COMPLETENESS] price_daily coverage too low: {price_coverage}/5000 symbols ({price_pct:.1f}%, need {min_coverage_pct}%)")
                    completeness_ok = False
                    coverage_check_failed = True
                else:
                    price_pct = 100 * price_coverage / 5000
                    logger.info(f"[COMPLETENESS] price_daily: {price_coverage}/5000 symbols ({price_pct:.1f}%) ✓")

                if technical_coverage < min_coverage:
                    tech_pct = 100 * technical_coverage / 5000
                    logger.error(f"[COMPLETENESS] technical_data_daily coverage too low: {technical_coverage}/5000 symbols ({tech_pct:.1f}%, need {min_coverage_pct}%)")
                    completeness_ok = False
                    coverage_check_failed = True
                else:
                    tech_pct = 100 * technical_coverage / 5000
                    logger.info(f"[COMPLETENESS] technical_data_daily: {technical_coverage}/5000 symbols ({tech_pct:.1f}%) ✓")

                if buysell_coverage < min_coverage:
                    bs_pct = 100 * buysell_coverage / 5000
                    logger.error(f"[COMPLETENESS] buy_sell_daily coverage too low: {buysell_coverage}/5000 symbols ({bs_pct:.1f}%, need {min_coverage_pct}%)")
                    completeness_ok = False
                    coverage_check_failed = True
                else:
                    bs_pct = 100 * buysell_coverage / 5000
                    logger.info(f"[COMPLETENESS] buy_sell_daily: {buysell_coverage}/5000 symbols ({bs_pct:.1f}%) ✓")

                # Also warn if coverage is degrading but above threshold (early warning)
                warn_threshold = int(5000 * (min_coverage_pct + 10) / 100)  # Warn at +10% above min (e.g., 85% if min=75%)
                coverage_warnings = []
                if price_coverage < warn_threshold:
                    coverage_warnings.append(f'price_daily: {price_coverage}/5000 ({100*price_coverage/5000:.1f}%)')
                if technical_coverage < warn_threshold:
                    coverage_warnings.append(f'technical_data_daily: {technical_coverage}/5000 ({100*technical_coverage/5000:.1f}%)')
                if buysell_coverage < warn_threshold:
                    coverage_warnings.append(f'buy_sell_daily: {buysell_coverage}/5000 ({100*buysell_coverage/5000:.1f}%)')

                if coverage_warnings and not first_run_state:
                    logger.warning(f"[COMPLETENESS] Coverage approaching threshold ({warn_threshold}/5000, {min_coverage_pct+10}%): {'; '.join(coverage_warnings)}")
                    alerts.send_position_alert(
                        'DATA', 'COVERAGE_DEGRADING',
                        f'Data coverage approaching {min_coverage_pct}% threshold. Early warning: {"; ".join(coverage_warnings)}',
                        {'tables': coverage_warnings, 'threshold': min_coverage_pct}
                    )

                if coverage_check_failed and not first_run_state:
                    logger.critical(f"[HALT] Critical loader coverage below {min_coverage_pct}%. This indicates a loader failure mid-execution.")
                    logger.critical(f"  price_daily: {price_coverage}/5000, technical_data_daily: {technical_coverage}/5000, buy_sell_daily: {buysell_coverage}/5000")
                    logger.critical("  Incomplete data will cause Phase 5 to generate incomplete signal set.")
                    logger.critical("  Check loader logs for partial failures.")
                    alerts.send_position_alert(
                        'DATA', 'INCOMPLETE_COVERAGE',
                        f'HALT: Data coverage below {min_coverage_pct}%. Loaders completed partially. '
                        f'price_daily: {price_coverage}/5000, technical_data_daily: {technical_coverage}/5000, buy_sell_daily: {buysell_coverage}/5000. '
                        f'Check loader logs for errors.',
                        {'price': price_coverage, 'technical': technical_coverage, 'buysell': buysell_coverage, 'min': min_coverage, 'threshold_pct': min_coverage_pct}
                    )
                    log_phase_result_fn(1, 'data_completeness', 'halt',
                                       f'Incomplete coverage: price={price_coverage}/{min_coverage}, technical={technical_coverage}/{min_coverage}, buysell={buysell_coverage}/{min_coverage}')
        except Exception as completeness_err:
            logger.warning(f"[COMPLETENESS] Could not check data coverage: {completeness_err}")

        if not completeness_ok and not first_run_state:
            return PhaseResult(1, 'data_completeness', 'halted', {}, True,
                             'Data coverage below acceptable threshold — loader may have failed partially')

        # BUY_SELL_DAILY DEPENDENCY VALIDATION: Verify source data completeness
        # buy_sell_daily depends on technical_data_daily. If technical data failed for 500+ symbols,
        # buy_sell_daily will be incomplete (only 4500/5000 signals). Phase 5 will see "fresh" signals
        # but generate an incomplete trade set. Check that technical_data_daily has adequate coverage.
        if not first_run_state:
            try:
                with DatabaseContext('read') as _dep_cur:
                    _dep_cur.execute("SET statement_timeout = 5000")

                    # Get most recent date for technical_data_daily
                    _dep_cur.execute("SELECT MAX(date) FROM technical_data_daily")
                    tech_date = _dep_cur.fetchone()[0] if _dep_cur.fetchone() else None

                    # Also verify buy_sell_daily's source (should match or be newer than tech_data)
                    _dep_cur.execute("SELECT MAX(date) FROM buy_sell_daily")
                    buysell_date = _dep_cur.fetchone()[0] if _dep_cur.fetchone() else None

                    if tech_date and buysell_date and buysell_date > tech_date:
                        logger.warning(f"[DEPENDENCY] buy_sell_daily ({buysell_date}) is newer than technical_data_daily ({tech_date})")
                        logger.warning(f"  This is expected if technical data updates slower than buy_sell.")
                    elif tech_date and buysell_date and buysell_date < tech_date:
                        # This is a problem: buy_sell is older than its source data
                        logger.error(f"[DEPENDENCY] buy_sell_daily ({buysell_date}) is OLDER than technical_data_daily ({tech_date})")
                        logger.error(f"  Gap: {(tech_date - buysell_date).days} days. Signals may be based on stale technical data.")
                        alerts.send_position_alert(
                            'DATA', 'DEPENDENCY_AGE_MISMATCH',
                            f'buy_sell_daily ({buysell_date}) is older than technical_data_daily ({tech_date}). '
                            f'Signals may be based on stale technical indicators.',
                            {'buysell_date': str(buysell_date), 'tech_date': str(tech_date), 'gap_days': (tech_date - buysell_date).days}
                        )
            except Exception as dep_err:
                logger.debug(f"[DEPENDENCY] Could not validate buy_sell/technical relationship: {dep_err}")

        # SWING TRADER SCORES SOURCE DATA VALIDATION: Verify that swing_trader_scores depends on fresh source data
        # swing_trader_scores requires: buy_sell_daily (fresh), technical_data_daily (fresh), trend_template_data (fresh)
        # If any source is stale, swing_trader_scores will be based on stale/incomplete data.
        # Note: We already checked swing_trader_scores freshness above; this validates its dependencies.
        if swing_scores_ok and not first_run_state:
            try:
                with DatabaseContext('read') as _sources_cur:
                    _sources_cur.execute("SET statement_timeout = 5000")

                    # Swing trader scores should not be older than 2 hours from expected_date
                    # (it depends on buy_sell_daily + technical_data which are typically from expected_date)
                    _sources_cur.execute("SELECT MAX(date) FROM buy_sell_daily")
                    buysell_date = _sources_cur.fetchone()[0] if _sources_cur.fetchone() else None

                    _sources_cur.execute("SELECT MAX(date) FROM technical_data_daily")
                    tech_date = _sources_cur.fetchone()[0] if _sources_cur.fetchone() else None

                    _sources_cur.execute("SELECT MAX(date) FROM trend_template_data")
                    trend_date = _sources_cur.fetchone()[0] if _sources_cur.fetchone() else None

                    # All three should be from expected_date (yesterday, most recent trading day)
                    sources_ok = True
                    for source_name, source_date in [('buy_sell_daily', buysell_date), ('technical_data_daily', tech_date), ('trend_template_data', trend_date)]:
                        if source_date and source_date < expected_date:
                            gap = (expected_date - source_date).days
                            logger.warning(f"[SWING_SOURCES] {source_name} is {gap}d behind expected_date ({expected_date})")
                            sources_ok = False
                        elif source_date:
                            logger.info(f"[SWING_SOURCES] {source_name}: {source_date} ✓")

                    if not sources_ok:
                        logger.warning(f"[SWING_SOURCES] swing_trader_scores may be based on stale source data. "
                                      f"buy_sell={buysell_date}, technical={tech_date}, trend={trend_date}. "
                                      f"Expected all from {expected_date}.")
                        alerts.send_position_alert(
                            'DATA', 'SWING_SOURCES_STALE',
                            f'swing_trader_scores sources may be stale: buy_sell={buysell_date}, technical={tech_date}, trend={trend_date}. '
                            f'Expected all from {expected_date}.',
                            {'buysell': str(buysell_date), 'technical': str(tech_date), 'trend': str(trend_date), 'expected': str(expected_date)}
                        )
            except Exception as sources_err:
                logger.debug(f"[SWING_SOURCES] Could not validate swing_trader_scores sources: {sources_err}")

        # SECTOR RANKING HEALTH CHECK: Verify that sector_ranking is fresh and populated
        # sector_ranking is used by Phase 3 (position monitor) to track sector exposure and limits.
        # If sector_ranking fails silently during morning prep, Phase 3 uses stale sector assignments
        # and Phase 5 may violate position limits (e.g., 8 positions per sector) unknowingly.
        try:
            with DatabaseContext('read') as _sector_cur:
                _sector_cur.execute("SET statement_timeout = 5000")

                _sector_cur.execute("""
                    SELECT MAX(updated_at), COUNT(*) as row_count FROM sector_ranking
                    WHERE updated_at >= %s
                """, (expected_date,))
                sector_row = _sector_cur.fetchone()
                sector_updated = sector_row[0] if sector_row else None
                sector_count = sector_row[1] if sector_row and len(sector_row) > 1 else 0

                if sector_count == 0 or sector_updated is None:
                    if not first_run_state:
                        logger.warning(f"[SECTOR] sector_ranking not updated since {expected_date}. Using possibly stale sector assignments.")
                        logger.warning(f"  Current row count: {sector_count}. Check morning-prep-pipeline logs if this is unexpected.")
                        alerts.send_position_alert(
                            'DATA', 'SECTOR_RANKING_STALE',
                            f'sector_ranking not updated since {expected_date}. Phase 3/5 may use stale sector data. Row count: {sector_count}. '
                            f'Check morning-prep-pipeline logs.',
                            {'updated': str(sector_updated), 'row_count': sector_count, 'expected_date': str(expected_date)}
                        )
                else:
                    logger.info(f"[SECTOR] sector_ranking: {sector_count} rows, updated {sector_updated} ✓")
        except Exception as sector_err:
            logger.debug(f"[SECTOR] Could not check sector_ranking health: {sector_err}")

        # Quick secondary checks (fast index scans, not full table scans).
        # Full COUNT(*) on large tables takes 1-3 minutes under load — expensive in Lambda.
        # Instead, use fast queries: SELECT ... LIMIT 1 (milliseconds), sample recent data.
        # These are observability-only, not halt conditions (swing_trader_scores is already halt).
        try:
            with DatabaseContext('read') as _sqs_cur:
                _sqs_cur.execute("SET statement_timeout = 5000")  # 5s max for observability query
                # Fast check: does table have ANY data? (index scan, not count)
                _sqs_cur.execute("SELECT 1 FROM signal_quality_scores LIMIT 1")
                has_data = _sqs_cur.fetchone() is not None

                if not has_data:
                    logger.warning("  [WARN] signal_quality_scores table is empty (observe-only, not blocking)")
                    logger.warning("         Phase 5 will use trend-score fallback ranking")
                    log_phase_result_fn(1, 'signal_quality_scores', 'warn', 'Table empty')
                elif verbose:
                    # Get latest date (fast index scan)
                    _sqs_cur.execute("SELECT MAX(date) FROM signal_quality_scores")
                    latest = _sqs_cur.fetchone()[0] if _sqs_cur.fetchone() else None
                    logger.info(f"  [OK] signal_quality_scores: has data, latest {latest}")
        except Exception as e:
            logger.warning(f"  [WARN] signal_quality_scores check failed: {e} (observe-only)")

        # Secondary health checks: lightweight observability-only checks (non-blocking)
        in_lambda = bool(os.getenv('AWS_LAMBDA_FUNCTION_NAME'))

        # Margin check via CloudWatch metrics (fast, non-blocking)
        # Query Alpaca API balance only if metrics unavailable
        try:
            from algo.algo_alerts import AlertManager
            margin_ok = True  # Assume OK unless we have evidence otherwise

            # Try to get balance from Alpaca API (lightweight, single call)
            try:
                import alpaca_trade_api as tradeapi
                api = tradeapi.REST()
                account = api.get_account()

                if hasattr(account, 'cash') and hasattr(account, 'portfolio_value'):
                    margin_usage_pct = max(0, (float(account.portfolio_value) - float(account.cash)) / float(account.portfolio_value) * 100) if account.portfolio_value else 0

                    if margin_usage_pct > 70:
                        alerts.send_position_alert(
                            'ACCOUNT', 'MARGIN_ALERT',
                            f'Margin usage {margin_usage_pct:.1f}% (threshold: 70%)',
                            {'margin_usage_pct': margin_usage_pct}
                        )
                        margin_ok = False
                        if verbose:
                            logger.warning(f"  [MARGIN] Usage {margin_usage_pct:.1f}% - approaching limit")
                    elif verbose:
                        logger.info(f"  [OK] Margin: {margin_usage_pct:.1f}% usage")
            except Exception as api_err:
                logger.debug(f"  [MARGIN] Alpaca API check unavailable: {api_err}")

            # Fast table presence check (LIMIT 1, not COUNT)
            try:
                with DatabaseContext('read') as _chk_cur:
                    _chk_cur.execute("SET statement_timeout = 3000")  # 3s max
                    # Check critical tables have any recent data (fast index scan)
                    critical_tables = ['buy_sell_daily', 'signal_quality_scores', 'swing_trader_scores']
                    for table in critical_tables:
                        try:
                            _chk_cur.execute(f"SELECT 1 FROM {table} WHERE date >= %s LIMIT 1", (run_date - timedelta(days=5),))
                            has_data = _chk_cur.fetchone() is not None
                            if not has_data:
                                logger.warning(f"  [WARN] {table}: no recent data (observe-only)")
                            elif verbose:
                                logger.info(f"  [OK] {table}: has recent data")
                        except Exception as t_err:
                            logger.debug(f"  [WARN] {table} check failed: {t_err}")
            except Exception as health_err:
                logger.debug(f"  [HEALTH] Secondary checks unavailable: {health_err}")

        except Exception as e:
            logger.warning(f'Secondary health checks failed: {e}')

        if verbose and in_lambda:
            logger.info("  [LAMBDA] Secondary checks completed (lightweight observability only)")

        log_phase_result_fn(1, 'data_freshness', 'success', 'All data fresh within window')
        return PhaseResult(1, 'data_freshness', 'ok', {}, False, None)

    except Exception as e:
        log_phase_result_fn(1, 'data_freshness', 'error', str(e))
        return PhaseResult(1, 'data_freshness', 'halted', {}, True, str(e))
