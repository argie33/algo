#!/usr/bin/env python3

import logging
import traceback
from datetime import date as _date
from typing import Any, Callable, Dict

from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager

logger = logging.getLogger(__name__)

def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable,
) -> PhaseResult:
    """Execute Phase 3a: Position Reconciliation.

    Delegates to DailyReconciliation (consolidated from PositionReconciler).
    Phase 3a is a lightweight check; comprehensive reconciliation is in Phase 7.

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
        from algo.infrastructure.reconciliation import DailyReconciliation

        recon = DailyReconciliation(config)
        result = recon.run_daily_reconciliation(run_date)

        if result.get('success'):
            log_phase_result_fn(
                '3a', 'reconciliation', 'success',
                f'{result.get("positions", 0)} positions verified'
            )
        elif result.get('reason') == 'Alpaca unavailable' or 'unavailable' in result.get('reason', '').lower():
            log_phase_result_fn(
                '3a', 'reconciliation', 'success',
                f'Skipped: {result.get("reason", "alpaca unavailable")}'
            )
        else:
            log_phase_result_fn(
                '3a', 'reconciliation', 'alert',
                result.get('reason', 'reconciliation failed')
            )

        return PhaseResult(3, 'reconciliation', 'ok', result, False, None)

    except Exception as e:
        traceback.print_exc()
        log_phase_result_fn('3a', 'reconciliation', 'error', str(e))
        return PhaseResult('3a', 'reconciliation', 'ok', {}, False, str(e))
