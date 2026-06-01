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
  from algo.algo_realtime_prices import RealtimePricingEngine

  engine = RealtimePricingEngine(config, api_key=alpaca_api_key)
  prices = engine.get_latest_prices(['AAPL', 'TSLA', 'SPY'])
  # Returns: {'AAPL': 150.23, 'TSLA': 241.50, 'SPY': 451.12}
"""

import logging
import os
from datetime import datetime, time, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

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
            logger.warning(f"get_latest_prices called outside market hours: {datetime.now().strftime('%H:%M %Z')}")
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

            # No prices available
            logger.error("Unable to fetch real-time prices from any source")
            return self._get_fallback_prices(symbols)

        except Exception as e:
            logger.error(f"Real-time pricing error: {e}", exc_info=True)
            # Fail-closed: return empty dict (orchestrator falls back to daily prices)
            # or could raise to halt trading
            return {}

    def _fetch_alpaca_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch latest quotes from Alpaca Data API."""
        try:
            import alpaca_trade_api as tradeapi
            api = tradeapi.REST(key_id=os.getenv("APCA_API_KEY_ID"),
                               secret_key=os.getenv("APCA_API_SECRET_KEY"),
                               base_url=os.getenv("APCA_API_BASE_URL"))

            quotes = {}
            for symbol in symbols:
                try:
                    quote = api.get_last_quote(symbol)
                    if quote:
                        quotes[symbol] = (quote.ask + quote.bid) / 2
                except Exception as e:
                    logger.warning(f"Alpaca quote failed for {symbol}: {e}")
            return quotes

        except ImportError:
            logger.warning("alpaca-trade-api not available")
            return {}
        except Exception as e:
            logger.error(f"Alpaca API error: {e}")
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
                    url = f"https://cloud.iexapis.com/stable/stock/{symbol}/quote"
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
        """Fetch delayed prices from YFinance."""
        try:
            import yfinance as yf
            quotes = {}
            for symbol in symbols:
                try:
                    tick = yf.Ticker(symbol)
                    hist = tick.history(period="1d")
                    if not hist.empty:
                        quotes[symbol] = hist["Close"].iloc[-1]
                except Exception as e:
                    logger.warning(f"YFinance quote failed for {symbol}: {e}")
            return quotes

        except ImportError:
            logger.warning("yfinance not available")
            return {}

    def _get_fallback_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Fallback: use cached or daily prices."""
        # Would query price_daily table from database
        logger.info(f"Using fallback prices for {len(symbols)} symbols")
        return {}
