#!/usr/bin/env python3
"""Market Events & Corporate Actions Handler.

Detects and responds to market anomalies:
- Single-stock halts (trading paused, then resumed)
- Market circuit breakers (L1: 7%, L2: 13%, L3: 20% down)
- Early close days (market closes 3 hours early)
- Corporate actions (stock splits, dividends, delisting)

Implements fail-safe protocols that override strategy logic.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from typing import Any

import psycopg2
import requests

from algo.infrastructure import (
    get_api_timeout,
    get_market_data_timeout,
)
from config.api_endpoints import get_alpaca_base_url, get_alpaca_data_url
from config.credential_manager import get_credential_manager
from utils.db import DatabaseContext
from utils.infrastructure import EASTERN_TZ

logger = logging.getLogger(__name__)


class MarketEventHandler:
    """Detect and respond to market events and halts."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.alpaca_base_url = get_alpaca_base_url()

        # In paper mode, market event checks (halts, circuit breakers) still require Alpaca API
        # because we need real market data to validate positions and detect halts.
        # However, we can use paper trading credentials instead of live trading credentials.
        # If credentials are not available, fail gracefully for paper mode operations.
        execution_mode = config.get("execution_mode", "paper")

        try:
            cm = get_credential_manager()
            creds = cm.get_alpaca_credentials()
        except ValueError as e:
            # In paper mode, credential failure is degraded but may be tolerable for some operations.
            # However, market halt checks REQUIRE credentials to call Alpaca API.
            if execution_mode == "paper":
                logger.warning(
                    f"[MARKET_EVENTS] Paper mode: Alpaca credentials not available. "
                    f"Market halt checks will not be performed. Position updates will still work from database. "
                    f"Error: {e}"
                )
                # Set dummy credentials so methods don't crash, but they'll fail on API calls
                self.alpaca_key = None
                self.alpaca_secret = None
                return
            else:
                # Live mode requires real credentials
                raise

        # CRITICAL: Fail fast if credentials missing (no defaults) in live mode
        if "key" not in creds:
            raise ValueError("[MARKET_EVENTS] Alpaca API key missing from credentials")
        if "secret" not in creds:
            raise ValueError("[MARKET_EVENTS] Alpaca API secret missing from credentials")
        self.alpaca_key = creds["key"]
        self.alpaca_secret = creds["secret"]

    def check_single_stock_halt(self, symbol: str) -> dict[str, Any] | None:
        """Check if symbol is currently halted from trading.

        Returns:
            dict with halt_status, reason if halted (halted=True, status, tradable fields)
            None: if symbol is tradable and not halted (normal trading state)

        """
        # In paper mode, if credentials unavailable, skip halt check and assume tradable
        if self.alpaca_key is None or self.alpaca_secret is None:
            logger.debug(f"[HALT_CHECK] Paper mode: credentials unavailable, assuming {symbol} is tradable")
            return {"halted": False, "symbol": symbol, "paper_mode": True}

        try:
            url = f"{self.alpaca_base_url}/v2/assets/{symbol}"
            headers = {
                "APCA-API-KEY-ID": self.alpaca_key,
                "APCA-API-SECRET-KEY": self.alpaca_secret,
            }
            resp = requests.get(url, headers=headers, timeout=get_api_timeout())
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Cannot verify halt status for {symbol}: API returned {resp.status_code}. "
                    f"Cannot trade without halt status verification."
                )

            try:
                data = resp.json()
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"CRITICAL: Invalid JSON response from {url}: {e}")
                raise RuntimeError(
                    f"Cannot parse market event status from {url}. Invalid JSON: {e}. Check data provider and retry."
                ) from e
            if "status" not in data or data["status"] is None:
                raise ValueError(f"Missing required 'status' field in market event response for {symbol}")
            if "tradable" not in data or data["tradable"] is None:
                raise ValueError(
                    f"Missing required 'tradable' field in market event response for {symbol}. "
                    f"API response structure may have changed or symbol data is incomplete."
                )
            status = data["status"].upper()
            tradable = data["tradable"]

            if not tradable or status != "ACTIVE":
                return {
                    "halted": True,
                    "symbol": symbol,
                    "status": status,
                    "tradable": tradable,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            logger.debug(f"[HALT_CHECK] {symbol} is tradable and active (no halt)")
            return {
                "halted": False,
                "symbol": symbol,
                "status": status,
                "tradable": tradable,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except requests.Timeout as e:
            logger.error(f"[HALT_CHECK] API timeout for {symbol}: {e}")
            return {
                "error": "halt_check_failed",
                "reason": "api_timeout",
                "symbol": symbol,
                "description": f"Timeout checking halt status for {symbol}: {e}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except requests.RequestException as e:
            logger.error(f"[HALT_CHECK] API error for {symbol}: {e}")
            return {
                "error": "halt_check_failed",
                "reason": "api_error",
                "symbol": symbol,
                "description": f"Cannot verify halt status for {symbol}: {e}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except (RuntimeError, TypeError, ValueError) as e:
            logger.error(f"[HALT_CHECK] Data validation error for {symbol}: {e}")
            return {
                "error": "halt_check_failed",
                "reason": "data_validation_error",
                "symbol": symbol,
                "description": f"Cannot verify halt status for {symbol}: {e}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def check_market_circuit_breaker(self) -> dict[str, Any] | None:
        """Check if market circuit breaker is active (S&P 500 down 7%+) with concurrent API calls.

        Circuit breaker levels:
        - L1: S&P 500 down 7% intraday -> 15-min halt
        - L2: S&P 500 down 13% intraday -> 15-min halt
        - L3: S&P 500 down 20% intraday -> halt for rest of day

        Fetches quotes and bars concurrently to reduce timeout latency from 15s sequential
        to ~10s concurrent (both timeout at 10s, run in parallel).

        Returns:
            dict with level, % down, timestamp if triggered (level 1-3)
            dict with error details if check failed (credentials missing, API timeout, etc.)
            None: if market is within normal ranges (no circuit breaker active)

        """
        try:
            # CRITICAL: Check if Alpaca credentials are available
            # Must fail fast with explicit error if credentials not configured (cannot verify circuit breaker status)
            if not self.alpaca_key or not self.alpaca_secret:
                logger.error(
                    "[MARKET_CIRCUIT_BREAKER CRITICAL] Alpaca credentials not configured. "
                    "Cannot verify circuit breaker status. Must have valid credentials to check market safety gates."
                )
                return {
                    "error": "circuit_breaker_check_failed",
                    "reason": "credentials_not_configured",
                    "description": "Alpaca API credentials missing - cannot verify circuit breaker status",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            headers = {
                "APCA-API-KEY-ID": self.alpaca_key,
                "APCA-API-SECRET-KEY": self.alpaca_secret,
            }

            def fetch_quotes() -> Any:
                # Use Market Data API (data.alpaca.markets) not Trading API (paper-api.alpaca.markets)
                alpaca_data_url = get_alpaca_data_url()
                url = f"{alpaca_data_url}/v2/stocks/SPY/quotes/latest"
                try:
                    resp = requests.get(url, headers=headers, timeout=get_api_timeout())
                    if resp.status_code != 200:
                        raise RuntimeError(f"Quotes API error: status {resp.status_code}")
                    data = resp.json()
                    quote = data.get("quote")
                    if quote is None:
                        raise RuntimeError("Quotes response missing 'quote' field")
                    ap = quote.get("ap")
                    if ap is None:
                        raise RuntimeError("Quote data missing 'ap' field")
                    return ap
                except (
                    requests.RequestException,
                    json.JSONDecodeError,
                    RuntimeError,
                ) as e:
                    raise RuntimeError(f"Operation failed: {e}") from e

            def fetch_bars() -> Any:
                # Use Market Data API (data.alpaca.markets) not Trading API (paper-api.alpaca.markets)
                alpaca_data_url = get_alpaca_data_url()
                # /bars/latest endpoint does not accept timeframe parameter (returns 400 if included)
                url = f"{alpaca_data_url}/v2/stocks/SPY/bars/latest"
                try:
                    resp = requests.get(url, headers=headers, timeout=get_market_data_timeout())
                    if resp.status_code == 400:
                        # Paper trading accounts may require feed=iex (SIP feed returns 400)
                        resp = requests.get(
                            url,
                            headers=headers,
                            params={"feed": "iex"},
                            timeout=get_market_data_timeout(),
                        )
                    if resp.status_code != 200:
                        raise RuntimeError(f"Bars API error: status {resp.status_code}")
                    data = resp.json()
                    bar = data.get("bar")
                    if bar is None:
                        raise RuntimeError("Bars response missing 'bar' field")
                    o = bar.get("o")
                    if o is None:
                        raise RuntimeError("Bar data missing 'o' field")
                    return o
                except (
                    requests.RequestException,
                    json.JSONDecodeError,
                    RuntimeError,
                ) as e:
                    raise RuntimeError(f"Operation failed: {e}") from e

            with ThreadPoolExecutor(max_workers=2) as executor:
                quote_future = executor.submit(fetch_quotes)
                bars_future = executor.submit(fetch_bars)
                current_price = quote_future.result(timeout=get_api_timeout() + 2)
                open_price = bars_future.result(timeout=get_market_data_timeout() + 2)

            if not current_price or not open_price:
                raise RuntimeError(
                    f"Cannot verify circuit breaker status: missing prices (current={current_price}, open={open_price}). "
                    f"Cannot trade without circuit breaker data validation."
                )

            pct_down = (float(open_price) - float(current_price)) / float(open_price) * 100

            if pct_down >= 20.0:
                return {
                    "level": 3,
                    "description": "20%+ down - market halted for rest of day",
                    "pct_down": round(pct_down, 2),
                    "action": "HALT_ALL_ENTRIES",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            elif pct_down >= 13.0:
                return {
                    "level": 2,
                    "description": "13%+ down - 15-minute halt",
                    "pct_down": round(pct_down, 2),
                    "action": "PAUSE_NEW_ENTRIES_15MIN",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            elif pct_down >= 7.0:
                return {
                    "level": 1,
                    "description": "7%+ down - 15-minute halt",
                    "pct_down": round(pct_down, 2),
                    "action": "PAUSE_NEW_ENTRIES_15MIN",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            logger.debug(f"[CIRCUIT_BREAKER] Market within normal ranges (down {pct_down:.2f}%, threshold 7%)")
            return None  # Documented return value: None = no circuit breaker active

        except requests.Timeout as e:
            logger.error(f"[MARKET_CIRCUIT_BREAKER] API timeout checking circuit breaker: {e}")
            return {
                "error": "circuit_breaker_check_failed",
                "reason": "api_timeout",
                "description": f"Timeout checking market circuit breaker status: {e}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except requests.RequestException as e:
            logger.error(f"[MARKET_CIRCUIT_BREAKER] API error checking circuit breaker: {e}")
            return {
                "error": "circuit_breaker_check_failed",
                "reason": "api_error",
                "description": f"Failed to check market circuit breaker status: {e}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except (RuntimeError, TypeError, ValueError) as e:
            logger.error(f"[MARKET_CIRCUIT_BREAKER] Data validation error: {e}")
            return {
                "error": "circuit_breaker_check_failed",
                "reason": "data_validation_error",
                "description": f"Cannot verify circuit breaker status: {e}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def check_early_close(self, check_date: date | None = None) -> bool:
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
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT early_close FROM market_health_daily
                    WHERE date = %s
                    """,
                    (check_date,),
                )
                row = cur.fetchone()

            if row is None:
                raise RuntimeError(
                    f"Cannot verify early close status for {check_date}: "
                    f"missing market_health_daily record. Cannot trade without verified market hours."
                )

            return bool(row[0])

        except RuntimeError:
            raise
        except (TypeError, ValueError, KeyError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def check_after_hours_window(self, check_time: datetime | None = None) -> bool:
        """Check if we're in after-hours window (after 15:45 ET or early close at 13:00).

        No new entries allowed after 15:45 ET on normal days or 13:00 ET on early close days.

        Args:
            check_time: Time to check (default now)

        Returns:
            True if in after-hours window, False otherwise

        """
        if not check_time:
            check_time = datetime.now(EASTERN_TZ)

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

