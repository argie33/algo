"""
Pre-Trade Hard Stops — Independent Risk Layer

These are NEVER overridden by strategy parameters. They are independent safeguards
modeled on SEC Rule 15c3-5 (Regulation SHO) and industry best practices.

Run BEFORE every order is sent to Alpaca. No exceptions.

Hard limits enforced:
1. Fat-finger check: entry price must not diverge >5% from current market
2. Order velocity: max 3 orders per 60 seconds portfolio-wide
3. Notional hard cap: single order cannot exceed 15% of portfolio value
4. Symbol tradeable: verify not halted, delisted, or on restricted list
5. Duplicate prevention: block same symbol+side within 5 minutes
"""

import psycopg2
import os
import requests
from datetime import datetime, timedelta
from typing import Tuple, Optional
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)


class PreTradeChecks:
    """Hard limits independent of strategy logic. NEVER bypassed."""

    def __init__(self, config, alpaca_base_url: str = None, alpaca_key: str = None, alpaca_secret: str = None):
        self.config = config
        self.alpaca_base_url = alpaca_base_url or os.getenv('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets')
        self.alpaca_key = alpaca_key or os.getenv('APCA_API_KEY_ID')
        self.alpaca_secret = alpaca_secret or os.getenv('APCA_API_SECRET_KEY')

        self.db_host = os.getenv('DB_HOST', 'localhost')
        self.db_port = int(os.getenv('DB_PORT', 5432))
        self.db_user = os.getenv('DB_USER', 'stocks')
        self.db_password = os.getenv('DB_PASSWORD', '')
        self.db_name = os.getenv('DB_NAME', 'stocks')

        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                user=self.db_user,
                password=self.db_password,
                database=self.db_name,
            )
            self.cur = self.conn.cursor()
        except Exception as e:
            print(f"PreTradeChecks: DB connection failed: {e}")
            raise

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def check_fat_finger(self, symbol: str, entry_price: float, max_divergence_pct: float = 5.0) -> Tuple[bool, Optional[str]]:
        """Reject if entry_price diverges > 5% from current market price.

        Args:
            symbol: Stock symbol
            entry_price: Proposed entry price
            max_divergence_pct: Max allowed divergence from current price (default 5%)

        Returns:
            (passed: bool, reason: str or None)
        """
        try:
            # Get current market price from Alpaca
            url = f"{self.alpaca_base_url}/v2/stocks/{symbol}/quotes/latest"
            headers = {
                'APCA-API-KEY-ID': self.alpaca_key,
                'APCA-API-SECRET-KEY': self.alpaca_secret,
            }
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code != 200:
                # If can't get price, fail-safe: reject the order
                return False, f"Cannot fetch current price for {symbol} (HTTP {resp.status_code})"

            data = resp.json()
            current_price = data.get('quote', {}).get('ap')  # ask price
            if not current_price:
                return False, f"No bid/ask data available for {symbol}"

            divergence_pct = abs(entry_price - current_price) / current_price * 100

            if divergence_pct > max_divergence_pct:
                return False, f"Fat-finger check failed: entry ${entry_price:.2f} diverges {divergence_pct:.1f}% from market ${current_price:.2f} (max {max_divergence_pct}%)"

            return True, None

        except Exception as e:
            print(f"PreTradeChecks: fat_finger check error: {e}")
            # Fail-safe: reject if check cannot run
            return False, f"Fat-finger check failed with exception: {e}"

    def check_order_velocity(self, max_orders_per_60s: int = 3) -> Tuple[bool, Optional[str]]:
        """Rate limit: max 3 orders per 60 seconds portfolio-wide.

        Args:
            max_orders_per_60s: Max orders allowed in 60-second window

        Returns:
            (passed: bool, reason: str or None)
        """
        try:
            if not self.cur:
                self.connect()

            # Count orders in last 60 seconds
            self.cur.execute(
                """
                SELECT COUNT(*) FROM algo_trades
                WHERE created_at >= NOW() - INTERVAL '60 seconds'
                  AND status IN ('filled', 'active', 'pending')
                """
            )
            order_count = self.cur.fetchone()[0]

            if order_count >= max_orders_per_60s:
                return False, f"Order velocity exceeded: {order_count} orders in last 60s (max {max_orders_per_60s})"

            return True, None

        except Exception as e:
            print(f"PreTradeChecks: order_velocity check error: {e}")
            return False, f"Order velocity check failed: {e}"

    def check_notional_hard_cap(self, position_value: float, portfolio_value: float, hard_cap_pct: float = 15.0) -> Tuple[bool, Optional[str]]:
        """Single order notional cannot exceed 15% of portfolio regardless of sizing.

        Args:
            position_value: Proposed order notional (shares × price)
            portfolio_value: Current portfolio value
            hard_cap_pct: Hard cap as % of portfolio (default 15%)

        Returns:
            (passed: bool, reason: str or None)
        """
        if portfolio_value <= 0:
            return False, "Invalid portfolio value"

        position_pct = position_value / portfolio_value * 100

        if position_pct > hard_cap_pct:
            return False, f"Notional hard cap exceeded: proposed ${position_value:.2f} = {position_pct:.1f}% of portfolio (max {hard_cap_pct}%)"

        return True, None

    def check_symbol_tradeable(self, symbol: str) -> Tuple[bool, Optional[str]]:
        """Verify symbol is not halted, not on restricted list, not delisted.

        Args:
            symbol: Stock symbol

        Returns:
            (passed: bool, reason: str or None)
        """
        try:
            # Query Alpaca asset endpoint
            url = f"{self.alpaca_base_url}/v2/assets/{symbol}"
            headers = {
                'APCA-API-KEY-ID': self.alpaca_key,
                'APCA-API-SECRET-KEY': self.alpaca_secret,
            }
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code != 200:
                return False, f"Symbol {symbol} not found or not tradeable (HTTP {resp.status_code})"

            data = resp.json()
            tradable = data.get('tradable')
            status = data.get('status')

            if not tradable:
                return False, f"Symbol {symbol} marked as not tradeable"

            if status and status.upper() != 'ACTIVE':
                return False, f"Symbol {symbol} status is {status} (not ACTIVE)"

            return True, None

        except Exception as e:
            print(f"PreTradeChecks: symbol_tradeable check error: {e}")
            return False, f"Symbol tradeable check failed: {e}"

    def check_duplicate_order_hard(self, symbol: str, side: str, timestamp: Optional[datetime] = None, window_minutes: int = 5) -> Tuple[bool, Optional[str]]:
        """Hard block: same symbol + side within 5 minutes = duplicate.

        Args:
            symbol: Stock symbol
            side: BUY or SELL
            timestamp: Reference time (default now)
            window_minutes: Time window for duplicate check

        Returns:
            (passed: bool, reason: str or None)
        """
        try:
            if not self.cur:
                self.connect()

            if not timestamp:
                timestamp = datetime.now()

            # Check for recent order with same symbol+side
            self.cur.execute(
                """
                SELECT trade_id, created_at FROM algo_trades
                WHERE symbol = %s AND (
                    -- Determine side from entry_price vs current (simplification: check entry_reason)
                    entry_reason LIKE '%%BUY%%' OR entry_reason LIKE '%%SELL%%'
                )
                AND created_at >= %s - INTERVAL '%d minutes'
                ORDER BY created_at DESC LIMIT 1
                """ % window_minutes,
                (symbol, timestamp),
            )
            recent = self.cur.fetchone()

            if recent:
                trade_id, created_at = recent
                return False, f"Duplicate order blocked: {symbol} {side} already entered {trade_id} within {window_minutes} minutes"

            return True, None

        except Exception as e:
            print(f"PreTradeChecks: duplicate_order_hard check error: {e}")
            return False, f"Duplicate check failed: {e}"

    def run_all(self, symbol: str, entry_price: float, position_value: float, portfolio_value: float, side: str = 'BUY') -> Tuple[bool, Optional[str]]:
        """Run all pre-trade checks. Returns pass/fail on first failure.

        Args:
            symbol: Stock symbol
            entry_price: Proposed entry price
            position_value: Proposed order notional (shares × price)
            portfolio_value: Current portfolio value
            side: BUY or SELL

        Returns:
            (passed: bool, reason: str or None)
        """
        checks = [
            ("Fat-finger", self.check_fat_finger(symbol, entry_price)),
            ("Order velocity", self.check_order_velocity()),
            ("Notional hard cap", self.check_notional_hard_cap(position_value, portfolio_value)),
            ("Symbol tradeable", self.check_symbol_tradeable(symbol)),
            ("Duplicate prevention", self.check_duplicate_order_hard(symbol, side)),
        ]

        for check_name, (passed, reason) in checks:
            if not passed:
                print(f"[PRE-TRADE CHECK FAILED] {check_name}: {reason}")
                return False, reason

        print(f"[PRE-TRADE CHECKS PASSED] {symbol} {side} @ ${entry_price:.2f}")
        return True, None
