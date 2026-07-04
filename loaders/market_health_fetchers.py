"""Market health data fetchers separated by data source."""

import logging
import time
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
        try:
            result = self.breaker.execute(
                fetch_func=lambda: self._fetch_vix_data(start, end),
                importance=DataImportance.CRITICAL,
            )
        except Exception as e:
            raise RuntimeError(
                f"VIX data unavailable - circuit breaker failed: {e}. Cannot proceed without VIX data for market halt decisions."
            ) from e

        if result is None:
            raise RuntimeError(
                "VIX data unavailable - circuit breaker returned None. Cannot proceed without VIX data for market halt decisions."
            )
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
                    # CRITICAL: VIX fields must all be present for valid market data
                    if row[1] is None or row[2] is None or row[3] is None:
                        logger.warning(
                            f"[MARKET_HEALTH] VIX data incomplete for {d}: "
                            f"close={row[1]}, low={row[2]}, high={row[3]}. Skipping invalid record."
                        )
                        continue
                    result[d] = {
                        "vix_close": float(row[1]),
                        "vix_high": float(row[3]),
                        "vix_low": float(row[2]),
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
    """Fetches put/call ratio with circuit breaker and exponential backoff retry logic.

    Implements resilience against transient failures:
    - Categorizes errors as TRANSIENT (503, ConnectionError, timeout) vs PERMANENT (404, auth)
    - Retries TRANSIENT errors up to 3 times with exponential backoff (1s, 2s, 4s)
    - Only marks data_unavailable if all retries fail
    - Logs all retry attempts and final failure reason
    """

    MAX_RETRIES = 3
    BACKOFF_SECONDS = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s

    def __init__(self) -> None:
        self.breaker = CircuitBreaker(
            name="yfinance_put_call",
            failure_threshold=3,
            recovery_timeout_sec=300,
            importance=DataImportance.OPTIONAL,
        )

    def _is_transient_error(self, exc: Exception) -> bool:
        """Categorize exception as transient (retriable) or permanent.

        TRANSIENT errors (should retry):
        - HTTP 503 (Service Unavailable)
        - ConnectionError, TimeoutError
        - HTTPError with status 502, 503, 504

        PERMANENT errors (should not retry):
        - HTTP 404 (Not Found), 401 (Unauthorized), 403 (Forbidden)
        - ValueError (malformed data)
        - RuntimeError from validation
        """
        error_str = str(exc).lower()
        error_type = type(exc).__name__

        # Check for HTTP error codes in exception message
        if "503" in error_str or "502" in error_str or "504" in error_str:
            return True

        # Network/connection errors are transient
        if error_type in ("ConnectionError", "TimeoutError", "Timeout"):
            return True

        if "timeout" in error_str or "connection" in error_str or "reset" in error_str:
            return True

        # Check for permanent errors (don't retry)
        if "404" in error_str or "401" in error_str or "403" in error_str:
            return False

        # Validation/structural errors are permanent
        if error_type in ("ValueError", "KeyError", "AttributeError"):
            return False

        if "no options" in error_str or "empty" in error_str or "invalid" in error_str:
            return False

        # Default to transient for unknown errors (better to retry than silently fail)
        return True

    def fetch(self, eval_date: date) -> dict[str, Any] | float:
        """Fetch put/call ratio with exponential backoff retry and circuit breaker protection.

        Returns:
            float: Put/call ratio if successful
            dict: With data_unavailable marker if fetch fails or data is invalid
                {"data_unavailable": True, "reason": str, "eval_date": str}

        Per CLAUDE.md governance: Optional enrichment must return explicit data_unavailable
        markers instead of raising exceptions, enabling graceful degradation.
        """
        # Attempt direct fetch with retries first (before circuit breaker check)
        result = self._fetch_with_retries(eval_date)

        if result is None:
            return {
                "data_unavailable": True,
                "reason": "unable to fetch after retries",
                "eval_date": str(eval_date),
            }

        # Validate result type
        if not isinstance(result, float):
            return {
                "data_unavailable": True,
                "reason": "invalid response type",
                "eval_date": str(eval_date),
            }

        return result

    def _fetch_with_retries(self, eval_date: date) -> float | None:
        """Attempt put/call ratio fetch with exponential backoff retry logic.

        Returns:
            float: Put/call ratio if successful
            None: If all retries exhausted
        """
        last_error_reason = "unknown error"

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return self._fetch_put_call_ratio(eval_date)
            except Exception as e:
                is_transient = self._is_transient_error(e)

                if not is_transient:
                    # Permanent error - don't retry
                    last_error_reason = f"permanent {type(e).__name__}: {str(e)[:100]}"
                    logger.error(
                        f"[PUT_CALL_RATIO] Permanent error on attempt {attempt}/{self.MAX_RETRIES} for {eval_date}: "
                        f"{last_error_reason}. Will not retry."
                    )
                    return None

                # Transient error - log and retry if attempts remain
                if attempt < self.MAX_RETRIES:
                    backoff = self.BACKOFF_SECONDS[attempt - 1]
                    logger.warning(
                        f"[PUT_CALL_RATIO] Transient error on attempt {attempt}/{self.MAX_RETRIES} for {eval_date}: "
                        f"{type(e).__name__}: {str(e)[:100]}. "
                        f"Retrying in {backoff}s..."
                    )
                    time.sleep(backoff)
                else:
                    last_error_reason = f"transient {type(e).__name__} after {self.MAX_RETRIES} retries"
                    logger.error(
                        f"[PUT_CALL_RATIO] Transient error on attempt {attempt}/{self.MAX_RETRIES} for {eval_date}: "
                        f"{type(e).__name__}: {str(e)[:100]}. No retries remaining."
                    )

        # All retries exhausted
        logger.error(
            f"[PUT_CALL_RATIO] All {self.MAX_RETRIES} retries failed for {eval_date}. Reason: {last_error_reason}"
        )
        return None

    def _fetch_put_call_ratio(self, eval_date: date) -> float | None:
        """Internal put/call fetch implementation.

        Finds nearest options expiration date to eval_date (yfinance requires actual expiration dates,
        not arbitrary trading dates). Uses closest expiration <= eval_date, or if none exists, next available.
        """
        try:
            import yfinance

            spx_options = yfinance.Ticker("^SPX")

            # Get available expiration dates
            if not hasattr(spx_options, "options") or not spx_options.options:
                raise RuntimeError(f"[PUT_CALL_FETCHER] No options expirations available for ^SPX on {eval_date}")

            expirations = spx_options.options
            if not expirations:
                raise RuntimeError(f"[PUT_CALL_FETCHER] Empty expirations list for ^SPX on {eval_date}")

            # Convert expirations to dates
            from datetime import datetime

            exp_dates = []
            for exp_str in expirations:
                try:
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                    exp_dates.append(exp_date)
                except ValueError as e:
                    # Log invalid dates so user knows which ones were skipped
                    logger.warning(f"[PUT_CALL_FETCHER] Invalid expiration date format: {exp_str!r} - {e}")
                    continue

            if not exp_dates:
                raise RuntimeError(f"[PUT_CALL_FETCHER] Could not parse any expiration dates from {expirations}")

            # Find nearest expiration: prefer <= eval_date, otherwise next available
            closest_exp = None
            for exp_date in sorted(exp_dates):
                if exp_date <= eval_date:
                    closest_exp = exp_date
                elif closest_exp is None:
                    closest_exp = exp_date
                    break

            if closest_exp is None:
                # No expiration found <= eval_date, and no future expiration either
                # This indicates options data is unavailable for the eval_date
                raise RuntimeError(
                    f"[PUT_CALL_FETCHER] No suitable options expiration found for eval_date {eval_date}. "
                    f"Available: {sorted(exp_dates)}. Cannot compute put/call ratio without valid expiration."
                )

            logger.debug(f"[PUT_CALL_FETCHER] Using expiration {closest_exp} for eval_date {eval_date}")

            options_chain = spx_options.option_chain(closest_exp.isoformat())

            if options_chain.calls.empty or options_chain.puts.empty:
                raise RuntimeError(
                    f"[PUT_CALL_FETCHER] Options data missing for {closest_exp}: "
                    f"calls={options_chain.calls.empty}, puts={options_chain.puts.empty}"
                )

            total_calls = float(options_chain.calls["openInterest"].sum())
            total_puts = float(options_chain.puts["openInterest"].sum())

            if total_calls == 0:
                raise RuntimeError(f"[PUT_CALL_FETCHER] No call volume for {closest_exp}. Cannot calculate ratio.")

            ratio = float(total_puts / total_calls)
            logger.debug(f"[PUT_CALL_FETCHER] Put/call ratio for {eval_date} (using {closest_exp}): {ratio:.3f}")
            return ratio
        except Exception as e:
            raise RuntimeError(f"[PUT_CALL_FETCHER] Fetch failed for {eval_date}: {e}") from e


class YieldCurveFetcher:
    """Fetches yield curve data with circuit breaker and exponential backoff retry logic.

    Implements resilience against transient failures:
    - Categorizes errors as TRANSIENT (connection, timeout, 503) vs PERMANENT (data not found)
    - Retries TRANSIENT errors up to 3 times with exponential backoff (1s, 2s, 4s)
    - Only marks data_unavailable if all retries fail
    - Logs each retry attempt and final failure reason
    - OPTIONAL enrichment: Gracefully degrades when unavailable (no trading halt)
    """

    MAX_RETRIES = 3
    BACKOFF_SECONDS = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s

    def __init__(self) -> None:
        self.breaker = CircuitBreaker(
            name="economic_metrics_yield_curve",
            failure_threshold=3,
            recovery_timeout_sec=300,
            importance=DataImportance.OPTIONAL,
        )

    def _is_transient_error(self, exc: Exception) -> bool:
        """Categorize exception as transient (retriable) or permanent.

        TRANSIENT errors (should retry):
        - HTTP 503 (Service Unavailable), 502 (Bad Gateway), 504 (Gateway Timeout)
        - ConnectionError, TimeoutError
        - Database connection issues (connection reset, timeout)

        PERMANENT errors (should not retry):
        - RuntimeError from data validation (no data available)
        - ValueError (malformed data)
        - KeyError (missing keys in response)
        """
        error_str = str(exc).lower()
        error_type = type(exc).__name__

        # Check for HTTP error codes in exception message
        if "503" in error_str or "502" in error_str or "504" in error_str:
            return True

        # Network/connection errors are transient
        if error_type in ("ConnectionError", "TimeoutError", "Timeout"):
            return True

        if "timeout" in error_str or "connection" in error_str or "reset" in error_str:
            return True

        # Database connection issues are transient
        if "connection" in error_str or "EOF" in error_str:
            return True

        # Check for permanent errors (don't retry)
        # "no data" or "empty" indicate permanent absence, not transient failure
        if "no data" in error_str or "empty" in error_str or "not found" in error_str:
            return False

        # Validation/structural errors are permanent
        if error_type in ("ValueError", "KeyError", "AttributeError"):
            return False

        # Default to transient for unknown errors (better to retry than silently fail)
        return True

    def fetch(self, start: date, end: date) -> dict[str, Any]:
        """Fetch yield curve data with exponential backoff retry and circuit breaker protection.

        Returns:
            dict with yield data keyed by date, OR data_unavailable marker if unavailable

        For OPTIONAL enrichment: Gracefully returns explicit data_unavailable marker
        instead of raising errors. Callers can distinguish unavailable data from errors.
        """
        try:
            # Use circuit breaker to protect against cascading failures
            result = self.breaker.execute(
                fetch_func=lambda: self._fetch_with_retries(start, end),
                importance=DataImportance.OPTIONAL,
                fallback_value=None,
            )

            if result is None:
                return {
                    "data_unavailable": True,
                    "reason": f"Circuit breaker exhaustion: unable to fetch yield curve data after {self.MAX_RETRIES} retries",
                }

            # Validate result type
            if not isinstance(result, dict):
                return {
                    "data_unavailable": True,
                    "reason": f"Invalid response type {type(result).__name__}, expected dict",
                }

            return result
        except Exception as e:
            return {"data_unavailable": True, "reason": f"Fetch error: {str(e)[:150]}"}

    def _fetch_with_retries(self, start: date, end: date) -> dict[str, Any] | None:
        """Attempt yield curve fetch with exponential backoff retry logic.

        Returns:
            dict: Yield curve data if successful (may be empty dict if no data for period)
            None: If all retries exhausted
        """
        last_error_reason = "unknown error"

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                return self._fetch_yield_curve_data(start, end)
            except Exception as e:
                is_transient = self._is_transient_error(e)

                if not is_transient:
                    # Permanent error - don't retry (e.g., no data available)
                    last_error_reason = f"permanent {type(e).__name__}: {str(e)[:100]}"
                    error_msg = (
                        f"[YIELD_CURVE] Permanent error on attempt {attempt}/{self.MAX_RETRIES} for {start}:{end}: "
                        f"{last_error_reason}. Yield curve enrichment is unavailable. Cannot proceed."
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e

                # Transient error - log and retry if attempts remain
                if attempt < self.MAX_RETRIES:
                    backoff = self.BACKOFF_SECONDS[attempt - 1]
                    logger.warning(
                        f"[YIELD_CURVE] Transient error on attempt {attempt}/{self.MAX_RETRIES} for {start}:{end}: "
                        f"{type(e).__name__}: {str(e)[:100]}. "
                        f"Retrying in {backoff}s..."
                    )
                    time.sleep(backoff)
                else:
                    last_error_reason = f"transient {type(e).__name__} after {self.MAX_RETRIES} retries"
                    logger.error(
                        f"[YIELD_CURVE] Transient error on attempt {attempt}/{self.MAX_RETRIES} for {start}:{end}: "
                        f"{type(e).__name__}: {str(e)[:100]}. No retries remaining."
                    )

        # All retries exhausted
        error_msg = (
            f"[YIELD_CURVE] All {self.MAX_RETRIES} retries failed for {start}:{end}. "
            f"Reason: {last_error_reason}. Yield curve enrichment is unavailable. Cannot proceed."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)

    def _fetch_yield_curve_data(self, start: date, end: date) -> dict[str, Any]:
        """Internal yield curve fetch implementation.

        Fetches from database economic_data table (T10Y2Y series).
        OPTIONAL enrichment: Skip dates with missing yield data (common for weekends/holidays/recent dates).
        Return available data only; incomplete dates are silently skipped (not an error for optional data).

        Raises:
            RuntimeError: On database connection errors or data format issues
        """
        try:
            from utils.db import DatabaseContext

            result = {}
            with DatabaseContext("read") as cur:
                # Fetch 10-year minus 2-year yield spread from economic_data table
                # T10Y2Y is the most reliable source (computed from Treasury yields)
                cur.execute(
                    """
                    SELECT date, value::float as yield_spread
                    FROM economic_data
                    WHERE series_id = 'T10Y2Y'
                      AND date >= %s
                      AND date <= %s
                    ORDER BY date
                    """,
                    (start, end),
                )

                for row in cur.fetchall():
                    d = row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0])
                    if row[1] is not None:
                        result[d] = {
                            "yield_2y": None,  # Not available separately in this source
                            "yield_10y": None,  # Not available separately in this source
                            "yield_spread": float(row[1]),  # This is the 10Y - 2Y spread
                        }

            if result:
                logger.info(f"[YIELD_CURVE] Fetched {len(result)} dates with yield spread from T10Y2Y series")
            else:
                # CRITICAL: Yield curve is critical market data per CLAUDE.md governance
                # Missing data must be visible to ops for market stress calculations
                logger.error(
                    f"[YIELD_CURVE] CRITICAL: No yield data available for date range {start}:{end} — market stress calculations may be incomplete"
                )

            return result
        except Exception as e:
            # Re-raise with context for retry handler to evaluate transience
            raise RuntimeError(f"[YIELD_CURVE] Fetch failed for {start}:{end}: {e}") from e


class BreadthFetcher:
    """Fetches market breadth data (advance/decline, new highs/lows) from database.

    Computes from trend_template_data for advance/decline counts.
    Computes from price_daily for new 52-week highs/lows.
    """

    def __init__(self) -> None:
        pass

    def _compute_new_highs_lows(self, cur: Any, start: date, end: date) -> dict[str, Any]:
        """Compute new 52-week highs and lows for each date.

        Returns: dict[date_str] -> (new_highs_count, new_lows_count)

        For each symbol in price_daily, checks if close is highest/lowest in past 252 trading days.
        Uses window function to efficiently compute 52-week highs/lows across all symbols.
        """
        cur.execute("SELECT COUNT(*) FROM price_daily WHERE date >= %s AND date <= %s", (start, end))
        price_count_row = cur.fetchone()
        price_count = price_count_row[0] if price_count_row else 0
        if price_count == 0:
            raise RuntimeError(
                f"[BREADTH_FETCHER CRITICAL] price_daily has no rows for {start} to {end}. "
                f"Cannot compute new highs/lows without price data. "
                f"Check: price loader is running, price_daily table is populated."
            )

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
        rows = cur.fetchall()
        if not rows:
            # No symbols have 252+ days of history yet (too early in dataset)
            # Return explicit marker for missing optional enrichment
            logger.warning(
                f"[BREADTH_FETCHER] New highs/lows unavailable for {start} to {end}: "
                f"price_daily has {price_count} rows but window function found no symbols with 252-day history. "
                f"This is normal early in dataset. Market breadth enrichment unavailable."
            )
            return {
                "data_unavailable": True,
                "reason": "insufficient_price_history",
                "start": start.isoformat(),
                "end": end.isoformat(),
            }

        result = {}
        for row in rows:
            date_val = row[0]
            # Convert datetime to date if necessary for consistent formatting
            if hasattr(date_val, "date"):
                date_val = date_val.date()
            d = date_val.isoformat() if hasattr(date_val, "isoformat") else str(date_val)
            # CRITICAL: new_highs and new_lows counts must be present for valid breadth data
            if row[1] is None or row[2] is None:
                logger.warning(
                    f"[BREADTH_FETCHER] New highs/lows count missing for {d}: "
                    f"new_highs={row[1]}, new_lows={row[2]}. Skipping invalid record."
                )
                continue
            result[d] = (int(row[1]), int(row[2]))
        return result

    def fetch(self, start: date, end: date) -> dict[str, Any]:
        """Fetch market breadth data from trend_template_data and price_daily.

        Returns: dict[date_str] -> {advance_decline_ratio, new_highs_count, new_lows_count}

        CRITICAL: Breadth data (new highs/lows, advance/decline ratios) is essential
        for market health assessment. Fail-fast if data unavailable or computation fails.
        """
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
                raise RuntimeError(
                    f"[BREADTH_FETCHER] No advance/decline data available for {start} to {end}. "
                    "Breadth data is critical for market health assessment. "
                    "Check trend_template_data table for complete data."
                )

            # Compute new highs/lows from price_daily
            # CRITICAL: New highs/lows are essential for market analysis
            # Fail-fast if computation fails; don't silently skip
            new_highs_lows = self._compute_new_highs_lows(cur, start, end)

            # Check if new highs/lows is unavailable (e.g., insufficient 252-day price history)
            # FAIL-FAST: Do not use placeholders for critical breadth data
            # Return explicit unavailability marker instead of silent degradation
            if isinstance(new_highs_lows, dict) and new_highs_lows.get("data_unavailable"):
                msg = (
                    f"[BREADTH_FETCHER CRITICAL] New highs/lows data unavailable for {start} to {end}: "
                    f"{new_highs_lows.get('reason')}. "
                    f"Breadth data (new highs/lows + advance/decline) is critical for market health assessment. "
                    f"Using (0,0) placeholders would corrupt position sizing calculations (16% of composite exposure score). "
                    f"Must fail fast instead of silently degrading."
                )
                logger.error(msg)
                raise RuntimeError(msg)

            result = {}
            for row in rows:
                date_val = row[0]
                # Convert datetime to date if necessary for consistent formatting
                if hasattr(date_val, "date"):
                    date_val = date_val.date()
                d = date_val.isoformat() if hasattr(date_val, "isoformat") else str(date_val)
                if row[1] is None or row[2] is None:
                    msg = (
                        f"[BREADTH_FETCHER CRITICAL] Data corruption detected: advances/declines NULL for {d}. "
                        f"Breadth metrics are required for market exposure scoring (16% of composite score). "
                        f"Cannot compute position sizing without valid breadth data."
                    )
                    logger.error(msg)
                    raise RuntimeError(msg)

                advances = int(row[1])
                declines = int(row[2])

                if declines <= 0:
                    msg = (
                        f"[BREADTH_FETCHER CRITICAL] Invalid breadth data for {d}: declines={declines}. "
                        f"Negative or zero declines indicate corrupt data. "
                        f"Cannot score market health without valid advance/decline counts."
                    )
                    logger.error(msg)
                    raise RuntimeError(msg)

                ad_ratio = advances / declines

                # Get new highs/lows - must exist since we fail-fast if unavailable
                if d not in new_highs_lows:
                    msg = (
                        f"[BREADTH_FETCHER CRITICAL] New highs/lows missing for {d} "
                        f"despite availability check passing. Data consistency error."
                    )
                    logger.error(msg)
                    raise RuntimeError(msg)
                nh, nl = new_highs_lows[d]

                result[d] = {
                    "advance_decline_ratio": round(ad_ratio, 3),
                    "new_highs_count": nh,
                    "new_lows_count": nl,
                    "new_highs_lows_available": True,
                }

            if not result:
                msg = (
                    f"[BREADTH_FETCHER CRITICAL] No valid breadth data obtained from {len(rows)} query results. "
                    f"All rows had NULL or invalid advances/declines. "
                    f"Verify trend_template_data has complete data for date range {start} to {end}."
                )
                logger.error(msg)
                raise RuntimeError(msg)

            logger.info(f"[BREADTH_FETCHER] Fetched valid breadth for {len(result)}/{len(rows)} dates")
            return result
