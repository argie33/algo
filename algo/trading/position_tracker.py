#!/usr/bin/env python3
"""Position Tracker - Manage position lifecycle and state."""

import logging
from decimal import Decimal
from typing import Any

from utils.trading import PositionStatus


logger = logging.getLogger(__name__)


class PositionTracker:
    """Tracks position state and lifecycle throughout entry, adjustment, and exit."""

    def __init__(self, config: Any) -> None:
        """Initialize position tracker."""
        self.config = config
        self.positions: dict[str, dict[str, Any]] = {}

    def create_position(self, symbol: str, entry_price: Decimal, shares: int, stop_loss: Decimal) -> None:
        """Record new position."""
        self.positions[symbol] = {
            "symbol": symbol,
            "entry_price": entry_price,
            "shares": shares,
            "stop_loss": stop_loss,
            "status": PositionStatus.OPEN,
            "exit_price": None,
            "exit_shares": 0,
            "pnl": None,
        }
        logger.info(f"[POSITION_CREATED] {symbol}: {shares}sh @ ${entry_price}, stop=${stop_loss}")

    def update_stop_loss(self, symbol: str, new_stop: Decimal) -> None:
        """Update position stop loss."""
        if symbol in self.positions:
            old_stop = self.positions[symbol]["stop_loss"]
            self.positions[symbol]["stop_loss"] = new_stop
            logger.info(f"[STOP_UPDATED] {symbol}: ${old_stop} → ${new_stop}")

    def record_partial_exit(self, symbol: str, exit_price: Decimal, exit_shares: int, pnl: Decimal) -> None:
        """Record partial position exit."""
        if symbol in self.positions:
            pos = self.positions[symbol]
            pos["exit_price"] = exit_price
            pos["exit_shares"] += exit_shares
            pos["pnl"] = pnl
            if pos["exit_shares"] >= pos["shares"]:
                pos["status"] = PositionStatus.CLOSED
            logger.info(f"[EXIT_RECORDED] {symbol}: {exit_shares}sh @ ${exit_price}, PnL=${pnl}")

    def get_position(self, symbol: str) -> dict[str, Any] | None:
        """Get position details."""
        return self.positions.get(symbol)

    def get_remaining_shares(self, symbol: str) -> int:
        """Get remaining open shares."""
        if symbol in self.positions:
            pos = self.positions[symbol]
            return pos["shares"] - pos["exit_shares"]
        return 0

    def close_position(self, symbol: str) -> None:
        """Mark position as closed."""
        if symbol in self.positions:
            self.positions[symbol]["status"] = PositionStatus.CLOSED
            logger.info(f"[POSITION_CLOSED] {symbol}")
