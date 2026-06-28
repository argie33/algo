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
                raise RuntimeError(
                    f"[PUT_CALL_FETCHER] Options data missing for {eval_date}: "
                    f"calls={options_chain.calls.empty}, puts={options_chain.puts.empty}"
                )

            total_calls = float(options_chain.calls["openInterest"].sum())
            total_puts = float(options_chain.puts["openInterest"].sum())

            if total_calls == 0:
                raise RuntimeError(
                    f"[PUT_CALL_FETCHER] No call volume for {eval_date}. Cannot calculate ratio."
                )

            return float(total_puts / total_calls)
        except Exception as e:
            raise RuntimeError(
                f"[PUT_CALL_FETCHER] Fetch failed for {eval_date}: {e}"
            ) from e


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
                logger.warning(f"Yield curve data unavailable for {start} to {end} - circuit breaker exhausted. Returning empty dict for optional enrichment.")
                return {}
            if not isinstance(result, dict):
                logger.warning(f"Yield curve fetch returned invalid type {type(result).__name__}. Expected dict, got {result!r}. Returning empty dict for optional enrichment.")
                return {}
            return result
        except Exception as e:
            logger.warning(f"Yield curve fetch failed at circuit breaker level: {e}. Returning empty dict for optional enrichment.")
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
                raise RuntimeError("FRED_API_KEY not configured — cannot fetch yield curve")

            url = "https://www.alphavantage.co/query"
            params = {
                "function": "TREASURY_YIELD",
                "interval": "daily",
                "apikey": fred_api_key,
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if "data" not in data:
                raise ValueError(f"[YIELD_CURVE] No data field in API response: {data}")

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
            logger.warning(f"Yield curve fetch failed: {e}. Returning empty dict for optional enrichment.")
            return {}


class BreadthFetcher:
    """Fetches market breadth data (advance/decline, new highs/lows) from database.

    Computes from trend_template_data for advance/decline counts.
    Computes from price_daily for new 52-week highs/lows.
    """

    def __init__(self) -> None:
        pass

    def _compute_new_highs_lows(self, cur: Any, start: date, end: date) -> dict[str, tuple[int, int]]:
        """Compute new 52-week highs and lows for each date.

        Returns: dict[date_str] -> (new_highs_count, new_lows_count)

        For each symbol in price_daily, checks if close is highest/lowest in past 252 trading days.
        Uses window function to efficiently compute 52-week highs/lows across all symbols.
        """
        cur.execute(
            """
            WITH price_window AS (
                SELECT
                    date,
                    symbol,
                    close,
                    MAX(close) OVER (
                        PARTITION BY symbol
                        ORDER BY date
                        ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
                    ) AS high_252,
                    MIN(close) OVER (
                        PARTITION BY symbol
                        ORDER BY date
                        ROWS BETWEEN 251 PRECEDING AND CURRENT ROW
                    ) AS low_252
                FROM price_daily
                WHERE date >= %s AND date <= %s
            )
            SELECT
                date,
                COUNT(*) FILTER (WHERE close = high_252 AND high_252 IS NOT NULL) AS new_highs,
                COUNT(*) FILTER (WHERE close = low_252 AND low_252 IS NOT NULL) AS new_lows
            FROM price_window
            WHERE close IS NOT NULL AND high_252 IS NOT NULL AND low_252 IS NOT NULL
            GROUP BY date
            ORDER BY date ASC
            """,
            (start, end),
        )
        result = {}
        for row in cur.fetchall():
            d = row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0])
            result[d] = (int(row[1]) if row[1] is not None else 0, int(row[2]) if row[2] is not None else 0)
        return result

    def fetch(self, start: date, end: date) -> dict[str, Any]:
        """Fetch market breadth data from trend_template_data and price_daily.

        Returns: dict[date_str] -> {advance_decline_ratio, new_highs_count, new_lows_count}

        Breadth data is optional enrichment. If unavailable or incomplete, returns empty dict.
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
                    logger.debug(f"[BREADTH_FETCHER] No breadth data available for {start} to {end}. Returning empty dict for optional enrichment.")
                    return {}

                # Compute new highs/lows from price_daily
                try:
                    new_highs_lows = self._compute_new_highs_lows(cur, start, end)
                except Exception as e:
                    logger.warning(f"[BREADTH_FETCHER] New highs/lows computation failed: {e}. Proceeding without these values.")
                    new_highs_lows = {}

                result = {}
                for row in rows:
                    d = row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0])
                    if row[1] is None or row[2] is None:
                        logger.debug(f"[BREADTH_FETCHER] Skipping date {d} - missing advances or declines data (optional enrichment)")
                        continue

                    advances = int(row[1])
                    declines = int(row[2])

                    if declines <= 0:
                        logger.debug(f"[BREADTH_FETCHER] Skipping date {d} - invalid declines count ({declines}). Optional enrichment continues.")
                        continue

                    ad_ratio = advances / declines

                    # Get new highs/lows if available
                    nh, nl = new_highs_lows.get(d, (None, None))

                    result[d] = {
                        "advance_decline_ratio": round(ad_ratio, 3),
                        "new_highs_count": nh,
                        "new_lows_count": nl,
                    }

                logger.info(f"[BREADTH_FETCHER] Fetched breadth for {len(result)} dates (advances/declines + new highs/lows)")
                return result
        except Exception as e:
            logger.warning(f"[BREADTH_FETCHER] Failed to fetch breadth data: {e}. Returning empty dict for optional enrichment.")
            return {}
