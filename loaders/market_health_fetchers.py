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
        if result is not None and not isinstance(result, float):
            raise RuntimeError(
                f"[PUT_CALL_RATIO] Circuit breaker returned unexpected type {type(result).__name__}. "
                f"Expected float or None, got {result!r}. Circuit breaker logic may be corrupted."
            )
        return result

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
            dict with yield data keyed by date (may be empty if data unavailable/incomplete).
            Yield curve is OPTIONAL enrichment—returns empty dict rather than raising on data issues.
        """
        try:
            result = self.breaker.execute(
                fetch_func=lambda: self._fetch_yield_curve_data(start, end),
                importance=DataImportance.OPTIONAL,
                fallback_value=None,
            )
            if result is None:
                logger.debug(f"Yield curve data unavailable for {start} to {end} - circuit breaker exhausted")
                return {}
            if not isinstance(result, dict):
                logger.warning(
                    f"Yield curve fetch returned invalid type {type(result).__name__}. "
                    f"Expected dict, got {result!r}. Returning empty dict for optional enrichment."
                )
                return {}
            return result
        except RuntimeError as e:
            logger.warning(f"Yield curve fetch failed (optional enrichment): {e}")
            return {}
        except Exception as e:
            logger.warning(f"Yield curve fetch error (optional enrichment): {e}")
            return {}

    def _fetch_yield_curve_data(self, start: date, end: date) -> dict[str, Any]:
        """Internal yield curve fetch implementation.

        OPTIONAL enrichment: Skip dates with missing yield data (common for weekends/holidays/recent dates).
        Return available data only; incomplete dates are silently skipped (not an error for optional data).
        """
        try:
            import pandas as pd
            import requests

            fred_api_key = __import__("os").getenv("FRED_API_KEY")
            if not fred_api_key:
                logger.debug("FRED_API_KEY not configured — yield curve unavailable (optional enrichment)")
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
                logger.debug("[YIELD_CURVE] No data field in API response — yield curve unavailable")
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
                logger.debug(f"[YIELD_CURVE] Skipped {len(incomplete_dates)} dates with incomplete data (optional enrichment)")
            if result:
                logger.info(f"[YIELD_CURVE] Fetched {len(result)} dates with complete yield data")
            return result
        except Exception as e:
            logger.debug(f"Yield curve fetch failed (optional enrichment): {e}")
            return {}


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
        """
        try:
            from utils.db import DatabaseContext

            with DatabaseContext("read") as cur:
                # Compute daily advance/decline counts from trend_template_data
                cur.execute(
                    """
                    SELECT
                        date,
                        COUNT(*) FILTER (WHERE price_above_sma50 = true) AS advances,
                        COUNT(*) FILTER (WHERE price_above_sma50 = false) AS declines
                    FROM trend_template_data
                    WHERE date >= %s AND date <= %s
                    GROUP BY date
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
                    if row[1] is None:
                        raise ValueError(f"Missing advances data for date {d}")
                    if row[2] is None:
                        raise ValueError(f"Missing declines data for date {d}")

                    advances = int(row[1])
                    declines = int(row[2])

                    if declines <= 0:
                        raise ValueError(f"Invalid declines count ({declines}) for date {d} - cannot calculate breadth ratio")

                    ad_ratio = advances / declines

                    result[d] = {
                        "advance_decline_ratio": round(ad_ratio, 3),
                        "new_highs_count": None,  # Computed from price_daily separately if needed
                        "new_lows_count": None,   # Computed from price_daily separately if needed
                    }

                logger.info(f"[BREADTH_FETCHER] Fetched breadth for {len(result)} dates from trend_template_data")
                return result
        except Exception as e:
            logger.warning(f"[BREADTH_FETCHER] Failed to fetch breadth data: {e}. Breadth is optional enrichment, skipping.")
            return {}
