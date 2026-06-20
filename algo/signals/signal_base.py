#!/usr/bin/env python3

"""
Signal Base -- Shared connection, caching, and helper methods.

All SignalComputer mixins inherit indirectly through SignalBase for:
- Database connection management
- Price/RS percentile caching
- Helper functions (period_return, rs_percentile_vs_spy)
"""

import logging

from utils.db.context import DatabaseContext
from utils.db.query_cache import CacheStrategy, QueryCache


logger = logging.getLogger(__name__)


class SignalBase:
    """Base class for all signal computations -- connection, cache, helpers."""

    def __init__(self):
        self._rs_percentile_cache = QueryCache(
            "rs_percentile",
            ttl_seconds=3600,  # 1 hour TTL
            max_entries=1000,  # Limit cache size
            strategy=CacheStrategy.LRU,  # Auto-evict oldest when full
        )

    def _with_cursor(self, operation):
        """Execute an operation with a cursor via DatabaseContext."""
        try:
            with DatabaseContext("read") as cur:
                return operation(cur)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def clear_cache(self):
        """Clear RS percentile cache to prevent stale data."""
        self._rs_percentile_cache.invalidate()

    def _rs_percentile_vs_spy(
        self, cur, symbol: str, eval_date, lookback: int = 60
    ) -> float:
        """
        Mansfield-style RS percentile ranking over `lookback` days.

        Computes (stock_return - SPY_return) for all symbols, then ranks
        the stock against the universe. Returns 0-100 percentile (higher = stronger).

        Batch-cached per (eval_date, lookback): first call computes the full universe
        in one query; subsequent calls within the same run are O(1) dict lookups.
        TTL = 1 hour; LRU evicts oldest entries when cache exceeds 1000 entries.

        Raises:
            ValueError: If symbol has insufficient price history for percentile calculation
        """
        cache_key = (str(eval_date), lookback)

        def compute_percentiles():
            # Batch-compute RS percentiles for the full investable universe at once.
            # Uses all non-ETF stocks so non-SP500 stocks get proper percentile rankings
            # instead of returning None (which gave them 0 momentum points and dropped swing scores).
            # Uses LATERAL JOINs instead of correlated subqueries to avoid N*2 round-trips.
            # idx_price_daily_symbol_date covers the DISTINCT ON efficiently for 5000+ symbols.
            cur.execute(
                """
                WITH
                universe AS (
                    SELECT DISTINCT symbol FROM stock_symbols WHERE COALESCE(etf, 'N') != 'Y'
                ),
                end_prices AS (
                    SELECT DISTINCT ON (pd.symbol) pd.symbol, pd.close AS end_close
                    FROM price_daily pd
                    JOIN universe u ON u.symbol = pd.symbol
                    WHERE pd.date <= %s
                    ORDER BY pd.symbol, pd.date DESC
                ),
                start_prices AS (
                    SELECT DISTINCT ON (pd.symbol) pd.symbol, pd.close AS start_close
                    FROM price_daily pd
                    JOIN universe u ON u.symbol = pd.symbol
                    WHERE pd.date <= %s::date - make_interval(days => %s)
                    ORDER BY pd.symbol, pd.date DESC
                ),
                spy_end AS (
                    SELECT close FROM price_daily WHERE symbol = 'SPY' AND date <= %s
                    ORDER BY date DESC LIMIT 1
                ),
                spy_start AS (
                    SELECT close FROM price_daily WHERE symbol = 'SPY'
                        AND date <= %s::date - make_interval(days => %s)
                    ORDER BY date DESC LIMIT 1
                ),
                spy_ret AS (
                    SELECT (spy_end.close / NULLIF(spy_start.close, 0) - 1) AS r
                    FROM spy_end CROSS JOIN spy_start
                ),
                all_returns AS (
                    SELECT
                        ep.symbol,
                        (ep.end_close / NULLIF(sp.start_close, 0) - 1) - (SELECT r FROM spy_ret) AS excess_return
                    FROM end_prices ep
                    JOIN start_prices sp ON sp.symbol = ep.symbol
                ),
                ranked AS (
                    SELECT
                        symbol,
                        PERCENT_RANK() OVER (ORDER BY excess_return) * 100 AS percentile_rank
                    FROM all_returns
                    WHERE excess_return IS NOT NULL
                )
                SELECT symbol, percentile_rank FROM ranked
                """,
                (eval_date, eval_date, lookback, eval_date, eval_date, lookback),
            )
            rows = cur.fetchall()
            return {r[0]: float(r[1]) for r in rows if r[1] is not None}

        percentile_dict = self._rs_percentile_cache.get_or_compute(
            cache_key,
            compute_percentiles,
            context=f"RS percentile {eval_date} {lookback}d",
            allow_stale=True,  # Return stale data if DB is down
        )
        result = percentile_dict.get(symbol)
        if result is None:
            raise ValueError(
                f"RS percentile not available for {symbol} on {eval_date} ({lookback}d lookback) — insufficient price history"
            )
        return float(result)

    def _period_return(self, cur, symbol, end_date, lookback_days):
        """Compute simple return over a lookback period.

        Raises:
            ValueError: If price data is missing or invalid for the period
        """
        cur.execute(
            """
            WITH bracket AS (
                SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                FROM price_daily
                WHERE symbol = %s AND date <= %s
                  AND date >= %s::date - (%s * INTERVAL '1 day')
            )
            SELECT
                (SELECT close FROM bracket WHERE rn = 1),
                (SELECT close FROM bracket ORDER BY rn DESC LIMIT 1)
            """,
            (symbol, end_date, end_date, lookback_days + 5),
        )
        row = cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            raise ValueError(
                f"Period return data missing for {symbol} on {end_date} ({lookback_days}d lookback) — insufficient price history"
            )
        recent = float(row[0])
        oldest = float(row[1])
        if oldest <= 0:
            raise ValueError(
                f"Invalid historical price for {symbol}: oldest close {oldest} <= 0"
            )
        return (recent - oldest) / oldest
