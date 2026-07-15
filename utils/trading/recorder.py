#!/usr/bin/env python3
"""Trade Recorder - logs executed trades to algo_trades and algo_positions tables.

Provides a simple interface for recording trades as they're executed by the orchestrator.
Maintains position state and trade history for analysis and compliance.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg2

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class TradeRecorder:
    """Records executed trades and maintains position state in database."""

    def record_entry(
        self,
        symbol: str,
        entry_date: date,
        entry_price: float,
        quantity: int,
        signal_type: str,
        reason: str = "",
        portfolio_allocation: float | None = None,
    ) -> bool:
        """Record a buy/entry trade.

        Args:
            symbol: Stock symbol
            entry_date: Date of entry
            entry_price: Entry price ($/share)
            quantity: Shares purchased
            signal_type: Signal that triggered entry (e.g., "minervini_trend_follow")
            reason: Optional narrative reason for entry
            portfolio_allocation: % of portfolio allocated to this position

        Returns:
            True if recorded successfully
        """
        try:
            with DatabaseContext("write") as cursor:
                # Insert trade record
                cursor.execute(
                    """
                    INSERT INTO algo_trades (
                        symbol, entry_date, entry_price, quantity, signal_type,
                        reason, portfolio_allocation, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (symbol, entry_date) DO UPDATE SET
                        entry_price = %s, quantity = %s, updated_at = CURRENT_TIMESTAMP
                """,
                    (
                        symbol,
                        entry_date,
                        Decimal(str(entry_price)),
                        quantity,
                        signal_type,
                        reason,
                        (Decimal(str(portfolio_allocation)) if portfolio_allocation else None),
                        Decimal(str(entry_price)),
                        quantity,
                    ),
                )

                # Insert or update position
                cursor.execute(
                    """
                    INSERT INTO algo_positions (
                        symbol, entry_date, entry_price, current_price, quantity,
                        status, unrealized_pnl, stage_in_exit_plan, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 'OPEN', 0, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (symbol) DO UPDATE SET
                        entry_date = %s,
                        entry_price = %s,
                        quantity = %s,
                        status = 'OPEN',
                        stage_in_exit_plan = 'active',
                        updated_at = CURRENT_TIMESTAMP
                """,
                    (
                        symbol,
                        entry_date,
                        Decimal(str(entry_price)),
                        Decimal(str(entry_price)),
                        quantity,
                        entry_date,
                        Decimal(str(entry_price)),
                        quantity,
                    ),
                )

                logger.info(f"Recorded entry: {symbol} {quantity}sh @ ${entry_price} on {entry_date}")
                return True

        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"Failed to record entry for {symbol}: {e}. Cannot proceed without recording trade entry."
            ) from e

    def record_exit(
        self,
        symbol: str,
        exit_date: date,
        exit_price: float,
        quantity: int | None = None,
        reason: str = "",
    ) -> bool:
        """Record a sell/exit trade.

        Args:
            symbol: Stock symbol
            exit_date: Date of exit
            exit_price: Exit price ($/share)
            quantity: Shares sold (if None, uses remaining position quantity)
            reason: Optional narrative reason for exit

        Returns:
            True if recorded successfully
        """
        try:
            with DatabaseContext("write") as cursor:
                # Get existing position if quantity not specified
                if quantity is None:
                    cursor.execute(
                        "SELECT quantity FROM algo_positions WHERE symbol = %s",
                        (symbol,),
                    )
                    pos = cursor.fetchone()
                    if pos:
                        quantity = pos[0]
                    else:
                        logger.warning(f"No open position for {symbol}, cannot record exit")
                        return False

                # Get entry price and entry date for P&L calculation and duration
                cursor.execute(
                    """
                    SELECT entry_price, entry_date FROM algo_trades
                    WHERE symbol = %s AND exit_date IS NULL
                    ORDER BY entry_time DESC LIMIT 1
                """,
                    (symbol,),
                )
                entry_row = cursor.fetchone()
                if not entry_row or entry_row[0] is None:
                    logger.error(f"Cannot record exit for {symbol}: no open entry found in database")
                    return False

                entry_price = float(entry_row[0])
                entry_date = entry_row[1]

                # Validate entry price
                if entry_price <= 0:
                    logger.error(f"Cannot record exit for {symbol}: invalid entry price {entry_price}")
                    return False

                # Calculate P&L
                pnl = (exit_price - entry_price) * quantity
                if entry_price <= 0:
                    logger.error(
                        f"[RECORDER CRITICAL] Cannot calculate P&L percent for {symbol}: "
                        f"entry_price is {entry_price} (must be positive)"
                    )
                    raise ValueError(
                        f"Cannot record trade P&L: entry price is invalid ({entry_price}). "
                        f"Trade records must have valid entry prices for P&L calculation."
                    )
                pnl_pct = (exit_price - entry_price) / entry_price * 100

                # Calculate trade duration
                trade_duration_days = (exit_date - entry_date).days

                # Update trade record (most recent entry for this symbol)
                cursor.execute(
                    """
                    UPDATE algo_trades
                    SET exit_date = %s, exit_price = %s, profit_loss_dollars = %s, profit_loss_pct = %s,
                        exit_reason = %s, trade_duration_days = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = (
                        SELECT id FROM algo_trades
                        WHERE symbol = %s AND exit_date IS NULL
                        ORDER BY entry_time DESC LIMIT 1
                    )
                """,
                    (
                        exit_date,
                        Decimal(str(exit_price)),
                        Decimal(str(pnl)),
                        Decimal(str(pnl_pct)),
                        reason,
                        trade_duration_days,
                        symbol,
                    ),
                )

                # Close position
                cursor.execute(
                    """
                    UPDATE algo_positions
                    SET status = 'CLOSED', current_price = %s, unrealized_pnl = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = %s
                """,
                    (Decimal(str(exit_price)), Decimal(str(pnl)), symbol),
                )

                logger.info(
                    f"Recorded exit: {symbol} {quantity}sh @ ${exit_price} on {exit_date} "
                    f"(P&L: ${pnl:.2f} / {pnl_pct:.1f}%)"
                )
                return True

        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"Failed to record exit for {symbol}: {e}. Cannot proceed without recording trade exit."
            ) from e

    def update_position_price(self, symbol: str, current_price: float) -> bool:
        """Update current price for open position (for unrealized P&L tracking).

        Args:
            symbol: Stock symbol
            current_price: Current market price

        Returns:
            True if updated successfully
        """
        try:
            with DatabaseContext("write") as cursor:
                cursor.execute(
                    """
                    UPDATE algo_positions
                    SET current_price = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = %s AND status = 'OPEN'
                """,
                    (Decimal(str(current_price)), symbol),
                )

                return True

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"Failed to update price for {symbol}: {e}. Cannot proceed without updating position price."
            ) from e

    def get_open_positions(self) -> list[dict[str, Any]]:
        try:
            with DatabaseContext("read") as cursor:
                cursor.execute("""
                    SELECT symbol, quantity, entry_price, current_price, entry_date,
                           (current_price - entry_price) * quantity as unrealized_pnl
                    FROM algo_positions
                    WHERE status = 'OPEN'
                    ORDER BY entry_date DESC
                """)

                rows = cursor.fetchall()
                return [
                    {
                        "symbol": r[0],
                        "quantity": r[1],
                        "entry_price": float(r[2]),
                        "current_price": float(r[3]),
                        "entry_date": r[4],
                        "unrealized_pnl": float(r[5]) if r[5] else 0,
                    }
                    for r in rows
                ]

        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(
                f"Failed to get open positions: {e}. Cannot proceed without accurate position tracking."
            ) from e
