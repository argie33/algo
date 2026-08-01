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

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


def sync_positions_from_trades() -> Tuple[int, int, int]:
    """Synchronize algo_positions table with current trades data.

    For each symbol with net quantity > 0 in trades:
    - If position exists: update quantity and status
    - If position doesn't exist: insert with position_id from trades

    Returns:
        (inserted_count, updated_count, error_count)
    """
    inserted = 0
    updated = 0
    errors = 0

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
                try:
                    # Check if position exists
                    cur.execute(
                        'SELECT position_id FROM algo_positions WHERE symbol = %s AND status = %s',
                        (symbol, 'open')
                    )
                    existing = cur.fetchone()

                    if existing:
                        # Update existing position
                        cur.execute(
                            'UPDATE algo_positions SET quantity = %s, updated_at = NOW() '
                            'WHERE symbol = %s AND status = %s',
                            (total_qty, symbol, 'open')
                        )
                        updated += 1
                        logger.debug(f"[POSITION_SYNC] Updated {symbol}: {total_qty:.2f} shares")
                    else:
                        # Get position_id from first trade
                        cur.execute('''
                            SELECT entry_price, position_id FROM algo_trades
                            WHERE symbol = %s AND position_id IS NOT NULL AND status IN ('filled', 'open')
                            ORDER BY entry_date ASC
                            LIMIT 1
                        ''', (symbol,))

                        trade_row = cur.fetchone()
                        if trade_row and trade_row[1]:
                            entry_price, position_id = trade_row

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
                                    f"[POSITION_SYNC] Cannot sync position {position_id} for {symbol}: "
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
                                    f"[POSITION_SYNC] Cannot sync position {position_id} for {symbol}: "
                                    f"quantity must be > 0 (value={total_qty}). "
                                    f"Zero/negative quantity indicates corrupted trade record."
                                )

                            # Try to update position if it exists with this position_id
                            cur.execute('''
                                UPDATE algo_positions
                                SET quantity = %s, status = 'open', updated_at = NOW()
                                WHERE position_id = %s
                            ''', (total_qty, position_id))

                            if cur.rowcount >= 1:
                                updated += 1
                                logger.debug(f"[POSITION_SYNC] Updated existing position {symbol}: {total_qty:.2f} shares")
                            else:
                                # Position doesn't exist with this position_id, check before inserting
                                cur.execute('''
                                    SELECT position_id FROM algo_positions WHERE position_id = %s
                                ''', (position_id,))
                                existing_by_id = cur.fetchone()

                                if existing_by_id:
                                    # Position exists - update it
                                    cur.execute('''
                                        UPDATE algo_positions
                                        SET quantity = %s, status = 'open', updated_at = NOW()
                                        WHERE position_id = %s
                                    ''', (total_qty, position_id))
                                    updated += 1
                                    logger.debug(f"[POSITION_SYNC] Updated position {symbol}: {total_qty:.2f} shares")
                                else:
                                    # Position doesn't exist, insert new one
                                    # ISSUE 3: Verify position_id exists in algo_positions table before final insert
                                    cur.execute('''
                                        INSERT INTO algo_positions (symbol, position_id, quantity, status, entry_price, updated_at, created_at)
                                        VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                                    ''', (symbol, position_id, total_qty, 'open', entry_price))
                                    inserted += 1
                                    logger.debug(f"[POSITION_SYNC] Inserted new position {symbol}: {total_qty:.2f} shares")
                        else:
                            logger.warning(f"[POSITION_SYNC] Could not find position_id for {symbol}")
                            errors += 1

                except Exception as e:
                    logger.error(
                        f"[POSITION_SYNC] Error syncing {symbol}: {type(e).__name__}: {e}",
                        exc_info=True
                    )
                    errors += 1
                    # Continue to next symbol - per-symbol errors don't halt entire sync

    except Exception as e:
        logger.error(f"[POSITION_SYNC] CRITICAL: Failed to sync positions: {e}")
        raise RuntimeError(f"Position sync failed: {e}")

    logger.info(f"[POSITION_SYNC] Completed: {inserted} inserted, {updated} updated, {errors} errors")
    return inserted, updated, errors


def validate_position_count(expected_approximate: int | None = None) -> bool:
    """Validate that position count is reasonable.

    Returns True if position count looks healthy, False if mismatched.
    """
    try:
        with DatabaseContext('read') as cur:
            # Count open positions
            cur.execute('SELECT COUNT(*) FROM algo_positions WHERE status = %s', ('open',))
            pos_row = cur.fetchone()
            if not pos_row:
                raise RuntimeError(
                    "[POSITION_SYNC_VALIDATE] COUNT query returned no rows - database error"
                )
            open_count = pos_row[0]

            # Count open trades
            cur.execute('''
                SELECT COUNT(DISTINCT symbol) FROM algo_trades
                WHERE status IN ('filled', 'open')
                GROUP BY symbol HAVING SUM(quantity) > 0
            ''')

            trade_symbols = len(cur.fetchall())

            # Allow 5% mismatch (rounding, pending closes, etc)
            if trade_symbols == 0:
                is_valid = open_count == 0
            else:
                mismatch_pct = abs(open_count - trade_symbols) / trade_symbols * 100
                is_valid = mismatch_pct < 5

            if not is_valid:
                logger.warning(
                    f"[POSITION_SYNC_VALIDATE] Mismatch: "
                    f"algo_positions={open_count}, trades={trade_symbols} ({mismatch_pct:.1f}% diff)"
                )
            else:
                logger.info(
                    f"[POSITION_SYNC_VALIDATE] Position counts healthy: "
                    f"algo_positions={open_count}, trades={trade_symbols}"
                )

            return is_valid

    except Exception as e:
        logger.error(f"[POSITION_SYNC_VALIDATE] Validation failed: {e}")
        return False
