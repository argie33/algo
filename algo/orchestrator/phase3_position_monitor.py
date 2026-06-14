#!/usr/bin/env python3

import logging
import traceback
from datetime import date as _date
from typing import Any, Callable, List, Dict

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
    """Execute Phase 3: Position Monitor.

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
        PhaseResult with status 'ok', data containing position recommendations
    """
    try:
        from algo.monitoring import PositionMonitor
        from algo.infrastructure import MarketEventHandler
        monitor = PositionMonitor(config)

        try:
            meh = MarketEventHandler(config)
            open_positions = monitor.get_open_positions() or []
            halts_found = []
            for pos in open_positions:
                halt_check = meh.check_single_stock_halt(pos.get('symbol') or pos.get('name', ''))
                if halt_check and halt_check.get('halted'):
                    symbol = pos.get('symbol') or pos.get('name', '')
                    halts_found.append(symbol)
                    if verbose:
                        logger.warning(f"  [WARN] {symbol} halted — pending orders cancelled")
            if halts_found:
                log_phase_result_fn(3, 'single_stock_halts', 'warn',
                                   f'{len(halts_found)} symbols halted: {", ".join(halts_found)}')
        except Exception as e:
            logger.warning(f"Halt check failed for position: {e}")
            log_phase_result_fn(3, 'halt_check_error', 'warn', f'Halt check failed: {str(e)[:100]}')

        stale_result = monitor.check_stale_orders(run_date)
        if stale_result and stale_result.get('status') == 'STALE_ORDERS_FOUND':
            alerts.send_position_alert(
                'STALE_ORDERS',
                'STALE_ORDER_ALERT',
                f'{stale_result.get("count", 0)} orders pending >1 hour',
                {'orders': stale_result.get('count', 0)}
            )

        recommendations = monitor.review_positions(run_date)

        n_raise_stop = sum(1 for r in recommendations if r['action'] == 'RAISE_STOP')
        n_early_exit = sum(1 for r in recommendations if r['action'] == 'EARLY_EXIT')
        n_hold = sum(1 for r in recommendations if r['action'] == 'HOLD')
        log_phase_result_fn(
            3, 'position_monitor', 'success',
            f'{len(recommendations)} positions: {n_hold} hold, {n_raise_stop} raise-stop, {n_early_exit} early-exit',
        )
        return PhaseResult(
            3, 'position_monitor', 'ok',
            {'recommendations': recommendations, 'count': len(recommendations)},
            False, None
        )

    except Exception as e:
        traceback.print_exc()
        log_phase_result_fn(3, 'position_monitor', 'error', str(e))
        return PhaseResult(3, 'position_monitor', 'ok', {'recommendations': []}, False, str(e))
