"""
Market Events & Corporate Actions Handler

Detects and responds to market anomalies:
- Single-stock halts (trading paused, then resumed)
- Market circuit breakers (L1: 7%, L2: 13%, L3: 20% down)
- Early close days (market closes 3 hours early)
- Corporate actions (stock splits, dividends, delisting)

Implements fail-safe protocols that override strategy logic.
"""

from config.credential_manager import get_credential_manager
from config.alpaca_config import get_alpaca_base_url
from algo.algo_config import get_api_timeout, get_market_data_timeout, get_alpaca_timeout
from utils.database_context import DatabaseContext

import requests
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)

class MarketEventHandler:
    """Detect and respond to market events and halts."""

    def __init__(self, config):
        self.config = config
        self.alpaca_base_url = get_alpaca_base_url()
        try:
            cm = get_credential_manager()
            self.alpaca_key = cm.get_alpaca_credentials()["key"]
            self.alpaca_secret = cm.get_alpaca_credentials()["secret"]
        except Exception as e:
            logger.warning(f"Alpaca credentials not available: {e}")
            self.alpaca_key = None
            self.alpaca_secret = None

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
            resp = requests.get(url, headers=headers, timeout=get_api_timeout())
            if resp.status_code != 200:
                return None

            try:
                data = resp.json()
            except (ValueError, Exception) as e:
                logger.debug(f"Invalid JSON response from {url}: {e}")
                return None
            status = data.get('status', '').upper()
            tradable = data.get('tradable', False)

            if not tradable or status != 'ACTIVE':
                return {
                    'halted': True,
                    'symbol': symbol,
                    'status': status,
                    'tradable': tradable,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                }

            return None

        except Exception as e:
            logger.warning(f"MarketEventHandler: check_single_stock_halt error: {e}")
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
            url = f"{self.alpaca_base_url}/v2/stocks/SPY/quotes/latest"
            headers = {
                'APCA-API-KEY-ID': self.alpaca_key,
                'APCA-API-SECRET-KEY': self.alpaca_secret,
            }
            resp = requests.get(url, headers=headers, timeout=get_api_timeout())
            if resp.status_code != 200:
                return None

            try:
                data = resp.json()
            except (ValueError, Exception) as e:
                logger.debug(f"Invalid JSON response from {url}: {e}")
                return None
            current_price = data.get('quote', {}).get('ap')  # ask price
            if not current_price:
                return None

            url_bars = f"{self.alpaca_base_url}/v2/stocks/SPY/bars/latest?timeframe=1day"
            resp_bars = requests.get(url_bars, headers=headers, timeout=get_market_data_timeout())
            if resp_bars.status_code != 200:
                return None

            try:
                bars_data = resp_bars.json()
            except (ValueError, Exception) as e:
                logger.debug(f"Invalid JSON response from {url_bars}: {e}")
                return None
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
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                }
            elif pct_down >= 13.0:
                return {
                    'level': 2,
                    'description': '13%+ down — 15-minute halt',
                    'pct_down': round(pct_down, 2),
                    'action': 'PAUSE_NEW_ENTRIES_15MIN',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                }
            elif pct_down >= 7.0:
                return {
                    'level': 1,
                    'description': '7%+ down — 15-minute halt',
                    'pct_down': round(pct_down, 2),
                    'action': 'PAUSE_NEW_ENTRIES_15MIN',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                }

            return None

        except Exception as e:
            logger.warning(f"MarketEventHandler: check_market_circuit_breaker error: {e}")
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
            with DatabaseContext('read') as cur:
                cur.execute(
                    """
                    SELECT early_close FROM market_health_daily
                    WHERE date = %s
                    """,
                    (check_date,)
                )
                row = cur.fetchone()

                if row:
                    return bool(row[0])

            # Fallback: check known dates
            # Day after Thanksgiving (4th Thursday of November)
            # Find all Thursdays in November (weekday() == 3 means Thursday)
            nov_thursdays = [d for d in range(1, 31) if datetime(check_date.year, 11, d).weekday() == 3]
            if len(nov_thursdays) >= 4:
                day_after_thanksgiving = nov_thursdays[3] + 1  # 4th Thursday + 1 day
                if check_date.month == 11 and check_date.day == day_after_thanksgiving:
                    return True

            # Christmas Eve (Dec 24)
            if check_date.month == 12 and check_date.day == 24:
                return True

            return False

        except Exception as e:
            logger.warning(f"MarketEventHandler: check_early_close error: {e}")
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
            check_time = datetime.now(ZoneInfo("America/New_York"))

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
            from utils.database_context import database_transaction
            with database_transaction() as cur:
                # Cancel any pending orders for this symbol
                cur.execute(
                    """
                    UPDATE algo_trades
                    SET status = 'cancelled'
                    WHERE symbol = %s AND status IN ('pending', 'open')
                    """,
                    (symbol,)
                )

                # Log the halt event
                cur.execute(
                    """
                    INSERT INTO algo_audit_log (
                        action_type, action_date, details, severity
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    ('SINGLE_STOCK_HALT', datetime.now(timezone.utc), f'Symbol {symbol} halted — pending orders cancelled', 'WARN')
                )

                cur.connection.commit()

            return {
                'action': 'HALT_SYMBOL',
                'symbol': symbol,
                'status': 'orders_cancelled',
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"MarketEventHandler: handle_single_stock_halt error: {e}")
            return {'action': 'ERROR', 'message': str(e)}

    def handle_market_circuit_breaker(self, level: int) -> Dict[str, Any]:
        """Handle market circuit breaker: halt entries, tighten stops, or close positions.

        Args:
            level: CB level (1, 2, or 3)

        Returns:
            dict with action taken
        """
        try:
            from utils.database_context import database_transaction

            if level == 3:
                # L3: Full halt, no new orders, close positions
                action = 'HALT_ALL_ENTRIES'
                message = 'Market circuit breaker L3 (20%+ down) — halting all new entries and preparing for forced exit'
                severity = 'CRITICAL'
                action_type = 'CIRCUIT_BREAKER_L3'
            elif level in (1, 2):
                # L1/L2: Pause new entries for 15 minutes, tighten stops
                action = 'PAUSE_ENTRIES_15MIN'
                message = f'Market circuit breaker L{level} ({"7" if level == 1 else "13"}%+ down) — pausing new entries for 15 minutes'
                severity = 'ERROR'
                action_type = f'CIRCUIT_BREAKER_L{level}'
            else:
                return {'action': 'ERROR', 'message': f'Invalid circuit breaker level: {level}'}

            with database_transaction() as cur:
                cur.execute(
                    """
                    INSERT INTO algo_audit_log (
                        action_type, action_date, details, severity
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (action_type, datetime.now(timezone.utc), message, severity)
                )
                cur.connection.commit()

            return {
                'action': action,
                'level': level,
                'status': 'logged',
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"MarketEventHandler: handle_market_circuit_breaker error: {e}")
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
            resp = requests.get(url, headers=headers, timeout=get_api_timeout())
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
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                }

            return None

        except Exception as e:
            logger.warning(f"MarketEventHandler: check_delisting error: {e}")
            return None

    def run_pre_market_checks(self) -> Dict[str, Any]:
        """Run all pre-market checks at start of trading day.

        Returns:
            dict with all checks and any alerts
        """
        result = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'checks': {},
            'alerts': [],
        }

        early_close = self.check_early_close()
        result['checks']['early_close'] = early_close
        if early_close:
            result['alerts'].append('MARKET CLOSES EARLY AT 13:00 ET')

        cb = self.check_market_circuit_breaker()
        result['checks']['circuit_breaker'] = cb
        if cb:
            result['alerts'].append(f"CIRCUIT BREAKER LEVEL {cb['level']}: {cb['description']}")

        after_hours = self.check_after_hours_window()
        result['checks']['after_hours_window'] = after_hours

        return result

