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
        """Internal put/call fetch implementation.

        Finds nearest options expiration date to eval_date (yfinance requires actual expiration dates,
        not arbitrary trading dates). Uses closest expiration <= eval_date, or if none exists, next available.
        """
        try:
            import yfinance

            spx_options = yfinance.Ticker("^SPX")

            # Get available expiration dates
            if not hasattr(spx_options, 'options') or not spx_options.options:
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
                except ValueError:
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
                closest_exp = min(exp_dates)  # Fallback to earliest

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
                raise RuntimeError(
                    f"[PUT_CALL_FETCHER] No call volume for {closest_exp}. Cannot calculate ratio."
                )

            ratio = float(total_puts / total_calls)
            logger.debug(f"[PUT_CALL_FETCHER] Put/call ratio for {eval_date} (using {closest_exp}): {ratio:.3f}")
            return ratio
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

        IMPORTANT: This is OPTIONAL enrichment (not critical for trading).
        Returns explicit data_unavailable flag on failures so callers can distinguish
        between "no data available" and "fetcher failed".

        Returns:
            dict with yield data keyed by date, or marker dict with data_unavailable=True if data unavailable.
        """
        try:
            result = self.breaker.execute(
                fetch_func=lambda: self._fetch_yield_curve_data(start, end),
                importance=DataImportance.OPTIONAL,
                fallback_value=None,
            )
            if result is None:
                logger.warning(f"[YIELD_CURVE] Circuit breaker exhausted for {start}:{end} — enrichment unavailable")
                return {"data_unavailable": True, "reason": "Circuit breaker exhausted"}
            if not isinstance(result, dict):
                logger.warning(f"[YIELD_CURVE] Invalid response type {type(result).__name__} for {start}:{end} — enrichment unavailable")
                return {"data_unavailable": True, "reason": f"Invalid response type {type(result).__name__}"}
            if result.get("data_unavailable"):
                return result
            return result
        except Exception as e:
            logger.warning(f"[YIELD_CURVE] Fetch failed for {start}:{end}: {e} — enrichment unavailable")
            return {"data_unavailable": True, "reason": f"Fetch error: {str(e)[:100]}"}

    def _fetch_yield_curve_data(self, start: date, end: date) -> dict[str, Any]:
        """Internal yield curve fetch implementation.

        Fetches from database economic_data table (T10Y2Y series).
        OPTIONAL enrichment: Skip dates with missing yield data (common for weekends/holidays/recent dates).
        Return available data only; incomplete dates are silently skipped (not an error for optional data).
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
            return result
        except Exception as e:
            logger.error(
                f"[YIELD_CURVE] Fetch failed: {e}. Yield curve is CRITICAL for market regime detection. "
                f"Cannot continue with empty yield curve data — system must detect API failures explicitly."
            )
            raise RuntimeError(
                f"[YIELD_CURVE] Failed to fetch yield spread data: {e}. "
                f"Market regime classification requires valid yield curve. "
                f"Not using empty fallback — API failure must be visible and handled explicitly."
            ) from e


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
            raise RuntimeError(
                f"[BREADTH_FETCHER CRITICAL] New highs/lows computation returned 0 rows for {start} to {end}. "
                f"price_daily has {price_count} rows in range but window function produced no results. "
                f"This typically means price data is too recent (< 252 days history). "
                f"Verify: (1) price_daily has >= 252 days of history per symbol, "
                f"(2) symbols have continuous trading data without gaps."
            )

        result = {}
        for row in rows:
            date_val = row[0]
            # Convert datetime to date if necessary for consistent formatting
            if hasattr(date_val, "date"):
                date_val = date_val.date()
            d = date_val.isoformat() if hasattr(date_val, "isoformat") else str(date_val)
            result[d] = (int(row[1]) if row[1] is not None else 0, int(row[2]) if row[2] is not None else 0)
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

                # Get new highs/lows if available
                nh, nl = new_highs_lows.get(d, (None, None))

                result[d] = {
                    "advance_decline_ratio": round(ad_ratio, 3),
                    "new_highs_count": nh,
                    "new_lows_count": nl,
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
