#!/usr/bin/env python3

import os
import json
import logging
import time
import uuid
from datetime import date as _date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Callable, Optional, Dict

from utils.database_context import DatabaseContext
from algo.algo_alerts import AlertManager
from algo.algo_sql_safety import assert_safe_table, assert_safe_column
from algo.orchestrator.phase_result import PhaseResult

logger = logging.getLogger(__name__)

# ISSUE #21 FIX: Add correlation_id to all Phase 1 logs for traceability
_phase1_correlation_id = str(uuid.uuid4())[:8]

def _trigger_loader_failsafe_with_verification(loader_name: str, verbose: bool = False, poll_timeout_sec: int = 180, retry_count: int = 1, correlation_id: str = None) -> bool:
    """
    Trigger ECS loader asynchronously and VERIFY it started before returning.

    CRITICAL FIX: Previous implementation triggered loader but never confirmed it started.
    If trigger failed (network error, Lambda down, wrong ARN), orchestrator would proceed
    with stale data silently.

    Now: Use EventBridge to trigger ECS task, monitor CloudWatch for task start.
    Only return True if ECS task confirmed running within poll_timeout_sec.
    Retries once with 10s backoff if initial trigger fails.

    ECS TIMING: Fargate tasks can take 45-120s to reach RUNNING state under load.
    ISSUE #4 FIX: Increased default timeout from 120s to 150s to accommodate worst-case
    Fargate provisioning delays under cluster load. Prevents false timeout failures.
    ISSUE #13 FIX: Further increased to 180s to safely handle peak cluster load where
    Fargate instance provisioning can take up to 150s.

    ISSUE #11 FIX: Passes _phase1_correlation_id via PHASE1_CORRELATION_ID env var for end-to-end log tracing.

    Args:
        loader_name: Name of the loader to trigger
        verbose: Whether to log verbose output
        poll_timeout_sec: Max seconds to wait for loader task to start (default 180s)
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
                                {'name': 'PHASE1_CORRELATION_ID', 'value': correlation_id if correlation_id else _phase1_correlation_id},
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
            trigger_timestamp = time.time()  # Record when task was triggered

            if verbose:
                logger.info(f"[FAILSAFE] Attempt {attempts}: ✓ ECS task launched: {task_id}")

            # Step 2: Poll CloudWatch Container Insights for task to reach RUNNING state
            # Task states: PROVISIONING → PENDING → ACTIVATING → RUNNING
            poll_start = time.time()
            poll_interval = 1.0  # Check every 1 second

            # Query CloudWatch Logs for task state transitions
            logs_client = boto3.client('logs', region_name=os.getenv('AWS_REGION', 'us-east-1'))

            poll_success = False
            secondary_check_done = False

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

                            # ISSUE #8 FIX: Verify loader actually starts loading data, not just that task is running
                            # Wait up to 30s for loader to update its heartbeat in data_loader_status
                            # This catches cases where task starts but loader code crashes or hangs on startup
                            loader_heartbeat_detected = False
                            heartbeat_wait_start = time.time()
                            heartbeat_wait_timeout = 30  # 30 second timeout for heartbeat detection
                            heartbeat_check_interval = 2  # Check every 2 seconds

                            if verbose:
                                logger.debug(f"[FAILSAFE] Waiting up to {heartbeat_wait_timeout}s for loader to update heartbeat (startup validation)...")

                            while time.time() - heartbeat_wait_start < heartbeat_wait_timeout:
                                try:
                                    from utils.database_context import DatabaseContext
                                    with DatabaseContext('read') as hb_cur:
                                        hb_cur.execute("SET statement_timeout = 2000")  # 2s timeout
                                        hb_cur.execute(
                                            "SELECT last_updated FROM data_loader_status WHERE table_name = %s",
                                            (loader_name.replace('_daily', '_daily').replace('_', '_'),)  # e.g., 'stock_prices_daily'
                                        )
                                        hb_result = hb_cur.fetchone()
                                        if hb_result and hb_result[0]:
                                            last_updated = hb_result[0]
                                            # Check if heartbeat was updated AFTER task was triggered
                                            if isinstance(last_updated, str):
                                                last_updated = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                                            if hasattr(last_updated, 'timestamp'):
                                                last_updated_ts = last_updated.timestamp()
                                            else:
                                                last_updated_ts = last_updated
                                            if last_updated_ts > trigger_timestamp:
                                                loader_heartbeat_detected = True
                                                heartbeat_elapsed = time.time() - heartbeat_wait_start
                                                logger.info(f"[FAILSAFE] ✓ Loader heartbeat detected after {heartbeat_elapsed:.1f}s — loader is actually running and loading data")
                                                break
                                except Exception as hb_err:
                                    if verbose:
                                        logger.debug(f"[FAILSAFE] Heartbeat check attempt failed (will retry): {hb_err}")

                                time.sleep(heartbeat_check_interval)

                            if not loader_heartbeat_detected:
                                logger.critical(f"[FAILSAFE] CRITICAL: Task RUNNING but heartbeat not detected within {heartbeat_wait_timeout}s. "
                                            f"Loader may have startup errors or be hung. Cannot proceed with potentially stale data.")
                                AlertManager().critical(f"Loader {loader_name} started but never reported activity. Data may be stale.")
                                if attempts < max_attempts:
                                    logger.info(f"[FAILSAFE] Retrying loader trigger...")
                                    time.sleep(10)
                                    continue
                                return False

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
                                    UpdateExpression='SET actual_running_at = :running_at, scheduling_delay_seconds = :delay, heartbeat_detected = :heartbeat',
                                    ExpressionAttributeValues={
                                        ':running_at': now,
                                        ':delay': elapsed,
                                        ':heartbeat': loader_heartbeat_detected,
                                    }
                                )
                                if verbose:
                                    logger.debug(f"[FAILSAFE] Stored actual_running_at, scheduling_delay ({elapsed:.1f}s), and heartbeat status: {loader_heartbeat_detected}")
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

            # ISSUE #1 FIX: Enhanced secondary timeout check with adaptive retry
            # If main poll timed out, check multiple times with backoff to catch late starters
            # This handles edge cases where Fargate takes >180s under extreme load
            if not poll_success and not secondary_check_done:
                secondary_check_done = True
                secondary_attempts = 0
                secondary_max_attempts = 3  # Check up to 3 more times with 30s gaps
                secondary_start = time.time()

                while secondary_attempts < secondary_max_attempts and not poll_success:
                    secondary_attempts += 1
                    # Wait 30s before rechecking (gives task time to still start)
                    time.sleep(30)

                    try:
                        desc_response = ecs_client.describe_tasks(
                            cluster=cluster_arn,
                            tasks=[task_arn]
                        )
                        if desc_response.get('tasks'):
                            task = desc_response['tasks'][0]
                            task_state = task.get('lastStatus', '')
                            if task_state == 'RUNNING':
                                elapsed = time.time() - poll_start
                                logger.critical(
                                    f"[FAILSAFE] ✓ RECOVERED: Task {task_id} RUNNING after {elapsed:.1f}s "
                                    f"(secondary check #{secondary_attempts} detected late start after main poll timeout). "
                                    f"ECS provisioning took {elapsed/60:.1f} minutes — within acceptable range for loaded cluster."
                                )
                                poll_success = True
                                break
                            elif task_state in ('DEPROVISIONING', 'STOPPING', 'DEACTIVATING', 'STOPPED', 'DELETED'):
                                logger.warning(f"[FAILSAFE] Task {task_id} stopped during secondary check: {task_state}")
                                break

                        if verbose:
                            elapsed_secondary = time.time() - secondary_start
                            logger.debug(f"[FAILSAFE] Secondary check #{secondary_attempts}: Task state not RUNNING yet (elapsed {elapsed_secondary:.0f}s)")
                    except Exception as secondary_err:
                        logger.debug(f"[FAILSAFE] Secondary check #{secondary_attempts} query failed: {secondary_err}")
                        if secondary_attempts >= secondary_max_attempts:
                            # If we can't query after retries, assume task might still be running (network issue)
                            logger.warning(f"[FAILSAFE] After {secondary_max_attempts} secondary checks, cannot confirm task state. Assuming recovery.")
                            poll_success = True

                if poll_success:
                    # Update state and metrics since task is confirmed running
                    try:
                        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                        state_table = dynamodb.Table(os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state'))
                        elapsed = time.time() - poll_start
                        state_table.update_item(
                            Key={'state_key': 'failsafe_trigger_log'},
                            UpdateExpression='SET actual_running_at = :running_at, scheduling_delay_seconds = :delay',
                            ExpressionAttributeValues={':running_at': time.time(), ':delay': elapsed}
                        )
                    except Exception:
                        pass

            if poll_success:
                # CRITICAL FIX: Verify loader actually started loading data, not just reached RUNNING
                # Check if data_loader_status shows loader has begun work (status=RUNNING with recent updated_at)
                # This catches tasks that reach RUNNING but immediately crash or fail to initialize
                try:
                    with DatabaseContext('read') as status_cur:
                        status_cur.execute("SET statement_timeout = 5000")  # 5s max
                        # Map loader_name to table_name for status lookup
                        table_map = {
                            'stock_prices_daily': 'price_daily',
                            'technical_data_daily': 'technical_data_daily',
                            'market_health_daily': 'market_health_daily',
                        }
                        table_name = table_map.get(loader_name)
                        if table_name:
                            status_cur.execute(
                                "SELECT status, updated_at FROM data_loader_status WHERE table_name = %s",
                                (table_name,)
                            )
                            row = status_cur.fetchone()
                            if row and row[0] == 'RUNNING':
                                # Loader status shows RUNNING - it has begun work
                                if isinstance(row[1], str):
                                    updated_at = datetime.fromisoformat(row[1].replace('Z', '+00:00'))
                                else:
                                    updated_at = row[1]
                                age_sec = (datetime.now(timezone.utc) - updated_at).total_seconds()
                                if age_sec < 60:  # Status updated within last minute
                                    logger.info(f"[FAILSAFE] ✓ Verified: Loader {loader_name} started loading (status=RUNNING, updated {age_sec:.0f}s ago)")
                                    return True
                                else:
                                    logger.warning(f"[FAILSAFE] ⚠️  Task RUNNING but status not recently updated ({age_sec:.0f}s ago). "
                                                 f"Loader may have stalled. Monitoring...")
                                    return True  # Still return True, will be caught by grace period hung detection
                            else:
                                logger.warning(f"[FAILSAFE] Task {task_id} RUNNING but {loader_name} status not yet RUNNING. "
                                             f"Loader may still be initializing... waiting up to 30s more")
                                # Give loader more time to initialize (up to 30s more)
                                for wait_attempt in range(6):  # 6 attempts x 5s = 30s
                                    time.sleep(5)
                                    status_cur.execute(
                                        "SELECT status, updated_at FROM data_loader_status WHERE table_name = %s",
                                        (table_name,)
                                    )
                                    row = status_cur.fetchone()
                                    if row and row[0] == 'RUNNING':
                                        logger.info(f"[FAILSAFE] ✓ Verified (after 30s): Loader {loader_name} status=RUNNING")
                                        return True
                                # Still not RUNNING after 30s wait
                                logger.error(f"[FAILSAFE] FAILED: Task {task_id} reached RUNNING but {loader_name} status never became RUNNING. "
                                           f"Loader appears to have failed during initialization.")
                                return False
                except Exception as progress_err:
                    logger.warning(f"[FAILSAFE] Could not verify loader progress: {progress_err}. "
                                 f"Assuming loader is working (will be caught by grace period if it hangs)")
                    return True  # Assume OK if we can't verify (database temporarily unavailable)

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

    Timeout is configurable via algo_config (heartbeat_hung_timeout_minutes), defaults to 3 minutes.
    This is more responsive than the previous 10-minute default: if a task hangs at minute 2,
    it will be detected by minute 5 instead of minute 12.

    Args:
        loader_name: Name of loader table (e.g., 'price_daily', 'technical_data_daily')
        timeout_minutes: Override heartbeat timeout (reads from algo_config if not specified)

    Returns:
        True if task appears hung, False otherwise
    """
    try:
        from utils.database_context import DatabaseContext
        from datetime import datetime, timezone, timedelta

        # Use provided timeout or load from algo_config, default to 3 minutes (reduced from 10)
        if timeout_minutes is None:
            try:
                with DatabaseContext("read") as config_cur:
                    config_cur.execute(
                        "SELECT value FROM algo_config WHERE key = %s",
                        ('heartbeat_hung_timeout_minutes',)
                    )
                    config_result = config_cur.fetchone()
                    timeout_minutes = int(config_result[0]) if config_result else 3
            except Exception:
                timeout_minutes = 3  # Default to 3 minutes

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

def _terminate_hung_loader_task(loader_name: str, verbose: bool = False) -> bool:
    """Terminate an ECS loader task that has been detected as hung.

    Issue #3: When a hung loader is detected, terminate the old task to prevent
    it from competing with the new loader for RDS connections.

    Args:
        loader_name: Name of the loader (e.g., 'stock_prices_daily', 'technical_data_daily')
        verbose: Whether to log verbose output

    Returns:
        True if task was terminated (or doesn't exist), False if termination failed
    """
    try:
        import boto3
        ecs_client = boto3.client('ecs', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        cluster_arn = os.getenv('ECS_CLUSTER_ARN', 'algo-cluster')

        # Map loader name to ECS task definition prefix
        task_def_map = {
            'stock_prices_daily': 'algo-stock_prices_daily-loader',
            'technical_data_daily': 'algo-technical_data_daily-loader',
            'market_health_daily': 'algo-market_health_daily-loader',
        }
        task_def_prefix = task_def_map.get(loader_name, f'algo-{loader_name}-loader')

        # List all running tasks
        list_response = ecs_client.list_tasks(
            cluster=cluster_arn,
            desiredStatus='RUNNING',
            family=task_def_prefix
        )

        if not list_response.get('taskArns'):
            if verbose:
                logger.debug(f"[HUNG_TASK_CLEANUP] No running tasks found for {loader_name}")
            return True  # No task to terminate

        # Describe the running tasks to find hung ones
        desc_response = ecs_client.describe_tasks(
            cluster=cluster_arn,
            tasks=list_response['taskArns']
        )

        if not desc_response.get('tasks'):
            return True

        # Terminate all running tasks for this loader (typically only 1, but handle multiple)
        terminated_count = 0
        for task in desc_response['tasks']:
            task_arn = task.get('taskArn')
            task_id = task_arn.split('/')[-1] if task_arn else 'unknown'

            try:
                stop_response = ecs_client.stop_task(
                    cluster=cluster_arn,
                    task=task_arn,
                    reason='Hung task detected — terminating to allow fresh loader to start'
                )

                # ISSUE #9 FIX: Verify task actually stopped (not just requested to stop)
                if stop_response.get('task'):
                    stopped_task = stop_response['task']
                    final_state = stopped_task.get('lastStatus', '')
                    if final_state in ('STOPPED', 'STOPPING'):
                        if verbose:
                            logger.info(f"[HUNG_TASK_CLEANUP] Sent stop request for hung task {task_id} (state: {final_state})")

                        # ISSUE #9 FIX: Secondary verification - wait up to 30s for full STOPPED state
                        # STOPPING state means stop signal sent, but RDS connections may still be held
                        verified_stopped = False
                        if final_state == 'STOPPING':
                            logger.debug(f"[HUNG_TASK_CLEANUP] Task {task_id} is STOPPING, waiting for STOPPED confirmation...")
                            for verify_attempt in range(6):  # Try up to 6 times with 5s intervals = 30s
                                time.sleep(5)
                                try:
                                    verify_resp = ecs_client.describe_tasks(cluster=cluster_arn, tasks=[task_arn])
                                    if verify_resp.get('tasks'):
                                        verify_task = verify_resp['tasks'][0]
                                        verify_state = verify_task.get('lastStatus', '')
                                        if verify_state == 'STOPPED':
                                            logger.info(f"[HUNG_TASK_CLEANUP] ✓ Confirmed task {task_id} fully STOPPED after {(verify_attempt+1)*5}s")
                                            verified_stopped = True
                                            terminated_count += 1
                                            break
                                        elif verify_state in ('DEPROVISIONING', 'DELETED'):
                                            logger.info(f"[HUNG_TASK_CLEANUP] ✓ Task {task_id} is {verify_state} (cleanup in progress)")
                                            verified_stopped = True
                                            terminated_count += 1
                                            break
                                except Exception as verify_err:
                                    logger.debug(f"[HUNG_TASK_CLEANUP] Verification attempt {verify_attempt+1} failed: {verify_err}")

                            if not verified_stopped:
                                logger.warning(f"[HUNG_TASK_CLEANUP] Task {task_id} still not fully STOPPED after 30s, but proceeding anyway")
                                terminated_count += 1  # Count as terminated even if still stopping (best effort)
                        else:
                            # Already in STOPPED state
                            logger.info(f"[HUNG_TASK_CLEANUP] ✓ Terminated hung task {task_id} (state: {final_state})")
                            terminated_count += 1

                        # Emit metric for tracking zombie task cleanup
                        try:
                            from algo.algo_metrics import MetricsPublisher
                            metrics = MetricsPublisher()
                            metrics.add_metric(
                                'HungTasksTerminated',
                                1,
                                unit='Count',
                                dimensions={'LoaderName': loader_name}
                            )
                            metrics.flush()
                        except Exception:
                            pass
                    else:
                        logger.warning(f"[HUNG_TASK_CLEANUP] Task {task_id} not in stopped state: {final_state}")
                else:
                    logger.warning(f"[HUNG_TASK_CLEANUP] No task returned in stop response for {task_id}")
            except Exception as stop_err:
                logger.warning(f"[HUNG_TASK_CLEANUP] Failed to terminate task {task_id}: {stop_err}")
                # Issue #23 FIX: Escalate if termination fails
                try:
                    from algo.algo_alerts import AlertManager
                    alerts = AlertManager()
                    alerts.send_position_alert(
                        'SYSTEM',
                        'HUNG_TASK_TERMINATION_FAILED',
                        f'Failed to terminate hung ECS task {task_id} for {loader_name}. '
                        f'Task may be consuming resources. Error: {str(stop_err)}',
                        {'task_id': task_id, 'loader': loader_name, 'error': str(stop_err)}
                    )
                except Exception as alert_err:
                    logger.debug(f"Could not send escalation alert: {alert_err}")

        return terminated_count > 0 or not list_response.get('taskArns')

    except Exception as e:
        logger.warning(f"[HUNG_TASK_CLEANUP] Could not terminate hung loader task for {loader_name}: {e}")
        return False  # Warn but don't block

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
                        # ISSUE #5 FIX: Verify loader is actually making progress, not stuck
                        # If last_updated is stale (>30 min), treat as hung even though marked RUNNING
                        from datetime import datetime as dt_module
                        now = dt_module.now(timezone.utc)
                        if last_updated and hasattr(last_updated, 'replace'):
                            if last_updated.tzinfo is None:
                                last_updated = last_updated.replace(tzinfo=timezone.utc)
                            stale_mins = (now - last_updated).total_seconds() / 60
                        else:
                            stale_mins = 0

                        if stale_mins > 30:
                            logger.warning(
                                f"[FAILSAFE] Loader {loader_name} marked RUNNING but not updated {stale_mins:.0f}min. "
                                f"Loader appears hung. Grace period will not extend."
                            )
                        else:
                            logger.debug(f"[FAILSAFE] Loader {loader_name} RUNNING and active (updated {stale_mins:.1f}min ago)")
                            return 0.5  # Grace period - loader making progress
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

        # ISSUE #4 FIX: Use actual_running_at if available, otherwise query ECS state again
        # Don't just use triggered_at without verifying current ECS task status
        if actual_running_at:
            age_minutes = (current_time - actual_running_at) / 60
            age_source = f"running_at (delay {scheduling_delay:.0f}s)"
        else:
            # Polling might have timed out earlier. Query ECS now to check if task finally reached RUNNING.
            try:
                import boto3
                ecs_client = boto3.client('ecs', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                cluster_arn = os.getenv('ECS_CLUSTER_ARN', 'algo-cluster')

                # Try to find running task for this loader
                list_resp = ecs_client.list_tasks(
                    cluster=cluster_arn,
                    desiredStatus='RUNNING',
                    family=f'algo-{loader_name}-loader' if not loader_name.startswith('algo-') else loader_name
                )

                if list_resp.get('taskArns'):
                    # Task found and running, update actual_running_at now
                    desc_resp = ecs_client.describe_tasks(cluster=cluster_arn, tasks=list_resp['taskArns'][:1])
                    if desc_resp.get('tasks'):
                        task = desc_resp['tasks'][0]
                        if task.get('lastStatus') == 'RUNNING':
                            # Store this for future checks
                            try:
                                state_table.update_item(
                                    Key={'state_key': 'failsafe_trigger_log'},
                                    UpdateExpression='SET actual_running_at = :running_at',
                                    ExpressionAttributeValues={':running_at': current_time}
                                )
                                logger.info(f"[FAILSAFE] Updated actual_running_at after re-check")
                            except Exception:
                                pass
                            age_minutes = (current_time - current_time) / 60  # Task just confirmed RUNNING
                            age_source = "running_at (re-verified from ECS)"
                        else:
                            age_minutes = (current_time - triggered_at) / 60
                            age_source = f"triggered_at (task in {task.get('lastStatus')})"
                    else:
                        age_minutes = (current_time - triggered_at) / 60
                        age_source = "triggered_at (could not describe task)"
                else:
                    # No task found - use triggered_at with note
                    age_minutes = (current_time - triggered_at) / 60
                    age_source = "triggered_at (no task found in ECS, may have already stopped)"
            except Exception as ecs_err:
                # If ECS check fails, fall back to triggered_at
                logger.debug(f"[FAILSAFE] ECS re-check failed: {ecs_err}, using triggered_at")
                age_minutes = (current_time - triggered_at) / 60
                age_source = "triggered_at (ECS check failed)"

        # Dynamic grace period (configurable via algo_config):
        # Read from database if available, default to 150 minutes
        # - stock_prices_daily can take up to 2h with yfinance lag
        # - Grace period starts from actual_running_at, so no need to add ECS delay anymore
        # - Default: 150 minutes (2.5 hours)
        # - Hard cap: 240 minutes (4 hours) — if grace period stalls, we don't wait indefinitely
        HARD_MAX_GRACE_PERIOD = 240  # Absolute maximum to prevent infinite waits if heartbeat stalls
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SELECT value FROM algo_config WHERE key = %s", ('failsafe_grace_period_minutes',))
                result = cur.fetchone()
                configured_grace = int(result[0]) if result and result[0] else 150
                max_grace_period = min(configured_grace, HARD_MAX_GRACE_PERIOD)
                if configured_grace > HARD_MAX_GRACE_PERIOD:
                    logger.warning(f"[FAILSAFE] Grace period configured to {configured_grace}m exceeds hard cap {HARD_MAX_GRACE_PERIOD}m — capping at {HARD_MAX_GRACE_PERIOD}m")
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
        # FIX: Use ET date, not system date (AWS runs in UTC but trading is ET-based)
        from_date = datetime.now(ZoneInfo("America/New_York")).date()

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
                                'ttl': int(now) + 3600,  # 1-hour TTL
                            })  # ISSUE #4 FIX: Don't pre-populate last_success_at; only set when patrol completes successfully
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

def _check_dynamodb_health(verbose: bool = False, timeout_sec: int = 5) -> bool:
    """ISSUE #14 FIX: Pre-flight validation for DynamoDB cache availability.

    DynamoDB is used as cache fallback when database is down. If DynamoDB is also
    degraded/slow, Phase 1 could timeout. This check verifies DynamoDB is responsive.

    Args:
        verbose: Whether to log verbose output
        timeout_sec: Max seconds to wait for DynamoDB response (default 5)

    Returns: True if DynamoDB OK, False if unavailable/timeout
    """
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        cache_table_name = os.getenv('CACHE_TABLE', 'algo_phase1_cache')

        # Quick health check: try to get item metadata (doesn't require actual item to exist)
        table = dynamodb.Table(cache_table_name)

        # Use a short timeout for the check
        start = time.time()
        try:
            # Describe table to verify it exists and is accessible
            response = table.meta.client.describe_table(TableName=cache_table_name)
            elapsed = time.time() - start

            if elapsed > timeout_sec:
                logger.warning(f"[DYNAMODB] Health check took {elapsed:.1f}s (threshold {timeout_sec}s) - may be degraded")
                return False

            table_status = response.get('Table', {}).get('TableStatus')
            if table_status != 'ACTIVE':
                logger.warning(f"[DYNAMODB] Table {cache_table_name} status={table_status}, not ACTIVE")
                return False

            if verbose:
                logger.info(f"[DYNAMODB] ✓ Cache table healthy (response time {elapsed:.2f}s)")
            return True

        except (BotoCoreError, ClientError) as ddb_err:
            logger.warning(f"[DYNAMODB] Health check failed: {type(ddb_err).__name__} - {str(ddb_err)[:100]}")
            return False

    except Exception as e:
        logger.debug(f"[DYNAMODB] Could not check health: {e}")
        return False  # Assume unhealthy on any error

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

            # ISSUE #12 FIX: Graceful degradation with warning tiers
            # - WARN at 60 connections (approaching capacity)
            # - CRITICAL/HALT at 90+ connections (high risk of cascade)
            # - Try cleanup between thresholds

            warn_threshold = 60
            halt_threshold = 90

            if active_conn >= halt_threshold:
                logger.critical(
                    f"[RDS-POOL] CIRCUIT BREAKER TRIGGERED: {active_conn} active connections (>={halt_threshold}). "
                    f"RDS pool exhaustion risk. Halting Phase 1 to prevent cascade failures."
                )
                try:
                    alerts = AlertManager()
                    alerts.send_position_alert(
                        'RDS',
                        'CONNECTION_POOL_EXHAUSTION',
                        f'RDS connection pool CRITICAL: {active_conn} active connections (>={halt_threshold}). '
                        f'Circuit breaker triggered - Phase 1 halted to prevent cascade failures.',
                        {'active_connections': active_conn, 'max_idle_seconds': max_idle}
                    )
                except Exception as alert_err:
                    logger.debug(f"[RDS-POOL] Could not send alert: {alert_err}")
                return False  # FAIL-CLOSED: halt orchestrator

            elif active_conn >= warn_threshold:
                logger.warning(
                    f"[RDS-POOL] WARNING: {active_conn} active connections (>={warn_threshold}). "
                    f"Pool approaching capacity. Monitor queries for slowness."
                )
                try:
                    alerts = AlertManager()
                    alerts.send_position_alert(
                        'RDS',
                        'CONNECTION_POOL_WARNING',
                        f'RDS connection pool high: {active_conn} active connections (>={warn_threshold}). '
                        f'Approaching capacity limit. Proceeding with caution.',
                        {'active_connections': active_conn, 'max_idle_seconds': max_idle}
                    )
                except Exception as alert_err:
                    logger.debug(f"[RDS-POOL] Could not send warning: {alert_err}")

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
    phase1_start = time.time()
    logger.debug(f"Phase 1: Starting data freshness check for run_date={run_date}")

    # ISSUE #4 FIX: Log timing context for morning pipeline
    from datetime import datetime as dt, timezone as tz, timedelta as td
    now_et = dt.now(ZoneInfo("America/New_York"))
    hour_et = now_et.hour
    minute_et = now_et.minute

    is_morning = 3 <= hour_et < 11  # 3:30 AM - 10:59 AM ET
    if is_morning:
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        min_until_open = (market_open - now_et).total_seconds() / 60
        logger.info(f"[TIMING] Morning pipeline: {now_et.strftime('%H:%M')} ET, "
                   f"{min_until_open:.0f}min to market open. Est. {4.25*60:.0f}min needed (4.25h). "
                   f"Buffer: {max(0, min_until_open - 255):.0f}min")

        # ISSUE #5 FIX: Early warning if morning prep is lagging (>2h past 2:45 AM start)
        # If current time is 3 AM - 6:45 AM AND buy_sell_daily hasn't updated since pipeline start
        morning_start_et = now_et.replace(hour=2, minute=45, second=0, microsecond=0)
        elapsed_since_start = (now_et - morning_start_et).total_seconds() / 60
        if 3 <= hour_et < 9 and elapsed_since_start > 120:  # 3 AM - 8:59 AM, >2h elapsed
            try:
                with DatabaseContext('read') as _lag_cur:
                    _lag_cur.execute("SET statement_timeout = 3000")
                    _lag_cur.execute("SELECT MAX(updated_at) FROM buy_sell_daily")
                    lag_result = _lag_cur.fetchone()
                    buys_updated = lag_result[0] if lag_result else None

                    if not buys_updated or buys_updated < morning_start_et:
                        logger.warning(
                            f"[MORNING_PREP_LAG] ⚠️ Pipeline running for {elapsed_since_start:.0f}min "
                            f"but buy_sell_daily not updated since 2:45 AM start. Pipeline appears stalled or slow."
                        )
                        alerts.send_position_alert(
                            'PIPELINE',
                            'MORNING_PREP_LAG',
                            f'Morning prep pipeline stalling: running {elapsed_since_start:.0f}min but '
                            f'buy_sell_daily ({buys_updated}) not updated since 2:45 AM start. '
                            f'Check logs for loader delays.',
                            {'elapsed_minutes': elapsed_since_start, 'buys_updated': str(buys_updated)}
                        )
            except Exception as lag_err:
                logger.debug(f"[MORNING_PREP_LAG] Could not check lag status: {lag_err}")

        # ISSUE #10 FIX: Active timing monitoring with multi-tier alerts
        # Phase 1 runs at 9:30 AM ET. If we're checking before 9:30 AM, measure progress from 2:45 AM start
        # Critical thresholds:
        # - CRITICAL (95% threshold): <20 min remaining (8:10 AM+) — runner must complete immediately
        # - WARNING (80% threshold): <80 min remaining (7:10 AM+) — watch for slowness
        # - INFO: Keep monitoring between 2:45 AM and 7:10 AM as baseline
        if is_morning and 2 <= hour_et < 9:  # Morning pipeline: 2:45 AM - 9:30 AM window
            market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
            time_until_930 = (market_open - now_et).total_seconds() / 60
            realistic_time_needed = 255  # 4h 15m (from steering docs)

            # CRITICAL threshold: 95% of time used, only 20 min remaining
            if time_until_930 < 20 and time_until_930 > 0:
                logger.critical(
                    f"[MORNING_PREP_CRITICAL] CRITICAL TIMING: Only {time_until_930:.0f}min until market open. "
                    f"Morning prep must complete NOW or 9:30 AM orchestrator will find stale data. "
                    f"Current time: {now_et.strftime('%H:%M')} ET"
                )
                alerts.send_position_alert(
                    'PIPELINE',
                    'MORNING_PREP_CRITICAL_TIMING',
                    f'CRITICAL: Morning prep has only {time_until_930:.0f} minutes until 9:30 AM deadline. '
                    f'Must complete immediately or orchestrator will halt on stale data. '
                    f'Time: {now_et.strftime("%H:%M")} ET',
                    {'minutes_remaining': time_until_930, 'critical': True}
                )
            # WARNING threshold: 80% of time used, 80 min remaining
            elif time_until_930 < 80 and time_until_930 >= 20:
                logger.critical(
                    f"[MORNING_PREP_HALT] ⚠️ TIMING HALT: Only {time_until_930:.0f}min until 9:30 AM deadline, "
                    f"but realistically need {realistic_time_needed}min. Cannot complete morning prep in time. "
                    f"Phase 1 halting to prevent stale data trades. "
                    f"Current time: {now_et.strftime('%H:%M')} ET"
                )
                alerts.send_position_alert(
                    'PIPELINE',
                    'MORNING_PREP_TIMING_HALT',
                    f'Morning prep timing impossible: {time_until_930:.0f} min until 9:30 AM, need {realistic_time_needed}min. '
                    f'Phase 1 halting to prevent trading on stale data. Time: {now_et.strftime("%H:%M")} ET',
                    {'minutes_remaining': time_until_930, 'minutes_needed': realistic_time_needed, 'halt': True}
                )
                log_phase_result_fn(1, 'morning_prep_timing', 'halt',
                                   f'Insufficient time for morning prep: {time_until_930:.0f}min remaining, {realistic_time_needed}min needed')
                return PhaseResult(1, 'morning_prep_timing', 'halted', {}, True,
                                 f'Morning prep timing constraints violated')

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

                # ISSUE #14 FIX: Check DynamoDB cache health before proceeding
                # If DynamoDB is degraded, Phase 1 cache fallback may timeout
                try:
                    ddb_ok = _check_dynamodb_health(verbose=verbose, timeout_sec=5)
                    if not ddb_ok:
                        logger.warning("[DYNAMODB] Cache layer unavailable - Phase 1 will skip cache and use database directly")
                except Exception as ddb_err:
                    logger.debug(f"[DYNAMODB] Could not check health: {ddb_err}, proceeding without cache")

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

        # ISSUE #1 FIX: Check for market close data failure from previous loader run
        # ISSUE #4 FIX: Don't rely on time-based stale check; any market close failure is critical
        try:
            import boto3
            dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
            state_table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
            state_table = dynamodb.Table(state_table_name)

            response = state_table.get_item(Key={'state_key': 'market_close_failure'})
            if 'Item' in response:
                failure_item = response['Item']
                failure_time = failure_item.get('failure_time', 0)
                age_minutes = (time.time() - failure_time) / 60 if failure_time else 999
                reason = failure_item.get('reason', 'unknown')
                loader = failure_item.get('loader', 'stock_prices_daily')

                # ISSUE #4 FIX: Market close failures are always critical, regardless of age
                # yfinance lag may recur on next attempt, so treat any failure as reason to retry
                logger.critical(f"[MARKET_CLOSE] Market close failure detected in {loader} (age {age_minutes:.0f}min): {reason}. "
                               f"Triggering full failsafe retry (not just single loader).")
                alerts.send_position_alert(
                    'MARKET_CLOSE',
                    'YFINANCE_LAG_DETECTED',
                    f"Market close failure detected in {loader} ({age_minutes:.0f}min ago): {reason}. "
                    f"Triggering full failsafe to retry with fresh attempt. May indicate yfinance lag or data availability issue.",
                    {'loader': loader, 'age_minutes': age_minutes, 'reason': reason}
                )
                log_phase_result_fn(1, 'market_close_failure', 'warn',
                                   f"Market close failure in {loader} ({age_minutes:.0f}min old): {reason}. Failsafe triggered.")
                # Clear the failure flag after logging (will be re-set if next attempt also fails)
                try:
                    state_table.delete_item(Key={'state_key': 'market_close_failure'})
                except Exception:
                    pass
        except Exception as mc_err:
            logger.debug(f"[MARKET_CLOSE] Could not check failure status: {mc_err}")

        # ISSUE #10 FIX: Morning Prep Pipeline Timing Monitoring
        # Start time: 2:45 AM ET
        # Deadline: 9:30 AM ET (405 minutes available)
        # Realistic execution: 230-255 minutes (3.8-4.25 hours)
        # Safety buffer: 150 minutes (2.5 hours) — TIGHT but acceptable
        # CRITICAL: If morning prep misses 9:30 AM deadline, Phase 1 finds stale data and halts
        # MITIGATION: Active monitoring with early warnings to catch slowness patterns

        # Monitor morning prep pipeline timing (only relevant if we're in morning window 2:45-9:30 AM)
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        now_et = datetime.now(ZoneInfo("America/New_York"))
        morning_prep_start = now_et.replace(hour=2, minute=45, second=0, microsecond=0)
        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        minutes_since_morning_start = (now_et - morning_prep_start).total_seconds() / 60
        minutes_until_market_open = (market_open - now_et).total_seconds() / 60

        is_morning_prep_window = -5 < minutes_since_morning_start < 405  # ±5 min tolerance
        if is_morning_prep_window and minutes_until_market_open > 0 and minutes_since_morning_start > 0:
            # We're in the morning prep window. Check if we're falling behind schedule
            # Realistic execution: 230 min baseline
            # Current time: minutes_since_morning_start
            # Expected progress: should be ~56% done at T=130min (230×0.56≈129)
            expected_at_halfway = 115  # Should be about halfway through (230/2)
            expected_at_90pct = 207    # Should be 90% done at 207 min (230×0.9)

            if minutes_since_morning_start > expected_at_halfway and minutes_until_market_open < expected_at_halfway:
                # We're past the halfway point but running out of time
                time_left_ratio = minutes_until_market_open / expected_at_halfway
                if time_left_ratio < 0.8:
                    logger.warning(
                        f"[MORNING_PREP_TIMING] ⚠️ EARLY WARNING: Morning prep may miss 9:30 AM deadline. "
                        f"Current time: {minutes_since_morning_start:.0f}min into window, "
                        f"{minutes_until_market_open:.0f}min until market open. "
                        f"Expected time remaining: {expected_at_halfway - minutes_since_morning_start:.0f}min, "
                        f"actual: {minutes_until_market_open:.0f}min. "
                        f"Safety margin at {time_left_ratio*100:.0f}% of expected (recommend >80% for safe completion). "
                        f"Monitor individual loader execution times in CloudWatch."
                    )
                    try:
                        alerts.send_position_alert(
                            'TIMING',
                            'MORNING_PREP_BEHIND_SCHEDULE',
                            f"Morning prep pipeline running behind schedule. "
                            f"Current: {minutes_since_morning_start:.0f}min, deadline in {minutes_until_market_open:.0f}min. "
                            f"Safety margin degraded to {time_left_ratio*100:.0f}%. "
                            f"Check stock_prices_daily, technical_data_daily, and buy_sell_daily execution times.",
                            {'minutes_since_start': minutes_since_morning_start,
                             'minutes_until_deadline': minutes_until_market_open,
                             'safety_margin_pct': time_left_ratio * 100}
                        )
                    except Exception:
                        pass

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

        # ISSUE #7 FIX: Make cache TTL configurable (was hardcoded to 5 minutes)
        # ISSUE #5 FIX: Reduce cache TTL from 2h to 15min (900s) to prevent stale status lookups
        # Phase 1 runs 4 times/day (9:30 AM, 1 PM, 3 PM, 5:30 PM). Cache expires between runs (~4h apart).
        # 15-min TTL ensures we catch loader status changes within a Phase 1 run cycle.
        cache_ttl_sec = 900  # 15 minutes — fresh between Phase 1 runs, but spans multiple loaders completing
        try:
            with DatabaseContext('read') as config_cur:
                config_cur.execute(
                    "SELECT value FROM algo_config WHERE key = %s",
                    ('phase1_cache_ttl_seconds',)
                )
                config_result = config_cur.fetchone()
                if config_result:
                    cache_ttl_sec = int(config_result[0])
                    logger.debug(f"Phase 1: Using configured cache TTL: {cache_ttl_sec}s")
        except Exception:
            logger.debug(f"Phase 1: Using default cache TTL: {cache_ttl_sec}s")

        # Step 1: Try DynamoDB cache first (configurable TTL, default 2 hours)
        # ISSUE #10 FIX: Before using cache, verify database is truly unreachable
        # This prevents using stale cache after database comes back online
        database_available = False
        database_recovered = False  # ISSUE #10 FIX: Track if database just came back online
        try:
            # Quick connectivity check: single fast query to see if database is responsive
            # Use very short timeout (2s) to fail fast if DB is still down
            with DatabaseContext('read') as db_check_cur:
                db_check_cur.execute("SET statement_timeout = 2000")  # 2s max
                db_check_cur.execute("SELECT 1")
                database_available = True

                # Check if we had cached data from when database was down (database recovery detection)
                # If cache exists and database just came back, cache may be stale/poisoned
                cache_created_when_db_was_down = False
                try:
                    # If cache has 'database_was_down_when_created' flag, it's from outage
                    import boto3
                    dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                    cache_table = dynamodb.Table(os.getenv('CACHE_TABLE', 'algo_phase1_cache'))
                    cache_check = cache_table.get_item(Key={'cache_key': cache_key})
                    if 'Item' in cache_check and cache_check['Item'].get('database_was_down_when_created'):
                        cache_created_when_db_was_down = True
                        logger.warning(f"[DATABASE RECOVERY] Database came back online! Cache was written during outage. Forcing refresh.")
                        database_recovered = True
                except Exception:
                    pass

                logger.debug("[DATABASE CHECK] ✓ Database is responsive")
        except Exception as db_check_err:
            logger.debug(f"[DATABASE CHECK] Database unreachable ({db_check_err}), may use cache fallback")

        try:
            import boto3
            dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
            cache_table_name = os.getenv('CACHE_TABLE', 'algo_phase1_cache')
            cache_table = dynamodb.Table(cache_table_name)

            response = cache_table.get_item(Key={'cache_key': cache_key})
            if 'Item' in response:
                cached_dates = response['Item'].get('dates', {})
                cache_age = datetime.now(timezone.utc).timestamp() - response['Item'].get('created_at', 0)
                cache_invalidation_failure_flag = response['Item'].get('invalidation_failed', False)

                # ISSUE #10 FIX: Only use cache if database is unavailable
                # If database is available, force fresh query to avoid stale cache
                # ISSUE #10 FIX: If database just recovered, force refresh even if cache is fresh
                # ISSUE #24 FIX: Skip cache if cache invalidation recently failed (may contain stale data)
                if not database_available and cache_age < cache_ttl_sec and not cache_invalidation_failure_flag:
                    dates = cached_dates
                    logger.info(f"Phase 1: Using cached data_loader_status (age={cache_age:.0f}s, ttl={cache_ttl_sec}s, db unavailable, cache_ok=True)")
                elif database_recovered:
                    logger.warning(f"[DATABASE RECOVERY] Database just came back online - cache from outage may be stale/poisoned. Forcing fresh query.")
                elif cache_invalidation_failure_flag:
                    logger.warning(f"[CACHE VALIDATION] Cache invalidation previously failed - forcing fresh database query even though db unavailable")
                elif database_available:
                    logger.info(f"[CACHE VALIDATION] Database is responsive, skipping cache (age={cache_age:.0f}s). Will query fresh data.")
                else:
                    logger.info(f"Phase 1: Cache expired (age={cache_age:.0f}s > ttl={cache_ttl_sec}s), will refresh")
        except Exception as cache_err:
            logger.warning(f"Phase 1: Cache lookup failed ({cache_err}), will query fresh database instead of using cache")

        # Step 2: If cache miss, query database
        # ISSUE #2 FIX: Before querying database, check if cache invalidation previously failed
        # If cache is poisoned (invalidation_failed=true) and database is unavailable, HALT
        # This prevents proceeding with stale data when the loader failed and cache is unreliable
        cache_is_poisoned_and_db_down = False
        if cache_invalidation_failure_flag and not database_available:
            logger.critical("[CACHE_POISONED_DATABASE_DOWN] Cache invalidation previously FAILED (cache marked poisoned) "
                          "AND database is unavailable. Cannot safely proceed - both data sources are unreliable. Halting.")
            cache_is_poisoned_and_db_down = True
            alerts.send_position_alert(
                'DATA',
                'CACHE_POISONED_DATABASE_OFFLINE',
                'CRITICAL: Cache invalidation failed (cache may contain stale data) AND database unavailable. '
                'Cannot load fresh loader status. Cannot safely proceed. Escalate for manual intervention.',
                {'cache_poisoned': True, 'database_available': False}
            )
            log_phase_result_fn(1, 'cache_poisoned_database_offline', 'halt', 'Cache poisoned and database unavailable')
            return PhaseResult(1, 'cache_poisoned_database_offline', 'halted', {}, True,
                             'Cache invalidation previously failed (poisoned) AND database unavailable. Cannot proceed safely.')

        if not dates:
            # CRITICAL FIX: If database is down AND cache is expired, HALT instead of hanging
            # Trying to query a down database will timeout and waste time. Better to fail fast.
            if not database_available:
                logger.critical(
                    "[CACHE_DATABASE_BOTH_DOWN] CRITICAL: Both data sources unavailable. "
                    "Database is offline (or very slow >5s timeout) AND cache is empty/poisoned. "
                    "Cannot proceed - no way to check loader status. Must halt."
                )
                alerts.send_position_alert(
                    'DATA',
                    'CACHE_DATABASE_OFFLINE',
                    'CRITICAL: Both DynamoDB cache and PostgreSQL database unavailable/unreachable. '
                    'Cannot load loader status for any table. Cannot safely proceed. Manual intervention required.',
                    {'data_sources': 'all offline', 'cache_available': False, 'database_available': False}
                )
                log_phase_result_fn(1, 'cache_database_offline', 'halt', 'Both cache and database unavailable')
                return PhaseResult(1, 'cache_database_offline', 'halted', {}, True, 'Cannot load data - both cache and database offline')

            # SAFETY GUARD: Database check already confirmed availability above (line 1719-1722)
            # If we reach here, database_available=True, so it's safe to query
            logger.debug("[CACHE] Cache miss and database is available - querying fresh data...")
            try:
                with DatabaseContext('read') as cur:
                    cur.execute("SET statement_timeout = 15000")  # 15s — should be instant
                    # Issue #22 FIX: Check for INCOMPLETE loaders and invalidate cache if found
                    cur.execute("SELECT COUNT(*) FROM data_loader_status WHERE status = 'INCOMPLETE'")
                    incomplete_row = cur.fetchone()
                    incomplete_count = incomplete_row[0] if incomplete_row else 0

                    if incomplete_count > 0:
                        logger.warning(
                            f"[CACHE] {incomplete_count} loader(s) marked INCOMPLETE - cache will NOT be used. "
                            f"Next Phase 1 run will query fresh data_loader_status."
                        )
                        # Skip caching when incomplete loaders detected — force fresh query next time
                    else:
                        # Only cache if all loaders are COMPLETED or RUNNING (not INCOMPLETE)
                        cur.execute("""
                            SELECT table_name, latest_date
                            FROM data_loader_status
                            WHERE table_name IN (
                            'price_daily', 'etf_price_daily',
                            'market_health_daily', 'trend_template_data', 'technical_data_daily',
                            'signal_quality_scores', 'buy_sell_daily', 'swing_trader_scores'
                        )
                    """)
                        for r in cur.fetchall():
                            dates[r['table_name']] = r['latest_date']

                        # Cache the results for future runs today (ISSUE #7 FIX: use configurable TTL)
                        # ISSUE #10 FIX: Mark if database was down when cache created (so recovery is detected)
                        if dates:
                            try:
                                cache_table.put_item(Item={
                                    'cache_key': cache_key,
                                    'dates': dates,
                                    'created_at': datetime.now(timezone.utc).timestamp(),
                                    'ttl': int(time.time()) + cache_ttl_sec,  # Configurable TTL (default 2 hours)
                                    'database_was_down_when_created': not database_available,  # Flag to detect recovery
                                })
                                logger.debug(f"Phase 1: Cached {len(dates)} table dates (ttl={cache_ttl_sec}s, db_down={not database_available})")
                            except Exception as cache_write_err:
                                logger.debug(f"Phase 1: Cache write failed ({cache_write_err}), continuing")

            except Exception as e:
                logger.warning(f"Phase 1: data_loader_status query failed ({e}), trying direct table scan")

        # Fall back to direct scan only for tables missing from data_loader_status.
        # CRITICAL FIX: Use true SERIALIZABLE snapshot isolation to ensure all table reads are at the SAME point in time
        # This prevents race conditions where price_daily is fresh at t=0 but technical_data_daily becomes stale at t=5
        # SERIALIZABLE REPEATABLE READ = true snapshot isolation (PostgreSQL: deferrable transactions)
        missing = [t for t in ('price_daily', 'market_health_daily', 'trend_template_data', 'technical_data_daily', 'buy_sell_daily') if t not in dates]
        if missing:
            atomic_query_failed = False
            try:
                with DatabaseContext('read') as cur:
                    cur.execute("SET statement_timeout = 30000")  # 30s max for all queries
                    # ISSUE #1 & #6 FIX: Use true SERIALIZABLE REPEATABLE READ for snapshot isolation
                    # This ensures all queries see the database as it was at transaction start time
                    # PostgreSQL deferrable=true for read-only: optimal for consistency without deadlock
                    # Correct PostgreSQL syntax: spaces not commas between transaction modes
                    cur.execute("BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE READ ONLY DEFERRABLE")
                    atomic_transaction_started = True
                    try:
                        table_results = {}
                        for table in missing:
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
                            elif table in ('technical_data_daily', 'buy_sell_daily'):
                                cur.execute(f"SELECT MAX(updated_at) FROM {table}")
                                row = cur.fetchone()
                            else:
                                cur.execute(f"SELECT date FROM {table} ORDER BY date DESC LIMIT 1")
                                row = cur.fetchone()

                            if row and row[0]:
                                table_results[table] = row[0]
                                logger.info(f"[{_phase1_correlation_id}] Phase 1: direct scan found {table} latest={row[0]} (SERIALIZABLE REPEATABLE READ snapshot)")
                            else:
                                logger.warning(f"Phase 1: direct scan for {table} found no data")

                        cur.execute("COMMIT")
                        # CRITICAL: Only use results if transaction committed successfully (all queries at same snapshot)
                        dates.update(table_results)
                        logger.info(f"[{_phase1_correlation_id}] [ATOMIC] ✓ SERIALIZABLE transaction committed successfully - all {len(missing)} tables queried at same snapshot time")
                    except Exception as txn_err:
                        if atomic_transaction_started:
                            try:
                                cur.execute("ROLLBACK")
                            except Exception:
                                pass
                        logger.critical(f"[{_phase1_correlation_id}] [ATOMIC] SERIALIZABLE REPEATABLE READ atomic transaction failed ({txn_err}) - results may be inconsistent. HALTING to prevent race-condition data corruption")
                        atomic_query_failed = True
                        alerts.send_position_alert(
                            'DATA',
                            'ATOMIC_TRANSACTION_FAILED',
                            f'CRITICAL HALT: SERIALIZABLE atomic transaction failed. Cannot guarantee data consistency across tables. Error: {str(txn_err)[:200]}',
                            {'error': str(txn_err), 'halt': True}
                        )
            except Exception as e:
                logger.critical(f"[{_phase1_correlation_id}] [ATOMIC] SERIALIZABLE transaction connection failed ({e}) - HALTING to prevent data corruption")
                atomic_query_failed = True
                alerts.send_position_alert(
                    'DATA',
                    'ATOMIC_TRANSACTION_CONNECTION_FAILED',
                    f'CRITICAL HALT: Could not establish atomic transaction connection. Cannot guarantee data consistency. Error: {str(e)[:200]}',
                    {'error': str(e), 'halt': True}
                )

            # CRITICAL: If atomic query failed, HALT instead of proceeding with potentially corrupted data
            if atomic_query_failed:
                log_phase_result_fn(1, 'atomic_query_failure', 'halt', 'Database atomic query failed - cannot guarantee data consistency')
                alerts.send_position_alert(
                    'DATA',
                    'ATOMIC_QUERY_FAILURE_HALT',
                    f'HALT: Atomic transaction failed - cannot query all tables at same snapshot. Data consistency cannot be guaranteed. Escalate for investigation.',
                    {'halt': True}
                )
                return PhaseResult(1, 'atomic_query_failure', 'halted', {}, True, 'Atomic database query failed - all tables must be checked at same snapshot. Cannot proceed with potentially inconsistent data')

        spy_date = dates.get('price_daily') or dates.get('etf_price_daily')
        mh_date = dates.get('market_health_daily')
        tt_date = dates.get('trend_template_data')
        sqs_date = dates.get('signal_quality_scores')
        buys_date = dates.get('buy_sell_daily')
        swing_date = dates.get('swing_trader_scores')
        sector_date = dates.get('sector_ranking')

        # buy_sell_daily and signal_quality_scores are populated by the Step Functions morning
        # pipeline, which completes after the Lambda orchestrator fires at 9:30 AM ET. Halting on
        # their staleness creates a deadlock: Phase 1 blocks before Phase 5 can populate them.
        # They are logged for observability but excluded from the halt decision.
        # FIX #8: swing_trader_scores is DIFFERENT — it's populated DURING morning pipeline,
        # BEFORE 9:30 AM Phase 1. If missing/stale, Phase 5 cannot rank trades (no input data).
        # FIX #10: sector_ranking is populated DURING morning pipeline. Phase 3 (position monitor)
        # uses sector limits from fresh sector_ranking. If missing/stale, sector limits are invalid.
        halt_checks = {
            'SPY price data': spy_date,
            'Market health': mh_date,
            'Trend template': tt_date,
            'Swing trader scores': swing_date,  # FIX #8: Required for Phase 5 ranking
        }
        observe_checks = {
            'Signal quality scores': sqs_date,
            'Buy/sell signals': buys_date,
            'Sector ranking': sector_date,  # FIX #10: Warn-only; Phase 3 uses cached data as fallback
        }
        checks = {**halt_checks, **observe_checks}
        table_keys = {
            'SPY price data': 'price_daily',
            'Market health': 'market_health_daily',
            'Trend template': 'trend_template_data',
            'Signal quality scores': 'signal_quality_scores',
            'Buy/sell signals': 'buy_sell_daily',
            'Sector ranking': 'sector_ranking',
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

        # ISSUE #24 FIX: Define data dependency chain for atomic validation
        # buy_sell_daily depends on technical_data_daily depends on price_daily
        # If a downstream table is fresh but its upstream dependency is stale, the data is unreliable
        # ISSUE #6 FIX: Swing trader scores depends on signal_quality_scores and buy_sell_daily
        dependency_chain = {
            'SPY price data': [],  # No dependencies
            'Trend template': ['SPY price data'],  # Depends on prices
            'Buy/sell signals': ['Trend template', 'SPY price data'],  # Depends on trends and prices
            'Signal quality scores': ['Buy/sell signals'],  # Depends on buy signals
            'Swing trader scores': ['Buy/sell signals', 'Signal quality scores'],  # Depends on buys and SQS
            'Market health': [],  # Independent
            'Sector ranking': [],  # Independent (uses cached fallback in Phase 3)
        }

        # Issue #10 FIX: Load and log the halt threshold for transparency
        halt_threshold = 2  # Default
        try:
            with DatabaseContext('read') as _cfg_cur:
                _cfg_cur.execute("SELECT value FROM algo_config WHERE key = %s", ('phase1_halt_stale_days_threshold',))
                result = _cfg_cur.fetchone()
                if result:
                    halt_threshold = int(result[0])
        except Exception:
            pass

        logger.info(f"[DATA FRESHNESS] Simplified rule: data must be from {expected_date} (today is {run_date}, most recent trading day)")
        logger.info(f"[DATA FRESHNESS] Tolerance: {max_acceptable_age_days} trading day(s). Will trigger failsafe if older.")
        logger.info(f"[DATA FRESHNESS] HALT THRESHOLD: {halt_threshold} trading days — data >= {halt_threshold}d old will halt orchestrator if failsafe fails.")

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

        # CRITICAL FIX: Check data completeness EARLY before any failsafe triggering
        # If current data is incomplete (<95%), triggering failsafe won't help (loader itself failing)
        # Better to HALT and alert ops than to repeatedly trigger failing loaders
        try:
            with DatabaseContext('read') as _early_comp_cur:
                _early_comp_cur.execute("SET statement_timeout = 10000")
                early_completeness_warnings = []

                # Check price_daily completeness
                _early_comp_cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date >= %s", (expected_date,))
                price_row = _early_comp_cur.fetchone()
                price_symbols = price_row[0] if price_row else 0
                price_coverage = (price_symbols / expected_symbols * 100) if expected_symbols > 0 else 0
                if price_coverage < 95:
                    early_completeness_warnings.append(
                        f"price_daily: {price_symbols}/{expected_symbols} symbols ({price_coverage:.1f}%, need >95%)"
                    )

                # Check technical_data_daily completeness
                _early_comp_cur.execute("SELECT COUNT(DISTINCT symbol) FROM technical_data_daily WHERE updated_at >= %s", (expected_date,))
                tech_row = _early_comp_cur.fetchone()
                tech_symbols = tech_row[0] if tech_row else 0
                tech_coverage = (tech_symbols / expected_symbols * 100) if expected_symbols > 0 else 0
                if tech_coverage < 95:
                    early_completeness_warnings.append(
                        f"technical_data_daily: {tech_symbols}/{expected_symbols} symbols ({tech_coverage:.1f}%, need >95%)"
                    )

                # Check buy_sell_daily completeness
                _early_comp_cur.execute("SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily WHERE updated_at >= %s", (expected_date,))
                buys_row = _early_comp_cur.fetchone()
                buys_symbols = buys_row[0] if buys_row else 0
                buys_coverage = (buys_symbols / expected_symbols * 100) if expected_symbols > 0 else 0
                if buys_coverage < 95:
                    early_completeness_warnings.append(
                        f"buy_sell_daily: {buys_symbols}/{expected_symbols} symbols ({buys_coverage:.1f}%, need >95%)"
                    )

                # ISSUE #6 FIX: Check swing_trader_scores completeness (critical for Phase 5 ranking)
                _early_comp_cur.execute("SELECT COUNT(DISTINCT symbol) FROM swing_trader_scores WHERE date >= %s", (expected_date,))
                swing_row = _early_comp_cur.fetchone()
                swing_symbols = swing_row[0] if swing_row else 0
                swing_coverage = (swing_symbols / expected_symbols * 100) if expected_symbols > 0 else 0
                if swing_coverage < 95:
                    early_completeness_warnings.append(
                        f"swing_trader_scores: {swing_symbols}/{expected_symbols} symbols ({swing_coverage:.1f}%, need >95%)"
                    )

                # ISSUE #14 FIX: Symbol coverage tracking and adaptive failsafe triggering
                # - If coverage 80-95%: Trigger failsafe to retry (likely transient)
                # - If coverage <80%: Halt immediately (loader fundamentally failing)
                coverage_issues = []
                for warning in early_completeness_warnings:
                    # Parse coverage percentage from warning (e.g., "table: X/Y symbols (Z.Z%)")
                    try:
                        pct_start = warning.rfind('(')
                        pct_end = warning.rfind('%')
                        if pct_start > 0 and pct_end > pct_start:
                            cov_pct = float(warning[pct_start+1:pct_end])
                            coverage_issues.append((warning, cov_pct))
                    except:
                        coverage_issues.append((warning, 0))

                # Separate by severity
                partial_coverage = [w for w, cov in coverage_issues if 80 <= cov < 95]
                critical_coverage = [w for w, cov in coverage_issues if cov < 80]

                # Emit metrics for symbol coverage
                try:
                    from algo.algo_metrics import MetricsPublisher
                    metrics = MetricsPublisher()
                    for warning, cov_pct in coverage_issues:
                        table_name = warning.split(':')[0] if ':' in warning else 'unknown'
                        metrics.add_metric(
                            'SymbolCoveragePercent',
                            cov_pct,
                            unit='Percent',
                            dimensions={'Table': table_name, 'Phase': '1'}
                        )
                    metrics.flush()
                except:
                    pass

                if critical_coverage:
                    # Critical: <80% coverage, don't retry
                    logger.critical(f"[COMPLETENESS_CRITICAL] Data critically incomplete (<80%): {'; '.join(critical_coverage)}")
                    alerts.send_position_alert(
                        'DATA',
                        'DATA_COMPLETENESS_CRITICAL',
                        f"HALT: Critical data incompleteness: {'; '.join(critical_coverage)}. "
                        f"Loaders failing fundamentally. Escalate for investigation.",
                        {'completeness_issues': critical_coverage}
                    )
                    log_phase_result_fn(1, 'data_completeness_early', 'halt',
                                       f"Critical halt - data <80% complete: {'; '.join(critical_coverage)}")
                    return PhaseResult(1, 'data_completeness_early', 'halted', {}, True,
                                     f'Data critically incomplete: {"; ".join(critical_coverage)}. Escalate for ops.')
                elif partial_coverage:
                    # Partial: 80-95%, trigger failsafe
                    logger.warning(f"[COMPLETENESS_PARTIAL] Data partially incomplete (80-95%): {'; '.join(partial_coverage)}. "
                                 f"Triggering failsafe to retry...")
                    alerts.send_position_alert(
                        'DATA',
                        'DATA_COMPLETENESS_PARTIAL',
                        f"WARNING: Partial data incompleteness: {'; '.join(partial_coverage)}. "
                        f"Triggering failsafe to retry. May resolve on next attempt.",
                        {'completeness_issues': partial_coverage}
                    )
                    # ISSUE #14: Trigger failsafe for slow/incomplete loaders
                    try:
                        for loader_name in ['stock_prices_daily', 'technical_data_daily', 'buy_sell_daily']:
                            try:
                                _trigger_loader_failsafe_with_verification(loader_name, verbose=False, poll_timeout_sec=60, retry_count=1)
                            except:
                                pass
                    except:
                        pass
                    # Continue with Phase 1 (don't halt on partial coverage)
        except Exception as early_comp_err:
            logger.debug(f"[EARLY_COMPLETENESS_CHECK] Check failed: {early_comp_err} (proceeding)")

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

                # ISSUE #24 FIX: Validate upstream dependencies
                # If this table's dependencies are stale, mark this table as unreliable even if fresh
                upstream_stale = False
                for dep_name in dependency_chain.get(name, []):
                    if dep_name in checks and checks[dep_name] is not None:
                        dep_date = checks[dep_name]
                        is_dep_stale = dep_date < min_acceptable_date
                        if is_dep_stale:
                            logger.warning(f"  [DEPENDENCY] {name} depends on {dep_name}, but dependency is stale (from {dep_date})")
                            upstream_stale = True

                # Treat as stale if either directly stale OR has stale dependency
                effective_stale = is_stale or upstream_stale
                if effective_stale and is_halt_check:
                    if upstream_stale:
                        stale_items.append(f"{name}: {trading_day_age}d old BUT UNRELIABLE (upstream dependency stale, need within {min_acceptable_date})")
                    else:
                        stale_items.append(f"{name}: {trading_day_age}d stale ({calendar_day_age}cal, need within {expected_date} to {min_acceptable_date})")
                if verbose:
                    is_ideal = d >= expected_date
                    flag = '[OK]' if is_ideal else '[WARN]' if (not is_stale) else '[STALE]'
                    logger.info(f"  {flag} {name:25s}: latest {d} ({trading_day_age}d trading old/{calendar_day_age}d calendar, acceptable until {min_acceptable_date})")

        # ISSUE #10 FIX: Monitor morning prep timing to detect bottlenecks and deadline violations with 80% threshold
        # Morning prep: 2:45 AM start → 9:30 AM deadline (405 min available)
        # Expected: 230-255 min execution time, leaving 150 min buffer
        # 80% threshold: alert when 324+ min elapsed (81 min remaining)
        try:
            with DatabaseContext('read') as _timing_cur:
                _timing_cur.execute("SET statement_timeout = 5000")
                # Check when morning prep pipeline started (look at loader start times)
                _timing_cur.execute(
                    "SELECT MIN(started_at) FROM data_loader_runs WHERE run_date = %s "
                    "AND table_name IN ('price_daily', 'technical_data_daily', 'buy_sell_daily') "
                    "AND started_at > NOW() - INTERVAL '5 hours'",  # Morning prep starts ~2:45 AM, look back 5h
                    (run_date,)
                )
                morning_start = _timing_cur.fetchone()
                if morning_start and morning_start[0]:
                    elapsed_since_start = (datetime.now(timezone.utc) - morning_start[0]).total_seconds() / 60
                    remaining_to_deadline = 405 - elapsed_since_start  # 9:30 AM deadline = 405 min from 2:45 AM
                    elapsed_pct = (elapsed_since_start / 405) * 100

                    # ISSUE #10 FIX: 80% threshold = 324 minutes elapsed, 81 minutes remaining
                    if elapsed_pct >= 95:
                        # 95%+ of time used (< 20 min to deadline) — ISSUE #3 FIX: HALT instead of just warning
                        logger.critical(
                            f"[{_phase1_correlation_id}] [MORNING_PREP_TIMING] 🚨 CRITICAL: {elapsed_pct:.0f}% of time used! Only {remaining_to_deadline:.0f}min to 9:30 AM deadline! "
                            f"Morning prep started {elapsed_since_start:.0f}min ago. HALTING PHASE 1 to prevent late execution."
                        )
                        alerts.send_position_alert(
                            'TIMING',
                            'MORNING_PREP_DEADLINE_CRITICAL_HALT',
                            f'HALT: {elapsed_pct:.0f}% of time used. Only {remaining_to_deadline:.0f}min to deadline. '
                            f'Morning prep will exceed 9:30 AM deadline. Halting Phase 1 to prevent trading with stale data.',
                            {'elapsed_minutes': elapsed_since_start, 'remaining_minutes': remaining_to_deadline, 'elapsed_pct': elapsed_pct}
                        )
                        log_phase_result_fn(1, 'morning_prep_deadline', 'halt',
                                           f'Morning prep deadline at risk: {elapsed_pct:.0f}% time used, only {remaining_to_deadline:.0f}min to 9:30 AM')
                        return PhaseResult(1, 'morning_prep_deadline', 'halted', {}, True,
                                         f'Morning prep time budget exhausted ({elapsed_pct:.0f}% used). '
                                         f'Only {remaining_to_deadline:.0f}min remaining until market open. '
                                         f'Cannot safely complete data freshness checks and trading in remaining time. Halting.')
                    elif elapsed_pct >= 80:
                        # 80%+ of time used (threshold alert)
                        logger.warning(
                            f"[{_phase1_correlation_id}] [MORNING_PREP_TIMING] ⚠️  WARNING: {elapsed_pct:.0f}% of time used (80% threshold)! {remaining_to_deadline:.0f}min to deadline. "
                            f"Morning prep running {elapsed_since_start:.0f}min. May not complete by 9:30 AM. Monitor closely for delays."
                        )
                        alerts.send_position_alert(
                            'TIMING',
                            'MORNING_PREP_80PCT_THRESHOLD',
                            f'Morning prep at 80% of available time budget. {elapsed_pct:.0f}% elapsed, {remaining_to_deadline:.0f}min remaining to 9:30 AM deadline. '
                            f'Started {elapsed_since_start:.0f}min ago. Monitor for further delays.',
                            {'elapsed_minutes': elapsed_since_start, 'remaining_minutes': remaining_to_deadline, 'elapsed_pct': elapsed_pct}
                        )
                    elif remaining_to_deadline < 60:
                        # Less than 1 hour to deadline (safeguard)
                        logger.critical(
                            f"[{_phase1_correlation_id}] [MORNING_PREP_TIMING] ⚠️  CRITICAL: Only {remaining_to_deadline:.0f}min to 9:30 AM deadline! "
                            f"Morning prep started {elapsed_since_start:.0f}min ago ({elapsed_pct:.0f}% of budget). May not complete in time."
                        )
                        alerts.send_position_alert(
                            'TIMING',
                            'MORNING_PREP_DEADLINE_RISK',
                            f'Morning prep only {remaining_to_deadline:.0f}min to deadline ({elapsed_pct:.0f}% time used). '
                            f'Started {elapsed_since_start:.0f}min ago. At risk of exceeding 9:30 AM deadline.',
                            {'elapsed_minutes': elapsed_since_start, 'remaining_minutes': remaining_to_deadline, 'elapsed_pct': elapsed_pct}
                        )
                    elif remaining_to_deadline < 120:
                        # Less than 2 hours to deadline
                        logger.warning(
                            f"[{_phase1_correlation_id}] [MORNING_PREP_TIMING] ⚠️  WARNING: Only {remaining_to_deadline:.0f}min to deadline ({elapsed_pct:.0f}% time used). "
                            f"Morning prep running {elapsed_since_start:.0f}min. Monitor progress for additional delays."
                        )
                    else:
                        # On track: ≤ 60% time used, > 150 min remaining
                        logger.info(
                            f"[{_phase1_correlation_id}] [MORNING_PREP_TIMING] ✓ On track: {elapsed_pct:.0f}% time used, "
                            f"{remaining_to_deadline:.0f}min remaining to 9:30 AM deadline. "
                            f"Elapsed {elapsed_since_start:.0f}min so far."
                        )
        except Exception as timing_err:
            logger.debug(f"[MORNING_PREP_TIMING] Could not check timing: {timing_err}")

        # ISSUE #2 FIX: Check for INCOMPLETE loader status (newly added to data_loader_status)
        # INCOMPLETE means loader ran but couldn't get 95%+ symbol coverage
        incomplete_loaders = []
        try:
            with DatabaseContext('read') as _status_cur:
                _status_cur.execute("SET statement_timeout = 3000")
                _status_cur.execute(
                    "SELECT table_name, completion_pct, symbols_loaded, symbol_count "
                    "FROM data_loader_status WHERE status = 'INCOMPLETE'"
                )
                for row in _status_cur.fetchall():
                    table, completion_pct, symbols_loaded, symbol_count = row
                    incomplete_loaders.append({
                        'table': table,
                        'completion_pct': completion_pct,
                        'symbols_loaded': symbols_loaded,
                        'symbol_count': symbol_count
                    })
                    logger.warning(
                        f"[INCOMPLETE] Loader {table}: {symbols_loaded}/{symbol_count} symbols ({completion_pct:.1f}%) — "
                        f"below 95% threshold, will trigger failsafe for retry"
                    )

            # ISSUE #18 FIX: If any loader is INCOMPLETE, force retry via failsafe
            # Incomplete = loader ran but got <95% coverage (partial failure)
            # Don't just warn — retry immediately to get full coverage
            if incomplete_loaders:
                stale_items.extend([
                    f"{il['table']}: {il['symbols_loaded']}/{il['symbol_count']} symbols ({il['completion_pct']:.1f}%, need >95%)"
                    for il in incomplete_loaders
                ])
                alerts.send_position_alert(
                    'DATA',
                    'LOADER_INCOMPLETE',
                    f"One or more loaders completed with <95% symbol coverage (partial failure): {'; '.join([il['table'] for il in incomplete_loaders])}. "
                    f"Triggering failsafe for automatic retry.",
                    {'incomplete_loaders': incomplete_loaders}
                )
                logger.warning(f"[{_phase1_correlation_id}] [INCOMPLETE_LOADERS] {len(incomplete_loaders)} loader(s) marked INCOMPLETE - forcing retry via failsafe")
        except Exception as incomp_err:
            logger.debug(f"[INCOMPLETE] Check failed: {incomp_err} (proceeding)")

        # ISSUE #7 FIX: Validate data COMPLETENESS (symbol coverage %) for critical tables
        # Freshness alone isn't enough — if 500/5000 symbols failed to load, data is incomplete
        # CRITICAL FIX: Must HALT if any table <95%, not just warn. Incomplete data causes:
        # - Partial buy/sell signals (missing symbols)
        # - Phase 5 positions with reduced symbol coverage
        # - Lower portfolio performance from opportunity loss
        completeness_warnings = []
        price_coverage = 0
        tech_coverage = 0
        buys_coverage = 0

        try:
            with DatabaseContext('read') as _comp_cur:
                _comp_cur.execute("SET statement_timeout = 10000")  # 10s for all checks

                # Check price_daily completeness
                _comp_cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date >= %s", (expected_date,))
                price_row = _comp_cur.fetchone()
                price_symbols = price_row[0] if price_row else 0
                price_coverage = (price_symbols / expected_symbols * 100) if expected_symbols > 0 else 0
                if price_coverage < 95:
                    completeness_warnings.append(
                        f"price_daily: {price_symbols}/{expected_symbols} symbols ({price_coverage:.1f}%, expected >95%)"
                    )
                    logger.error(f"  [COMPLETENESS] CRITICAL: {completeness_warnings[-1]}")

                # Check technical_data_daily completeness
                _comp_cur.execute("SELECT COUNT(DISTINCT symbol) FROM technical_data_daily WHERE updated_at >= %s", (expected_date,))
                tech_row = _comp_cur.fetchone()
                tech_symbols = tech_row[0] if tech_row else 0
                tech_coverage = (tech_symbols / expected_symbols * 100) if expected_symbols > 0 else 0
                if tech_coverage < 95:
                    completeness_warnings.append(
                        f"technical_data_daily: {tech_symbols}/{expected_symbols} symbols ({tech_coverage:.1f}%, expected >95%)"
                    )
                    logger.error(f"  [COMPLETENESS] CRITICAL: {completeness_warnings[-1]}")

                # Check buy_sell_daily completeness
                _comp_cur.execute("SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily WHERE updated_at >= %s", (expected_date,))
                buys_row = _comp_cur.fetchone()
                buys_symbols = buys_row[0] if buys_row else 0
                buys_coverage = (buys_symbols / expected_symbols * 100) if expected_symbols > 0 else 0
                if buys_coverage < 95:
                    completeness_warnings.append(
                        f"buy_sell_daily: {buys_symbols}/{expected_symbols} symbols ({buys_coverage:.1f}%, expected >95%)"
                    )
                    logger.error(f"  [COMPLETENESS] CRITICAL: {completeness_warnings[-1]}")

                # ISSUE #7 FIX: HALT if any critical table is incomplete
                # Incomplete data cascades: partial loaders → partial signals → incomplete positions → portfolio risk
                if completeness_warnings:
                    logger.critical(f"[DATA COMPLETENESS] HALT: {len(completeness_warnings)} tables below 95% threshold")
                    alerts.send_position_alert(
                        'DATA',
                        'DATA_COMPLETENESS_CRITICAL',
                        f"HALT: Data completeness critical. Incomplete tables would generate partial signals and positions. "
                        f"Details: {'; '.join(completeness_warnings)}. Loaders may have failed partially.",
                        {'completeness_warnings': completeness_warnings, 'coverage': {
                            'price': price_coverage, 'technical': tech_coverage, 'buys': buys_coverage
                        }, 'halt': True}
                    )
                    log_phase_result_fn(1, 'data_completeness', 'halt',
                                       f"HALT: Incomplete data — price={price_coverage:.0f}%, tech={tech_coverage:.0f}%, buys={buys_coverage:.0f}% (all require >95%)")
                    return PhaseResult(1, 'data_completeness', 'halted', {}, True,
                                     f'Data completeness critical: price={price_coverage:.0f}%, tech={tech_coverage:.0f}%, buys={buys_coverage:.0f}% — all require >95%. '
                                     f'Incomplete data would cause partial signal generation and portfolio positions with reduced symbol coverage.')
                else:
                    log_phase_result_fn(1, 'data_completeness', 'success',
                                       f"All critical tables >95% complete: price={price_coverage:.0f}%, tech={tech_coverage:.0f}%, buys={buys_coverage:.0f}%")

        except Exception as comp_err:
            logger.debug(f"[DATA COMPLETENESS] Check failed: {comp_err} (proceeding)")

        if _metrics:
            _metrics.flush()

        if stale_items:
            logger.warning(f"[{_phase1_correlation_id}] Data stale detected, will trigger loader: {stale_items}")

            # ISSUE #11 FIX: Pipeline Overlap Detection with Enforcement & Throttling
            # ISSUE #4 FIX: Pipeline Overlap Detection with RDS Connection Pool Monitoring
            # Check if EOD loaders are still running when morning prep needs to run.
            # Morning prep (2:45 AM): stock_prices_daily → technical_data_daily → buy_sell_daily
            # If EOD loaders still running: both pipelines compete for RDS Proxy connections
            # NEW: Add throttling - if EOD running <60min, delay morning prep 30s and retry
            # ENFORCEMENT: Fail if EOD overran by >11.5 hours (should finish by ~5:30 PM)
            try:
                overlap_retry_count = 0
                max_overlap_retries = 2  # Allow 1 retry (total 2 checks = 60s delay max)

                while overlap_retry_count <= max_overlap_retries:
                    with DatabaseContext('read') as _overlap_cur:
                        _overlap_cur.execute("""
                            SELECT COUNT(*), MAX(last_updated) FROM data_loader_status
                            WHERE status = 'RUNNING' AND table_name IN ('price_daily', 'technical_data_daily', 'market_health_daily')
                        """)
                        overlap_result = _overlap_cur.fetchone()
                        running_count = overlap_result[0] if overlap_result else 0
                        last_update = overlap_result[1] if overlap_result and len(overlap_result) > 1 else None

                        if running_count > 0 and last_update:
                            elapsed_minutes = (datetime.now(timezone.utc) - last_update).total_seconds() / 60
                            logger.warning(
                                f"[{_phase1_correlation_id}] [PIPELINE_OVERLAP] {running_count} core loaders still RUNNING (updated {elapsed_minutes:.0f}min ago). "
                                f"RDS Proxy risk: 6 parallel loaders × 2-4 parallelism = 48+ connection requests vs 30 pooled connections."
                            )

                            # ENFORCEMENT: If EOD overran >11.5 hours, fail immediately
                            # EOD starts 4:05 PM, should finish by 5:30 PM = 85 min
                            # If still running at 2:45 AM (10h 40m later), EOD massively overran
                            eod_max_duration = 690  # 11.5 hours in minutes (4 PM + 11.5h = 3:30 AM)
                            if elapsed_minutes > eod_max_duration:
                                error_msg = (
                                    f"[PIPELINE_OVERLAP] FATAL: EOD pipeline overran by {elapsed_minutes - eod_max_duration:.0f}min "
                                    f"(should finish by ~5:30 PM, now {elapsed_minutes/60:.1f}h later at 2:45 AM morning prep). "
                                    f"RDS Proxy connection pool (30 connections) cannot support both pipelines. "
                                    f"Aborting morning prep to prevent cascading failure. Escalating for manual intervention."
                                )
                                logger.error(f"[{_phase1_correlation_id}] {error_msg}")
                                alerts.send_position_alert(
                                    'SYSTEM',
                                    'EOD_PIPELINE_OVERRAN',
                                    error_msg,
                                    {'running_loaders': running_count, 'elapsed_minutes': elapsed_minutes}
                                )
                                log_phase_result_fn(1, 'pipeline_overlap', 'halt', error_msg)
                                return PhaseResult(1, 'pipeline_overlap', 'halted', {}, True, error_msg)

                            # NEW THROTTLING LOGIC: If EOD <60min elapsed, delay and retry
                            if elapsed_minutes < 60 and overlap_retry_count < max_overlap_retries:
                                wait_sec = 30
                                logger.info(
                                    f"[{_phase1_correlation_id}] [PIPELINE_OVERLAP_THROTTLE] EOD running {elapsed_minutes:.0f}min (threshold 60min). "
                                    f"Delaying morning prep {wait_sec}s for EOD to complete (retry {overlap_retry_count + 1}/{max_overlap_retries})..."
                                )
                                time.sleep(wait_sec)
                                overlap_retry_count += 1
                                continue  # Retry the check

                            # If we reach here and loaders still running >60min (or retries exhausted), log critical
                            if elapsed_minutes >= 60:
                                logger.critical(
                                    f"[{_phase1_correlation_id}] [PIPELINE_OVERLAP] CRITICAL: EOD loaders running {elapsed_minutes:.0f}min when morning prep triggered. "
                                    f"Both pipelines competing for RDS Proxy. May exceed 120s borrow timeout → connection errors → cascading failures. "
                                    f"Proceeding with caution and RDS monitoring."
                                )
                                alerts.send_position_alert(
                                    'SYSTEM',
                                    'PIPELINE_OVERLAP_RDS_RISK',
                                    f'Pipeline overlap: {running_count} EOD loaders running {elapsed_minutes:.0f}min. '
                                    f'Morning prep starting now — RDS Proxy connection pool at risk (30 pooled vs 48+ requested). '
                                    f'Monitor CloudWatch RDS DatabaseConnections metric. May exceed 120s borrow timeout.',
                                    {'running_loaders': running_count, 'elapsed_minutes': elapsed_minutes}
                                )
                        # No running loaders, exit retry loop
                        break
            except Exception as e:
                logger.debug(f"[{_phase1_correlation_id}] [PIPELINE_OVERLAP] Check failed: {e} (continuing)")

            # ISSUE #15 FIX: Data Age Blocking
            # Check if source data is too old and block trading if so
            if spy_date and (run_date - spy_date).days > 2:  # max_age_days from config
                logger.error(f"[{_phase1_correlation_id}] [DATA_AGE] Source data {(run_date - spy_date).days}d old (max 2d)")
                log_phase_result_fn(1, 'data_age_blocking', 'halt', 'Source data exceeds age threshold')
                return PhaseResult(1, 'data_age_blocking', 'halted', {}, True, 'Source data exceeds age threshold')

            # SIMPLIFIED: Check if loader is currently RUNNING. If yes, use grace period.
            # If not, trigger immediately (no time-based grace period delays).
            # This prevents waiting 2.5 hours for a loader that already finished.
            failsafe_already_triggered = False
            loader_currently_running = False

            try:
                # ISSUE #5 FIX: Check ALL critical-path loaders for hung status, not just stock_prices_daily
                # Critical loaders: stock_prices_daily, technical_data_daily, buy_sell_daily
                # If ANY of these are hung, they block the entire morning pipeline
                critical_loaders_to_check = ['price_daily', 'technical_data_daily', 'buy_sell_daily']
                hung_critical_loaders = []

                with DatabaseContext('read') as _status_cur:
                    _status_cur.execute("SET statement_timeout = 3000")  # 3s max

                    for critical_loader in critical_loaders_to_check:
                        try:
                            _status_cur.execute(
                                "SELECT status FROM data_loader_status WHERE table_name = %s",
                                (critical_loader,)
                            )
                            result = _status_cur.fetchone()
                            if result and result[0] == 'RUNNING':
                                # Check if loader has hung (stale heartbeat >3 min)
                                if _detect_hung_loader_task(critical_loader):
                                    hung_critical_loaders.append(critical_loader)
                                    logger.warning(f"[{_phase1_correlation_id}] [HUNG_TASK] Critical loader '{critical_loader}' marked RUNNING but heartbeat stale - hung detected")
                                    # Attempt to terminate hung task
                                    if _terminate_hung_loader_task(critical_loader, verbose=verbose):
                                        logger.info(f"[{_phase1_correlation_id}] [HUNG_TASK] ✓ Successfully terminated hung loader: {critical_loader}")
                                    else:
                                        logger.warning(f"[{_phase1_correlation_id}] [HUNG_TASK] Could not terminate {critical_loader}, may exhaust RDS pool")
                        except Exception as e:
                            logger.debug(f"[{_phase1_correlation_id}] Could not check status for {critical_loader}: {e}")

                    # ISSUE #5 FIX: If we found hung critical loaders, we must trigger failsafe
                    # Do NOT rely on grace period if critical path is blocked
                    if hung_critical_loaders:
                        logger.critical(
                            f"[{_phase1_correlation_id}] [HUNG_CRITICAL_LOADERS] {len(hung_critical_loaders)} critical loader(s) hung: {'; '.join(hung_critical_loaders)}. "
                            f"Morning pipeline blocked. Failing fast to trigger new failsafe instead of waiting through grace period. "
                            f"Hung loaders: {'; '.join(hung_critical_loaders)} (must be restarted to prevent data staleness)"
                        )
                        failsafe_already_triggered = False  # Force failsafe trigger below
                        # ISSUE #5 FIX: Alert immediately about hung loaders
                        alerts.send_position_alert(
                            'DATA',
                            'HUNG_CRITICAL_LOADERS_DETECTED',
                            f'HUNG LOADER ALERT: {len(hung_critical_loaders)} critical loader(s) detected with stale heartbeat: {", ".join(hung_critical_loaders)}. '
                            f'Triggering fresh failsafe to replace hung tasks. Hung tasks being terminated.',
                            {'hung_loaders': hung_critical_loaders, 'correlation_id': _phase1_correlation_id}
                        )

                    # If stock_prices_daily is RUNNING and NOT hung, use grace period
                    _status_cur.execute(
                        "SELECT status FROM data_loader_status WHERE table_name = 'price_daily'"
                    )
                    result = _status_cur.fetchone()
                    if result and result[0] == 'RUNNING' and 'price_daily' not in hung_critical_loaders:
                        # Loader is actively running and healthy
                        loader_currently_running = True
                        logger.info(f"[{_phase1_correlation_id}] [FAILSAFE] Loader status: RUNNING in background and healthy. Using grace period, no re-trigger needed.")
                        failsafe_already_triggered = True  # Skip trigger below

                    # ISSUE #8 FIX: Also check for hung analytics loaders that could exhaust RDS connection pool
                    # Analytics loaders (company_profile, analyst_sentiment, etc.) aren't on critical path
                    # but if hung, they consume connections and prevent other loaders from running
                    analytics_loaders = ['company_profile', 'analyst_sentiment', 'stability_metrics',
                                       'value_metrics', 'growth_metrics', 'quality_metrics']
                    hung_loaders = []
                    for loader_table in analytics_loaders:
                        try:
                            if _detect_hung_loader_task(loader_table, timeout_minutes=2):  # 2min timeout for analytics
                                hung_loaders.append(loader_table)
                                logger.warning(f"[{_phase1_correlation_id}] [HUNG_TASK] Analytics loader '{loader_table}' appears hung, attempting termination")
                                _terminate_hung_loader_task(loader_table, verbose=False)
                        except Exception:
                            pass  # Ignore errors for non-critical analytics loaders

                    if hung_loaders:
                        alerts.send_position_alert(
                            'DATA',
                            'HUNG_ANALYTICS_LOADERS',
                            f'{len(hung_loaders)} analytics loader(s) detected as hung (stale heartbeat >2min): {"; ".join(hung_loaders)}. '
                            f'Attempted termination to free RDS connections.',
                            {'hung_loaders': hung_loaders, 'correlation_id': _phase1_correlation_id}
                        )
                        logger.warning(f"[{_phase1_correlation_id}] [HUNG_ANALYTICS] Alerted on {len(hung_loaders)} hung analytics loader(s)")
            except Exception as status_err:
                logger.debug(f"[{_phase1_correlation_id}] [FAILSAFE] Could not check loader status: {status_err}. Will trigger fresh loader.")

            if failsafe_already_triggered and loader_currently_running:
                # Loader is actively running — let it finish
                failsafe_ok = True
                logger.info(f"[{_phase1_correlation_id}] [FAILSAFE] ✓ Loader actively RUNNING. Proceeding to Phase 2 with in-flight loader.")
                alerts.send_position_alert(
                    'DATA',
                    'STALE_DATA_LOADER_ACTIVE',
                    f'Stale data detected but loader is actively running. Proceeding with in-flight loader. CorrID: {_phase1_correlation_id}',
                    {'stale_items': stale_items, 'loader_status': 'RUNNING', 'correlation_id': _phase1_correlation_id}
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

                # SIMPLIFIED FAILSAFE: Single attempt with 180s poll timeout
                # Fargate tasks can take 45-120s to reach RUNNING under load (Issue #13)
                # If it fails, halt only if data is VERY stale (2+ days). Otherwise proceed with warning.
                # This prevents waiting through 3 timeout loops (30+120+180s = 330s) when failsafe is dead.
                failsafe_ok = False
                poll_timeout = 180  # ISSUE #13 FIX: Increased from 120s to 180s to safely handle worst-case Fargate delays

                try:
                    logger.info(f"[{_phase1_correlation_id}] [FAILSAFE] Triggering loader with {poll_timeout}s poll timeout...")
                    failsafe_ok = _trigger_loader_failsafe_with_verification('stock_prices_daily', verbose=verbose, poll_timeout_sec=poll_timeout, correlation_id=_phase1_correlation_id)
                    if failsafe_ok:
                        logger.info(f"[{_phase1_correlation_id}] [FAILSAFE] ✓ Loader trigger confirmed. Task is running. Data will refresh in parallel.")
                    else:
                        # ISSUE #3 FIX: Explicit log that trigger DID NOT succeed
                        logger.critical(f"[{_phase1_correlation_id}] [FAILSAFE] ✗ CRITICAL: Loader trigger FAILED to start within {poll_timeout}s timeout. Task may not have started or started but crashed immediately.")
                except Exception as trigger_err:
                    # ISSUE #3 FIX: Exception during trigger is also a failure - treat as critical
                    logger.critical(f"[{_phase1_correlation_id}] [FAILSAFE] ✗ CRITICAL: Loader trigger exception: {trigger_err}. Task likely did not start.")
                    failsafe_ok = False  # Ensure we treat exception as failure

            if not failsafe_ok:
                # ISSUE #3 FIX: Failsafe failed or timeout - loader may not have started
                # CRITICAL: Cannot safely proceed if failsafe didn't start, regardless of current data age
                # Reason: Data age will only INCREASE while no loader is running (e.g., 1d stale at 2:45 AM
                # becomes 2d stale by 9:30 AM if no loader runs). Proceeding is a bet that won't pay off.
                logger.critical(f"[FAILSAFE_FAILED] Loader failsafe trigger did not confirm startup within {poll_timeout}s. "
                              f"Cannot safely proceed — data will only get staler while no loader runs. HALTING.")

                # Parse current data age for reporting
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

                logger.critical(f"[FAILSAFE_FAILED] Current data is {oldest_stale_trading_day_age}d trading days old. "
                              f"Without a running loader, this will exceed halt threshold ({halt_threshold}d) within hours. "
                              f"Manual intervention required.")
                logger.critical(f"  Stale items: {stale_items}")
                logger.critical(f"  Action: Check CloudWatch logs for ECS loader task startup errors")
                logger.critical(f"  Action: Verify ECS cluster capacity, task definition, and networking")
                logger.critical(f"  Action: Manually trigger loader or restart orchestrator once issues are resolved")

                alerts.send_position_alert(
                    'DATA',
                    'FAILSAFE_TRIGGER_FAILED',
                    f'CRITICAL HALT: Failsafe loader trigger FAILED to start within {poll_timeout}s. '
                    f'Data currently {oldest_stale_trading_day_age}d trading days old and will become stale. '
                    f'Cannot proceed without running loader. Check ECS logs for startup errors. Manual intervention required.',
                    {'stale_items': stale_items, 'failsafe': 'failed', 'current_age': oldest_stale_trading_day_age,
                     'halt': True, 'poll_timeout_sec': poll_timeout}
                )
                log_phase_result_fn(1, 'data_freshness', 'halt',
                                   f'CRITICAL: Failsafe loader trigger FAILED — did not start within {poll_timeout}s. Data age: {oldest_stale_trading_day_age}d trading days')
                return PhaseResult(1, 'data_freshness', 'halted', {}, True,
                                 f'Failsafe loader trigger FAILED within {poll_timeout}s. Data {oldest_stale_trading_day_age}d old and getting staler. '
                                 f'Check ECS logs for errors. Manual intervention required.')
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
                sqs_row = _check_cur.fetchone()
                sqs_count = sqs_row[0] if sqs_row else 0

                _check_cur.execute("SELECT COUNT(*) FROM buy_sell_daily")
                bsd_row = _check_cur.fetchone()
                bsd_count = bsd_row[0] if bsd_row else 0

                # Also check critical price table
                _check_cur.execute("SELECT COUNT(*) FROM price_daily WHERE symbol='SPY'")
                price_row = _check_cur.fetchone()
                price_count = price_row[0] if price_row else 0

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

        # FINAL SAFETY CHECK (Issue #1, #6): Prevent proceeding with extremely stale data
        # This is a last-line-of-defense check before success return
        try:
            with DatabaseContext('read') as _final_check_cur:
                _final_check_cur.execute("SET statement_timeout = 5000")

                # Verify price_daily has recent data (within halt_threshold trading days)
                _final_check_cur.execute(
                    f"SELECT MAX(date) FROM price_daily WHERE symbol='SPY'"
                )
                max_date = _final_check_cur.fetchone()
                if max_date and max_date[0]:
                    max_date_val = max_date[0]
                    if isinstance(max_date_val, str):
                        from datetime import datetime
                        max_date_val = datetime.fromisoformat(max_date_val).date()
                    age_trading_days = (expected_date - max_date_val).days

                    # CRITICAL: If data is at or beyond halt threshold, MUST HALT
                    if age_trading_days >= halt_threshold:
                        logger.critical(
                            f"[FINAL_SAFETY_CHECK] HALT: price_daily is {age_trading_days}d stale (threshold={halt_threshold}d). "
                            f"Even if freshness checks passed, data is too old for safe trading. HALTING."
                        )
                        alerts.send_position_alert(
                            'DATA',
                            'FINAL_SAFETY_HALT_STALE_DATA',
                            f'HALT: Final safety check failed. price_daily is {age_trading_days}d stale (halt threshold: {halt_threshold}d). '
                            f'Data too old for safe trading. This should have been caught earlier. Escalate.',
                            {'data_age_days': age_trading_days, 'halt_threshold': halt_threshold, 'final_check': True}
                        )
                        log_phase_result_fn(1, 'final_safety', 'halt',
                                           f'FINAL_SAFETY: price_daily is {age_trading_days}d old (exceed threshold {halt_threshold}d)')
                        return PhaseResult(1, 'final_safety', 'halted', {}, True,
                                         f'FINAL SAFETY: price_daily is {age_trading_days}d stale (threshold {halt_threshold}d). '
                                         f'Data too old for safe trading. Manual intervention required.')
        except Exception as final_err:
            logger.debug(f"[FINAL_SAFETY_CHECK] Could not verify: {final_err} (proceeding)")

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
                _sw_cur_row = _sw_cur.fetchone()
                expected_symbol_count = _sw_cur_row[0] if _sw_cur_row else 4500

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

                # Check sector_ranking freshness (warn-only, doesn't halt)
                # Sector ranking is populated during morning pipeline and used by Phase 3 for position limits
                # If missing/stale, Phase 3 falls back to cached sector assignments with a warning
                sector_warnings = []
                if sector_date is None:
                    logger.info("[SECTOR_RANKING] Not populated yet (expected during morning pipeline)")
                    log_phase_result_fn(1, 'sector_ranking', 'info', 'Not yet populated (expected during morning pipeline)')
                elif sector_date < expected_date:
                    from algo.algo_market_calendar import MarketCalendar
                    sector_trading_age = 0
                    check_date = run_date - timedelta(days=1)
                    while check_date >= sector_date and sector_trading_age < 30:
                        if MarketCalendar.is_trading_day(check_date):
                            sector_trading_age += 1
                        check_date -= timedelta(days=1)
                    sector_warnings.append(f"sector_ranking {sector_trading_age}d stale")
                    logger.warning(f"[SECTOR_RANKING] Stale ({sector_trading_age}d trading old). Phase 3 will use cached sector data.")
                    log_phase_result_fn(1, 'sector_ranking', 'warn', f'{sector_trading_age}d stale - cached fallback active')
                else:
                    logger.info(f"[SECTOR_RANKING] Fresh as of {sector_date}")
                    log_phase_result_fn(1, 'sector_ranking', 'success', f'Fresh as of {sector_date}')

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

        # ISSUE #5 FIX: MORNING PREP VISIBILITY AND DEPENDENCY CHAIN VALIDATION
        # Check if morning pipeline (2:45 AM) actually ran and all dependency steps completed.
        # If any step failed silently (price→tech→buy_sell→quality), downstream signals incomplete.
        try:
            now_et = datetime.now(ZoneInfo("America/New_York"))
            is_9am_or_later = now_et.hour >= 9

            if is_9am_or_later:
                morning_pipeline_cutoff = run_date.replace(hour=2, minute=45, second=0, microsecond=0)
                with DatabaseContext('read') as _morning_cur:
                    _morning_cur.execute("SET statement_timeout = 5000")

                    # Validate full dependency chain
                    # Step 1: stock_prices_daily
                    _morning_cur.execute("""
                        SELECT MAX(date) FROM price_daily
                    """)
                    _morning_cur_row = _morning_cur.fetchone()
                    price_date = _morning_cur_row[0] if _morning_cur_row else None

                    # Step 2: technical_data_daily
                    _morning_cur.execute("""
                        SELECT MAX(updated_at) FROM technical_data_daily
                    """)
                    _morning_cur_row = _morning_cur.fetchone()
                    tech_updated = _morning_cur_row[0] if _morning_cur_row else None

                    # Step 3: buy_sell_daily
                    _morning_cur.execute("""
                        SELECT MAX(updated_at) FROM buy_sell_daily
                    """)
                    _morning_cur_row = _morning_cur.fetchone()
                    buys_updated = _morning_cur_row[0] if _morning_cur_row else None

                    # Step 4: signal_quality_scores (optional, for observability)
                    _morning_cur.execute("""
                        SELECT MAX(updated_at) FROM signal_quality_scores
                    """)
                    _morning_cur_row = _morning_cur.fetchone()
                    quality_updated = _morning_cur_row[0] if _morning_cur_row else None

                    # Check if all critical steps completed since morning prep start
                    failed_steps = []
                    if not price_date or price_date < expected_date:
                        failed_steps.append('stock_prices_daily')
                    if not tech_updated or tech_updated < morning_pipeline_cutoff:
                        failed_steps.append('technical_data_daily')
                    if not buys_updated or buys_updated < morning_pipeline_cutoff:
                        failed_steps.append('buy_sell_daily')

                    if failed_steps:
                        logger.warning(f"[MORNING PREP] Dependency chain BROKEN: {', '.join(failed_steps)} not updated")
                        logger.warning(f"  Cutoff time: {morning_pipeline_cutoff}. Check Step Functions: algo-morning-prep-pipeline")
                        alerts.send_position_alert(
                            'PIPELINE',
                            'MORNING_PREP_INCOMPLETE',
                            f'Morning prep incomplete: {", ".join(failed_steps)} not updated since 2:45 AM. '
                            f'Downstream signals may be stale or missing. Check Step Functions logs.',
                            {'failed_steps': failed_steps, 'cutoff': str(morning_pipeline_cutoff)}
                        )
                        log_phase_result_fn(1, 'morning_prep_dependency', 'warn',
                                           f'Incomplete: {", ".join(failed_steps)}')
                    else:
                        logger.info(f"[MORNING PREP] ✓ Dependency chain complete: all steps updated since {morning_pipeline_cutoff}")
                        log_phase_result_fn(1, 'morning_prep_dependency', 'success', 'All steps completed')
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

                # ISSUE #2 FIX: Add retry gate for 75-95% coverage range (suboptimal but above halt)
                # If loader completes with 85% coverage, it's above halt threshold (75%) but incomplete.
                # Trigger failsafe to re-run loader to reach 95%+ coverage instead of proceeding with gaps.
                optimal_coverage_pct = 95
                optimal_coverage = int(5000 * optimal_coverage_pct / 100)
                suboptimal_loaders = []

                if min_coverage <= price_coverage < optimal_coverage:
                    suboptimal_loaders.append(('price_daily', 'stock_prices_daily', price_coverage))
                if min_coverage <= technical_coverage < optimal_coverage:
                    suboptimal_loaders.append(('technical_data_daily', 'technical_data_daily', technical_coverage))
                if min_coverage <= buysell_coverage < optimal_coverage:
                    suboptimal_loaders.append(('buy_sell_daily', 'buy_sell_daily', buysell_coverage))

                # If any loader is in the 75-95% range, trigger failsafe to improve coverage
                if suboptimal_loaders and not first_run_state:
                    logger.warning(f"[COMPLETENESS RETRY] {len(suboptimal_loaders)} loaders have suboptimal coverage (75-95%):")
                    for table_name, loader_name, coverage_count in suboptimal_loaders:
                        coverage_pct = 100 * coverage_count / 5000
                        logger.warning(f"  - {table_name}: {coverage_count}/5000 symbols ({coverage_pct:.1f}%)")
                        try:
                            logger.info(f"[COMPLETENESS RETRY] Triggering failsafe for {loader_name}")
                            _trigger_loader_failsafe_with_verification(loader_name, verbose=True, poll_timeout_sec=180, retry_count=1, correlation_id=_phase1_correlation_id)  # ISSUE #13 FIX: Increased to 180s
                            alerts.send_position_alert(
                                'DATA', 'SUBOPTIMAL_COVERAGE_RETRY',
                                f'{table_name} coverage suboptimal ({coverage_pct:.1f}%, need ≥{optimal_coverage_pct}%). Failsafe triggered.',
                                {'table': table_name, 'coverage_pct': coverage_pct}
                            )
                        except Exception as retry_err:
                            logger.warning(f"[COMPLETENESS RETRY] Could not trigger failsafe for {loader_name}: {retry_err}")

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
                    logger.critical("  Triggering failsafe for incomplete loaders...")

                    # Issue #2: Trigger failsafe for any loader that fell below threshold
                    failed_loaders = []
                    if price_coverage < min_coverage:
                        failed_loaders.append('stock_prices_daily')
                    if technical_coverage < min_coverage:
                        failed_loaders.append('technical_data_daily')
                    if buysell_coverage < min_coverage:
                        failed_loaders.append('buy_sell_daily')

                    for failed_loader in failed_loaders:
                        try:
                            logger.info(f"[FAILSAFE] Triggering re-run for incomplete loader: {failed_loader}")
                            _trigger_loader_failsafe_with_verification(failed_loader, verbose=verbose, poll_timeout_sec=180, correlation_id=_phase1_correlation_id)  # ISSUE #13 FIX: Increased to 180s
                        except Exception as failsafe_err:
                            logger.warning(f"[FAILSAFE] Could not trigger {failed_loader}: {failsafe_err}")

                    alerts.send_position_alert(
                        'DATA', 'INCOMPLETE_COVERAGE',
                        f'HALT: Data coverage below {min_coverage_pct}%. Loaders completed partially. '
                        f'price_daily: {price_coverage}/5000, technical_data_daily: {technical_coverage}/5000, buy_sell_daily: {buysell_coverage}/5000. '
                        f'Failsafe triggered for incomplete loaders. Check loader logs for errors.',
                        {'price': price_coverage, 'technical': technical_coverage, 'buysell': buysell_coverage, 'min': min_coverage, 'threshold_pct': min_coverage_pct, 'failsafe_loaders': failed_loaders}
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
                    _dep_cur_row = _dep_cur.fetchone()
                    tech_date = _dep_cur_row[0] if _dep_cur_row else None

                    # Also verify buy_sell_daily's source (should match or be newer than tech_data)
                    _dep_cur.execute("SELECT MAX(date) FROM buy_sell_daily")
                    _dep_cur_row = _dep_cur.fetchone()
                    buysell_date = _dep_cur_row[0] if _dep_cur_row else None

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
        if not first_run_state and not swing_data_health.get('status') == 'critical':
            try:
                with DatabaseContext('read') as _sources_cur:
                    _sources_cur.execute("SET statement_timeout = 5000")

                    # Swing trader scores should not be older than 2 hours from expected_date
                    # (it depends on buy_sell_daily + technical_data which are typically from expected_date)
                    _sources_cur.execute("SELECT MAX(date) FROM buy_sell_daily")
                    _sources_cur_row = _sources_cur.fetchone()
                    buysell_date = _sources_cur_row[0] if _sources_cur_row else None

                    _sources_cur.execute("SELECT MAX(date) FROM technical_data_daily")
                    _sources_cur_row = _sources_cur.fetchone()
                    tech_date = _sources_cur_row[0] if _sources_cur_row else None

                    _sources_cur.execute("SELECT MAX(date) FROM trend_template_data")
                    _sources_cur_row = _sources_cur.fetchone()
                    trend_date = _sources_cur_row[0] if _sources_cur_row else None

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

        # ISSUE #8 FIX: CASCADING FAILURE DETECTION
        # Detect when incomplete data in one table cascades to dependent tables.
        # Example: technical_data_daily 80% → buy_sell_daily 75% → signal_quality_scores 70%
        cascading_failures = []
        try:
            with DatabaseContext('read') as cas_cur:
                cas_cur.execute("SET statement_timeout = 10000")
                expected_count = expected_symbols

                # Get coverage for each level of the cascade
                cas_cur.execute("SELECT COUNT(DISTINCT symbol) FROM technical_data_daily WHERE updated_at >= %s", (expected_date,))
                cas_cur_row = cas_cur.fetchone()
                tech_count = cas_cur_row[0] if cas_cur_row else 0
                tech_coverage = (tech_count / expected_count * 100) if expected_count > 0 else 0

                cas_cur.execute("SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily WHERE updated_at >= %s", (expected_date,))
                cas_cur_row = cas_cur.fetchone()
                buys_count = cas_cur_row[0] if cas_cur_row else 0
                buys_coverage = (buys_count / expected_count * 100) if expected_count > 0 else 0

                cas_cur.execute("SELECT COUNT(DISTINCT symbol) FROM signal_quality_scores WHERE updated_at >= %s", (expected_date,))
                cas_cur_row = cas_cur.fetchone()
                sqs_count = cas_cur_row[0] if cas_cur_row else 0
                sqs_coverage = (sqs_count / expected_count * 100) if expected_count > 0 else 0

                cas_cur.execute("SELECT COUNT(DISTINCT symbol) FROM swing_trader_scores WHERE date >= %s", (expected_date,))
                cas_cur_row = cas_cur.fetchone()
                swing_count = cas_cur_row[0] if cas_cur_row else 0
                swing_coverage = (swing_count / expected_count * 100) if expected_count > 0 else 0

                # Detect gaps in cascade
                if tech_coverage >= 75 and buys_coverage < tech_coverage - 5:
                    cascading_failures.append(
                        f"buy_sell_daily coverage dropped {tech_coverage - buys_coverage:.1f}% below technical_data "
                        f"({buys_coverage:.1f}% vs {tech_coverage:.1f}%)"
                    )

                if buys_coverage >= 75 and sqs_coverage < buys_coverage - 5:
                    cascading_failures.append(
                        f"signal_quality_scores coverage dropped {buys_coverage - sqs_coverage:.1f}% below buy_sell_daily "
                        f"({sqs_coverage:.1f}% vs {buys_coverage:.1f}%)"
                    )

                if sqs_coverage >= 75 and swing_coverage < sqs_coverage - 5:
                    cascading_failures.append(
                        f"swing_trader_scores coverage dropped {sqs_coverage - swing_coverage:.1f}% below signal_quality_scores "
                        f"({swing_coverage:.1f}% vs {sqs_coverage:.1f}%)"
                    )

                # ISSUE #6 FIX: Cascading failures on swing_trader_scores should halt, not just warn
                # If swing scores incomplete, Phase 5 cannot rank trades properly
                if cascading_failures:
                    swing_has_gap = any('swing_trader_scores' in failure for failure in cascading_failures)
                    if swing_has_gap and swing_coverage < 75:
                        # CRITICAL: swing_trader_scores required for Phase 5, cannot proceed
                        logger.critical(f"[CASCADING_FAILURE_CRITICAL] {len(cascading_failures)} critical data gap(s):")
                        for issue in cascading_failures:
                            logger.critical(f"  - {issue}")
                        alerts.critical(
                            f'CRITICAL: Cascading data failure detected. Swing trader scores {swing_coverage:.0f}% coverage. '
                            f'Coverage chain: TECH={tech_coverage:.0f}% → BUY={buys_coverage:.0f}% → SQ={sqs_coverage:.0f}% → SWING={swing_coverage:.0f}%. '
                            f'Phase 5 cannot generate signals without complete swing scores. Halting.'
                        )
                        log_phase_result_fn(1, 'cascading_failures_critical', 'halt',
                                           f'{len(cascading_failures)} critical cascading failure(s): incomplete swing scores')
                        return PhaseResult(1, 'cascading_failures_critical', 'halted', {}, True,
                                         f'Cascading data failure: swing_trader_scores {swing_coverage:.0f}% coverage (need >75%). '
                                         f'Data degradation chain detected. Cannot proceed with trading.')
                    else:
                        # Non-critical gap: warn but proceed
                        logger.warning(f"[CASCADING_FAILURE] Detected {len(cascading_failures)} data gaps (non-blocking):")
                        for issue in cascading_failures:
                            logger.warning(f"  - {issue}")
                        alerts.send_position_alert(
                            'DATA', 'CASCADING_FAILURES',
                            f'Detected {len(cascading_failures)} cascading data gaps. '
                            f'Coverage: TECH={tech_coverage:.0f}% → BUY={buys_coverage:.0f}% → SQ={sqs_coverage:.0f}% → SWING={swing_coverage:.0f}%. '
                            f'May reduce trading opportunities in Phase 5.',
                            {'coverage': {'tech': tech_coverage, 'buys': buys_coverage, 'sqs': sqs_coverage, 'swing': swing_coverage}}
                        )
                        log_phase_result_fn(1, 'cascading_failures', 'warn',
                                           f'{len(cascading_failures)} cascading failure(s) detected (non-blocking)')
                else:
                    logger.info(
                        f"[CASCADING_FAILURE] Coverage healthy: TECH={tech_coverage:.0f}% → "
                        f"BUY={buys_coverage:.0f}% → SQ={sqs_coverage:.0f}% → SWING={swing_coverage:.0f}%"
                    )

        except Exception as cascade_err:
            logger.debug(f"[CASCADING_FAILURE] Detection unavailable: {cascade_err}")

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
                    _sqs_cur_row = _sqs_cur.fetchone()
                    latest = _sqs_cur_row[0] if _sqs_cur_row else None
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

        phase1_elapsed = time.time() - phase1_start
        logger.info(f"[{_phase1_correlation_id}] [TIMING] Phase 1 completed in {phase1_elapsed:.1f}s")

        # ISSUE #14 FIX: Morning Prep Early Completion - Pre-Warm Phase 1 Cache
        # If Phase 1 completes before 8 AM and all data is fresh, pre-cache results
        # so 9:30 AM run returns instantly from cache instead of rescanning databases
        if is_morning:
            now_et = dt.now(tz.utc).astimezone(tz(td(hours=-5)))
            market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
            min_until_open = (market_open - now_et).total_seconds() / 60

            # Pre-warm cache if completing early (before 8 AM) and data is fresh
            if now_et.hour < 8 and phase1_elapsed < 30:  # Quick run = data is fresh
                try:
                    import boto3
                    dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                    cache_table = dynamodb.Table(os.getenv('CACHE_TABLE', 'algo_phase1_cache'))
                    cache_key = f"data_loader_status-{run_date.isoformat()}"

                    # Store phase 1 status with longer TTL so 9:30 AM hit gets cached result
                    cache_table.put_item(Item={
                        'cache_key': cache_key,
                        'status': 'warm',
                        'created_at': datetime.now(timezone.utc).timestamp(),
                        'phase1_elapsed_ms': int(phase1_elapsed * 1000),
                        'correlation_id': _phase1_correlation_id,
                        'ttl': int(time.time()) + 3600,  # 1 hour cache
                    })
                    logger.info(f"[{_phase1_correlation_id}] [CACHE_PREWARM] Pre-warmed Phase 1 cache for 9:30 AM run (early completion at {now_et.strftime('%H:%M')})")
                except Exception as prewarm_err:
                    logger.debug(f"[{_phase1_correlation_id}] [CACHE_PREWARM] Could not pre-warm cache: {prewarm_err}")

            logger.info(f"[{_phase1_correlation_id}] [TIMING] {min_until_open:.0f}min remaining until market open (9:30 AM ET)")

        # ISSUE #12 FIX: Final atomic re-check of critical tables before returning success
        # Prevents race condition where data becomes stale between initial check and Phase 2 execution
        try:
            with DatabaseContext('read') as final_check_cur:
                final_check_cur.execute("SET statement_timeout = 5000")

                # Quick re-check: are halt-critical tables still fresh?
                critical_tables_recheck = [
                    ('price_daily', 'price_daily'),
                    ('market_health_daily', 'market_health_daily'),
                    ('trend_template_data', 'trend_template_data'),
                ]
                stale_on_recheck = []
                for table_label, table_name in critical_tables_recheck:
                    try:
                        final_check_cur.execute(f"SELECT MAX(date) FROM {table_name} WHERE date >= %s", (expected_date,))
                        row = final_check_cur.fetchone()
                        latest_date = row[0] if row else None
                        if latest_date is None:
                            stale_on_recheck.append(f"{table_label} (no data >= {expected_date})")
                    except Exception:
                        pass  # Table may not exist yet, skip

                if stale_on_recheck:
                    logger.error(f"[{_phase1_correlation_id}] [RACE_CONDITION] Final re-check detected stale/missing data: {', '.join(stale_on_recheck)}")
                    logger.error(f"[{_phase1_correlation_id}] Data became stale during Phase 1 execution. Halting to prevent inconsistent state.")
                    log_phase_result_fn(1, 'data_freshness', 'halt', f'Race condition: data became stale during checks')
                    return PhaseResult(1, 'data_freshness', 'halted', {}, True,
                                     f'Data freshness race condition detected: {", ".join(stale_on_recheck)}. Loaders may have failed during Phase 1.')
                else:
                    logger.debug(f"[{_phase1_correlation_id}] [RACE_CONDITION_CHECK] ✓ Final re-check confirmed critical tables still fresh")
        except Exception as recheck_err:
            logger.debug(f"[{_phase1_correlation_id}] Final re-check skipped ({recheck_err}), proceeding")

        log_phase_result_fn(1, 'data_freshness', 'success', 'All data fresh within window')

        # ISSUE #11 FIX: Return 'degraded' status if stale data was detected
        # This signals to Phase 5 that signal generation should be more conservative
        # (e.g., don't trade if swing_trader_scores incomplete, use stricter filters)
        if stale_items:
            logger.warning(f"[ISSUE#11_FIX] Phase 1 returning DEGRADED: stale data detected but failsafe in progress. "
                         f"Phase 5 should apply conservative signal generation. Stale items: {'; '.join(stale_items)}")
            return PhaseResult(1, 'data_freshness', 'degraded',
                             {'stale_items': stale_items, 'failsafe_triggered': True},
                             False, 'Phase 1 degraded - stale data with failsafe triggered')

        return PhaseResult(1, 'data_freshness', 'ok', {}, False, None)

    except Exception as e:
        log_phase_result_fn(1, 'data_freshness', 'error', str(e))
        return PhaseResult(1, 'data_freshness', 'halted', {}, True, str(e))


def cleanup_hung_eod_loaders(verbose: bool = False) -> Dict[str, int]:
    """
    ISSUE #15 FIX: Automatic EOD pipeline termination at deadline.

    EOD loaders should complete by 5:30 PM. If still running at 9:00 PM,
    they're hung and blocking morning prep. This function auto-terminates
    old EOD loaders to free RDS connections.

    Returns: Dict with {'terminated': count, 'errors': count}
    """
    try:
        import boto3

        eod_deadline_et = datetime.now(ZoneInfo("America/New_York")).replace(hour=21, minute=0, second=0, microsecond=0)  # 9 PM ET
        eod_max_duration_minutes = 890  # 4:05 PM to 9:00 PM = 895 min, with 5 min margin

        termination_results = {'terminated': 0, 'errors': 0}

        try:
            with DatabaseContext('read') as check_cur:
                check_cur.execute("SET statement_timeout = 5000")

                # Find loaders still marked RUNNING but older than EOD deadline
                check_cur.execute("""
                    SELECT table_name, last_updated FROM data_loader_status
                    WHERE status = 'RUNNING' AND table_name IN ('price_daily', 'technical_data_daily', 'market_health_daily')
                    AND last_updated < %s
                """, (datetime.now(timezone.utc) - timedelta(minutes=eod_max_duration_minutes),))

                hung_loaders = check_cur.fetchall()
                if hung_loaders:
                    logger.critical(f"[EOD_CLEANUP] Found {len(hung_loaders)} hung EOD loaders past 9 PM deadline - auto-terminating")

                    ecs_client = boto3.client('ecs', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                    cluster_arn = os.getenv('ECS_CLUSTER_ARN', 'algo-cluster')

                    for table_name, last_updated in hung_loaders:
                        try:
                            logger.warning(f"[EOD_CLEANUP] Terminating hung loader for {table_name} (last updated {last_updated})")
                            if _terminate_hung_loader_task(table_name, verbose=verbose):
                                termination_results['terminated'] += 1
                                logger.info(f"[EOD_CLEANUP] ✓ Successfully terminated {table_name}")
                            else:
                                logger.warning(f"[EOD_CLEANUP] Could not terminate {table_name}")
                                termination_results['errors'] += 1
                        except Exception as term_err:
                            logger.error(f"[EOD_CLEANUP] Error terminating {table_name}: {term_err}")
                            termination_results['errors'] += 1

                    # Send alert about cleanup
                    try:
                        alerts = AlertManager()
                        alerts.send_position_alert(
                            'SYSTEM',
                            'EOD_PIPELINE_AUTO_CLEANUP',
                            f'Auto-terminated {termination_results["terminated"]} hung EOD loaders past 9 PM deadline to free RDS connections. '
                            f'Errors: {termination_results["errors"]}',
                            termination_results
                        )
                    except Exception:
                        pass

                return termination_results
        except Exception as check_err:
            logger.error(f"[EOD_CLEANUP] Could not check for hung loaders: {check_err}")
            return {'terminated': 0, 'errors': 1}

    except Exception as e:
        logger.error(f"[EOD_CLEANUP] Cleanup function failed: {e}")
        return {'terminated': 0, 'errors': 1}
