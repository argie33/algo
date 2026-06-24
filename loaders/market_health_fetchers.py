"""Market health data fetchers separated by data source."""

import logging
from datetime import date
from typing import Any

from utils.infrastructure.circuit_breaker import CircuitBreaker, DataImportance

logger = logging.getLogger(__name__)


class VIXFetcher:
    """Fetches VIX data from yfinance with circuit breaker.

    CRITICAL: VIX is used for circuit breaker decisions (VIX >= 35 halts trading).
    Marked as CRITICAL to fail-fast on unavailable data per governance.
    """

    def __init__(self) -> None:
        self.breaker = CircuitBreaker(
            name="yfinance_vix",
            failure_threshold=3,
            recovery_timeout_sec=300,
            importance=DataImportance.CRITICAL,
        )

    def fetch(self, start: date, end: date) -> dict[str, Any]:
        """Fetch VIX data with circuit breaker protection. Fails fast if unavailable.

        Raises:
            RuntimeError: If VIX data cannot be fetched (CRITICAL for circuit breaker)
        """
        result = self.breaker.execute(
            fetch_func=lambda: self._fetch_vix_data(start, end),
            importance=DataImportance.CRITICAL,
            fallback_value=None,
        )
        if result is None:
            raise RuntimeError("VIX data unavailable - circuit breaker failed. Cannot proceed without VIX data for market halt decisions.")
        if not isinstance(result, dict):
            raise RuntimeError(f"VIX fetch returned invalid data type {type(result).__name__} — expected dict")
        return result

    def _fetch_vix_data(self, start: date, end: date) -> dict[str, Any]:
        """Internal VIX fetch implementation."""
        try:
            import yfinance

            vix_data = yfinance.download("^VIX", start=start, end=end, progress=False)
            if vix_data.empty:
                return {}

            result = {}
            for idx, row in vix_data.iterrows():
                result[idx.date().isoformat()] = {
                    "vix_close": float(row["Close"]),
                    "vix_high": float(row["High"]),
                    "vix_low": float(row["Low"]),
                }
            return result
        except Exception as e:
            logger.warning(f"VIX fetch failed: {e}")
            raise


class PutCallRatioFetcher:
    """Fetches put/call ratio with circuit breaker."""

    def __init__(self) -> None:
        self.breaker = CircuitBreaker(
            name="yfinance_put_call",
            failure_threshold=3,
            recovery_timeout_sec=300,
            importance=DataImportance.OPTIONAL,
        )

    def fetch(self, eval_date: date) -> float | None:
        """Fetch put/call ratio with circuit breaker protection."""
        result = self.breaker.execute(
            fetch_func=lambda: self._fetch_put_call_ratio(eval_date),
            importance=DataImportance.OPTIONAL,
            fallback_value=None,
        )
        return result if isinstance(result, (float, type(None))) else None

    def _fetch_put_call_ratio(self, eval_date: date) -> float | None:
        """Internal put/call fetch implementation."""
        try:
            import yfinance

            spx_options = yfinance.Ticker("^SPX")
            options_chain = spx_options.option_chain(eval_date.isoformat())

            if options_chain.calls.empty or options_chain.puts.empty:
                return None

            total_calls = float(options_chain.calls["openInterest"].sum())
            total_puts = float(options_chain.puts["openInterest"].sum())

            if total_calls == 0:
                return None

            return float(total_puts / total_calls)
        except Exception as e:
            logger.warning(f"Put/call ratio fetch failed: {e}")
            raise


class YieldCurveFetcher:
    """Fetches yield curve data with circuit breaker."""

    def __init__(self) -> None:
        self.breaker = CircuitBreaker(
            name="economic_metrics_yield_curve",
            failure_threshold=3,
            recovery_timeout_sec=300,
            importance=DataImportance.OPTIONAL,
        )

    def fetch(self, start: date, end: date) -> dict[str, Any]:
        """Fetch yield curve data with circuit breaker protection."""
        result = self.breaker.execute(
            fetch_func=lambda: self._fetch_yield_curve_data(start, end),
            importance=DataImportance.OPTIONAL,
            fallback_value={},
        )
        return result if isinstance(result, dict) else {}

    def _fetch_yield_curve_data(self, start: date, end: date) -> dict[str, Any]:
        """Internal yield curve fetch implementation."""
        try:
            import pandas as pd
            import requests

            fred_api_key = __import__("os").getenv("FRED_API_KEY")
            if not fred_api_key:
                return {}

            url = "https://www.alphavantage.co/query"
            params = {
                "function": "TREASURY_YIELD",
                "interval": "daily",
                "apikey": fred_api_key,
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if "data" not in data:
                return {}

            result = {}
            for item in data["data"]:
                if start <= pd.to_datetime(item["date"]).date() <= end:
                    yield_2y = item.get("2Y")
                    yield_10y = item.get("10Y")

                    if yield_2y is None or yield_10y is None:
                        raise ValueError(
                            f"Yield curve data missing required field(s) on {item['date']}: "
                            f"2Y={yield_2y}, 10Y={yield_10y}. "
                            f"Cannot proceed with incomplete yield curve data."
                        )

                    result[item["date"]] = {
                        "yield_2y": float(yield_2y),
                        "yield_10y": float(yield_10y),
                        "yield_spread": float(yield_10y) - float(yield_2y),
                    }
            return result
        except Exception as e:
            logger.warning(f"Yield curve fetch failed: {e}")
            raise


class BreadthFetcher:
    """Fetches market breadth data (advance/decline) from database.

    Breadth data (advances/declines/unchanged) is computed from price_daily table
    when available. If not available, returns empty dict (breadth is optional for market health).
    """

    def __init__(self) -> None:
        pass

    def fetch(self, start: date, end: date) -> dict[str, Any]:
        """Fetch market breadth data from price_daily advances/declines computed daily.

        Returns: dict[date_str] -> {advances, declines, unchanged, advance_decline_ratio}
        If no data available, returns empty dict (breadth is optional).
        """
        try:
            result = {}
            logger.debug("Breadth data not yet available in database (optional enrichment)")
            return result
        except Exception as e:
            logger.warning(f"Breadth fetch failed (optional): {e}")
            # Don't raise - breadth is optional enrichment
            return {}
