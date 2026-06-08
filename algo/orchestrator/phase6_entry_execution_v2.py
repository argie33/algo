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
            cur.execute(f"""
                SELECT AVG(daily_range) as atr
                FROM (
                    SELECT high - low as daily_range
                    FROM price_daily
                    WHERE symbol = %s
                      AND date <= CURRENT_DATE
                    ORDER BY date DESC
                    LIMIT {period}
                ) recent
            """, (symbol,))
            result = cur.fetchone()
            return float(result[0]) if result and result[0] else None
    except Exception as e:
        logger.warning(f"Could not compute ATR for {symbol}: {e}")
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
        logger.warning(f"Could not compute SMA_50 for {symbol}: {e}")
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
        logger.warning(f"Could not get close for {symbol}: {e}")
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

    trade_executor = TradeExecutor(config=config)
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

            # Only execute if stop is reasonable (min 1.5% below entry; ETFs like SPY have tighter ATR)
            risk_pct = ((entry_price - stop_loss) / entry_price) * 100
            if risk_pct < 1.5:
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
                # Position size: risk 1% of portfolio per trade
                # shares = (portfolio * 0.01) / (entry - stop)
                try:
                    with DatabaseContext('read') as pcur:
                        pcur.execute(
                            "SELECT total_portfolio_value FROM algo_portfolio_snapshots "
                            "ORDER BY snapshot_date DESC LIMIT 1"
                        )
                        row = pcur.fetchone()
                        portfolio_value = float(row[0]) if row and row[0] else 75000.0
                except Exception:
                    portfolio_value = 75000.0

                risk_dollars = portfolio_value * 0.01  # 1% risk per trade
                shares = max(1, int(risk_dollars / (entry_price - stop_loss)))
                logger.info(f"[PHASE 6] {symbol}: portfolio=${portfolio_value:.0f} risk_$=${risk_dollars:.0f} shares={shares}")

                try:
                    result = trade_executor.execute_trade(
                        symbol=symbol,
                        entry_price=entry_price,
                        shares=float(shares),
                        stop_loss_price=stop_loss,
                        signal_date=run_date,
                        entry_date=run_date,
                    )
                    if result.get('success'):
                        executed_count += 1
                        logger.info(f"[PHASE 6] {symbol}: ENTERED trade_id={result.get('trade_id')}")
                    else:
                        logger.warning(f"[PHASE 6] {symbol}: Execute returned not-success: {result.get('message')}")
                        failed_count += 1
                except Exception as exec_err:
                    logger.error(f"[PHASE 6] {symbol}: Execution failed: {exec_err}")
                    failed_count += 1
            else:
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
