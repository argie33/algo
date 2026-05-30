#!/usr/bin/env python3
"""
Phase 4b: PYRAMID ADDS (winners)

Adds to winning positions (Livermore strategy).
Runs after exits, before new entries.

FAIL-OPEN: log errors but continue.
"""

import logging
import traceback
from datetime import date as _date
from typing import Any, Callable, List, Dict

from algo.orchestrator.phase_result import PhaseResult
from algo.algo_alerts import AlertManager

logger = logging.getLogger(__name__)


def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable,
) -> PhaseResult:
    """Execute Phase 4b: Pyramid Adds.

    Args:
        config: Configuration object
        run_date: Date for this run
        dry_run: Whether running in dry-run mode
        alerts: AlertManager instance
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results

    Returns:
        PhaseResult with status 'ok', data containing pyramid adds
    """
    try:
        from algo.algo_pyramid import PyramidEngine
        engine = PyramidEngine(config)
        recs = engine.evaluate_pyramid_adds(run_date)

        if not recs:
            log_phase_result_fn('4b', 'pyramid_adds', 'success', 'No qualifying adds')
            return PhaseResult('4b', 'pyramid_adds', 'ok', {'adds': []}, False, None)

        executed = 0
        for r in recs:
            if dry_run:
                logger.info(f"  [DRY-RUN] PYRAMID {r['symbol']} #{r['add_number']}: "
                           f"+{r['add_size_shares']} sh @ ${r['add_price']:.2f}")
                continue
            result = engine.execute_add(r)
            if result.get('success'):
                executed += 1
                logger.info(f"  PYRAMID: {result['message']}")

        log_phase_result_fn('4b', 'pyramid_adds', 'success',
                           f'{len(recs)} recommended, {executed} executed')
        return PhaseResult(
            '4b', 'pyramid_adds', 'ok',
            {'recommendations': recs, 'executed': executed},
            False, None
        )

    except Exception as e:
        traceback.print_exc()
        log_phase_result_fn('4b', 'pyramid_adds', 'error', str(e))
        return PhaseResult('4b', 'pyramid_adds', 'ok', {'adds': []}, False, str(e))
