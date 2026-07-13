#!/usr/bin/env python3
"""Position Sizer Specialist - Extract position sizing logic (Feature Envy fix)."""

from decimal import Decimal
from typing import Any

from utils.test_data_detector import TestDataDetector


class PositionSizerSpecialist:
    """Handles position sizing calculations independently."""

    def __init__(self, config: Any) -> None:
        self.config = config
        base_risk_val = config.get("base_risk_pct")
        if base_risk_val is None:
            raise ValueError(
                "CRITICAL: base_risk_pct config missing. "
                "Cannot initialize PositionSizerSpecialist without explicit base risk percentage."
            )
        max_size_val = config.get("max_position_size_pct")
        if max_size_val is None:
            raise ValueError(
                "CRITICAL: max_position_size_pct config missing. "
                "Cannot initialize PositionSizerSpecialist without explicit max position size threshold."
            )
        self.base_risk_pct = float(base_risk_val)
        self.max_position_size_pct = float(max_size_val)

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

        Raises:
            RuntimeError: If test/mock data markers detected in portfolio_value
        """
        TestDataDetector.assert_not_test_data(
            {"portfolio_value": portfolio_value}, location="PositionSizerSpecialist.calculate_shares"
        )

        # CRITICAL: Validate absolute price values before any calculation
        entry_price_float = float(entry_price)
        stop_loss_float = float(stop_loss)
        portfolio_value_float = float(portfolio_value)

        if entry_price_float <= 0:
            raise ValueError(
                f"CRITICAL: Invalid entry price ${entry_price_float}. "
                f"Entry price must be positive. Cannot calculate position size with invalid price."
            )

        if stop_loss_float < 0:
            raise ValueError(
                f"CRITICAL: Invalid stop loss price ${stop_loss_float}. "
                f"Stop loss must be non-negative. Cannot calculate position size with invalid price."
            )

        if portfolio_value_float <= 0:
            raise ValueError(
                f"CRITICAL: Invalid portfolio value ${portfolio_value_float}. "
                f"Portfolio value must be positive. Cannot calculate position size."
            )

        risk_amount = portfolio_value_float * (self.base_risk_pct / 100)
        price_diff = entry_price_float - stop_loss_float

        if price_diff <= 0:
            raise ValueError(
                f"CRITICAL: Invalid stop loss configuration. "
                f"Entry price ${entry_price_float:.2f} <= stop loss ${stop_loss_float:.2f}. "
                f"Stop loss must be below entry price. Cannot calculate valid risk per share. "
                f"Check position_sizer_specialist configuration."
            )

        shares = int(risk_amount / price_diff)
        max_shares = int((portfolio_value_float * self.max_position_size_pct / 100) / entry_price_float)

        return min(shares, max_shares)

    def validate_position_size(self, shares: int, portfolio_value: Decimal, entry_price: Decimal) -> bool:
        entry_price_float = float(entry_price)
        portfolio_value_float = float(portfolio_value)

        # CRITICAL: Validate inputs before calculation
        if entry_price_float <= 0 or portfolio_value_float <= 0 or shares < 0:
            raise ValueError(
                f"CRITICAL: Invalid position parameters for validation: "
                f"shares={shares}, entry_price=${entry_price_float}, portfolio_value=${portfolio_value_float}. "
                f"All must be positive (or zero shares). Cannot validate position."
            )

        position_value = shares * entry_price_float
        position_pct = (position_value / portfolio_value_float) * 100
        return position_pct <= self.max_position_size_pct
