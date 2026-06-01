#!/usr/bin/env python3

import os
import logging
from datetime import date as _date, timedelta
from typing import Any, Callable, Optional, Dict

from utils.database_context import DatabaseContext
from algo.algo_alerts import AlertManager
from algo.algo_sql_safety import assert_safe_table, assert_safe_column
from algo.orchestrator.phase_result import PhaseResult

logger = logging.getLogger(__name__)

def _trigger_loader_failsafe(loader_name: str, verbose: bool = False) -> bool:
    """
    Failsafe: trigger ECS loader via Lambda if EventBridge failed.

    Returns: True if trigger succeeded, False otherwise.
    """
    try:
        import boto3
        import json

        # Invoke trigger-loaders Lambda
        lambda_client = boto3.client('lambda')
        loader_lambda = os.getenv('LOADER_TRIGGER_LAMBDA_ARN', '')

        if not loader_lambda:
            if verbose:
                logger.warning("[FAILSAFE] LOADER_TRIGGER_LAMBDA_ARN not configured, cannot trigger")
            return False

        response = lambda_client.invoke(
            FunctionName=loader_lambda,
            InvocationType='Event',  # async
            Payload=json.dumps({
                'loader_name': loader_name,
                'task_count': 1,
                'priority': 'FARGATE'  # critical, use on-demand
            })
        )

        if response['StatusCode'] in (200, 202, 204):
            if verbose:
                logger.info(f"[FAILSAFE] ✓ Triggered {loader_name} loader via Lambda")
            return True
        else:
            if verbose:
                logger.warning(f"[FAILSAFE] Failed to trigger {loader_name}: {response['StatusCode']}")
            return False
    except Exception as e:
        logger.warning(f"[FAILSAFE] Could not trigger loader: {e}")
        return False

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
                f"expected ({expected_patrol_date}) — skipping stale findings"
            )
            return True  # Stale patrol: don't block on old findings

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
                    elif table in ('sector_ranking', 'industry_ranking'):
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
        # column (fast, non-blocking) and takes <5s even on large tables.
        try:
            with DatabaseContext('read') as cur:
                cur.execute("SET statement_timeout = 60000")  # 60s for ANALYZE
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
        dates = {}
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

        # Compute the most recent trading day before run_date as the expected data date.
        # Using trading-day comparison prevents false halts after 3-day weekends where
        # the calendar gap (e.g. Friday → Tuesday = 4 days) exceeds a raw day threshold.
        try:
            from algo.algo_market_calendar import MarketCalendar
            expected_date = run_date - timedelta(days=1)
            for _ in range(10):
                if MarketCalendar.is_trading_day(expected_date):
                    break
                expected_date -= timedelta(days=1)
        except Exception as cal_e:
            logger.debug(f"MarketCalendar check failed, falling back to weekday check: {cal_e}")
            expected_date = run_date - timedelta(days=1)
            while expected_date.weekday() >= 5:
                expected_date -= timedelta(days=1)

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
                is_stale = d < expected_date
                if is_stale and is_halt_check:
                    stale_items.append(f"{name}: {age}d old (expected {expected_date})")
                if verbose:
                    flag = '[WARN]' if (is_stale and not is_halt_check) else '[STALE]' if is_stale else '[OK]'
                    logger.info(f"  {flag} {name:25s}: latest {d} ({age}d ago)")

        if _metrics:
            _metrics.flush()

        if stale_items:
            logger.warning(f"[FAILSAFE] Data stale, firing async loader trigger: {stale_items}")
            _trigger_loader_failsafe('stock_prices_daily', verbose=verbose)

            if stale_items:
                alerts.send_position_alert(
                    'DATA',
                    'STALE_DATA_HALT',
                    f'Data freshness check failed. Stale items: {"; ".join(stale_items)}',
                    {'stale_items': stale_items, 'expected_date': str(expected_date)}
                )
                log_phase_result_fn(1, 'data_freshness', 'halt',
                                   f'Stale: {"; ".join(stale_items)}')
                return PhaseResult(1, 'data_freshness', 'halted', {}, True,
                                 f'Stale: {"; ".join(stale_items)}')

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

        # Skip slow secondary checks in Lambda to preserve budget for trading phases.
        # Under EOD pipeline load, COUNT(*) and health queries on large tables take
        # 1-3 minutes each — Phase 1 would consume the entire 600s Lambda budget
        # before reaching Phases 2-7. These are observability-only, not halt conditions.
        in_lambda = bool(os.getenv('AWS_LAMBDA_FUNCTION_NAME'))
        if not in_lambda:
            # Observability: log signal_quality_scores row count — not a halt condition.
            try:
                with DatabaseContext('read') as _sqs_cur:
                    _sqs_cur.execute("SELECT COUNT(*), MAX(date) FROM signal_quality_scores")
                    sqs_row = _sqs_cur.fetchone()
                    total_sqs, latest_sqs_date = (sqs_row[0], sqs_row[1]) if sqs_row else (0, None)
                    if total_sqs == 0:
                        logger.warning("  [WARN] signal_quality_scores table is empty (observe-only, not blocking)")
                        log_phase_result_fn(1, 'signal_quality_scores', 'warn', 'Table empty, first run expected')
                    elif verbose:
                        logger.info(f"  [OK] signal_quality_scores: {total_sqs} rows, latest {latest_sqs_date}")
            except Exception as e:
                logger.warning(f"  [WARN] signal_quality_scores count check failed: {e} (observe-only)")

            # Margin health check
            try:
                from algo.algo_position_monitor import PositionMonitor
                pm = PositionMonitor(config)
                margin_info = pm.get_margin_usage()
                if margin_info and margin_info['margin_usage_pct'] > 70:
                    alerts.send_position_alert(
                        'ACCOUNT', 'MARGIN_ALERT',
                        f'Margin usage {margin_info["margin_usage_pct"]:.1f}% (threshold: 70%)',
                        margin_info
                    )
                    if verbose:
                        logger.warning(f"  [MARGIN] Usage {margin_info['margin_usage_pct']:.1f}% - approaching limit")
                elif verbose and margin_info:
                    logger.info(f"  [OK] Margin: {margin_info['margin_usage_pct']:.1f}% usage")
            except Exception as e:
                logger.warning(f'Margin check failed: {e}')

            # Pipeline health check
            with DatabaseContext('read') as _health_cur:
                _check_pipeline_health(_health_cur, run_date, verbose)
        else:
            logger.info("  [LAMBDA] Skipping secondary checks (SQS count, margin, pipeline health) to preserve 600s budget")

        log_phase_result_fn(1, 'data_freshness', 'success', 'All data fresh within window')
        return PhaseResult(1, 'data_freshness', 'ok', {}, False, None)

    except Exception as e:
        log_phase_result_fn(1, 'data_freshness', 'error', str(e))
        return PhaseResult(1, 'data_freshness', 'halted', {}, True, str(e))
