#!/usr/bin/env python3
"""Intraday position synchronization from trades to algo_positions.

DATA VALIDATION STRATEGY (AUDIT ISSUE #3):
This module synchronizes position data from the trades table to the algo_positions table,
ensuring position tracking stays accurate throughout intraday trading. Critical data
validation ensures corrupted or incomplete position records never enter algo_positions:

1. Entry price validation:
   - REQUIRED: entry_price NOT NULL (prevents orphaned positions)
   - REQUIRED: entry_price > 0 (prevents negative/zero prices)
   - RATIONALE: Entry price is essential for P&L calculation, position sizing,
     and risk metrics. NULL or invalid entry prices mask position data problems.

2. Quantity validation:
   - REQUIRED: quantity > 0 (prevents zero/negative quantities)
   - RATIONALE: Position size must be positive. Zero quantity = no position.
     Negative quantity = position corrupted (double-sell or sync error).

3. Position ID validation:
   - REQUIRED: position_id exists before insert/update
   - RATIONALE: Ensures referential integrity with trades table

This ensures position data stays in sync with actual trades throughout the day,
not just at the midnight loader refresh.

Used by: Phase 1 (after data validation) to ensure positions are fresh
See also: algo/orchestrator/phase8_entry_execution.py for related position tracking
"""

import logging
from decimal import Decimal
from typing import Tuple

from algo.config.credential_manager import get_algo_owner_cognito_sub
from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


def sync_positions_from_trades() -> Tuple[int, int, int, list[dict[str, str]]]:
    """Synchronize algo_positions table with current trades data.

    For each symbol with net quantity > 0 in trades:
    - If position exists: update quantity and status
    - If position doesn't exist: insert new position

    Returns:
        (inserted_count, updated_count, error_count, error_details)
        where error_details is list of {symbol: str, reason: str} dicts
    """
    import psycopg2

    inserted = 0
    updated = 0
    errors = 0
    error_details: list[dict[str, str]] = []

    try:
        with DatabaseContext('write') as cur:
            # Get all open positions from trades
            cur.execute('''
                SELECT symbol, SUM(quantity) as total_qty
                FROM algo_trades
                WHERE status IN ('filled', 'open')
                GROUP BY symbol
                HAVING SUM(quantity) > 0
                ORDER BY symbol
            ''')

            open_positions = cur.fetchall()
            logger.info(f"[POSITION_SYNC] Found {len(open_positions)} open positions in trades")

            for symbol, total_qty in open_positions:
                savepoint = f"sp_{symbol.replace('-', '_')}"
                try:
                    # Create savepoint before each symbol to isolate transaction errors
                    cur.execute(f"SAVEPOINT {savepoint}")

                    # Check if position exists (open or closed - reopen if needed)
                    cur.execute(
                        'SELECT id, status FROM algo_positions WHERE symbol = %s ORDER BY updated_at DESC LIMIT 1',
                        (symbol,)
                    )
                    existing = cur.fetchone()

                    if existing:
                        existing_id, existing_status = existing
                        # Update existing position and reopen if it was closed
                        cur.execute(
                            'UPDATE algo_positions SET quantity = %s, status = %s, updated_at = NOW() '
                            'WHERE symbol = %s',
                            (total_qty, 'open', symbol)
                        )
                        updated += 1
                        action = "reopened" if existing_status == 'closed' else "updated"
                        logger.debug(f"[POSITION_SYNC] {action.capitalize()} {symbol}: {total_qty:.2f} shares (was {existing_status})")
                    else:
                        # Get entry_price and risk/position-linkage fields from first trade.
                        # algo_positions requires position_id, avg_entry_price, stop_loss_price,
                        # and current_stop_price (all NOT NULL, no defaults) - pulling them from
                        # the originating algo_trades row instead of leaving them unset, which
                        # previously made every insert here raise a NOT NULL violation, caught by
                        # the broad except below and logged as a per-symbol error. That silently
                        # defeated this function's entire purpose (AUDIT ISSUE #3: healing
                        # positions orphaned when a crash landed the algo_trades row but not the
                        # matching algo_positions row) - the exact orphaned-position case this
                        # reconciliation exists to catch was the one case it could never fix.
                        cur.execute('''
                            SELECT entry_price, position_id, stop_loss_price,
                                   target_1_price, target_2_price, target_3_price,
                                   target_1_r_multiple, target_2_r_multiple, target_3_r_multiple
                            FROM algo_trades
                            WHERE symbol = %s AND status IN ('filled', 'open')
                            ORDER BY entry_date ASC
                            LIMIT 1
                        ''', (symbol,))

                        trade_row = cur.fetchone()
                        if trade_row:
                            (
                                entry_price, trade_position_id, stop_loss_price,
                                target_1_price, target_2_price, target_3_price,
                                target_1_r_multiple, target_2_r_multiple, target_3_r_multiple,
                            ) = trade_row

                            # AUDIT ISSUE #3 FIX: Validate position data BEFORE insert/update
                            # CHECKPOINT 1: Check entry_price IS NOT NULL and > 0
                            # WHY: Entry price is mandatory for P&L calculation, stop loss placement,
                            # and risk metrics. NULL entry_price creates orphaned positions that:
                            # - Cannot calculate realized/unrealized P&L
                            # - Cannot place valid stop losses
                            # - Corrupt portfolio risk calculations (SUM ignores NULL)
                            # FAIL-FAST: Reject position rather than insert corrupted data
                            if not entry_price or entry_price <= 0:
                                raise RuntimeError(
                                    f"[POSITION_SYNC] Cannot sync position for {symbol}: "
                                    f"entry_price is NULL or <= 0 (value={entry_price}). "
                                    f"Cannot create corrupted position data. "
                                    f"Verify trade entry_price was recorded correctly."
                                )

                            # CHECKPOINT 2: Check quantity > 0 (already checked in GROUP BY but verify again)
                            # WHY: Quantity must be positive. Zero quantity = no position (shouldn't exist).
                            # Negative quantity = position corrupted (double-sold or sync error).
                            # Verify defensive: GROUP BY HAVING enforces this, but double-check here
                            # in case SQL execution or sync state changed between GROUP BY and this point.
                            if total_qty <= 0:
                                raise RuntimeError(
                                    f"[POSITION_SYNC] Cannot sync position for {symbol}: "
                                    f"quantity must be > 0 (value={total_qty}). "
                                    f"Zero/negative quantity indicates corrupted trade record."
                                )

                            # CHECKPOINT 3: Check position_id and stop_loss_price are present.
                            # WHY: Both are NOT NULL on algo_positions with no default. A position
                            # with no stop_loss_price is also unmanageable by every downstream exit
                            # check (exit_engine.py, circuit_breaker.py), so refuse to synthesize a
                            # placeholder value here rather than create a position no safety check
                            # can act on.
                            if not trade_position_id or not stop_loss_price or stop_loss_price <= 0:
                                raise RuntimeError(
                                    f"[POSITION_SYNC] Cannot sync position for {symbol}: "
                                    f"position_id={trade_position_id!r}, stop_loss_price={stop_loss_price!r}. "
                                    f"Both required (NOT NULL) - trade record is incomplete."
                                )

                            # Position doesn't exist, insert new one
                            cur.execute('''
                                INSERT INTO algo_positions (
                                    position_id, symbol, quantity, avg_entry_price, entry_price,
                                    current_price, status, entry_date,
                                    stop_loss_price, current_stop_price,
                                    target_1_price, target_2_price, target_3_price,
                                    target_1_r_multiple, target_2_r_multiple, target_3_r_multiple,
                                    cognito_sub, created_at, updated_at
                                )
                                VALUES (
                                    %s, %s, %s, %s, %s,
                                    %s, %s, NOW(),
                                    %s, %s,
                                    %s, %s, %s,
                                    %s, %s, %s,
                                    %s, NOW(), NOW()
                                )
                            ''', (
                                trade_position_id, symbol, total_qty, entry_price, entry_price,
                                entry_price, 'open',
                                stop_loss_price, stop_loss_price,
                                target_1_price, target_2_price, target_3_price,
                                target_1_r_multiple, target_2_r_multiple, target_3_r_multiple,
                                get_algo_owner_cognito_sub(),
                            ))
                            inserted += 1
                            logger.debug(f"[POSITION_SYNC] Inserted new position {symbol}: {total_qty:.2f} shares")
                        else:
                            error_reason = f"No entry_price found in trades"
                            logger.warning(f"[POSITION_SYNC] Could not find entry_price for {symbol}")
                            errors += 1
                            error_details.append({"symbol": symbol, "reason": error_reason})

                except Exception as e:
                    error_reason = f"{type(e).__name__}: {str(e)[:500]}"
                    logger.error(
                        f"[POSITION_SYNC] Error syncing {symbol}: {type(e).__name__}: {e}",
                        exc_info=True
                    )
                    errors += 1
                    error_details.append({"symbol": symbol, "reason": error_reason})
                    # Rollback to savepoint to recover from transaction abort
                    # This allows continuing to process remaining symbols even if one fails
                    try:
                        cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                    except psycopg2.Error as rollback_err:
                        logger.error(f"[POSITION_SYNC] Savepoint rollback failed for {symbol}: {rollback_err}")
                        # Continue anyway - the per-symbol error already logged

    except Exception as e:
        logger.error(f"[POSITION_SYNC] CRITICAL: Failed to sync positions: {e}")
        raise RuntimeError(f"Position sync failed: {e}")

    if error_details:
        error_summary = ", ".join(
            f"{d['symbol']}({d['reason'][:30]})" for d in error_details[:5]
        )
        if len(error_details) > 5:
            error_summary += f" ... and {len(error_details) - 5} more"
        logger.warning(f"[POSITION_SYNC] Sync errors for {len(error_details)} symbols: {error_summary}")
    logger.info(f"[POSITION_SYNC] Completed: {inserted} inserted, {updated} updated, {errors} errors")
    return inserted, updated, errors, error_details


def validate_position_count(expected_approximate: int | None = None) -> bool:
    """Validate that position count and symbols match exactly (no silent position loss).

    CRITICAL FIX (Session 2026-08-02): Previous percentage-based check allowed 5% mismatch,
    which could silently lose hundreds of positions. Example: 100 positions tracked, 95 synced
    = "healthy" by percentage, but 5 positions ($100K each) lost silently.

    New approach: STRICT validation with detailed mismatch reporting.
    - Every symbol in trades MUST have a matching position
    - Every position MUST have corresponding trades
    - Zero tolerance for discrepancies beyond expected race conditions

    Returns True only if positions and trades match perfectly or with explained variance.
    """
    try:
        with DatabaseContext('read') as cur:
            # Get all open positions by symbol
            cur.execute('''
                SELECT symbol, COUNT(*) as pos_count
                FROM algo_positions
                WHERE status = %s
                GROUP BY symbol
            ''', ('open',))
            position_symbols = {row[0]: row[1] for row in cur.fetchall()}
            open_count = sum(position_symbols.values())

            # Get all symbols with open trades and positive quantity
            cur.execute('''
                SELECT symbol, SUM(quantity) as total_qty
                FROM algo_trades
                WHERE status IN ('filled', 'open')
                GROUP BY symbol
                HAVING SUM(quantity) > 0
            ''')
            trade_symbols = {row[0]: row[1] for row in cur.fetchall()}

            # STRICT VALIDATION: Check for discrepancies
            missing_in_positions = set(trade_symbols.keys()) - set(position_symbols.keys())
            orphaned_in_positions = set(position_symbols.keys()) - set(trade_symbols.keys())

            is_valid = len(missing_in_positions) == 0 and len(orphaned_in_positions) == 0

            if missing_in_positions:
                logger.error(
                    f"[POSITION_SYNC_VALIDATE] CRITICAL: {len(missing_in_positions)} symbols have trades but NO position: "
                    f"{', '.join(sorted(missing_in_positions)[:10])}{'...' if len(missing_in_positions) > 10 else ''}. "
                    f"Positions were lost during sync or entry execution."
                )

            if orphaned_in_positions:
                logger.error(
                    f"[POSITION_SYNC_VALIDATE] CRITICAL: {len(orphaned_in_positions)} symbols have positions but NO trades: "
                    f"{', '.join(sorted(orphaned_in_positions)[:10])}{'...' if len(orphaned_in_positions) > 10 else ''}. "
                    f"Positions orphaned from trades (data integrity issue)."
                )

            if is_valid:
                logger.info(
                    f"[POSITION_SYNC_VALIDATE] Positions validated: "
                    f"{len(position_symbols)} symbols, {open_count} total positions match trades perfectly"
                )
            else:
                logger.critical(
                    f"[POSITION_SYNC_VALIDATE] VALIDATION FAILED: "
                    f"Missing positions: {len(missing_in_positions)}, Orphaned positions: {len(orphaned_in_positions)}"
                )

            return is_valid

    except Exception as e:
        logger.error(f"[POSITION_SYNC_VALIDATE] Validation failed: {e}")
        return False
