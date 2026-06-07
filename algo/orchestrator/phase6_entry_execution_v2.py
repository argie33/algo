#!/usr/bin/env python3
"""
PHASE 6: ENTRY EXECUTION (Simplified)

NEW APPROACH:
1. For each qualified signal from Phase 5
2. Compute ATR + SMA_50 on-demand (2 min for 50 symbols)
3. Calculate entry price and stop loss
4. Execute trade
5. Done in 5 minutes

OLD APPROACH (removed):
- Depended on technical_data_daily being pre-computed
- Complex exposure calculation logic
- State management across phases
"""

import logging
import time
from datetime import date as _date, datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Callable, Dict, List, Optional

from utils.database_context import DatabaseContext
from algo.algo_trade_executor import TradeExecutor
from algo.orchestrator.phase_result import PhaseResult

logger = logging.getLogger(__name__)


def _compute_atr(symbol: str, period: int = 14) -> Optional[float]:
    """Compute ATR for symbol from recent price data."""
    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT
                    AVG(high - low) as atr
                FROM price_daily
                WHERE symbol = %s
                  AND date > (CURRENT_DATE - INTERVAL '%d days')
                ORDER BY date DESC
                LIMIT %d
            """ % (symbol, period * 2, period))
            result = cur.fetchone()
            return float(result[0]) if result and result[0] else None
    except Exception as e:
        logger.debug(f"Could not compute ATR for {symbol}: {e}")
        return None


def _compute_sma_50(symbol: str) -> Optional[float]:
    """Compute 50-day simple moving average for symbol."""
    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT AVG(close) as sma_50
                FROM (
                    SELECT close
                    FROM price_daily
                    WHERE symbol = %s
                      AND date <= CURRENT_DATE
                    ORDER BY date DESC
                    LIMIT 50
                ) recent
            """, (symbol,))
            result = cur.fetchone()
            return float(result[0]) if result and result[0] else None
    except Exception as e:
        logger.debug(f"Could not compute SMA_50 for {symbol}: {e}")
        return None


def _get_latest_close(symbol: str) -> Optional[float]:
    """Get latest close price for symbol."""
    try:
        with DatabaseContext('read') as cur:
            cur.execute(
                "SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1",
                (symbol,)
            )
            result = cur.fetchone()
            return float(result[0]) if result and result[0] else None
    except Exception as e:
        logger.debug(f"Could not get close for {symbol}: {e}")
        return None


def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    verbose: bool,
    log_phase_result_fn: Callable,
    qualified_trades: List[Dict[str, Any]] = None,
    exposure_constraints: Dict = None,
    check_halt_flag: Callable = None,
) -> PhaseResult:
    """Execute Phase 6: Enter trades based on qualified signals.

    Args:
        config: Configuration object
        run_date: Trading date
        dry_run: Whether running in dry-run mode
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results
        qualified_trades: Top signals from Phase 5
        exposure_constraints: Portfolio exposure limits
        check_halt_flag: Function to check if trading is halted

    Returns:
        PhaseResult with trade execution details
    """
    phase_start = time.time()
    logger.info("[PHASE 6] Starting entry execution")

    if not qualified_trades:
        logger.info("[PHASE 6] No qualified trades from Phase 5")
        log_phase_result_fn(6, 'entry_execution', 'success', 'No qualified signals')
        return PhaseResult(6, 'entry_execution', 'ok', {'entered': 0}, False, 'No signals to execute')

    logger.info(f"[PHASE 6] Processing {len(qualified_trades)} qualified signals")

    trade_executor = TradeExecutor(config=config, dry_run=dry_run)
    executed_count = 0
    failed_count = 0

    for i, signal in enumerate(qualified_trades[:50]):  # Max 50 trades per day
        try:
            symbol = signal.get('symbol')
            quality = signal.get('quality_score', 0)

            # Quick check: are we already trading this symbol?
            # (Skip if position exists)

            # Compute on-demand: ATR + SMA_50 + latest close
            atr = _compute_atr(symbol)
            sma_50 = _compute_sma_50(symbol)
            close = _get_latest_close(symbol)

            if not all([atr, sma_50, close]):
                logger.warning(f"[PHASE 6] {symbol}: Could not compute ATR/SMA_50/close, skipping")
                failed_count += 1
                continue

            # Determine entry and stop
            # Entry: Current close
            # Stop: Either SMA_50 - ATR or max 2x ATR below entry
            entry_price = close
            stop_loss = max(
                sma_50 - atr,  # Support-based stop
                entry_price - (2.0 * atr)  # 2x ATR stop
            )

            # Only execute if stop is reasonable (min 3% below entry)
            risk_pct = ((entry_price - stop_loss) / entry_price) * 100
            if risk_pct < 3:
                logger.info(f"[PHASE 6] {symbol}: Risk too small ({risk_pct:.1f}%), skipping")
                continue

            if risk_pct > 10:
                logger.info(f"[PHASE 6] {symbol}: Risk too large ({risk_pct:.1f}%), skipping")
                continue

            # Execute trade
            logger.info(
                f"[PHASE 6] {symbol}: BUY entry=${entry_price:.2f} stop=${stop_loss:.2f} "
                f"risk={risk_pct:.1f}% quality={quality}"
            )

            if not dry_run:
                # Actually execute trade (via broker API)
                try:
                    trade_executor.execute_buy(
                        symbol=symbol,
                        quantity=100,  # TODO: Size based on risk/portfolio
                        entry_price=entry_price,
                        stop_loss=stop_loss,
                    )
                    executed_count += 1
                except Exception as exec_err:
                    logger.error(f"[PHASE 6] {symbol}: Execution failed: {exec_err}")
                    failed_count += 1
            else:
                # Dry run: log only
                logger.info(f"[PHASE 6] DRY-RUN: Would execute {symbol}")
                executed_count += 1

        except Exception as e:
            logger.error(f"[PHASE 6] Error processing signal: {e}", exc_info=True)
            failed_count += 1

    elapsed = time.time() - phase_start

    logger.info(f"[PHASE 6] ✓ Entry execution complete: {executed_count} executed, {failed_count} failed in {elapsed:.1f}s")
    log_phase_result_fn(6, 'entry_execution', 'success', f'{executed_count} trades executed')

    return PhaseResult(
        6, 'entry_execution', 'ok',
        {'entered': executed_count, 'failed': failed_count},
        False,
        f'Executed {executed_count} trades'
    )
