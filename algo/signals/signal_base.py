#!/usr/bin/env python3

"""
Signal Base -- Shared connection, caching, and helper methods.

All SignalComputer mixins inherit indirectly through SignalBase for:
- Database connection management
- Price/RS percentile caching
- Helper functions (period_return, rs_percentile_vs_spy)
"""

from config.credential_manager import (
    get_db_password,
    get_db_config,
    DEFAULT_DB_PORT,
    DEFAULT_DB_USER,
    DEFAULT_DB_NAME,
)

import os
from utils.database_context import DatabaseContext
from datetime import datetime, timedelta, date as _date
import logging
from typing import Dict, List, Tuple, Optional, Any

logger = logging.getLogger(__name__)


class SignalBase:
    """Base class for all signal computations -- connection, cache, helpers."""

    def __init__(self, cur=None):
        self.cur = cur
        self._owned = None
        self._nesting_level = 0
        self._price_cache = {}  # Cache for N+1 query optimization
        self._rs_percentile_cache = {}  # {(eval_date, lookback): {symbol: percentile}}

    def connect(self):
        if self.cur is None:
            self._owned = get_db_connection()
            self.cur = self._owned.cursor()
            self._nesting_level = 1
        else:
            self._nesting_level += 1

    def disconnect(self):
        if self._nesting_level <= 1 and self._owned:
            self.cur.close()
            self._owned.close()
            self.cur = None
            self._owned = None
            self._nesting_level = 0
            self._price_cache = {}
        elif self._nesting_level > 1:
            self._nesting_level -= 1

    def clear_cache(self):
        """Clear price cache to prevent stale data."""
        self._price_cache = {}

    def _rs_percentile_vs_spy(self, symbol: str, eval_date, lookback: int = 60) -> Optional[float]:
        """
        Mansfield-style RS percentile ranking over `lookback` days.

        Computes (stock_return - SPY_return) for all symbols, then ranks
        the stock against the universe. Returns 0-100 percentile (higher = stronger).

        Batch-cached per (eval_date, lookback): first call computes the full universe
        in one query; subsequent calls within the same run are O(1) dict lookups.
        """
        cache_key = (str(eval_date), lookback)
        if cache_key in self._rs_percentile_cache:
            return self._rs_percentile_cache[cache_key].get(symbol)

        # Batch-compute RS percentiles for the full SP500 universe at once.
        # Uses LATERAL JOINs instead of correlated subqueries to avoid N*2 round-trips.
        self.cur.execute(
            """
            WITH
            universe AS (
                SELECT DISTINCT symbol FROM stock_symbols WHERE is_sp500 = true
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
                WHERE pd.date <= %s::date - (%s || ' days')::INTERVAL
                ORDER BY pd.symbol, pd.date DESC
            ),
            spy_end AS (
                SELECT close FROM price_daily WHERE symbol = 'SPY' AND date <= %s
                ORDER BY date DESC LIMIT 1
            ),
            spy_start AS (
                SELECT close FROM price_daily WHERE symbol = 'SPY'
                    AND date <= %s::date - (%s || ' days')::INTERVAL
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
        rows = self.cur.fetchall()
        cache = {r[0]: float(r[1]) for r in rows if r[1] is not None}
        self._rs_percentile_cache[cache_key] = cache
        return cache.get(symbol)

    def _period_return(self, symbol, end_date, lookback_days):
        """Compute simple return over a lookback period."""
        self.cur.execute(
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
        row = self.cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            return None
        recent = float(row[0])
        oldest = float(row[1])
        if oldest <= 0:
            return None
        return (recent - oldest) / oldest
