#!/usr/bin/env python3
"""
Real-time Pricing Module for Intraday Position Sizing (F-01)

Problem: Orchestrator runs at 9:30 AM, 1 PM, 3 PM ET using 4 AM daily prices.
Position sizing is wrong if a stock gaps 10%+ at open.

Solution: Fetch intraday prices during market hours (9:30 AM - 4 PM ET)
for position sizing and risk calculations.

Sources:
1. Alpaca Data API (real-time for paper/live accounts)
2. IEX Cloud (mid-market prices, ~100ms latency)
3. Fallback: YFinance minute bars (delayed ~15 min)

Usage:
  from algo.infrastructure import RealtimePricingEngine

  engine = RealtimePricingEngine(config, api_key=alpaca_api_key)
  prices = engine.get_latest_prices(['AAPL', 'TSLA', 'SPY'])
  # Returns: {'AAPL': 150.23, 'TSLA': 241.50, 'SPY': 451.12}
"""

import logging
import os
from datetime import datetime, time, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from utils.infrastructure import get_alpaca_data_url, get_iex_cloud_url
from utils.infrastructure import EASTERN_TZ

logger = logging.getLogger(__name__)

@dataclass
class PriceQuote:
    """Real-time price quote."""
    symbol: str
    price: float
    bid: float
    ask: float
    timestamp: datetime
    source: str  # 'alpaca', 'iex', 'yfinance'
    latency_ms: float

class RealtimePricingEngine:
    """Fetch and cache real-time intraday prices during market hours."""

    def __init__(self, config, api_key: Optional[str] = None):
        self.config = config
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self._price_cache: Dict[str, Tuple[float, datetime]] = {}
        self._cache_ttl_seconds = 60  # Refresh every 60 seconds

    def is_market_hours(self) -> bool:
        """Check if current time is during US market hours (9:30 AM - 4 PM ET)."""
        now = datetime.now(timezone.utc)
        et = now.astimezone()  # Convert to local (ET)
        market_open = time(9, 30)
        market_close = time(16, 0)
        # Only during Mon-Fri
        is_weekday = et.weekday() < 5
        return is_weekday and market_open <= et.time() <= market_close

    def get_latest_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get latest intraday prices for symbols.

        Args:
            symbols: List of ticker symbols

        Returns:
            Dict of {symbol: price} for successful quotes

        Raises:
            Exception if unable to fetch prices (circuit breaker halts trading)
        """
        if not self.is_market_hours():
            logger.warning(f"get_latest_prices called outside market hours: {datetime.now(EASTERN_TZ).strftime('%H:%M %Z')}")
            # Return cached prices or daily prices as fallback
            return self._get_fallback_prices(symbols)

        prices = {}
        try:
            # Try Alpaca real-time API first
            prices = self._fetch_alpaca_prices(symbols)
            if prices:
                logger.info(f"Fetched real-time prices from Alpaca: {len(prices)} symbols")
                return prices

            # Fallback to IEX Cloud
            logger.warning("Alpaca API unavailable, trying IEX Cloud...")
            prices = self._fetch_iex_prices(symbols)
            if prices:
                logger.info(f"Fetched prices from IEX: {len(prices)} symbols")
                return prices

            # Last resort: YFinance (delayed 15 min)
            logger.warning("IEX unavailable, falling back to YFinance (delayed)...")
            prices = self._fetch_yfinance_prices(symbols)
            if prices:
                logger.warning(f"Using delayed YFinance prices: {len(prices)} symbols")
                return prices

            # CRITICAL: All real-time price sources failed. Empty dict masks infrastructure failure
            # and allows orchestrator to silently fall back to 4 AM prices during 9:30 AM run
            # (causing gap-up/gap-down mis-sizing).
            # Fail-closed: raise exception to halt trading and alert ops.
            error_msg = "Unable to fetch real-time prices from any source (Alpaca/IEX/YFinance all failed)"
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

        except RuntimeError:
            raise  # Re-raise our critical errors
        except Exception as e:
            logger.error(f"Real-time pricing error: {e}", exc_info=True)
            # Fail-closed: raise to halt trading rather than silently using stale prices
            raise RuntimeError(f"Real-time pricing failed: {e}") from e

    def _fetch_alpaca_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch latest quotes from Alpaca Data API (direct REST, not trading API).

        Uses the Alpaca Data API directly for more reliable real-time quotes.
        The trading API get_latest_quote() may have permission or endpoint issues.
        """
        try:
            import requests

            api_key = os.getenv("ALPACA_API_KEY")
            if not api_key:
                logger.debug("ALPACA_API_KEY not set")
                return {}

            # Alpaca Data API endpoint for latest quotes
            base_url = f"{get_alpaca_data_url()}/v2/stocks"
            quotes = {}

            for symbol in symbols:
                try:
                    url = f"{base_url}/{symbol}/latest/quote"
                    headers = {"APCA-API-KEY-ID": api_key}
                    resp = requests.get(url, headers=headers, timeout=5)

                    if resp.status_code == 200:
                        data = resp.json()
                        quote = data.get('quote', {})
                        if quote.get('bid') and quote.get('ask'):
                            # Use mid-price (average of bid/ask)
                            quotes[symbol] = (quote['bid'] + quote['ask']) / 2
                    elif resp.status_code == 401:
                        logger.warning(f"Alpaca authentication failed - check API key: {resp.text}")
                    elif resp.status_code == 404:
                        logger.debug(f"Alpaca quote not found for {symbol}")
                    else:
                        logger.debug(f"Alpaca API returned {resp.status_code} for {symbol}: {resp.text[:100]}")

                except requests.Timeout:
                    logger.debug(f"Alpaca timeout for {symbol}")
                except Exception as sym_err:
                    logger.debug(f"Alpaca quote failed for {symbol}: {sym_err}")

            return quotes

        except ImportError:
            logger.debug("requests not available for Alpaca API")
            return {}
        except Exception as e:
            logger.debug(f"Alpaca Data API error: {e}")
            return {}

    def _fetch_iex_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch prices from IEX Cloud."""
        try:
            import requests
            iex_key = os.getenv("IEX_CLOUD_API_KEY")
            if not iex_key:
                return {}

            quotes = {}
            for symbol in symbols:
                try:
                    url = f"{get_iex_cloud_url()}/stock/{symbol}/quote"
                    resp = requests.get(url, params={"token": iex_key}, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        quotes[symbol] = data.get("iexRealtimePrice") or data.get("latestPrice")
                except Exception as e:
                    logger.warning(f"IEX quote failed for {symbol}: {e}")
            return quotes

        except ImportError:
            logger.warning("requests not available for IEX")
            return {}

    def _fetch_yfinance_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch delayed prices from YFinance via wrapper."""
        try:
            from utils.external import YFinanceWrapper
            quotes = {}
            for symbol in symbols:
                try:
                    ticker = YFinanceWrapper.get_ticker(symbol)
                    if ticker:
                        hist = ticker.history(period="1d")
                        if not hist.empty:
                            quotes[symbol] = hist["Close"].iloc[-1]
                except Exception as e:
                    logger.warning(f"YFinance quote failed for {symbol}: {e}")
            return quotes

        except ImportError:
            logger.warning("yfinance wrapper not available")
            return {}

    def _get_fallback_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Fallback: use cached or daily prices from database."""
        from utils.db import DatabaseContext
        from datetime import date as _date

        try:
            prices = {}
            with DatabaseContext('read') as cur:
                current_date = _date.today()
                for symbol in symbols:
                    cur.execute(
                        """
                        SELECT close FROM price_daily
                        WHERE symbol = %s AND date <= %s
                        ORDER BY date DESC LIMIT 1
                        """,
                        (symbol, current_date)
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        prices[symbol] = float(row[0])

            if prices:
                logger.info(f"Fetched fallback daily prices for {len(prices)} symbols")
            return prices
        except Exception as e:
            logger.error(f"Failed to fetch fallback prices from database: {e}")
            return {}
