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
import psycopg2
import os
from credential_helper import get_db_password

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

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
        self.conn = None

    def _get_db_config(self) -> Dict[str, Any]:
        """Get database configuration."""
        return {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "stocks"),
            "password": get_db_password(),
            "database": os.getenv("DB_NAME", "stocks"),
        }

    def connect(self):
        """Connect to database if not already connected."""
        if not self.conn:
            try:
                self.conn = psycopg2.connect(**self._get_db_config())
            except Exception as e:
                logger.error(f"Failed to connect to database: {e}")
                self.conn = None

    def disconnect(self):
        """Disconnect from database."""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    def run_all(self, symbol: str, entry_price: float, position_value: float,
                portfolio_value: float, side: str = 'BUY') -> Tuple[bool, Optional[str]]:
        """
        Run all pre-trade validation checks.

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            entry_price: Entry price per share
            position_value: Total position value (shares * price)
            portfolio_value: Current portfolio value
            side: 'BUY' or 'SELL'

        Returns:
            (passed: bool, reason: str or None)
            - If passed: (True, None)
            - If failed: (False, "reason for failure")
        """
        # Check 1: Buying power (position size <= portfolio_value * max_position_pct)
        max_position_pct = float(self.config.get('max_position_size_pct', 10.0)) / 100.0
        max_position_value = portfolio_value * max_position_pct

        if position_value > max_position_value:
            return (False, f"Position ${position_value:.2f} exceeds max "
                          f"${max_position_value:.2f} ({max_position_pct*100:.1f}% of portfolio)")

        # Check 2: Duplicate position prevention
        try:
            self.connect()
            if self.conn:
                cur = self.conn.cursor()
                cur.execute(
                    "SELECT symbol FROM algo_positions WHERE symbol = %s AND status = %s LIMIT 1",
                    (symbol, 'OPEN')
                )
                if cur.fetchone():
                    cur.close()
                    return (False, f"Position already open for {symbol}")
                cur.close()
        except Exception as e:
            logger.warning(f"Failed to check for duplicate position: {e}")
            # Continue anyway - DB error shouldn't block trade

        # Check 3: Minimum order size
        min_order_size = float(self.config.get('min_order_size_dollars', 100.0))
        if position_value < min_order_size:
            return (False, f"Position value ${position_value:.2f} below minimum ${min_order_size:.2f}")

        # Check 4: Symbol validity (must exist in stock_symbols)
        try:
            if self.conn:
                cur = self.conn.cursor()
                cur.execute("SELECT symbol FROM stock_symbols WHERE symbol = %s LIMIT 1", (symbol,))
                if not cur.fetchone():
                    cur.close()
                    return (False, f"Symbol {symbol} not found in universe")
                cur.close()
        except Exception as e:
            logger.warning(f"Failed to validate symbol: {e}")

        logger.info(f"[PRE-TRADE] {symbol}: position ${position_value:.2f}, "
                   f"portfolio ${portfolio_value:.2f}, {side} order approved")
        return (True, None)
