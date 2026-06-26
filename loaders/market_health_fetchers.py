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
        """Internal VIX fetch implementation. Try database first, then yfinance as fallback.

        VIX data is stored in price_daily table; prefer that over yfinance to ensure consistency
        with other market data (SPY prices, market health). Only fetch from yfinance if database
        has gaps or is missing data entirely.
        """
        # First, try to get VIX from price_daily table
        try:
            from utils.db import DatabaseContext

            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT date, close, high, low FROM price_daily "
                    "WHERE symbol = '^VIX' AND date >= %s AND date <= %s ORDER BY date",
                    (start, end),
                )
                rows = cur.fetchall()
                if rows and len(rows) > 0:
                    result = {}
                    for row in rows:
                        d = row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0])
                        result[d] = {
                            "vix_close": float(row[1]) if row[1] is not None else None,
                            "vix_high": float(row[3]) if row[3] is not None else None,
                            "vix_low": float(row[2]) if row[2] is not None else None,
                        }
                    logger.info(f"Fetched {len(result)} VIX dates from price_daily")
                    return result
        except Exception as db_err:
            logger.debug(f"Could not fetch VIX from price_daily: {db_err}, falling back to yfinance")

        # Fallback to yfinance if database fetch fails or returns no data
        try:
            import yfinance

            vix_data = yfinance.download("^VIX", start=start, end=end, progress=False)
            if vix_data.empty:
                raise ValueError(
                    f"VIX data unavailable from yfinance for {start} to {end}. "
                    f"Cannot compute circuit breaker decisions without valid VIX data."
                )

            result = {}
            for idx, row in vix_data.iterrows():
                result[idx.date().isoformat()] = {
                    "vix_close": float(row["Close"]) if row["Close"] is not None else None,
                    "vix_high": float(row["High"]) if row["High"] is not None else None,
                    "vix_low": float(row["Low"]) if row["Low"] is not None else None,
                }
            if not result:
                raise ValueError(
                    f"VIX fetch returned no data points despite non-empty frame for {start} to {end}. "
                    f"Data corruption or parsing error detected."
                )
            logger.info(f"Fetched {len(result)} VIX dates from yfinance")
            return result
        except ValueError:
            raise
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
        """Fetch yield curve data with circuit breaker protection.

        Returns:
            dict with yield data keyed by date, or special marker dict if data unavailable.
            Caller MUST check for _data_unavailable flag before using results.

        Raises:
            RuntimeError: Only for non-transient, non-recoverable failures (e.g., missing API key)

        Note: Yield curve data affects market health (Fed rate environment, inversion detection).
        Returning empty dict {} is confusing (looks like "successfully fetched 0 dates" vs. "API failed").
        Instead, we return {"_data_unavailable": True} to force explicit caller handling.
        """
        try:
            result = self.breaker.execute(
                fetch_func=lambda: self._fetch_yield_curve_data(start, end),
                importance=DataImportance.OPTIONAL,
                fallback_value=None,
            )
            if result is None:
                # Circuit breaker failed multiple times - return unavailable marker
                logger.warning(f"Yield curve circuit breaker OPEN: repeated failures for {start} to {end}. Data unavailable.")
                return {"_data_unavailable": True, "_reason": "circuit_breaker_open"}
            if not isinstance(result, dict):
                logger.warning(f"Yield curve fetch returned invalid type {type(result).__name__}, treating as unavailable")
                return {"_data_unavailable": True, "_reason": "invalid_response_type"}
            return result
        except Exception as e:
            # Optional data source failed - return unavailable marker instead of silently succeeding
            logger.warning(f"Yield curve fetch failed (optional data, marking unavailable): {e}")
            return {"_data_unavailable": True, "_reason": str(e)[:100]}

    def _fetch_yield_curve_data(self, start: date, end: date) -> dict[str, Any]:
        """Internal yield curve fetch implementation.

        Skip dates with missing yield data (common for weekends/holidays/recent dates).
        Return available data and allow forward-fill in the caller.
        """
        try:
            import pandas as pd
            import requests

            fred_api_key = __import__("os").getenv("FRED_API_KEY")
            if not fred_api_key:
                logger.error("CRITICAL: FRED_API_KEY environment variable not set — cannot fetch yield curve data for market regime detection")
                raise RuntimeError(
                    "FRED_API_KEY not configured. Yield curve data is required for market regime detection "
                    "(Fed rate environment, inversion detection). Check AWS Secrets Manager configuration."
                )

            url = "https://www.alphavantage.co/query"
            params = {
                "function": "TREASURY_YIELD",
                "interval": "daily",
                "apikey": fred_api_key,
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if "data" not in data:
                logger.debug("No yield curve data returned from API")
                return {}

            result = {}
            incomplete_dates = []
            for item in data["data"]:
                if start <= pd.to_datetime(item["date"]).date() <= end:
                    yield_2y = item.get("2Y")
                    yield_10y = item.get("10Y")

                    if yield_2y is None or yield_10y is None:
                        incomplete_dates.append(item["date"])
                        continue

                    result[item["date"]] = {
                        "yield_2y": float(yield_2y),
                        "yield_10y": float(yield_10y),
                        "yield_spread": float(yield_10y) - float(yield_2y),
                    }

            if incomplete_dates:
                raise RuntimeError(
                    f"[YIELD_CURVE] Incomplete yield data for {len(incomplete_dates)} date(s): "
                    f"{incomplete_dates[:3]}{'...' if len(incomplete_dates) > 3 else ''}. "
                    "Market regime detection requires complete 2Y/10Y yield data. Cannot proceed with partial data."
                )
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

        NOTE: Breadth calculation not yet implemented — returns empty dict.
        Market health metrics will proceed without breadth enrichment.
        """
        logger.info("[BREADTH_FETCHER] Breadth data calculation not yet implemented — market health will proceed without breadth metrics")
        return {}
