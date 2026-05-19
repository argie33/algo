#!/usr/bin/env python3
"""
Phase 3a: POSITION RECONCILIATION

Checks that DB positions match Alpaca account holdings.

FAIL-OPEN: alerts on divergence but doesn't block trading.
"""

import logging
import traceback
from datetime import date as _date
from typing import Any, Callable, Dict

from algo.orchestrator.phase_result import PhaseResult
from algo.algo_alerts import AlertManager

logger = logging.getLogger(__name__)


def run(
    config: Any,
    get_conn: Callable,
    put_conn: Callable,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable,
) -> PhaseResult:
    """Execute Phase 3a: Position Reconciliation.

    Args:
        config: Configuration object
        get_conn: Function to get database connection
        put_conn: Function to return database connection
        run_date: Date for this run
        dry_run: Whether running in dry-run mode
        alerts: AlertManager instance
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results

    Returns:
        PhaseResult with status 'ok' (fail-open)
    """
    try:
        from algo.algo_reconciliation import PositionReconciler
        reconciler = PositionReconciler()
        result = reconciler.reconcile()

        if result.get('status') == 'skipped':
            log_phase_result_fn('3a', 'reconciliation', 'success',
                               f'Skipped: {result.get("reason", "alpaca unavailable")}')
        elif result.get('critical_count', 0) > 0:
            alerts.send_position_alert(
                'RECONCILIATION',
                'CRITICAL',
                f'{result["critical_count"]} untracked Alpaca positions',
                result.get('issues', [])[:5]
            )
            log_phase_result_fn('3a', 'reconciliation', 'alert',
                               f'Critical divergence: {result["critical_count"]} issues')
        elif result.get('error_count', 0) > 0:
            alerts.send_position_alert(
                'RECONCILIATION',
                'ERROR',
                f'{result["error_count"]} missing/closed positions in Alpaca',
                result.get('issues', [])[:5]
            )
            log_phase_result_fn('3a', 'reconciliation', 'alert',
                               f'{result["error_count"]} position errors')
        else:
            log_phase_result_fn('3a', 'reconciliation', 'success',
                               f'{result.get("db_positions", 0)} positions reconciled OK')

        return PhaseResult('3a', 'reconciliation', 'ok', result, False, None)

    except Exception as e:
        traceback.print_exc()
        log_phase_result_fn('3a', 'reconciliation', 'error', str(e))
        return PhaseResult('3a', 'reconciliation', 'ok', {}, False, str(e))
