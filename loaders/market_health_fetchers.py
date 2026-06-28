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
        """Internal VIX fetch implementation. Fetch from database only.

        VIX is CRITICAL for circuit breaker logic (VIX >= 35 halts trading).
        FAIL-FAST: Do not silently fallback to yfinance. All VIX data must come from
        price_daily (single source of truth) to ensure circuit breaker decisions are
        based on consistent, auditable data.

        If price_daily is unavailable, this is a CRITICAL data failure that must surface
        immediately—trading cannot proceed without reliable VIX data for halt decisions.
        """
        try:
            from utils.db import DatabaseContext

            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT date, close, high, low FROM price_daily "
                    "WHERE symbol = '^VIX' AND date >= %s AND date <= %s ORDER BY date",
                    (start, end),
                )
                rows = cur.fetchall()
                if not rows or len(rows) == 0:
                    raise RuntimeError(
                        f"[CRITICAL] VIX data unavailable in price_daily for {start} to {end}. "
                        "VIX is required for circuit breaker halt decisions. "
                        "Check price_daily table and ensure VIX (^VIX) is loaded."
                    )
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
        except RuntimeError:
            raise
        except Exception as db_err:
            raise RuntimeError(
                f"[CRITICAL] Failed to fetch VIX from price_daily: {db_err}. "
                "VIX is required for circuit breaker halt decisions. "
                "Cannot proceed without CRITICAL market data. "
                "Check database connectivity and price_daily schema."
            ) from db_err


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
            dict with yield data keyed by date, or empty dict if no data available for date range.

        Raises:
            RuntimeError: If yield curve data cannot be fetched (OPTIONAL importance, but still fails fast)
        """
        try:
            result = self.breaker.execute(
                fetch_func=lambda: self._fetch_yield_curve_data(start, end),
                importance=DataImportance.OPTIONAL,
                fallback_value=None,
            )
            if result is None:
                raise RuntimeError(
                    f"Yield curve data unavailable for {start} to {end}. "
                    "Circuit breaker repeated failures. "
                    "Yield curve is used for market regime detection (Fed rate environment, inversion detection). "
                    "Cannot proceed without this data — check network connectivity and API availability."
                )
            if not isinstance(result, dict):
                raise RuntimeError(
                    f"Yield curve fetch returned invalid type {type(result).__name__}. "
                    f"Expected dict, got {result!r}. "
                    "Data corruption or API response format change detected."
                )
            return result
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(
                f"Yield curve fetch failed: {e}. "
                "Yield curve is used for market regime detection and cannot be unavailable. "
                f"Check database connectivity, API keys, and network status."
            ) from e

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
                raise RuntimeError(
                    "[YIELD_CURVE] No data field in API response. "
                    "Yield curve data is critical for market regime detection and cannot be absent."
                )

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

    Computes from trend_template_data to get advance/decline counts and new highs/lows.
    """

    def __init__(self) -> None:
        pass

    def fetch(self, start: date, end: date) -> dict[str, Any]:
        """Fetch market breadth data from trend_template_data.

        Returns: dict[date_str] -> {advance_decline_ratio, new_highs_count, new_lows_count}

        Breadth data is optional enrichment. If unavailable, returns empty dict.
        Fields will be NULL in market_health_daily until breadth data is available.
        """
        try:
            from utils.db import DatabaseContext

            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    WITH daily_breadth AS (
                        SELECT DISTINCT ON (date)
                            date,
                            COUNT(*) FILTER (WHERE price_above_sma50 = true) AS up_count,
                            COUNT(*) FILTER (WHERE price_above_sma50 = false) AS down_count,
                            COUNT(*) FILTER (WHERE high > LAG(high) OVER (PARTITION BY symbol ORDER BY date)) AS nh_count,
                            COUNT(*) FILTER (WHERE low < LAG(low) OVER (PARTITION BY symbol ORDER BY date)) AS nl_count
                        FROM trend_template_data
                        WHERE date >= %s AND date <= %s
                        GROUP BY date
                        ORDER BY date DESC
                    )
                    SELECT date, up_count, down_count, nh_count, nl_count
                    FROM daily_breadth
                    ORDER BY date ASC
                    """,
                    (start, end),
                )
                rows = cur.fetchall()
                if not rows:
                    logger.debug("[BREADTH_FETCHER] No breadth data available in trend_template_data")
                    return {}

                result = {}
                for row in rows:
                    d = row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0])
                    up = int(row[1]) if row[1] is not None else 0
                    down = int(row[2]) if row[2] is not None else 0
                    nh = int(row[3]) if row[3] is not None else 0
                    nl = int(row[4]) if row[4] is not None else 0

                    # Advance/decline ratio: up / down (neutral at 1.0)
                    ad_ratio = (up / down) if down > 0 else 1.0

                    result[d] = {
                        "advance_decline_ratio": round(ad_ratio, 3),
                        "new_highs_count": nh,
                        "new_lows_count": nl,
                    }

                logger.info(f"[BREADTH_FETCHER] Fetched breadth for {len(result)} dates from trend_template_data")
                return result
        except Exception as e:
            logger.warning(f"[BREADTH_FETCHER] Failed to fetch breadth data: {e} — returning empty (optional enrichment)")
            return {}
