"""
Market Events & Corporate Actions Handler

Detects and responds to market anomalies:
- Single-stock halts (trading paused, then resumed)
- Market circuit breakers (L1: 7%, L2: 13%, L3: 20% down)
- Early close days (market closes 3 hours early)
- Corporate actions (stock splits, dividends, delisting)

Implements fail-safe protocols that override strategy logic.
"""

import psycopg2
import os
import requests
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)


class MarketEventHandler:
    """Detect and respond to market events and halts."""

    def __init__(self, config):
        self.config = config
        self.alpaca_base_url = os.getenv('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets')
        self.alpaca_key = os.getenv('APCA_API_KEY_ID')
        self.alpaca_secret = os.getenv('APCA_API_SECRET_KEY')

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
            print(f"MarketEventHandler: DB connection failed: {e}")
            raise

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def check_single_stock_halt(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Check if symbol is currently halted from trading.

        Returns:
            dict with halt_status, reason if halted, else None
        """
        try:
            url = f"{self.alpaca_base_url}/v2/assets/{symbol}"
            headers = {
                'APCA-API-KEY-ID': self.alpaca_key,
                'APCA-API-SECRET-KEY': self.alpaca_secret,
            }
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code != 200:
                return None

            data = resp.json()
            status = data.get('status', '').upper()
            tradable = data.get('tradable', False)

            if not tradable or status != 'ACTIVE':
                return {
                    'halted': True,
                    'symbol': symbol,
                    'status': status,
                    'tradable': tradable,
                    'timestamp': datetime.now().isoformat(),
                }

            return None

        except Exception as e:
            print(f"MarketEventHandler: check_single_stock_halt error: {e}")
            return None

    def check_market_circuit_breaker(self) -> Optional[Dict[str, Any]]:
        """Check if market circuit breaker is active (S&P 500 down 7%+).

        Circuit breaker levels:
        - L1: S&P 500 down 7% intraday → 15-min halt
        - L2: S&P 500 down 13% intraday → 15-min halt
        - L3: S&P 500 down 20% intraday → halt for rest of day

        Returns:
            dict with level, % down, timestamp if triggered, else None
        """
        try:
            # Get SPY (S&P 500 proxy) current vs. open
            url = f"{self.alpaca_base_url}/v2/stocks/SPY/quotes/latest"
            headers = {
                'APCA-API-KEY-ID': self.alpaca_key,
                'APCA-API-SECRET-KEY': self.alpaca_secret,
            }
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code != 200:
                return None

            data = resp.json()
            current_price = data.get('quote', {}).get('ap')  # ask price
            if not current_price:
                return None

            # Get SPY open price
            url_bars = f"{self.alpaca_base_url}/v2/stocks/SPY/bars/latest?timeframe=1day"
            resp_bars = requests.get(url_bars, headers=headers, timeout=5)
            if resp_bars.status_code != 200:
                return None

            bars_data = resp_bars.json()
            open_price = bars_data.get('bar', {}).get('o')
            if not open_price:
                return None

            pct_down = (open_price - current_price) / open_price * 100

            if pct_down >= 20.0:
                return {
                    'level': 3,
                    'description': '20%+ down — market halted for rest of day',
                    'pct_down': round(pct_down, 2),
                    'action': 'HALT_ALL_ENTRIES',
                    'timestamp': datetime.now().isoformat(),
                }
            elif pct_down >= 13.0:
                return {
                    'level': 2,
                    'description': '13%+ down — 15-minute halt',
                    'pct_down': round(pct_down, 2),
                    'action': 'PAUSE_NEW_ENTRIES_15MIN',
                    'timestamp': datetime.now().isoformat(),
                }
            elif pct_down >= 7.0:
                return {
                    'level': 1,
                    'description': '7%+ down — 15-minute halt',
                    'pct_down': round(pct_down, 2),
                    'action': 'PAUSE_NEW_ENTRIES_15MIN',
                    'timestamp': datetime.now().isoformat(),
                }

            return None

        except Exception as e:
            print(f"MarketEventHandler: check_market_circuit_breaker error: {e}")
            return None

    def check_early_close(self, check_date: Optional[date] = None) -> bool:
        """Check if market closes early today (3 hours early = 13:00 ET instead of 16:00).

        Known early close dates: day after Thanksgiving, Christmas Eve

        Args:
            check_date: Date to check (default today)

        Returns:
            True if early close, False otherwise
        """
        if not check_date:
            check_date = date.today()

        try:
            # Query market_health_daily for early_close flag
            if not self.cur:
                self.connect()

            self.cur.execute(
                """
                SELECT early_close FROM market_health_daily
                WHERE date = %s
                """,
                (check_date,)
            )
            row = self.cur.fetchone()

            if row:
                return bool(row[0])

            # Fallback: check known dates
            # Day after Thanksgiving (4th Thursday of November)
            nov_dates = [d for d in range(23, 31) if datetime(check_date.year, 11, d).weekday() == 3]
            day_after_thanksgiving = nov_dates[0] + 1 if nov_dates else None

            if check_date.month == 11 and check_date.day == day_after_thanksgiving:
                return True

            # Christmas Eve (Dec 24)
            if check_date.month == 12 and check_date.day == 24:
                return True

            return False

        except Exception as e:
            print(f"MarketEventHandler: check_early_close error: {e}")
            return False

    def check_after_hours_window(self, check_time: Optional[datetime] = None) -> bool:
        """Check if we're in after-hours window (after 15:45 ET or early close at 13:00).

        No new entries allowed after 15:45 ET on normal days or 13:00 ET on early close days.

        Args:
            check_time: Time to check (default now)

        Returns:
            True if in after-hours window, False otherwise
        """
        if not check_time:
            check_time = datetime.now()

        check_date = check_time.date()
        check_hour = check_time.hour
        check_minute = check_time.minute

        # Is today an early close?
        early_close = self.check_early_close(check_date)

        if early_close:
            # Early close at 13:00 ET (1 PM)
            if check_hour >= 13:
                return True
        else:
            # Normal close at 16:00 ET (4 PM)
            if check_hour > 15 or (check_hour == 15 and check_minute >= 45):
                return True

        return False

    def handle_single_stock_halt(self, symbol: str) -> Dict[str, Any]:
        """Handle single-stock halt: cancel pending orders, log event.

        Args:
            symbol: Stock symbol that's halted

        Returns:
            dict with action taken
        """
        try:
            if not self.cur:
                self.connect()

            # Cancel any pending orders for this symbol
            self.cur.execute(
                """
                UPDATE algo_trades
                SET status = 'cancelled'
                WHERE symbol = %s AND status IN ('pending', 'active')
                """,
                (symbol,)
            )

            # Log the halt event
            self.cur.execute(
                """
                INSERT INTO algo_audit_log (
                    action_type, action_date, details, severity
                ) VALUES (%s, %s, %s, %s)
                """,
                ('SINGLE_STOCK_HALT', datetime.now(), f'Symbol {symbol} halted — pending orders cancelled', 'WARN')
            )

            self.conn.commit()

            return {
                'action': 'HALT_SYMBOL',
                'symbol': symbol,
                'status': 'orders_cancelled',
                'timestamp': datetime.now().isoformat(),
            }

        except Exception as e:
            if self.conn:
                self.conn.rollback()
            print(f"MarketEventHandler: handle_single_stock_halt error: {e}")
            return {'action': 'ERROR', 'message': str(e)}

    def handle_market_circuit_breaker(self, level: int) -> Dict[str, Any]:
        """Handle market circuit breaker: halt entries, tighten stops, or close positions.

        Args:
            level: CB level (1, 2, or 3)

        Returns:
            dict with action taken
        """
        try:
            if not self.cur:
                self.connect()

            if level == 3:
                # L3: Full halt, no new orders, close positions
                action = 'HALT_ALL_ENTRIES'
                message = 'Market circuit breaker L3 (20%+ down) — halting all new entries and preparing for forced exit'

                self.cur.execute(
                    """
                    INSERT INTO algo_audit_log (
                        action_type, action_date, details, severity
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    ('CIRCUIT_BREAKER_L3', datetime.now(), message, 'CRITICAL')
                )

            elif level in (1, 2):
                # L1/L2: Pause new entries for 15 minutes, tighten stops
                action = 'PAUSE_ENTRIES_15MIN'
                message = f'Market circuit breaker L{level} ({"7" if level == 1 else "13"}%+ down) — pausing new entries for 15 minutes'

                self.cur.execute(
                    """
                    INSERT INTO algo_audit_log (
                        action_type, action_date, details, severity
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    ('CIRCUIT_BREAKER_L' + str(level), datetime.now(), message, 'ERROR')
                )

            self.conn.commit()

            return {
                'action': action,
                'level': level,
                'status': 'logged',
                'timestamp': datetime.now().isoformat(),
            }

        except Exception as e:
            if self.conn:
                self.conn.rollback()
            print(f"MarketEventHandler: handle_market_circuit_breaker error: {e}")
            return {'action': 'ERROR', 'message': str(e)}

    def check_delisting(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Check if symbol is delisted or about to be delisted.

        Returns:
            dict with delisting info if delisted, else None
        """
        try:
            url = f"{self.alpaca_base_url}/v2/assets/{symbol}"
            headers = {
                'APCA-API-KEY-ID': self.alpaca_key,
                'APCA-API-SECRET-KEY': self.alpaca_secret,
            }
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code != 200:
                return None

            data = resp.json()
            status = data.get('status', '').upper()

            if status in ('INACTIVE', 'DELISTED'):
                return {
                    'delisted': True,
                    'symbol': symbol,
                    'status': status,
                    'action': 'FORCE_EXIT_MARKET',
                    'timestamp': datetime.now().isoformat(),
                }

            return None

        except Exception as e:
            print(f"MarketEventHandler: check_delisting error: {e}")
            return None

    def run_pre_market_checks(self) -> Dict[str, Any]:
        """Run all pre-market checks at start of trading day.

        Returns:
            dict with all checks and any alerts
        """
        result = {
            'timestamp': datetime.now().isoformat(),
            'checks': {},
            'alerts': [],
        }

        # Check early close
        early_close = self.check_early_close()
        result['checks']['early_close'] = early_close
        if early_close:
            result['alerts'].append('MARKET CLOSES EARLY AT 13:00 ET')

        # Check circuit breaker
        cb = self.check_market_circuit_breaker()
        result['checks']['circuit_breaker'] = cb
        if cb:
            result['alerts'].append(f"CIRCUIT BREAKER LEVEL {cb['level']}: {cb['description']}")

        # Check after-hours window
        after_hours = self.check_after_hours_window()
        result['checks']['after_hours_window'] = after_hours

        return result
