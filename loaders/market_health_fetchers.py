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

    def __init__(self):
        self.breaker = CircuitBreaker(
            name="yfinance_vix",
            failure_threshold=3,
            recovery_timeout_sec=300,
            importance=DataImportance.CRITICAL,
        )

    def fetch(self, start: date, end: date) -> dict[str, Any]:
        """Fetch VIX data with circuit breaker protection. Fails fast if unavailable."""
        result = self.breaker.execute(
            fetch_func=lambda: self._fetch_vix_data(start, end),
            importance=DataImportance.CRITICAL,
            fallback_value=None,
        )
        if result is None:
            raise RuntimeError("VIX data unavailable - circuit breaker failed")
        return result if isinstance(result, dict) else {}

    def _fetch_vix_data(self, start: date, end: date) -> dict[str, Any]:
        """Internal VIX fetch implementation."""
        try:
            from datetime import datetime, timezone

            import pandas as pd
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

    def __init__(self):
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
            from datetime import datetime, timezone

            import yfinance

            spx_options = yfinance.Ticker("^SPX")
            options_chain = spx_options.option_chain(eval_date.isoformat())

            if options_chain.calls.empty or options_chain.puts.empty:
                return None

            total_calls = options_chain.calls["openInterest"].sum()
            total_puts = options_chain.puts["openInterest"].sum()

            if total_calls == 0:
                return None

            return total_puts / total_calls  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning(f"Put/call ratio fetch failed: {e}")
            raise


class YieldCurveFetcher:
    """Fetches yield curve data with circuit breaker."""

    def __init__(self):
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
                    result[item["date"]] = {
                        "yield_2y": float(item.get("2Y", 0)),
                        "yield_10y": float(item.get("10Y", 0)),
                        "yield_spread": float(item.get("10Y", 0)) - float(item.get("2Y", 0)),
                    }
            return result
        except Exception as e:
            logger.warning(f"Yield curve fetch failed: {e}")
            raise


class BreadthFetcher:
    """Fetches market breadth data (advance/decline)."""

    def fetch(self, start: date, end: date) -> dict[str, Any]:
        """Fetch market breadth data."""
        try:
            import pandas as pd
            import requests

            url = "https://api.example.com/market/breadth"
            params = {"start": start.isoformat(), "end": end.isoformat()}
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            result = {}
            for item in data.get("data", []):
                result[item["date"]] = {
                    "advances": item.get("advances", 0),
                    "declines": item.get("declines", 0),
                    "unchanged": item.get("unchanged", 0),
                    "advance_decline_ratio": (
                        item.get("advances", 0) / item.get("declines", 1) if item.get("declines", 0) > 0 else 0
                    ),
                }
            return result
        except Exception as e:
            logger.warning(f"Breadth fetch failed: {e}")
            raise
