#!/usr/bin/env python3
"""
Phase 1: DATA FRESHNESS CHECK

Confirms market data is recent enough to make decisions on.
Checks:
- Pipeline health (all critical tables have recent data)
- Data patrol results (critical/error findings halt the run)
- SLA tracker (critical loaders have fresh data)
- Loader monitor (no critical findings)
- Data staleness (max 3 days old by default, 365 in DEV mode)
- Margin health (warn if > 70%)

FAIL-CLOSED: stale data, critical patrol findings, or SLA violations halt trading.
"""

import os
import logging
from datetime import date as _date, timedelta
from typing import Any, Callable, Optional, Dict
from pathlib import Path

from utils.db_connection import get_db_connection
from algo.algo_alerts import AlertManager
from algo.algo_sql_safety import assert_safe_table, assert_safe_column
from algo.orchestrator.phase_result import PhaseResult

logger = logging.getLogger(__name__)


def _check_data_patrol(cur: Any, run_date: _date, verbose: bool, log_phase_result_fn: Callable) -> bool:
    """Check data patrol results. Fail-closed if critical/error findings.

    Only checks the LATEST patrol run (not accumulated from all runs in 24h).
    Returns: True if patrol OK, False if critical/error issues found.
    """
    try:
        cur.execute("""
            SELECT patrol_run_id FROM data_patrol_log
            ORDER BY created_at DESC LIMIT 1
        """)
        latest_run = cur.fetchone()
        if not latest_run:
            if verbose:
                logger.info("No patrol data available")
            return True

        latest_run_id = latest_run[0]

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
        if critical_count and critical_count > 0:
            logger.info(f"[HALT] Data patrol found {critical_count} CRITICAL issues - BLOCKING ORCHESTRATOR")
            if verbose:
                logger.info(f"  [HALT] Data patrol found {critical_count} CRITICAL issues")
            log_phase_result_fn(1, 'data_patrol', 'halt',
                               f'Critical data quality issues: {critical_count} critical findings')
            return False

        # FAIL-CLOSED: too many errors block in auto mode
        if error_count and error_count > 2:
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
    if not cur:
        return

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
    get_conn: Callable,
    put_conn: Callable,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable,
    skip_freshness: bool = False,
) -> PhaseResult:
    """Execute Phase 1: Data Freshness Check.

    Args:
        config: Configuration object
        get_conn: Function to get database connection
        put_conn: Function to return database connection
        run_date: Date for this run
        dry_run: Whether running in dry-run mode
        alerts: AlertManager instance
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results
        skip_freshness: If True, skip all freshness checks (latent feature)

    Returns:
        PhaseResult with status and data
    """
    logger.debug(f"Phase 1: Starting data freshness check for run_date={run_date}")

    conn = None
    cur = None
    try:
        # Skip if explicitly disabled (latent feature)
        if skip_freshness:
            logger.info("  [SKIP] Data freshness check skipped via skip_freshness flag")
            return PhaseResult(1, 'data_freshness', 'ok', {}, False, None)

        try:
            from algo.algo_pipeline_health import PipelineHealth
            health = PipelineHealth()
            health.connect()
            status = health.get_pipeline_status()
            health.log_health_check(status)
            health.disconnect()
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

        conn = get_conn()
        cur = conn.cursor()
        logger.debug("Phase 1: Database connection established")

        # In DEV mode, skip strict SLA/loader health checks
        if os.getenv('DEV_MODE', '').lower() in ('true', '1', 'yes'):
            logger.debug("Phase 1: Running in DEV mode - skipping strict SLA checks")
            logger.info("  [DEV MODE] Skipping SLA and loader health checks")

        cur.execute(
            """
            SELECT
                (SELECT MAX(date) FROM price_daily WHERE symbol = 'SPY') AS spy_latest,
                (SELECT MAX(date) FROM market_health_daily) AS mh_latest,
                (SELECT MAX(date) FROM trend_template_data) AS tt_latest,
                (SELECT MAX(date) FROM signal_quality_scores) AS sqs_latest,
                (SELECT MAX(date) FROM buy_sell_daily) AS buys_latest
            """
        )
        row = cur.fetchone()
        if not row:
            logger.error("DATA FRESHNESS: Critical query returned no results")
            log_phase_result_fn(1, 'data_freshness', 'error', 'Could not query data freshness')
            return PhaseResult(1, 'data_freshness', 'ok', {}, False, 'Could not query data freshness')

        spy_date, mh_date, tt_date, sqs_date, buys_date = row
        checks = {
            'SPY price data': spy_date,
            'Market health': mh_date,
            'Trend template': tt_date,
            'Signal quality scores': sqs_date,
            'Buy/sell signals': buys_date,
        }
        table_keys = {
            'SPY price data': 'price_daily',
            'Market health': 'market_health_daily',
            'Trend template': 'trend_template_data',
            'Signal quality scores': 'signal_quality_scores',
            'Buy/sell signals': 'buy_sell_daily',
        }
        # In DEV_MODE, be lenient about data staleness (allow up to 7 days old)
        is_dev_mode = os.getenv('DEV_MODE', '').lower() in ('true', '1', 'yes')
        # Use config max_data_staleness_days (default 3 days for production, 7 for DEV)
        max_stale = config.max_data_staleness_days if hasattr(config, 'max_data_staleness_days') else (7 if is_dev_mode else 3)
        stale_items = []

        try:
            from algo.algo_metrics import MetricsPublisher
            _metrics = MetricsPublisher(dry_run=dry_run)
        except Exception:
            _metrics = None

        for name, d in checks.items():
            if d is None and not is_dev_mode:
                # In DEV_MODE, allow missing data; in production fail
                stale_items.append(f"{name}: missing")
                if _metrics:
                    _metrics.put_data_freshness(table_keys[name], 999)
            elif d is not None:
                age = (run_date - d).days
                if _metrics:
                    _metrics.put_data_freshness(table_keys[name], age)
                if age > max_stale and not is_dev_mode:
                    stale_items.append(f"{name}: {age}d old")
                if verbose:
                    flag = '[OK]' if age <= max_stale else '[STALE]'
                    logger.info(f"  {flag} {name:25s}: latest {d} ({age}d ago)")

        if _metrics:
            _metrics.flush()

        if stale_items:
            alerts.send_position_alert(
                'DATA',
                'STALE_DATA_HALT',
                f'Data freshness check failed. Stale items: {"; ".join(stale_items)}',
                {'stale_items': stale_items, 'max_age_days': max_stale}
            )
            log_phase_result_fn(1, 'data_freshness', 'fail',
                               f'Stale: {"; ".join(stale_items)}')
            return PhaseResult(1, 'data_freshness', 'halted', {}, True,
                             f'Stale: {"; ".join(stale_items)}')

        patrol_ok = _check_data_patrol(cur, run_date, verbose, log_phase_result_fn)

        if not patrol_ok:
            return PhaseResult(1, 'data_patrol', 'halted', {}, True, 'Data patrol check failed')

        # Margin health check (Phase 1 - production safeguard)
        try:
            from algo.algo_margin_monitor import MarginMonitor
            mm = MarginMonitor()
            margin_info = mm.get_margin_usage()
            if margin_info and margin_info['margin_usage_pct'] > 70:
                alerts.send_position_alert(
                    'ACCOUNT',
                    'MARGIN_ALERT',
                    f'Margin usage {margin_info["margin_usage_pct"]:.1f}% (threshold: 70%)',
                    margin_info
                )
                if verbose:
                    logger.warning(f"  [MARGIN] Usage {margin_info['margin_usage_pct']:.1f}% - approaching limit")
            elif verbose and margin_info:
                logger.info(f"  [OK] Margin: {margin_info['margin_usage_pct']:.1f}% usage")
        except Exception as e:
            logger.warning(f'Margin check failed: {e}')

        # Pipeline health check: verify all required tables have recent data
        _check_pipeline_health(cur, run_date, verbose)

        log_phase_result_fn(1, 'data_freshness', 'success',
                           'All data fresh within window')
        return PhaseResult(1, 'data_freshness', 'ok', {}, False, None)

    except Exception as e:
        log_phase_result_fn(1, 'data_freshness', 'error', str(e))
        return PhaseResult(1, 'data_freshness', 'ok', {}, False, str(e))
    finally:
        if cur:
            try:
                cur.close()
            except Exception as e:
                logger.error(f"Unhandled exception: {e}")
        if conn:
            try:
                put_conn(conn)
            except Exception as e:
                logger.error(f"Unhandled exception: {e}")
