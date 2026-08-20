#!/usr/bin/env python3
"""Per-symbol timeout enforcement for yfinance calls - prevents one stuck symbol from hanging loaders.

CRITICAL FIX SESSION 91 (2026-08-12):
yfinance.Ticker() can hang indefinitely even with socket timeout because socket timeout
doesn't interrupt already-open network connections. This wrapper uses ThreadPoolExecutor
with explicit timeout enforcement to truly limit per-symbol calls.

Without this, analyst_upgrade_downgrade hung for 5+ hours (confirmed 2026-08-12) when
a single symbol's yfinance call hung, blocking all remaining symbols.
"""

import concurrent.futures
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from utils.external.yfinance_symbol import to_yfinance_symbol

logger = logging.getLogger(__name__)

T = TypeVar("T")


def call_with_timeout(func: Callable[..., T], timeout_sec: float, *args: Any, **kwargs: Any) -> T:
    """Execute a function with an absolute timeout using ThreadPoolExecutor.

    This is stronger than socket timeout because it truly interrupts the thread
    if the function hangs, rather than just setting a socket-level timeout.

    Args:
        func: Callable to execute (e.g., yfinance fetch)
        timeout_sec: Hard timeout in seconds
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Result of func

    Raises:
        TimeoutError: If func doesn't complete within timeout_sec
        RuntimeError: If func raises any other exception
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="yf-timeout") as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_sec)
        except concurrent.futures.TimeoutError:
            # Thread will continue running in background but won't block us
            raise TimeoutError(f"yfinance call exceeded {timeout_sec}s timeout") from None


class YFinanceTimeoutWrapper:
    """Wrapper for yfinance.Ticker that enforces per-symbol timeout."""

    def __init__(self, symbol: str, timeout_sec: float = 10.0):
        """Initialize wrapper for a symbol.

        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            timeout_sec: Timeout per attribute access (default 10s)
        """
        self.symbol = symbol
        self.timeout_sec = timeout_sec
        self._ticker = None

    def _get_attribute(self, attr_name: str) -> Any:
        """Fetch an attribute from yfinance.Ticker with timeout enforcement."""
        if self._ticker is None:
            # First access - create Ticker with timeout
            import yfinance as yf

            def create_ticker() -> Any:
                return yf.Ticker(to_yfinance_symbol(self.symbol))

            try:
                self._ticker = call_with_timeout(create_ticker, self.timeout_sec)
            except TimeoutError as err:
                raise RuntimeError(
                    f"yfinance Ticker creation timeout for {self.symbol} (>{self.timeout_sec}s)"
                ) from err

        # Get attribute with timeout
        def get_attr() -> Any:
            return getattr(self._ticker, attr_name)

        try:
            return call_with_timeout(get_attr, self.timeout_sec)
        except TimeoutError as err:
            raise RuntimeError(f"yfinance {attr_name} fetch timeout for {self.symbol} (>{self.timeout_sec}s)") from err

    def __getattr__(self, attr_name: str) -> Any:
        """Intercept attribute access to apply timeout enforcement."""
        if attr_name in ("_ticker", "symbol", "timeout_sec", "_get_attribute"):
            return object.__getattribute__(self, attr_name)
        return self._get_attribute(attr_name)
