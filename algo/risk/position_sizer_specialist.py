#!/usr/bin/env python3
"""Position Sizer Specialist - Extract position sizing logic (Feature Envy fix)."""

from decimal import Decimal
from typing import Any


class PositionSizerSpecialist:
    """Handles position sizing calculations independently."""

    def __init__(self, config: Any) -> None:
        """Initialize with config."""
        self.config = config
        self.base_risk_pct = float(config.get("base_risk_pct", 0.75))
        self.max_position_size_pct = float(config.get("max_position_size_pct", 6.3))

    def calculate_shares(
        self,
        portfolio_value: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
    ) -> int:
        """Calculate optimal share size based on risk parameters.

        Args:
            portfolio_value: Total portfolio value
            entry_price: Entry price
            stop_loss: Stop loss price

        Returns:
            Number of shares to trade
        """
        risk_amount = float(portfolio_value) * (self.base_risk_pct / 100)
        price_diff = float(entry_price) - float(stop_loss)

        if price_diff <= 0:
            raise ValueError(
                f"CRITICAL: Invalid stop loss configuration. "
                f"Entry price ${entry_price:.2f} <= stop loss ${stop_loss:.2f}. "
                f"Stop loss must be below entry price. Cannot calculate valid risk per share. "
                f"Check position_sizer_specialist configuration."
            )

        shares = int(risk_amount / price_diff)
        max_shares = int((float(portfolio_value) * self.max_position_size_pct / 100) / float(entry_price))

        return min(shares, max_shares)

    def validate_position_size(self, shares: int, portfolio_value: Decimal, entry_price: Decimal) -> bool:
        """Validate position size against limits."""
        position_value = shares * float(entry_price)
        position_pct = (position_value / float(portfolio_value)) * 100
        return position_pct <= self.max_position_size_pct
