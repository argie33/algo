"""Mock Alpaca broker for end-to-end testing without real API calls.

Used for validating the complete trading pipeline works correctly.
In production, real AlpacaBrokerAdapter handles actual trades.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


class MockAlpacaBroker:
    """Mock Alpaca broker that simulates API responses without hitting real servers."""

    def __init__(self, initial_capital: float = 100_000) -> None:
        self.cash = Decimal(str(initial_capital))
        self.portfolio_value = Decimal(str(initial_capital))
        self.positions: dict[str, Any] = {}  # symbol -> {qty, entry_price, current_price}
        self.orders: list[dict[str, Any]] = []  # list of executed orders
        self.account_equity = Decimal(str(initial_capital))

    def get_account(self) -> dict[str, Any]:
        """Mock get_account response."""
        return {
            "cash": float(self.cash),
            "portfolio_value": float(self.portfolio_value),
            "buying_power": float(self.cash * 4),  # 4x leverage in paper
            "equity": float(self.account_equity),
        }

    def get_positions(self) -> list[dict[str, Any]]:
        """Mock get_positions response."""
        result = []
        for symbol, pos_data in self.positions.items():
            result.append(
                {
                    "symbol": symbol,
                    "qty": pos_data["qty"],
                    "avg_fill_price": float(pos_data["entry_price"]),
                    "current_price": float(pos_data["current_price"]),
                    "market_value": float(Decimal(str(pos_data["qty"])) * pos_data["current_price"]),
                    "unrealized_pl": float(
                        (pos_data["current_price"] - pos_data["entry_price"]) * Decimal(str(pos_data["qty"]))
                    ),
                }
            )
        return result

    def submit_order(
        self,
        symbol: str,
        qty: int,
        side: str,  # "buy" or "sell"
        type_: str = "market",
        time_in_force: str = "day",
    ) -> dict[str, Any]:
        """Mock submit_order - simulate trade execution."""
        # For testing, use current price of $100 (arbitrary)
        current_price = Decimal("100.00")

        if side == "buy":
            cost = Decimal(str(qty)) * current_price
            if cost > self.cash:
                raise ValueError(f"Insufficient buying power: need ${cost}, have ${self.cash}")

            self.cash -= cost
            if symbol in self.positions:
                self.positions[symbol]["qty"] += qty
            else:
                self.positions[symbol] = {
                    "qty": qty,
                    "entry_price": current_price,
                    "current_price": current_price,
                }

            logger.info(f"[MOCK_BROKER] BUY: {qty} x {symbol} @ ${current_price} = ${cost}")

        elif side == "sell":
            if symbol not in self.positions or self.positions[symbol]["qty"] < qty:
                raise ValueError(f"Cannot sell {qty} of {symbol} - insufficient shares")

            proceeds = Decimal(str(qty)) * current_price
            self.positions[symbol]["qty"] -= qty
            if self.positions[symbol]["qty"] == 0:
                del self.positions[symbol]
            self.cash += proceeds

            logger.info(f"[MOCK_BROKER] SELL: {qty} x {symbol} @ ${current_price} = ${proceeds}")

        # Create mock order response
        order = {
            "id": f"mock_order_{len(self.orders) + 1}",
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "type": type_,
            "time_in_force": time_in_force,
            "filled_qty": qty,
            "filled_avg_price": float(current_price),
            "status": "filled",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "filled_at": datetime.now(timezone.utc).isoformat(),
        }

        self.orders.append(order)
        return order

    def get_orders(self, status: str = "all") -> list[dict[str, Any]]:
        """Mock get_orders - return all submitted orders."""
        if status == "all":
            return self.orders
        return [o for o in self.orders if o["status"] == status]

    def cancel_order(self, order_id: str) -> None:
        """Mock cancel_order."""
        for order in self.orders:
            if order["id"] == order_id:
                order["status"] = "canceled"
                logger.info(f"[MOCK_BROKER] CANCEL: Order {order_id}")
                return
        raise ValueError(f"Order {order_id} not found")
