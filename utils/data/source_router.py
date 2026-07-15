#!/usr/bin/env python3
"""Unified data source router with automatic fallback.

One-stop shop for all loaders. Routes each data type to the best source
with health-check based fallback. Tracks per-source success rate so
unhealthy sources are temporarily skipped.

Sources by data type (in priority order):
    OHLCV:        yfinance (sole source - Alpaca data subscription required for alternative)
    Fundamentals: SEC EDGAR → yfinance
    Economic:     FRED (only)

Health tracking:
    Each source has a rolling success rate. If success rate drops below
    50% over the last 20 requests, source is paused for 5 minutes.
    Auto-resumes after pause if heartbeat succeeds.

Usage:
    router = DataSourceRouter()
    df = router.fetch_ohlcv("AAPL", start, end)
    # router automatically tries Alpaca first, falls back if needed

    # See which source was used
    logger.info(router.last_source)  # "alpaca" / "polygon" / "yfinance"
"""

import json
import logging
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, cast

import requests
import yfinance as yf

from algo.infrastructure import retry
from utils.external.yfinance_circuit_breaker import get_circuit_breaker
from utils.infrastructure import EASTERN_TZ

if TYPE_CHECKING:
    from utils.external import SecEdgarClient

logger = logging.getLogger(__name__)


def _is_data_unavailable_marker(result: Any) -> bool:
    """Check if result is an explicit unavailability marker dict.

    Marker dicts have data_unavailable=True and should trigger fallback to next source.
    """
    return isinstance(result, dict) and result.get("data_unavailable") is True


def _call_with_timeout(fn: Callable[[], Any], timeout_sec: float = 30, retries: int = 3) -> Any:
    """Call a function with timeout protection and automatic retry on timeout."""
    for attempt in range(retries):
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fn)
                return future.result(timeout=timeout_sec)
        except FuturesTimeoutError:
            if attempt < retries - 1:
                logger.warning(f"Timeout (attempt {attempt + 1}/{retries}), retrying...")
                time.sleep(2**attempt)  # Exponential backoff: 1s, 2s, 4s
            continue
    raise TimeoutError(f"Function call exceeded {timeout_sec}s timeout after {retries} retries")


_YF_RATE_LIMIT_KEYWORDS = ("429", "rate", "too many", "invalid crumb", "unauthorized")


def _is_yf_rate_limit_error(e: Exception) -> bool:
    error_str = str(e).lower()
    return any(keyword in error_str for keyword in _YF_RATE_LIMIT_KEYWORDS)


def _yf_download_with_circuit_breaker(do_download: Callable[[], Any], timeout_sec: float, retries: int) -> Any:
    """Call yf.download() (via do_download) under the shared cross-ECS-task IP circuit breaker.

    Every yf.download() call site in this module previously called _call_with_timeout()
    directly, bypassing the shared circuit breaker that utils/external/yfinance.py's
    Ticker-based path already respects. Loaders using this batch-download path could keep
    hammering yfinance during an active shared-IP ban (set by any other ECS task hitting
    Ticker() calls), repeatedly re-triggering fresh 429s and preventing the ban from
    ever expiring. Mirrors the check/report pattern in utils/external/yfinance.py.
    """
    # wait_or_raise() only blocks this (billed) task for short bans; long bans raise
    # so the task fails fast instead of burning paid compute time asleep.
    circuit_breaker = get_circuit_breaker()
    circuit_breaker.wait_or_raise()

    try:
        result = _call_with_timeout(do_download, timeout_sec=timeout_sec, retries=retries)
        circuit_breaker.report_success()
        return result
    except Exception as e:
        if _is_yf_rate_limit_error(e):
            circuit_breaker.report_rate_limit_error()
        raise


@dataclass
class SourceHealth:
    """Rolling health stats for a data source."""

    name: str
    recent_results: deque[bool] = field(default_factory=lambda: deque(maxlen=20))
    paused_until: float = 0.0
    total_requests: int = 0
    total_failures: int = 0
    last_error: str | None = None

    @property
    def success_rate(self) -> float:
        if not self.recent_results:
            return 1.0  # Optimistic until proven otherwise
        return sum(self.recent_results) / len(self.recent_results)

    @property
    def is_paused(self) -> bool:
        return time.monotonic() < self.paused_until

    def record(self, success: bool, error: str | None = None) -> None:
        self.recent_results.append(success)
        self.total_requests += 1
        if not success:
            self.total_failures += 1
            self.last_error = error
            # Pause if recent success rate drops below 50% with min sample
            if len(self.recent_results) >= 10 and self.success_rate < 0.5:
                self.paused_until = time.monotonic() + 300  # 5 min cool-off
                logger.warning(
                    "Pausing source '%s' for 5 min (success_rate=%.0f%%, last_error=%s)",
                    self.name,
                    self.success_rate * 100,
                    error,
                )


class DataSourceRouter:
    """Routes data fetches across providers with fallback + health tracking."""

    def __init__(self) -> None:
        self._health: dict[str, SourceHealth] = {}
        self._lock = threading.Lock()
        self.last_source: str | None = None

        # Lazy clients - only construct when needed
        self._alpaca: Any = None
        self._alpaca_data: Any = None  # AlpacaMarketData, lazily constructed
        self._sec: SecEdgarClient | None = None

    def _get_health(self, name: str) -> SourceHealth:
        with self._lock:
            if name not in self._health:
                self._health[name] = SourceHealth(name=name)
            return self._health[name]

    def _try_chain(
        self,
        sources: list[tuple[str, Callable[[], Any]]],
        request_desc: str,
    ) -> Any | None:
        """Try sources in order, skipping paused ones, recording outcomes.

        Raises DataSourceError if all sources fail (not if symbol has no data).

        Treats data_unavailable marker dicts as "no data" and continues to next source.
        Returns the marker from the last source if all return markers.
        """
        last_exc = None
        last_marker = None
        sources_attempted = []
        for i, (name, fn) in enumerate(sources):
            sources_attempted.append(name)
            health = self._get_health(name)
            if health.is_paused:
                logger.debug(f"Skipping paused source '{name}' for {request_desc}")
                continue
            try:
                result = fn()
                # Check for explicit unavailability markers
                if _is_data_unavailable_marker(result):
                    last_marker = result
                    # Treat marker like None - no data from this source, try next
                    continue
                if result is None or (hasattr(result, "__len__") and len(result) == 0):
                    # Empty result = symbol doesn't exist or has no data (not a source problem)
                    # Don't count as source failure - skip gracefully without affecting health
                    continue
                health.record(True)
                self.last_source = name
                logger.debug(f"Source '{name}' served {request_desc}")
                return result
            except Exception as e:
                health.record(False, str(e))
                last_exc = e
                if i < len(sources) - 1:
                    next_source = sources[i + 1][0]
                    logger.warning(
                        "[DataSourceRouter] Primary source '%s' failed for %s: %s. Falling back to '%s'.",
                        name,
                        request_desc,
                        e,
                        next_source,
                    )
                else:
                    logger.debug(f"Source '{name}' failed for {request_desc}: {e}")
                continue
        # All sources failed or returned no data
        # Return marker from last source if available (shows data was unavailable, not error)
        if last_marker:
            return last_marker
        if last_exc:
            logger.error("All sources failed for %s. Last error: %s", request_desc, last_exc)
            from algo.exceptions import DataSourceError

            raise DataSourceError(
                request_desc=request_desc,
                sources_attempted=sources_attempted,
                last_error=last_exc,
            )
        # No sources attempted (all paused) - fail-fast with explicit marker
        logger.warning("[SOURCE_ROUTER] All data sources paused or unavailable - marking data_unavailable")
        return {"data_unavailable": True, "reason": "all_sources_paused"}

    # ============== OHLCV ==============

    def fetch_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
    ) -> Any | None:
        """Daily OHLCV bars. Returns DataFrame-shaped data or None."""
        sources = [
            ("yfinance", lambda: self._fetch_yfinance_ohlcv(symbol, start, end)),
        ]
        return self._try_chain(sources, f"OHLCV[{symbol} {start}..{end}]")

    def fetch_ohlcv_interval(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> Any | None:
        """OHLCV bars at a specified interval (1d/1wk/1mo).

        For daily bars (interval='1d'), routes through Alpaca if PRICE_DATA_SOURCE=alpaca.
        Falls back to yfinance for unsupported symbols or other intervals.
        """
        request_desc = f"OHLCV[{symbol} {start}..{end} {interval}]"

        # Only Alpaca supports daily bars; other intervals use yfinance
        if interval == "1d" and os.getenv("PRICE_DATA_SOURCE", "yfinance").lower() == "alpaca":
            alpaca_results = self._alpaca_batch_or_none([symbol], start, end, request_desc)
            if alpaca_results is not None and alpaca_results.get(symbol):
                self.last_source = "alpaca"
                return alpaca_results[symbol]
            # Alpaca failed or symbol not served - fall through to yfinance

        sources = [
            (
                "yfinance",
                lambda: self._fetch_yfinance_ohlcv(symbol, start, end, interval=interval),
            ),
        ]
        return self._try_chain(sources, request_desc)

    def fetch_ohlcv_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
        interval: str = "1d",
    ) -> dict[str, list[dict[str, Any]] | None]:
        """Batch fetch OHLCV for multiple symbols. Returns dict[symbol] -> rows or None.

        Source selection (PRICE_DATA_SOURCE env / algo config):
        - "yfinance" (default): unchanged legacy path.
        - "alpaca": Alpaca Market Data first (genuinely batched - ~200 symbols per
          HTTP request, full SIP historical data on the free plan for windows older
          than 15 minutes). Fallback to yfinance is PER-SYMBOL: symbols Alpaca
          doesn't serve (caret indexes, OTC/delisted stragglers) are re-fetched
          through the yfinance batch path and merged, so switching primaries never
          creates per-symbol data holes. A wholesale Alpaca failure falls back to
          the full yfinance batch. Only daily bars route to Alpaca; other
          intervals stay on yfinance.
        """
        request_desc = f"OHLCV_BATCH[{len(symbols)} symbols {start}..{end} {interval}]"
        if interval == "1d" and os.getenv("PRICE_DATA_SOURCE", "yfinance").lower() == "alpaca":
            alpaca_results = self._alpaca_batch_or_none(symbols, start, end, request_desc)
            if alpaca_results is not None:
                self._fill_alpaca_residual_from_yfinance(alpaca_results, symbols, start, end)
                return alpaca_results
            # Wholesale Alpaca failure (auth/outage) - full yfinance fallback below.

        sources: list[tuple[str, Callable[[], Any]]] = [
            (
                "yfinance",
                lambda: self._fetch_yfinance_ohlcv_batch(symbols, start, end, interval=interval),
            )
        ]
        results = self._try_chain(sources, request_desc)
        return cast(dict[str, list[dict[str, Any]] | None], results if results else dict.fromkeys(symbols))

    def _alpaca_batch_or_none(
        self, symbols: list[str], start: date, end: date, request_desc: str
    ) -> dict[str, list[dict[str, Any]] | None] | None:
        """Alpaca batch with router health accounting; None on wholesale failure."""
        health = self._get_health("alpaca")
        if health.is_paused:
            logger.warning(f"[DataSourceRouter] Alpaca paused - full yfinance fallback for {request_desc}")
            return None
        try:
            results = self._fetch_alpaca_ohlcv_batch(symbols, start, end)
        except Exception as e:
            health.record(False, str(e))
            logger.warning(
                "[DataSourceRouter] Primary source 'alpaca' failed for %s: %s. Falling back to 'yfinance'.",
                request_desc,
                e,
            )
            return None
        health.record(True)
        self.last_source = "alpaca"
        return results

    def _fill_alpaca_residual_from_yfinance(
        self,
        alpaca_results: dict[str, list[dict[str, Any]] | None],
        symbols: list[str],
        start: date,
        end: date,
    ) -> None:
        """Re-fetch symbols Alpaca returned nothing for via yfinance and merge in place.

        Best-effort: a yfinance failure here must not discard the successful
        Alpaca batch - unresolved symbols simply stay None (same semantics as a
        symbol with no data).
        """
        residual = [s for s in symbols if not alpaca_results.get(s)]
        if not residual:
            return
        logger.info(
            f"[DataSourceRouter] Alpaca served {len(symbols) - len(residual)}/{len(symbols)} symbols; "
            f"fetching {len(residual)} residual via yfinance: {residual[:10]}"
        )
        try:
            yf_results = self._fetch_yfinance_ohlcv_batch(residual, start, end, interval="1d")
        except Exception as e:
            logger.warning(
                f"[DataSourceRouter] yfinance residual fetch failed for {len(residual)} symbols "
                f"(Alpaca batch retained): {e}"
            )
            return
        if not isinstance(yf_results, dict) or _is_data_unavailable_marker(yf_results):
            return
        for sym in residual:
            rows = yf_results.get(sym)
            if rows and not _is_data_unavailable_marker(rows):
                alpaca_results[sym] = rows

    def _fetch_alpaca_ohlcv_batch(
        self, symbols: list[str], start: date, end: date
    ) -> dict[str, list[dict[str, Any]] | None]:
        """Daily bars from Alpaca Market Data, shaped identically to the yfinance batch."""
        from utils.external.alpaca_market_data import AlpacaMarketData

        if self._alpaca_data is None:
            self._alpaca_data = AlpacaMarketData()
        fetched = self._alpaca_data.fetch_daily_bars(symbols, start, end)
        # Symbols absent from Alpaca's response get None so _try_chain/callers keep
        # the same per-symbol semantics as the yfinance batch path.
        results: dict[str, list[dict[str, Any]] | None] = dict.fromkeys(symbols)
        results.update(fetched)
        return results

    @retry(max_attempts=2, base_delay=2.0, exceptions=(Exception,))
    def _fetch_yfinance_ohlcv(
        self, symbol: str, start: date, end: date, interval: str = "1d"
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        if yf is None:
            logger.error("[yfinance] yfinance not installed - dependency missing")
            # MEDIUM FIX: Return explicit marker instead of None per GOVERNANCE.md
            # Allows _try_chain() to distinguish dependency failure from missing data
            return {
                "data_unavailable": True,
                "reason": "yfinance_not_installed",
                "details": "yfinance library required for price history download",
            }
        logger.debug(f"[yfinance] Fetching {symbol} from {start} to {end} interval={interval}")
        yf_symbol = symbol.replace(".", "-") if "." in symbol else symbol
        try:

            def do_download() -> Any:
                # yfinance 0.2.40+ requires curl_cffi and doesn't accept requests.Session
                # Let yfinance handle its own session management for compatibility
                return yf.download(
                    yf_symbol,
                    start=start,
                    end=end,
                    interval=interval,
                    auto_adjust=False,
                    progress=False,
                )

            logger.debug(f"[yfinance] Calling yf.download for {yf_symbol} with 120s timeout (AWS VPC)")
            hist = _yf_download_with_circuit_breaker(do_download, timeout_sec=120, retries=3)

            if hist is None or hist.empty:
                logger.debug(f"[yfinance] No data returned for {symbol}")
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "no_historical_data",
                }
            logger.debug(f"[yfinance] Got {len(hist)} rows for {symbol}")

            # Fix: yfinance returns MultiIndex DataFrame when symbol provided as string
            # Flatten column names from (Price, Ticker) to just Price
            if hasattr(hist.columns, "levels"):
                # MultiIndex columns: get level 0 (the price type)
                hist.columns = hist.columns.get_level_values(0)

            rows = []
            for idx, row in hist.iterrows():
                try:
                    rows.append(
                        {
                            "symbol": symbol,
                            "date": (idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]),
                            "open": float(row["Open"]),
                            "high": float(row["High"]),
                            "low": float(row["Low"]),
                            "close": float(row["Close"]),
                            "volume": int(row["Volume"]),
                        }
                    )
                except (KeyError, TypeError, ValueError) as e:
                    logger.debug(f"[yfinance] Skipped invalid row {idx}: {e}")
                    continue

            if not rows:
                logger.warning(f"[yfinance] No valid rows for {symbol} after parsing")
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "invalid_or_missing_data",
                }

            return rows
        except TimeoutError as e:
            logger.warning(f"yfinance timeout for {symbol} (60s exceeded): {e}")
            raise Exception(f"yfinance timeout: {e}") from e
        except (ValueError, ZeroDivisionError, TypeError) as e:
            if any(
                keyword in str(e).lower()
                for keyword in [
                    "429",
                    "rate",
                    "too many",
                    "temporarily",
                    "timeout",
                    "json",
                    "parse",
                ]
            ):
                logger.warning(f"yfinance rate limited or parse error for {symbol}: {e}")
                raise Exception(f"yfinance rate limited: {e}") from e
            logger.error(f"yfinance error for {symbol}: {e}")
            raise

    @retry(max_attempts=2, base_delay=2.0, exceptions=(Exception,))
    def _fetch_yfinance_ohlcv_batch(
        self, symbols: list[str], start: date, end: date, interval: str = "1d"
    ) -> dict[str, list[dict[str, Any]] | None]:
        """Batch fetch multiple symbols in one API call. Returns dict[symbol] -> rows."""
        if yf is None:
            logger.error("[yfinance] yfinance not installed")
            return dict.fromkeys(symbols)

        if not symbols:
            raise ValueError("symbols list cannot be empty")

        logger.debug(f"[yfinance] Batch fetching {len(symbols)} symbols from {start} to {end} interval={interval}")

        # Convert symbols to yfinance format
        yf_symbols = [sym.replace(".", "-") if "." in sym else sym for sym in symbols]

        try:

            def do_download() -> Any:
                # yfinance 0.2.40+ requires curl_cffi and doesn't accept requests.Session
                # Let yfinance handle its own session management for compatibility
                return yf.download(
                    yf_symbols,
                    start=start,
                    end=end,
                    interval=interval,
                    auto_adjust=False,
                    progress=False,
                )

            logger.info(f"[yfinance] Batch calling yf.download for {len(symbols)} symbols with 180s timeout")
            try:
                hist = _yf_download_with_circuit_breaker(do_download, timeout_sec=180, retries=3)
                logger.debug("[yfinance] Batch download completed successfully")
            except TimeoutError as timeout_e:
                logger.critical(f"[yfinance] BATCH TIMEOUT EXCEEDED: {timeout_e}")
                raise
            except (
                requests.RequestException,
                requests.Timeout,
                json.JSONDecodeError,
            ) as e:
                logger.critical(
                    f"[yfinance] BATCH FETCH FAILED: {type(e).__name__}: {e}",
                    exc_info=True,
                )
                raise

            if hist is None or hist.empty:
                logger.debug(f"[yfinance] No data returned for batch of {len(symbols)} symbols")
                return dict.fromkeys(symbols)

            logger.debug(f"[yfinance] Batch got {len(hist)} rows total for {len(symbols)} symbols")

            # Parse the batch result into per-symbol rows
            results: dict[str, list[dict[str, Any]]] = {sym: [] for sym in symbols}

            for idx, row in hist.iterrows():
                for i, symbol in enumerate(symbols):
                    try:
                        yf_symbol = yf_symbols[i]
                        # yfinance batch returns MultiIndex columns: (Price_Type, Symbol)
                        # E.g., ('Open', 'AAPL'), ('Close', 'AAPL'), etc.
                        open_val = row.get(("Open", yf_symbol))
                        high_val = row.get(("High", yf_symbol))
                        low_val = row.get(("Low", yf_symbol))
                        close_val = row.get(("Close", yf_symbol))
                        volume_val = row.get(("Volume", yf_symbol))

                        # Skip if any required value is missing or is NaN
                        if any(
                            v is None or (isinstance(v, float) and v != v)
                            for v in [
                                open_val,
                                high_val,
                                low_val,
                                close_val,
                                volume_val,
                            ]
                        ):
                            continue

                        results[symbol].append(
                            {
                                "symbol": symbol,
                                "date": (idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]),
                                "open": float(open_val),
                                "high": float(high_val),
                                "low": float(low_val),
                                "close": float(close_val),
                                "volume": int(volume_val),
                            }
                        )
                    except (KeyError, TypeError, ValueError) as e:
                        logger.debug(f"[yfinance] Skipped invalid row for {symbol} at {idx}: {e}")
                        continue

            # Filter out symbols with no valid rows and return only those with data
            return {sym: rows if rows else None for sym, rows in results.items()}

        except TimeoutError as e:
            logger.warning(f"yfinance timeout for batch of {len(symbols)} symbols: {e}")
            raise Exception(f"yfinance batch timeout: {e}") from e
        except (ValueError, ZeroDivisionError, TypeError) as e:
            if any(
                keyword in str(e).lower()
                for keyword in [
                    "429",
                    "rate",
                    "too many",
                    "temporarily",
                    "timeout",
                    "json",
                    "parse",
                ]
            ):
                logger.warning(f"yfinance batch rate limited or parse error: {e}")
                raise Exception(f"yfinance batch rate limited: {e}") from e
            logger.error(f"yfinance batch error: {e}")
            raise

    # ============== FUNDAMENTALS ==============

    def fetch_balance_sheet(self, symbol: str, period: str = "annual") -> Any | None:
        """Balance sheet rows. SEC EDGAR primary (free, official)."""
        sources = [
            ("sec_edgar", lambda: self._sec_balance_sheet(symbol, period)),
            ("yfinance", lambda: self._yf_balance_sheet(symbol, period)),
        ]
        return self._try_chain(sources, f"BalanceSheet[{symbol} {period}]")

    def fetch_income_statement(self, symbol: str, period: str = "annual") -> Any | None:
        sources = [
            ("sec_edgar", lambda: self._sec_income(symbol, period)),
            ("yfinance", lambda: self._yf_income(symbol, period)),
        ]
        return self._try_chain(sources, f"Income[{symbol} {period}]")

    def fetch_cash_flow(self, symbol: str, period: str = "annual") -> Any | None:
        sources = [
            ("sec_edgar", lambda: self._sec_cash_flow(symbol, period)),
            ("yfinance", lambda: self._yf_cash_flow(symbol, period)),
        ]
        return self._try_chain(sources, f"CashFlow[{symbol} {period}]")

    def _sec_client(self) -> Any:
        if self._sec is None:
            from utils.external import SecEdgarClient

            self._sec = SecEdgarClient()
        return self._sec

    def _sec_balance_sheet(self, symbol: str, period: str) -> Any:
        return self._sec_client().get_balance_sheet(symbol, period)

    def _sec_income(self, symbol: str, period: str) -> Any:
        return self._sec_client().get_income_statement(symbol, period)

    def _sec_cash_flow(self, symbol: str, period: str) -> Any:
        return self._sec_client().get_cash_flow(symbol, period)

    def _yf_balance_sheet(self, symbol: str, period: str) -> Any:
        try:
            from utils.external import get_ticker

            def fetch() -> Any:
                # Use wrapper's get_ticker to ensure rate-limited access
                ticker = get_ticker(symbol)
                if not ticker:
                    # MEDIUM FIX: Return marker instead of None per GOVERNANCE.md
                    # Allows _try_chain() to distinguish API failure from missing data
                    return {
                        "data_unavailable": True,
                        "reason": "ticker_fetch_failed",
                        "symbol": symbol,
                        "details": "Could not fetch ticker (API error, rate limit, or invalid symbol)",
                    }
                return ticker.balance_sheet if period == "annual" else ticker.quarterly_balance_sheet

            df = _call_with_timeout(fetch, timeout_sec=30)
            if df is None or df.empty:
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "balance_sheet_unavailable",
                }
            return df.to_dict(orient="index")
        except TimeoutError as e:
            raise TimeoutError(f"yfinance balance_sheet timeout for {symbol}") from e

    def _yf_income(self, symbol: str, period: str) -> Any:
        try:
            from utils.external import get_ticker

            def fetch() -> Any:
                # Use wrapper's get_ticker to ensure rate-limited access
                ticker = get_ticker(symbol)
                if not ticker:
                    # MEDIUM FIX: Return marker instead of None per GOVERNANCE.md
                    return {
                        "data_unavailable": True,
                        "reason": "ticker_fetch_failed",
                        "symbol": symbol,
                        "details": "Could not fetch ticker (API error, rate limit, or invalid symbol)",
                    }
                return ticker.income_stmt if period == "annual" else ticker.quarterly_income_stmt

            df = _call_with_timeout(fetch, timeout_sec=30)
            if df is None or df.empty:
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "income_statement_unavailable",
                }
            return df.to_dict(orient="index")
        except TimeoutError as e:
            raise TimeoutError(f"yfinance income_stmt timeout for {symbol}") from e

    def _yf_cash_flow(self, symbol: str, period: str) -> Any:
        try:
            from utils.external import get_ticker

            def fetch() -> Any:
                # Use wrapper's get_ticker to ensure rate-limited access
                ticker = get_ticker(symbol)
                if not ticker:
                    # MEDIUM FIX: Return marker instead of None per GOVERNANCE.md
                    return {
                        "data_unavailable": True,
                        "reason": "ticker_fetch_failed",
                        "symbol": symbol,
                        "details": "Could not fetch ticker (API error, rate limit, or invalid symbol)",
                    }
                return ticker.cashflow if period == "annual" else ticker.quarterly_cashflow

            df = _call_with_timeout(fetch, timeout_sec=30)
            if df is None or df.empty:
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "cashflow_unavailable",
                }
            return df.to_dict(orient="index")
        except TimeoutError as e:
            raise TimeoutError(f"yfinance cashflow timeout for {symbol}") from e

    # ============== MARKET CLOSE DATA CHECK ==============

    def check_market_close_data_available_fast(self, symbol: str = "SPY", timeout_sec: int = 15) -> bool:
        """Quick check if market close data is available from yfinance (short timeout).

        Used by EOD pipeline to verify yfinance has ingested today's close data.
        yfinance typically has data 5-15 min after market close (4 PM ET).

        Uses a SHORT timeout (default 15s) to quickly determine availability without
        burning time on long network calls. This allows more frequent retries within
        the overall market close wait budget.

        Args:
            symbol: Which symbol to check (default 'SPY')
            timeout_sec: Timeout for the yfinance API call (default 15s)

        Returns:
            True if data available, False if timeout/error
        """
        from datetime import datetime, timedelta

        try:
            today = datetime.now(EASTERN_TZ).date()

            if yf is None:
                logger.error("[yfinance-fast-check] yfinance not installed")
                return False

            yf_symbol = symbol.replace(".", "-") if "." in symbol else symbol

            def do_download() -> Any:
                return yf.download(
                    yf_symbol,
                    start=today,
                    end=today + timedelta(days=1),
                    interval="1d",
                    auto_adjust=False,
                    progress=False,
                )

            # Use SHORT timeout for quick check (don't burn time waiting for API)
            hist = _yf_download_with_circuit_breaker(do_download, timeout_sec=timeout_sec, retries=1)

            # Check if we got valid data with today's close
            if hist is None or hist.empty:
                logger.debug(f"[yfinance-fast-check] No data for {symbol}")
                return False

            latest_row = hist.iloc[-1] if not hist.empty else None
            if latest_row is not None and "Close" in latest_row:
                logger.info(f"[yfinance-fast-check] ✓ {symbol} close data available")
                return True

            logger.debug(f"[yfinance-fast-check] Data for {symbol} missing close column")
            return False

        except TimeoutError as e:
            msg = f"Market close data check timeout after {timeout_sec}s for {symbol}"
            raise TimeoutError(msg) from e
        except Exception as e:
            msg = f"Error checking market close data for {symbol}: {type(e).__name__}: {str(e)[:100]}"
            raise RuntimeError(msg) from e

    # ============== HEALTH REPORT ==============

    def health_report(self) -> dict[str, Any]:
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
