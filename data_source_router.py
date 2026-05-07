"""
Unified data source router with automatic fallback.

One-stop shop for all loaders. Routes each data type to the best source
with health-check based fallback. Tracks per-source success rate so
unhealthy sources are temporarily skipped.

Sources by data type (in priority order):
    OHLCV:        Alpaca → Polygon → yfinance
    Fundamentals: SEC EDGAR → Polygon → yfinance
    Economic:     FRED (only)
    Earnings:     Alpaca → Polygon → yfinance

Why this matters:
    Loaders today hard-code yfinance. When yfinance breaks (weekly), all
    loaders break. With this router, a yfinance outage degrades to fallback
    automatically — same data, different source.

Health tracking:
    Each source has a rolling success rate. If success rate drops below
    50% over the last 20 requests, source is paused for 5 minutes.
    Auto-resumes after pause if heartbeat succeeds.

Usage:
    router = DataSourceRouter()
    df = router.fetch_ohlcv("AAPL", start, end)
    # router automatically tries Alpaca first, falls back if needed

    # See which source was used
    print(router.last_source)  # "alpaca" / "polygon" / "yfinance"
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Deque, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

log = logging.getLogger(__name__)


def _call_with_timeout(fn: Callable, timeout_sec: float = 30) -> Any:
    """Call a function with timeout protection. Raises TimeoutError if it takes too long."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn)
        try:
            return future.result(timeout=timeout_sec)
        except FuturesTimeoutError:
            raise TimeoutError(f"Function call exceeded {timeout_sec}s timeout")


@dataclass
class SourceHealth:
    """Rolling health stats for a data source."""
    name: str
    recent_results: Deque[bool] = field(default_factory=lambda: deque(maxlen=20))
    paused_until: float = 0.0
    total_requests: int = 0
    total_failures: int = 0
    last_error: Optional[str] = None

    @property
    def success_rate(self) -> float:
        if not self.recent_results:
            return 1.0  # Optimistic until proven otherwise
        return sum(self.recent_results) / len(self.recent_results)

    @property
    def is_paused(self) -> bool:
        return time.monotonic() < self.paused_until

    def record(self, success: bool, error: Optional[str] = None) -> None:
        self.recent_results.append(success)
        self.total_requests += 1
        if not success:
            self.total_failures += 1
            self.last_error = error
            # Pause if recent success rate drops below 50% with min sample
            if len(self.recent_results) >= 10 and self.success_rate < 0.5:
                self.paused_until = time.monotonic() + 300  # 5 min cool-off
                log.warning(
                    "Pausing source '%s' for 5 min (success_rate=%.0f%%, last_error=%s)",
                    self.name, self.success_rate * 100, error,
                )


class DataSourceRouter:
    """Routes data fetches across providers with fallback + health tracking."""

    def __init__(self):
        self._health: Dict[str, SourceHealth] = {}
        self._lock = threading.Lock()
        self.last_source: Optional[str] = None

        # Lazy clients — only construct when needed
        self._alpaca = None
        self._sec = None

    def _get_health(self, name: str) -> SourceHealth:
        with self._lock:
            if name not in self._health:
                self._health[name] = SourceHealth(name=name)
            return self._health[name]

    def _try_chain(
        self,
        sources: List[tuple],  # [(name, callable), ...]
        request_desc: str,
    ) -> Optional[Any]:
        """Try sources in order, skipping paused ones, recording outcomes."""
        last_exc = None
        for i, (name, fn) in enumerate(sources):
            health = self._get_health(name)
            if health.is_paused:
                log.debug("Skipping paused source '%s' for %s", name, request_desc)
                continue
            try:
                result = fn()
                if result is None or (hasattr(result, "__len__") and len(result) == 0):
                    # Empty result = symbol doesn't exist or has no data (not a source problem)
                    # Don't count as source failure — skip gracefully without affecting health
                    continue
                health.record(True)
                self.last_source = name
                log.debug("Source '%s' served %s", name, request_desc)
                return result
            except Exception as e:
                health.record(False, str(e))
                last_exc = e
                if i < len(sources) - 1:
                    next_source = sources[i + 1][0]
                    log.warning("[DataSourceRouter] Primary source '%s' failed for %s: %s. Falling back to '%s'.", name, request_desc, e, next_source)
                else:
                    log.debug("Source '%s' failed for %s: %s", name, request_desc, e)
                continue
        if last_exc:
            log.warning("All sources failed for %s. Last error: %s", request_desc, last_exc)
        return None

    # ============== OHLCV ==============

    def fetch_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> Optional[Any]:
        """Daily OHLCV bars. Returns DataFrame-shaped data or None."""
        sources = [
            ("alpaca", lambda: self._fetch_alpaca_ohlcv(symbol, start, end)),
            ("yfinance", lambda: self._fetch_yfinance_ohlcv(symbol, start, end)),
        ]
        return self._try_chain(sources, f"OHLCV[{symbol} {start}..{end}]")

    def _fetch_alpaca_ohlcv(self, symbol: str, start: date, end: date):
        api_key = os.getenv("ALPACA_API_KEY")
        # Accept either ALPACA_API_SECRET (router default) or ALPACA_SECRET_KEY
        # (used by other loaders + .env.local in this repo).
        api_secret = os.getenv("ALPACA_API_SECRET") or os.getenv("ALPACA_SECRET_KEY")
        if not api_key or not api_secret:
            return None

        import requests
        url = "https://data.alpaca.markets/v2/stocks/bars"
        resp = requests.get(
            url,
            params={
                "symbols": symbol,
                "timeframe": "1Day",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": 10000,
                "adjustment": "raw",
            },
            headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        bars = data.get("bars", {}).get(symbol, [])
        if not bars:
            return None
        return [
            {
                "symbol": symbol,
                "date": bar["t"][:10],
                "open": bar["o"],
                "high": bar["h"],
                "low": bar["l"],
                "close": bar["c"],
                "volume": int(bar["v"]),
            }
            for bar in bars
        ]

    def _fetch_yfinance_ohlcv(self, symbol: str, start: date, end: date):
        try:
            import yfinance as yf
        except ImportError:
            return None
        hist = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=False, timeout=30)
        if hist.empty:
            return None
        return [
            {
                "symbol": symbol,
                "date": idx.date().isoformat(),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            }
            for idx, row in hist.iterrows()
        ]

    # ============== FUNDAMENTALS ==============

    def fetch_balance_sheet(self, symbol: str, period: str = "annual"):
        """Balance sheet rows. SEC EDGAR primary (free, official)."""
        sources = [
            ("sec_edgar", lambda: self._sec_balance_sheet(symbol, period)),
            ("yfinance", lambda: self._yf_balance_sheet(symbol, period)),
        ]
        return self._try_chain(sources, f"BalanceSheet[{symbol} {period}]")

    def fetch_income_statement(self, symbol: str, period: str = "annual"):
        sources = [
            ("sec_edgar", lambda: self._sec_income(symbol, period)),
            ("yfinance", lambda: self._yf_income(symbol, period)),
        ]
        return self._try_chain(sources, f"Income[{symbol} {period}]")

    def fetch_cash_flow(self, symbol: str, period: str = "annual"):
        sources = [
            ("sec_edgar", lambda: self._sec_cash_flow(symbol, period)),
            ("yfinance", lambda: self._yf_cash_flow(symbol, period)),
        ]
        return self._try_chain(sources, f"CashFlow[{symbol} {period}]")

    def _sec_client(self):
        if self._sec is None:
            from sec_edgar_client import SecEdgarClient
            self._sec = SecEdgarClient()
        return self._sec

    def _sec_balance_sheet(self, symbol: str, period: str):
        return self._sec_client().get_balance_sheet(symbol, period)

    def _sec_income(self, symbol: str, period: str):
        return self._sec_client().get_income_statement(symbol, period)

    def _sec_cash_flow(self, symbol: str, period: str):
        return self._sec_client().get_cash_flow(symbol, period)

    def _yf_balance_sheet(self, symbol: str, period: str):
        try:
            import yfinance as yf
        except ImportError:
            return None
        try:
            def fetch():
                ticker = yf.Ticker(symbol)
                return ticker.balance_sheet if period == "annual" else ticker.quarterly_balance_sheet
            df = _call_with_timeout(fetch, timeout_sec=30)
            if df is None or df.empty:
                return None
            return df.to_dict(orient="index")
        except TimeoutError:
            log.warning("yfinance balance_sheet timeout for %s", symbol)
            return None

    def _yf_income(self, symbol: str, period: str):
        try:
            import yfinance as yf
        except ImportError:
            return None
        try:
            def fetch():
                ticker = yf.Ticker(symbol)
                return ticker.income_stmt if period == "annual" else ticker.quarterly_income_stmt
            df = _call_with_timeout(fetch, timeout_sec=30)
            if df is None or df.empty:
                return None
            return df.to_dict(orient="index")
        except TimeoutError:
            log.warning("yfinance income_stmt timeout for %s", symbol)
            return None

    def _yf_cash_flow(self, symbol: str, period: str):
        try:
            import yfinance as yf
        except ImportError:
            return None
        try:
            def fetch():
                ticker = yf.Ticker(symbol)
                return ticker.cashflow if period == "annual" else ticker.quarterly_cashflow
            df = _call_with_timeout(fetch, timeout_sec=30)
            if df is None or df.empty:
                return None
            return df.to_dict(orient="index")
        except TimeoutError:
            log.warning("yfinance cashflow timeout for %s", symbol)
            return None

    # ============== EARNINGS ==============

    def fetch_earnings(self, symbol: str):
        sources = [
            ("yfinance", lambda: self._yf_earnings(symbol)),
            ("sec_edgar", lambda: self._sec_eps(symbol)),
        ]
        return self._try_chain(sources, f"Earnings[{symbol}]")

    def _yf_earnings(self, symbol: str):
        try:
            import yfinance as yf
        except ImportError:
            return None
        try:
            def fetch():
                ticker = yf.Ticker(symbol)
                return ticker.earnings_dates
            df = _call_with_timeout(fetch, timeout_sec=30)
            if df is None or df.empty:
                return None
            return df.to_dict(orient="index")
        except TimeoutError:
            log.warning("yfinance earnings_dates timeout for %s", symbol)
            return None

    def _sec_eps(self, symbol: str):
        return self._sec_client().get_quarterly_concept(symbol, "EarningsPerShareDiluted")

    def fetch_eps_revisions(self, symbol: str):
        """Fetch estimate revisions (up/down counts). yfinance only (no fallback)."""
        sources = [
            ("yfinance", lambda: self._fetch_yfinance_eps_revisions(symbol)),
        ]
        return self._try_chain(sources, f"EpsRevisions[{symbol}]")

    def _fetch_yfinance_eps_revisions(self, symbol: str):
        try:
            import yfinance as yf
        except ImportError:
            return None
        try:
            def fetch():
                ticker = yf.Ticker(symbol)
                return ticker.eps_revisions
            df = _call_with_timeout(fetch, timeout_sec=30)
            if df is None or df.empty:
                return None
            return df
        except TimeoutError:
            log.warning("yfinance eps_revisions timeout for %s", symbol)
            return None

    def fetch_eps_trend(self, symbol: str):
        """Fetch estimate trends (historical estimate changes). yfinance only (no fallback)."""
        sources = [
            ("yfinance", lambda: self._fetch_yfinance_eps_trend(symbol)),
        ]
        return self._try_chain(sources, f"EpsTrend[{symbol}]")

    def _fetch_yfinance_eps_trend(self, symbol: str):
        try:
            import yfinance as yf
        except ImportError:
            return None
        try:
            def fetch():
                ticker = yf.Ticker(symbol)
                return ticker.eps_trend
            df = _call_with_timeout(fetch, timeout_sec=30)
            if df is None or df.empty:
                return None
            return df
        except TimeoutError:
            log.warning("yfinance eps_trend timeout for %s", symbol)
            return None

    # ============== HEALTH REPORT ==============

    def health_report(self) -> Dict[str, Any]:
        """Snapshot of source health. Useful for dashboards/alerts."""
        with self._lock:
            return {
                name: {
                    "success_rate": round(h.success_rate * 100, 1),
                    "is_paused": h.is_paused,
                    "total_requests": h.total_requests,
                    "total_failures": h.total_failures,
                    "last_error": h.last_error,
                }
                for name, h in self._health.items()
            }
