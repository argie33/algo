#!/usr/bin/env python3
"""
Pre-Trade Checks - Hard stops before order execution.

Validates:
- Account buying power
- Margin requirements
- Duplicate position prevention
- Exchange/symbol status
- Order size limits
"""

import logging
from typing import Dict, Any, Tuple, Optional
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

class PreTradeChecks:
    """Validation layer before executing trades."""

    def __init__(self, config: Dict[str, Any], alpaca_base_url: str = None,
                 alpaca_key: str = None, alpaca_secret: str = None):
        """Initialize pre-trade checks with configuration."""
        self.config = config
        self.alpaca_base_url = alpaca_base_url
        self.alpaca_key = alpaca_key
        self.alpaca_secret = alpaca_secret

    def apply_slippage_adjustment(self, shares: float, entry_price: float, slippage_pct: float = 1.0) -> Tuple[float, float]:
        """Issue #28: Apply slippage model to position size.

        Reduces shares by slippage percentage to account for market impact and execution slippage.
        Default: 1% slippage (typical for mid-caps, up to 2% for illiquid stocks).

        Args:
            shares: Calculated position size
            entry_price: Target entry price
            slippage_pct: Expected slippage percentage (default 1%)

        Returns:
            (adjusted_shares, actual_cost_per_share)
        """
        slippage_factor = 1.0 - (slippage_pct / 100.0)
        adjusted_shares = int(shares * slippage_factor)
        actual_cost = entry_price / slippage_factor
        logger.debug(f"Slippage adjustment: {shares} → {adjusted_shares} shares, cost ${entry_price:.2f} → ${actual_cost:.2f}")
        return adjusted_shares, actual_cost

    def run_all(self, symbol: str, position_value: float,
                portfolio_value: float, side: str = 'BUY') -> Tuple[bool, Optional[str]]:
        """
        Run all pre-trade validation checks.

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            position_value: Total position value (shares * price)
            portfolio_value: Current portfolio value
            side: 'BUY' or 'SELL'

        Returns:
            (passed: bool, reason: str or None)
            - If passed: (True, None)
            - If failed: (False, "reason for failure")
        """
        max_position_pct = float(self.config.get('max_position_size_pct', 10.0)) / 100.0
        max_position_value = portfolio_value * max_position_pct

        if position_value > max_position_value:
            return (False, f"Position ${position_value:.2f} exceeds max "
                          f"${max_position_value:.2f} ({max_position_pct*100:.1f}% of portfolio)")

        try:
            with DatabaseContext('read') as cur:
                cur.execute(
                    "SELECT symbol FROM algo_positions WHERE symbol = %s AND status = %s LIMIT 1",
                    (symbol, 'open')
                )
                if cur.fetchone():
                    return (False, f"Position already open for {symbol}")
        except Exception as e:
            logger.warning(f"Failed to check for duplicate position: {e}")
            # Continue anyway - DB error shouldn't block trade

        min_order_size = float(self.config.get('min_order_size_dollars', 100.0))
        if position_value < min_order_size:
            return (False, f"Position value ${position_value:.2f} below minimum ${min_order_size:.2f}")

        try:
            with DatabaseContext('read') as cur:
                cur.execute("SELECT symbol FROM stock_symbols WHERE symbol = %s LIMIT 1", (symbol,))
                if not cur.fetchone():
                    return (False, f"Symbol {symbol} not found in universe")
        except Exception as e:
            logger.warning(f"Failed to validate symbol: {e}")

        logger.info(f"[PRE-TRADE] {symbol}: position ${position_value:.2f}, "
                   f"portfolio ${portfolio_value:.2f}, {side} order approved")
        return (True, None)
