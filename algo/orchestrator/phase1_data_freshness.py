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

def _trigger_loader_failsafe_with_verification(loader_name: str, verbose: bool = False, poll_timeout_sec: int = 30) -> bool:
    """
    Trigger ECS loader asynchronously and VERIFY it started before returning.

    CRITICAL FIX: Previous implementation triggered loader but never confirmed it started.
    If trigger failed (network error, Lambda down, wrong ARN), orchestrator would proceed
    with stale data silently.

    Now: Use EventBridge to trigger ECS task, monitor CloudWatch for task start.
    Only return True if ECS task confirmed running within poll_timeout_sec.

    Args:
        loader_name: Name of the loader to trigger
        verbose: Whether to log verbose output
        poll_timeout_sec: Max seconds to wait for loader task to start (default 30s)

    Returns: True if loader task confirmed running, False if timeout/error
    """
    try:
        import boto3

        # Map loader names to ECS task definitions
        task_defs = {
            'stock_prices_daily': 'algo-load-prices-daily',
            'technical_data_daily': 'algo-load-technicals',
            'market_health_daily': 'algo-load-market-health',
        }

        task_def = task_defs.get(loader_name)
        if not task_def:
            logger.warning(f"[FAILSAFE] Unknown loader '{loader_name}', cannot trigger")
            return False

        # Step 1: Trigger ECS task via RunTask (synchronous API)
        ecs_client = boto3.client('ecs', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        cluster_arn = os.getenv('ECS_CLUSTER_ARN', 'algo-cluster')

        if verbose:
            logger.info(f"[FAILSAFE] Launching ECS task {task_def} on cluster {cluster_arn}...")

        try:
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
                            'name': task_def.replace('algo-load-', '').replace('-', '_'),
                            'environment': [
                                {'name': 'FAILSAFE_TRIGGER', 'value': 'true'},
                                {'name': 'TRIGGER_TIME', 'value': datetime.now(timezone.utc).isoformat()},
                            ]
                        }
                    ]
                }
            )

            if not response.get('tasks'):
                logger.warning(f"[FAILSAFE] ECS RunTask returned no tasks")
                return False

            task_arn = response['tasks'][0]['taskArn']
            task_id = task_arn.split('/')[-1]

            if verbose:
                logger.info(f"[FAILSAFE] ✓ ECS task launched: {task_id}")

            # Step 2: Poll CloudWatch Container Insights for task to reach RUNNING state
            # Task states: PROVISIONING → PENDING → ACTIVATING → RUNNING
            cloudwatch = boto3.client('cloudwatch', region_name=os.getenv('AWS_REGION', 'us-east-1'))
            poll_start = time.time()
            poll_interval = 1.0  # Check every 1 second

            # Query CloudWatch Logs for task state transitions
            logs_client = boto3.client('logs', region_name=os.getenv('AWS_REGION', 'us-east-1'))

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

                            return True
                        elif task_state in ('DEPROVISIONING', 'STOPPING', 'DEACTIVATING', 'STOPPED', 'DELETED'):
                            logger.warning(f"[FAILSAFE] Task {task_id} stopped prematurely: {task_state}")
                            if task.get('stoppedReason'):
                                logger.warning(f"  Reason: {task['stoppedReason']}")
                            return False

                except Exception as desc_err:
                    logger.debug(f"[FAILSAFE] DescribeTasks failed: {desc_err}")

                time.sleep(poll_interval)

            logger.warning(f"[FAILSAFE] Task {task_id} did not reach RUNNING state within {poll_timeout_sec}s. "
                         "Check ECS task definition and CloudWatch logs.")
            return False

        except Exception as ecs_err:
            logger.error(f"[FAILSAFE] ECS RunTask failed: {ecs_err}")
            return False

    except Exception as e:
        logger.error(f"[FAILSAFE] Unexpected error in loader trigger: {e}")
        return False


def _trigger_loader_failsafe(loader_name: str, verbose: bool = False, wait_timeout: int = 600) -> bool:
    """
    DEPRECATED: Use _trigger_loader_failsafe_with_verification instead.
    This function kept for backward compatibility only.
    """
    return _trigger_loader_failsafe_with_verification(loader_name, verbose, poll_timeout_sec=30)

def _check_data_patrol(cur: Any, run_date: _date, verbose: bool, log_phase_result_fn: Callable) -> bool:
    """Check data patrol results. Fail-closed if critical/error findings.

    Only checks the LATEST patrol run (not accumulated from all runs in 24h).
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
                logger.info("No patrol data available")
            return True

        latest_run_id, latest_run_at = latest_run

        # Skip stale patrol findings — if the latest patrol ran before the previous
        # trading day, its findings are not representative of current data quality.
        try:
            from algo.algo_market_calendar import MarketCalendar
            expected_patrol_date = run_date - timedelta(days=1)
            for _ in range(10):
                if MarketCalendar.is_trading_day(expected_patrol_date):
                    break
                expected_patrol_date -= timedelta(days=1)
        except Exception as cal_e:
            logger.debug(f"MarketCalendar check failed, falling back to weekday check: {cal_e}")
            expected_patrol_date = run_date - timedelta(days=1)
            while expected_patrol_date.weekday() >= 5:
                expected_patrol_date -= timedelta(days=1)

        patrol_date = latest_run_at.date() if hasattr(latest_run_at, 'date') else run_date
        if patrol_date < expected_patrol_date:
            logger.warning(
                f"[PATROL] Latest patrol ({latest_run_id}, {patrol_date}) older than "
                f"expected ({expected_patrol_date}) — triggering fresh patrol"
            )
            # Trigger fresh patrol asynchronously so Phase 1 doesn't block
            try:
                import boto3
                ecs_client = boto3.client('ecs', region_name=os.getenv('AWS_REGION', 'us-east-1'))
                cluster_arn = os.getenv('ECS_CLUSTER_ARN', 'algo-cluster')
                logger.info("[PATROL] Triggering fresh data patrol via ECS...")
                ecs_client.run_task(
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
                logger.info("[PATROL] ✓ Fresh patrol task triggered async")
            except Exception as patrol_trigger_err:
                logger.warning(f"[PATROL] Could not trigger fresh patrol: {patrol_trigger_err}")

            return True  # Stale patrol: don't block on old findings, but fresh patrol now running

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

        # FAIL-CLOSED: critical findings always block
        if critical_count > 0:
            logger.info(f"[HALT] Data patrol found {critical_count} CRITICAL issues - BLOCKING ORCHESTRATOR")
            if verbose:
                logger.info(f"  [HALT] Data patrol found {critical_count} CRITICAL issues")
            log_phase_result_fn(1, 'data_patrol', 'halt',
                               f'Critical data quality issues: {critical_count} critical findings')
            return False

        # FAIL-CLOSED: too many errors block in auto mode
        if error_count > 2:
            if verbose:
                logger.error(f"  [HALT] Data patrol found {error_count} ERROR issues")
            log_phase_result_fn(1, 'data_patrol', 'halt',
                               f'Data quality errors: {error_count} findings')
            return False

        # Warnings are just logged, not blocking
        if error_count == 1 or error_count == 2:
            if verbose:
                logger.error(f"  [WARN] Data patrol found {error_count} error(s)")

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

        # Run ANALYZE on key tables to refresh PostgreSQL statistics. Stale statistics
        # cause the query planner to choose sequential scans instead of index scans,
        # making all downstream queries 30-100× slower. ANALYZE samples ~30k rows per
        # column but can take longer on large tables under concurrent load.
        try:
            with DatabaseContext('write') as cur:
                cur.execute("SET statement_timeout = 30000")  # 30s — allow time for large tables under load
                cur.execute(
                    "ANALYZE price_daily, market_health_daily, trend_template_data, "
                    "technical_data_daily, buy_sell_daily, data_loader_status"
                )
                logger.info("Phase 1: ANALYZE complete — PostgreSQL statistics refreshed")
        except Exception as e:
            logger.warning(f"Phase 1: ANALYZE failed ({e}) — proceeding with stale stats")

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

            logger.info(f"[DATA FRESHNESS] Expected date: {expected_date}, Min acceptable: {min_acceptable_date}")

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
                age = (run_date - d).days
                if _metrics:
                    _metrics.put_data_freshness(table_keys[name], age)
                is_stale = d < min_acceptable_date
                if is_stale and is_halt_check:
                    stale_items.append(f"{name}: {age}d old (need within {expected_date} to {min_acceptable_date})")
                if verbose:
                    is_ideal = d >= expected_date
                    flag = '[OK]' if is_ideal else '[WARN]' if (not is_stale) else '[STALE]'
                    logger.info(f"  {flag} {name:25s}: latest {d} ({age}d ago, acceptable until {min_acceptable_date})")

        if _metrics:
            _metrics.flush()

        if stale_items:
            logger.warning(f"[FAILSAFE] Data stale, attempting to trigger loader: {stale_items}")
            # Stock prices loader takes 1-2 hours to fetch 5000+ symbols. Lambda orchestrator has
            # 10min timeout total. Instead of waiting synchronously (exceeds timeout), trigger
            # asynchronously and verify it started before proceeding.

            # RETRY LOGIC: If first attempt fails, try once more with 10s backoff
            # (allows recovery from transient ECS/network issues without giving up)
            failsafe_ok = False
            for attempt in range(1, 3):
                try:
                    failsafe_ok = _trigger_loader_failsafe_with_verification('stock_prices_daily', verbose=verbose, poll_timeout_sec=30)
                    if failsafe_ok:
                        break
                    elif attempt < 2:
                        logger.warning(f"[FAILSAFE] Attempt {attempt}/2 failed. Retrying in 10s...")
                        time.sleep(10)
                except Exception as retry_err:
                    logger.warning(f"[FAILSAFE] Attempt {attempt}/2 error: {retry_err}. Retrying...")
                    if attempt < 2:
                        time.sleep(10)

            if not failsafe_ok:
                # Failsafe failed or timeout - loader may not have started.
                # Data is 2-5 trading days old (within acceptable window per tolerance).
                # Downstream phases (2-7) have circuit breakers to conservatively handle stale data.
                logger.warning(f"[FAILSAFE] Loader did not confirm startup within 30s. Proceeding with stale data (risky).")
                logger.warning(f"  Stale items: {stale_items}")
                logger.warning(f"  Data is within tolerance window (up to 5 calendar days old).")
                logger.warning(f"  Circuit breakers in Phase 2 will halt if portfolio conditions warrant.")
                logger.warning(f"  Check CloudWatch logs for LOADER_TRIGGER_LAMBDA_ARN and loader status.")

                alerts.send_position_alert(
                    'DATA',
                    'STALE_DATA_FAILSAFE_FAILED',
                    f'Failsafe loader trigger did not confirm startup. Stale items: {"; ".join(stale_items)}. '
                    f'Proceeding with caution — circuit breakers active. '
                    f'Check CloudWatch for loader startup errors.',
                    {'stale_items': stale_items, 'expected_date': str(expected_date), 'failsafe': 'failed'}
                )
                log_phase_result_fn(1, 'data_freshness', 'warn',
                                   f'Stale, failsafe unconfirmed: {"; ".join(stale_items)}')
                # Continue to Phase 2 circuit breakers instead of halting
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

        # Check swing_trader_scores freshness — FAIL-CLOSED if missing/stale.
        # When swing scores are missing, Phase 5 min_swing_score=55 gate kills ALL trades silently.
        # User sees "success" with 0 trades executed and no explanation. Halt explicitly instead.
        swing_scores_ok = True
        try:
            with DatabaseContext('read') as _sw_cur:
                _sw_cur.execute("SET statement_timeout = 5000")
                _sw_cur.execute("""
                    SELECT MAX(date) FROM swing_trader_scores
                """)
                sw_row = _sw_cur.fetchone()
                sw_latest = sw_row[0] if sw_row else None
                if sw_latest is None:
                    logger.error("[SWING SCORES] HALT: swing_trader_scores table is empty")
                    logger.error("  The EOD pipeline must run first to populate swing scores.")
                    logger.error("  Check: Step Functions algo-eod-pipeline-dev execution status.")
                    logger.error("  Or wait for the morning-prep-pipeline at 4:30 AM ET.")
                    alerts.send_position_alert(
                        'DATA', 'SWING_SCORES_MISSING',
                        'HALTING: swing_trader_scores table is empty. Phase 5 cannot rank trades without swing scores. '
                        'Check EOD pipeline Step Functions execution status.',
                        {'swing_latest': None, 'expected': str(expected_date), 'action': 'HALT'}
                    )
                    swing_scores_ok = False
                elif sw_latest < expected_date:
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
