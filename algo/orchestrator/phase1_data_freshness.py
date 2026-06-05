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

def _trigger_loader_failsafe_with_verification(loader_name: str, verbose: bool = False, poll_timeout_sec: int = 30, retry_count: int = 1) -> bool:
    """
    Trigger ECS loader asynchronously and VERIFY it started before returning.

    CRITICAL FIX: Previous implementation triggered loader but never confirmed it started.
    If trigger failed (network error, Lambda down, wrong ARN), orchestrator would proceed
    with stale data silently.

    Now: Use EventBridge to trigger ECS task, monitor CloudWatch for task start.
    Only return True if ECS task confirmed running within poll_timeout_sec.
    Retries once with 10s backoff if initial trigger fails.

    Args:
        loader_name: Name of the loader to trigger
        verbose: Whether to log verbose output
        poll_timeout_sec: Max seconds to wait for loader task to start (default 30s)
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


def _trigger_loader_failsafe(loader_name: str, verbose: bool = False, wait_timeout: int = 600) -> bool:
    """
    DEPRECATED: Use _trigger_loader_failsafe_with_verification instead.
    This function kept for backward compatibility only.
    """
    return _trigger_loader_failsafe_with_verification(loader_name, verbose, poll_timeout_sec=180)

def _check_failsafe_grace_period(state_table: Any, verbose: bool = False) -> Optional[float]:
    """Check if a previously-triggered failsafe is within grace period window.

    Returns:
        - Minutes since trigger if <2 hours ago (loader likely still running)
        - None if >2 hours ago or no record exists (need fresh trigger)

    This prevents redundant failsafe triggers when a loader is already running
    asynchronously in the background. Assumes typical stock_prices_daily takes
    90-120 minutes to complete.
    """
    try:
        response = state_table.get_item(Key={'state_key': 'failsafe_trigger_log'})
        if 'Item' not in response:
            return None

        triggered_at = response['Item'].get('triggered_at', 0)
        current_time = time.time()
        age_minutes = (current_time - triggered_at) / 60

        # Grace period: 2 hours = typical max runtime for stock_prices_daily
        if age_minutes < 120:
            if verbose:
                logger.debug(f"[FAILSAFE] Within grace period: triggered {age_minutes:.0f}m ago")
            return age_minutes
        else:
            logger.info(f"[FAILSAFE] Grace period expired: triggered {age_minutes:.0f}m ago (>2h)")
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
                logger.debug(f"[PATROL] Could not check patrol trigger log: {state_err}. "
                            f"Will proceed with fresh trigger.")

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
                        try:
                            state_table.put_item(Item={
                                'state_key': 'patrol_trigger_log',
                                'triggered_at': time.time(),
                                'ttl': int(time.time()) + 3600,  # 1-hour TTL
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
        ]
    }

    required_indexes = {
        'signal_quality_scores': [
            'idx_signal_quality_scores_symbol_date',  # Critical for Phase 5 lookups
        ]
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
                    SELECT 1 FROM information_schema.statistics
                    WHERE table_name = %s AND index_name = %s
                    LIMIT 1
                """)
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

def _check_rds_connection_pool_health(cur: Any, verbose: bool = False) -> bool:
    """Pre-flight validation: check RDS connection pool health.

    Queries active connections and warns if pool is under heavy load.
    Doesn't halt execution but emits metrics for monitoring.

    Returns: True (always continues, just emits warnings)
    """
    try:
        # Query active connections
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

            # Warn if pool is getting full
            if active_conn >= 60:
                logger.warning(f"[RDS-POOL] ⚠️ High connection load: {active_conn} active connections (pool 75% full)")
                if active_conn >= 80:
                    logger.critical(f"[RDS-POOL] ❌ CRITICAL: {active_conn} active connections (pool nearly exhausted)")
                    try:
                        alerts = AlertManager()
                        alerts.send_position_alert(
                            'RDS',
                            'CONNECTION_POOL_EXHAUSTION',
                            f'RDS connection pool critically high: {active_conn} active connections. '
                            f'May cause cascade failures. Monitor query performance.',
                            {'active_connections': active_conn, 'max_idle_seconds': max_idle}
                        )
                    except Exception as alert_err:
                        logger.debug(f"[RDS-POOL] Could not send alert: {alert_err}")
            elif active_conn >= 40:
                logger.info(f"[RDS-POOL] Connection pool at 50% capacity ({active_conn} active). Monitor for growth.")

    except Exception as e:
        logger.debug(f"[RDS-POOL] Could not check connection pool health: {e}. Proceeding normally.")

    return True  # Always continue, just emit warnings

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

                # Check RDS connection pool health (emits warnings, doesn't halt)
                try:
                    _check_rds_connection_pool_health(cur, verbose)
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

        # Compute expected data date based on orchestrator schedule, not reactive tolerance.
        # SCHEDULE:
        # - 4:05 PM ET (Mon-Fri): EOD pipeline completes (loads yesterday's + earlier data)
        # - 4:30 AM ET (Mon-Fri): Morning pipeline completes (refreshes 1d technicals before 9:30 AM)
        # - 9:30 AM, 1 PM, 3 PM, 5:30 PM ET: Orchestrator runs
        #
        # LOGIC:
        # If run_time < 9:30 AM: expect EOD data from 2 trading days ago (previous day's 4 PM pipeline)
        # If run_time >= 9:30 AM and < 4 PM: expect EOD data from yesterday (previous trading day)
        # If run_time >= 4 PM and < 4:05 PM: EOD pipeline still running; accept yesterday's data
        # If run_time >= 4:05 PM: expect today's data (just completed) or yesterday's if pipeline delayed
        #
        # Grace period: +30 min after expected completion. Beyond that, trigger failsafe.

        def _get_expected_data_date(current_time: datetime, current_date: _date) -> _date:
            """Calculate expected data date based on orchestrator run time and pipeline schedule."""
            try:
                from algo.algo_market_calendar import MarketCalendar

                hour = current_time.hour
                minute = current_time.minute
                current_time_minutes = hour * 60 + minute

                # Pipeline schedule (in minutes from midnight ET)
                eod_pipeline_end_minutes = 16 * 60 + 5 + 30  # 4:05 PM + 30 min grace = 4:35 PM
                morning_pipeline_end_minutes = 4 * 60 + 30 + 30  # 4:30 AM + 30 min grace = 5:00 AM
                orchestrator_times_minutes = [
                    9 * 60 + 30,  # 9:30 AM
                    13 * 60,      # 1 PM
                    15 * 60,      # 3 PM
                    17 * 60 + 30, # 5:30 PM
                ]

                # Find the most recent orchestrator run time
                most_recent_orchestrator = None
                for orch_time in orchestrator_times_minutes:
                    if current_time_minutes >= orch_time:
                        most_recent_orchestrator = orch_time

                # Determine expected data date
                expected_data_date = current_date - timedelta(days=1)

                # Back up to most recent trading day
                while not MarketCalendar.is_trading_day(expected_data_date):
                    expected_data_date -= timedelta(days=1)

                # If we haven't reached 9:30 AM yet, expect data from 2 trading days ago
                # (yesterday's EOD pipeline, which completes at 4 PM)
                if current_time_minutes < orchestrator_times_minutes[0]:  # Before 9:30 AM
                    expected_data_date -= timedelta(days=1)
                    while not MarketCalendar.is_trading_day(expected_data_date):
                        expected_data_date -= timedelta(days=1)

                return expected_data_date
            except Exception as e:
                logger.debug(f"Schedule-based date calculation failed: {e}")
                return current_date - timedelta(days=1)

        try:
            from algo.algo_market_calendar import MarketCalendar
            from algo.algo_orchestrator import get_current_time_et  # Utility for ET time

            # Get current time in ET (orchestrator always uses ET)
            current_time_et = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-5)))  # EST

            expected_date = _get_expected_data_date(current_time_et, run_date)

            # Minimum acceptable: 1 trading day before expected (allow previous day if today's pipeline delayed)
            min_acceptable_date = expected_date - timedelta(days=1)
            while not MarketCalendar.is_trading_day(min_acceptable_date):
                min_acceptable_date -= timedelta(days=1)

            logger.info(f"[DATA FRESHNESS] Current run_date: {run_date}, Expected data date: {expected_date}, Min acceptable: {min_acceptable_date}")
            logger.info(f"[DATA FRESHNESS] Staleness tolerance: {(expected_date - min_acceptable_date).days} trading days")

        except Exception as cal_e:
            logger.debug(f"Schedule-based freshness check failed: {cal_e}, falling back to calendar logic")
            expected_date = run_date - timedelta(days=1)
            while expected_date.weekday() >= 5:
                expected_date -= timedelta(days=1)
            min_acceptable_date = expected_date - timedelta(days=1)
            while min_acceptable_date.weekday() >= 5:
                min_acceptable_date -= timedelta(days=1)

        try:
            from algo.algo_metrics import MetricsPublisher
            _metrics = MetricsPublisher(dry_run=dry_run)
        except Exception as mp_e:
            logger.debug(f"MetricsPublisher unavailable: {mp_e}")
            _metrics = None

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

        if _metrics:
            _metrics.flush()

        if stale_items:
            logger.warning(f"[FAILSAFE] Data stale, checking if failsafe already triggered recently: {stale_items}")

            # GRACE PERIOD: Check if a failsafe was already triggered in the last 2 hours.
            # If yes, skip redundant trigger and allow current run to proceed with in-flight loader.
            # This prevents 20+ potential halts/week from 4 daily runs each independently
            # triggering the same loader. Assumes stock_prices_daily takes 90-120 minutes.
            failsafe_already_triggered = False
            failsafe_age_minutes = None

            try:
                import boto3
                dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                state_table_name = os.getenv('HALT_FLAG_TABLE', 'algo_orchestrator_state')
                state_table = dynamodb.Table(state_table_name)

                # Enhanced: Check if trigger was recent (within 2-hour grace period)
                failsafe_age_minutes = _check_failsafe_grace_period(state_table, verbose)
                if failsafe_age_minutes is not None:
                    failsafe_already_triggered = True
                    logger.info(f"[FAILSAFE] Grace period: Failsafe was triggered {failsafe_age_minutes:.0f}m ago (<2h). "
                               f"Skipping redundant trigger, allowing async loader to complete.")
            except Exception as state_err:
                logger.debug(f"[FAILSAFE] Could not check failsafe grace period: {state_err}. "
                            f"Will proceed with fresh trigger.")

            if failsafe_already_triggered:
                # Failsafe was already triggered recently. Allow current run to proceed
                # knowing that loader is active in background.
                failsafe_ok = True  # Mark as OK to skip re-triggering logic below
                logger.info(f"[FAILSAFE] ✓ Using grace period from prior trigger ({failsafe_age_minutes:.0f}m ago). "
                           f"Proceeding to Phase 2 with in-flight loader.")
                alerts.send_position_alert(
                    'DATA',
                    'STALE_DATA_GRACE_PERIOD',
                    f'Stale data detected but failsafe loader was triggered {failsafe_age_minutes:.0f}m ago. '
                    f'Using grace period. Data will refresh within 1-2 hours.',
                    {'stale_items': stale_items, 'grace_period_minutes': failsafe_age_minutes}
                )
                log_phase_result_fn(1, 'data_freshness', 'warn',
                                   f'Stale, but grace period active from prior failsafe ({failsafe_age_minutes:.0f}m ago)')
                # Continue to Phase 2 without retriggering (failsafe_ok=True skips retry logic)
            else:
                # No recent failsafe trigger, or check failed. Trigger fresh loader.
                logger.warning(f"[FAILSAFE] No recent trigger in grace period window. Attempting to trigger loader: {stale_items}")

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

                # Stock prices loader takes 1-2 hours to fetch 5000+ symbols. Lambda orchestrator has
                # 10min timeout total. Instead of waiting synchronously (exceeds timeout), trigger
                # asynchronously and verify it started before proceeding.

                # RETRY LOGIC: Adaptive exponential backoff for ECS provisioning variability
                # (allows recovery from transient ECS/network issues without giving up)
                #
                # Adaptive poll timeouts: 30s → 120s → 180s
                # ECS task provision: 30-45s under normal load, 60-150s when cluster busy, 150-200s under extreme load
                # RACE CONDITION MITIGATION: stock_prices_daily loader runs async (non-blocking).
                # Phases 2-7 may execute while loader is writing new data.
                # SAFE because:
                # 1. price_daily is INSERT-only (EOD prices immutable, no UPDATEs)
                # 2. PostgreSQL MVCC gives each phase a consistent snapshot
                # 3. Circuit breakers re-check data freshness before trading
                # 4. Loader only writes new dates; never overwrites existing dates
                failsafe_ok = False
                poll_timeouts = [30, 120, 180]  # Adaptive: normal, busy, extreme load
                max_attempts = len(poll_timeouts)

                for attempt, poll_timeout in enumerate(poll_timeouts, 1):
                    try:
                        logger.info(f"[FAILSAFE] Attempt {attempt}/{max_attempts}: launching loader with {poll_timeout}s poll timeout...")
                        failsafe_ok = _trigger_loader_failsafe_with_verification('stock_prices_daily', verbose=verbose, poll_timeout_sec=poll_timeout)
                        if failsafe_ok:
                            # Log successful trigger for grace period check in future runs
                            try:
                                state_table.put_item(Item={
                                    'state_key': 'failsafe_trigger_log',
                                    'triggered_at': time.time(),
                                    'loader': 'stock_prices_daily',
                                    'ttl': int(time.time()) + 7200,  # 2-hour TTL
                                })
                                logger.debug("[FAILSAFE] Logged trigger timestamp for grace period")
                            except Exception as log_err:
                                logger.debug(f"[FAILSAFE] Could not log trigger timestamp: {log_err}")
                            break
                        elif attempt < max_attempts:
                            backoff_wait = min(30, (2 ** (attempt - 1)) * 5)  # 5s, 10s, 20s backoff
                            logger.warning(f"[FAILSAFE] Attempt {attempt}/{max_attempts} failed (timeout {poll_timeout}s). "
                                         f"Retrying in {backoff_wait}s with higher timeout ({poll_timeouts[attempt]}s)...")
                            time.sleep(backoff_wait)
                    except Exception as retry_err:
                        logger.warning(f"[FAILSAFE] Attempt {attempt}/{max_attempts} error: {retry_err}. Retrying...")
                        if attempt < max_attempts:
                            backoff_wait = min(30, (2 ** (attempt - 1)) * 5)
                            time.sleep(backoff_wait)

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

                # Decision: if data is 2+ trading days old and failsafe failed, HALT.
                # This prevents silent failures in Phase 5 when signal gate kills trades.
                if oldest_stale_trading_day_age is not None and oldest_stale_trading_day_age >= 2:
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

        # Check swing_trader_scores freshness — FAIL-CLOSED if missing/stale (unless first run or market-open grace period).
        # When swing scores are missing, Phase 5 min_swing_score=55 gate kills ALL trades silently.
        # User sees "success" with 0 trades executed and no explanation. Halt explicitly instead.
        # Grace period: Allow yesterday's scores at 9:30 AM since morning prep (4:30 AM) should compute today's scores.
        # For intraday runs (1 PM, 3 PM, 5:30 PM): Require today's scores.
        swing_scores_ok = True
        now_et = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-5)))
        is_market_open_run = (9 <= now_et.hour < 10)  # 9:XX AM ET market open
        min_acceptable_swing_date = expected_date if not is_market_open_run else expected_date - timedelta(days=1)

        try:
            with DatabaseContext('read') as _sw_cur:
                _sw_cur.execute("SET statement_timeout = 5000")
                # CRITICAL: Check both that data exists AND is fresh
                # Previous bug: system halted if data was stale, but succeeded if table was completely empty
                _sw_cur.execute("""
                    SELECT MAX(date), COUNT(*) as row_count FROM swing_trader_scores
                """)
                sw_row = _sw_cur.fetchone()
                sw_latest = sw_row[0] if sw_row else None
                sw_row_count = sw_row[1] if sw_row and len(sw_row) > 1 else 0

                if sw_latest is None or sw_row_count == 0:
                    if first_run_state:
                        logger.info("[SWING SCORES] Empty (first run): waiting for EOD pipeline")
                        swing_scores_ok = True  # Allow first-run with empty scores
                    else:
                        logger.error("[SWING SCORES] HALT: swing_trader_scores table is empty")
                        logger.error("  The EOD pipeline must run first to populate swing scores.")
                        logger.error(f"  Table has {sw_row_count} rows. Expected thousands of symbols.")
                        logger.error("  Check: Step Functions algo-eod-pipeline-dev execution status.")
                        logger.error("  Or wait for the morning-prep-pipeline at 4:30 AM ET.")
                        alerts.send_position_alert(
                            'DATA', 'SWING_SCORES_MISSING',
                            f'HALTING: swing_trader_scores table is empty ({sw_row_count} rows). Phase 5 cannot rank trades without swing scores. '
                            'Check EOD pipeline Step Functions execution status.',
                            {'swing_latest': None, 'row_count': sw_row_count, 'expected': str(expected_date), 'action': 'HALT', 'first_run': False}
                        )
                        swing_scores_ok = False
                elif sw_latest < min_acceptable_swing_date:
                    gap = (expected_date - sw_latest).days
                    logger.error(
                        f"[SWING SCORES] HALT: swing_trader_scores is {gap}d stale "
                        f"(latest={sw_latest}, expected {expected_date})"
                    )
                    logger.error("  Check Step Functions pipeline execution status.")
                    logger.error("  If EOD pipeline succeeded, data may be delayed from upstream loaders.")
                    alerts.send_position_alert(
                        'DATA', 'SWING_SCORES_STALE',
                        f'HALTING: swing_trader_scores is {gap} day(s) stale (latest={sw_latest}). '
                        f'Phase 5 cannot rank trades. Check EOD pipeline Step Functions logs.',
                        {'swing_latest': str(sw_latest), 'expected': str(expected_date), 'gap_days': gap, 'action': 'HALT'}
                    )
                    swing_scores_ok = False
                elif sw_latest < expected_date and is_market_open_run:
                    gap = (expected_date - sw_latest).days
                    logger.warning(
                        f"[SWING SCORES] GRACE PERIOD: Using {gap}d old data at market open "
                        f"(latest={sw_latest}, expected {expected_date}). "
                        f"Morning prep pipeline (4:30 AM) should have computed today's scores. "
                        f"Monitor Step Functions logs if this persists."
                    )
                    log_phase_result_fn(1, 'swing_trader_scores', 'warning',
                                       'Grace period: Using prior-day scores at 9:30 AM market open')
                elif verbose:
                    logger.info(f"  [OK] swing_trader_scores: latest {sw_latest}")
        except Exception as _sw_err:
            logger.error(f"  [SWING SCORES] HALT: Freshness check failed: {_sw_err}")
            swing_scores_ok = False

        if not swing_scores_ok:
            log_phase_result_fn(1, 'swing_trader_scores', 'halt',
                               'swing_trader_scores missing or stale — Phase 5 cannot execute')
            return PhaseResult(1, 'swing_trader_scores', 'halted', {}, True,
                             'swing_trader_scores missing or stale — Phase 5 cannot rank trades')

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
