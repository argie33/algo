#!/usr/bin/env python3
"""Alpaca Market Data API client — multi-symbol daily OHLCV bars.

Parallel-track price source being evaluated against yfinance (2026-07-14).
Verified plan facts (docs.alpaca.markets, 2026):

- FREE/Basic plan: 200 API calls/min, and FULL SIP consolidated-tape historical
  data for anything older than 15 minutes ("the only thing a free Basic account
  restricts is the most recent 15 minutes of data" — Alpaca staff). For EOD
  loading after market close this means zero data-quality compromise: correct
  consolidated volume and OHLC, since 2016.
- The $99/mo Algo Trader Plus plan adds real-time SIP, unlimited websocket
  symbols, and a 10,000/min rate limit — relevant only for intraday/real-time.
- Multi-symbol bars endpoint is genuinely batched: ~200 symbols per request,
  limit=10000 data points per page, next_page_token pagination. A full
  ~8,500-symbol EOD day is ~43 requests ≈ 15-20s at the free rate limit.

Config (all plan-dependent knobs are env-tunable so upgrading is config-only):

  ALPACA_DATA_FEED                 sip (default — free for data >15min old) | iex
  ALPACA_DATA_RATE_LIMIT_PER_MIN   default 190 (free plan allows 200/min)
  ALPACA_DATA_SYMBOLS_PER_REQUEST  default 200
  ALPACA_DATA_ADJUSTMENT           raw (default; matches the yfinance
                                   auto_adjust=False rows the price loader
                                   stores today) | split | dividend | all

On the free plan a request whose `end` is within the last 15 minutes is rejected
for feed=sip; fetch_daily_bars() guards this by capping the end timestamp at
now-16min (a no-op for EOD runs, which query completed days).

Credentials come from config.credential_manager.get_alpaca_credentials() (same
key pair as the trading API; the data host is data.alpaca.markets).
"""

import logging
import os
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests

from config.api_endpoints import get_alpaca_data_url

logger = logging.getLogger(__name__)

# Alpaca uses "." for class shares (BRK.B) — same as the DB convention here;
# no symbol translation needed (yfinance is the one that wants "-").


class AlpacaDataError(RuntimeError):
    """Raised when the Alpaca Market Data API returns an unrecoverable error."""


class _TokenBucket:
    """Simple thread-safe sliding-window limiter (N requests per 60s)."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] > 60.0:
                    self._timestamps.popleft()
                if len(self._timestamps) < self.per_minute:
                    self._timestamps.append(now)
                    return
                wait = 60.0 - (now - self._timestamps[0]) + 0.05
            time.sleep(min(max(wait, 0.05), 60.0))


class AlpacaMarketData:
    """Daily-bar fetcher against /v2/stocks/bars with plan-aware defaults."""

    def __init__(
        self,
        feed: str | None = None,
        rate_limit_per_min: int | None = None,
        symbols_per_request: int | None = None,
        adjustment: str | None = None,
        timeout_sec: float = 30.0,
    ) -> None:
        self.feed = feed or os.getenv("ALPACA_DATA_FEED", "sip")
        self.adjustment = adjustment or os.getenv("ALPACA_DATA_ADJUSTMENT", "raw")
        self.symbols_per_request = symbols_per_request or int(os.getenv("ALPACA_DATA_SYMBOLS_PER_REQUEST", "200"))
        self.timeout_sec = timeout_sec
        per_min = rate_limit_per_min or int(os.getenv("ALPACA_DATA_RATE_LIMIT_PER_MIN", "190"))
        self._bucket = _TokenBucket(per_min)
        self._session = requests.Session()
        self._headers: dict[str, str] | None = None

    def _get_headers(self) -> dict[str, str]:
        if self._headers is None:
            from config.credential_manager import get_alpaca_credentials

            creds = get_alpaca_credentials()
            key = creds.get("key")
            secret = creds.get("secret")
            if not key or not secret:
                raise AlpacaDataError(
                    "Alpaca credentials missing 'key'/'secret' — cannot fetch market data. "
                    "Check Secrets Manager algo/alpaca entries."
                )
            self._headers = {
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
            }
        return self._headers

    @staticmethod
    def _sip_safe_end(end: date) -> str:
        """RFC-3339 end bound, capped at now-16min (free-plan SIP restriction).

        Querying an `end` inside the last 15 minutes with feed=sip on the free
        plan is rejected; EOD runs query completed days so the cap is a no-op,
        but it makes ad-hoc same-day calls safe too.
        """
        now_cap = datetime.now(timezone.utc) - timedelta(minutes=16)
        end_dt = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)
        return min(end_dt, now_cap).isoformat()

    def fetch_daily_bars(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch 1Day bars for many symbols. Returns symbol -> rows.

        Row shape matches the yfinance OHLCV-batch contract used by the price
        loader: {symbol, date (ISO str), open, high, low, close, volume}.
        Symbols with no bars in the window are absent from the result (callers
        decide between watermark-current and data_unavailable semantics).
        """
        if not symbols:
            raise ValueError("symbols list cannot be empty")

        # Alpaca's /v2/stocks endpoints serve equities only: index symbols (^DJI,
        # ^VIX, ^GSPC...) are yfinance-isms and 400 the WHOLE multi-symbol request.
        # Skip them here; they stay on the yfinance path (absent from the result).
        unsupported = [s for s in symbols if s.startswith("^")]
        if unsupported:
            logger.info(
                f"[ALPACA_DATA] Skipping {len(unsupported)} non-equity symbols not served by "
                f"Alpaca stocks endpoints (fall back to yfinance): {unsupported[:10]}"
            )
        tradable = [s for s in symbols if not s.startswith("^")]

        results: dict[str, list[dict[str, Any]]] = {}
        for chunk_start in range(0, len(tradable), self.symbols_per_request):
            chunk = tradable[chunk_start : chunk_start + self.symbols_per_request]
            self._fetch_chunk(chunk, start, end, results)
        return results

    def _fetch_chunk(
        self,
        chunk: list[str],
        start: date,
        end: date,
        results: dict[str, list[dict[str, Any]]],
    ) -> None:
        url = f"{get_alpaca_data_url()}/v2/stocks/bars"
        params: dict[str, Any] = {
            "symbols": ",".join(chunk),
            "timeframe": "1Day",
            "start": start.isoformat(),
            "end": self._sip_safe_end(end),
            "adjustment": self.adjustment,
            "feed": self.feed,
            "limit": 10000,
        }
        page_token: str | None = None
        pages = 0
        while True:
            if page_token:
                params["page_token"] = page_token
            elif "page_token" in params:
                del params["page_token"]

            self._bucket.acquire()
            resp = self._session.get(url, headers=self._get_headers(), params=params, timeout=self.timeout_sec)
            if resp.status_code == 429:
                # Sliding-window limiter should prevent this; if the server still
                # throttles, honor it with a fixed backoff and retry the same page.
                logger.warning("[ALPACA_DATA] 429 despite client-side limiter — backing off 5s")
                time.sleep(5.0)
                continue
            if resp.status_code == 403:
                raise AlpacaDataError(
                    f"Alpaca data API 403 (feed={self.feed}): this feed/plan combination is "
                    f"not authorized for this window. Free plan allows feed=sip only for data "
                    f"older than 15 minutes (feed=iex has no window restriction). "
                    f"Response: {resp.text[:200]}"
                )
            if resp.status_code == 400 and "invalid symbol" in resp.text.lower():
                # One unknown symbol 400s the entire multi-symbol request. Drop the
                # named symbol and retry the chunk without it (it will be absent from
                # the result, i.e. left to the yfinance path / unavailable marker).
                bad = resp.json().get("message", "").split(":")[-1].strip()
                remaining = [s for s in chunk if s != bad]
                if bad and len(remaining) < len(chunk):
                    logger.warning(f"[ALPACA_DATA] Dropping invalid symbol {bad!r} and retrying chunk")
                    if remaining:
                        self._fetch_chunk(remaining, start, end, results)
                    return
                raise AlpacaDataError(f"Alpaca bars API 400 (unparseable invalid-symbol): {resp.text[:300]}")
            if resp.status_code != 200:
                raise AlpacaDataError(f"Alpaca bars API error {resp.status_code}: {resp.text[:300]}")

            payload = resp.json()
            bars_by_symbol = payload.get("bars") or {}
            for symbol, bars in bars_by_symbol.items():
                if not bars:
                    continue
                rows = results.setdefault(symbol, [])
                for bar in bars:
                    ts = bar.get("t")
                    if not ts:
                        continue
                    rows.append(
                        {
                            "symbol": symbol,
                            "date": str(ts)[:10],
                            "open": float(bar["o"]),
                            "high": float(bar["h"]),
                            "low": float(bar["l"]),
                            "close": float(bar["c"]),
                            "volume": int(bar["v"]),
                        }
                    )

            pages += 1
            page_token = payload.get("next_page_token")
            if not page_token:
                break
            if pages > 500:
                raise AlpacaDataError(
                    f"Alpaca pagination runaway: >500 pages for a {len(chunk)}-symbol chunk "
                    f"({start}..{end}) — aborting to avoid an infinite loop."
                )
