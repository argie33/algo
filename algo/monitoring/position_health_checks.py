"""Position-health-assessment methods for PositionMonitor, extracted from
algo/monitoring/position_monitor.py (2026-09-05, file-size ratchet: that file is a Tier-2
bloater flagged for decomposition, same pattern already used for
`algo/monitoring/position_corporate_actions.py`'s CorporateActionsMixin). Bodies are
verbatim, no logic changed - mixed into PositionMonitor, which still defines the `config`
instance attribute these methods read via `self`.

`DatabaseContext` is accessed via the position_monitor module object at call time (not
imported by name here) because existing tests patch
`algo.monitoring.position_monitor.DatabaseContext` expecting that to affect these methods -
a plain import here would silently stop seeing those patches (same reasoning as
position_corporate_actions.py / position_order_management.py). `algo.monitoring.
position_monitor` itself imports this module at load time, so the reference is resolved
lazily (inside the method bodies, not at import time) to avoid a circular-import failure.
"""

from __future__ import annotations

import logging
from datetime import date as _date
from datetime import datetime
from typing import Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

import algo.monitoring.position_monitor as _pm
from algo.monitoring.position_monitor import PositionValidationError

logger = logging.getLogger(__name__)


class PositionHealthChecksMixin:
    """Sector-concentration, relative-strength, sector-trend, peak-drawdown, earnings-
    proximity and distribution-day health-check methods for PositionMonitor. Not usable
    standalone - relies on the `config` instance attribute defined on PositionMonitor itself.
    """

    config: Any

    def check_sector_concentration(
        self, current_date: _date | None = None, cur: PsycopgCursor[Any] | None = None
    ) -> dict[str, Any]:
        """Check if portfolio is overly concentrated in one sector (advisory logging only -
        see review_positions()'s call site, which only logs a warning on HIGH_CONCENTRATION,
        never blocks/reduces anything).

        FIXED 2026-08-25 (real-money-readiness goal session, monitoring-vs-enforcement
        consistency audit): threshold used to be a hardcoded `> 3` positions, completely
        independent of and inconsistent with the actual ENFORCED limit
        (pretrade_checks.py's max_positions_per_sector, config-driven, live value found well
        above 3) - meaning this monitor's own "HIGH_CONCENTRATION" alert could fire on a
        portfolio state pretrade_checks.py considers entirely within limits, or vice versa if
        the configured limit were ever lowered below 3. Now reads the same
        max_positions_per_sector config key pretrade_checks.py enforces, so this advisory
        alert actually reflects the real, currently-configured limit rather than a stale
        independent guess.

        Args:
            current_date: Accepted for API compatibility with callers/tests; unused - this
                check only reflects the CURRENT open-positions snapshot, not a historical date.
            cur: Optional cursor to use. If None, opens new DatabaseContext.
                 CRITICAL: If caller has an open DatabaseContext, MUST pass cursor
                 to avoid nested context closing the outer cursor (causes "cursor already closed" errors).

        Raises:
            RuntimeError: If concentration check fails (fail-fast for risk management)
        """
        max_per_sector_val = self.config.get("max_positions_per_sector")
        if max_per_sector_val is None:
            raise RuntimeError(
                "[POSITION_MONITOR] max_positions_per_sector config missing. "
                "Cannot evaluate sector concentration without the real enforced limit."
            )
        max_per_sector = int(max_per_sector_val)

        query = """
            -- Return NULL for missing sector (don't hide with 'Unknown')
            SELECT cp.sector, COUNT(DISTINCT ap.symbol) as position_count
            FROM algo_positions ap
            LEFT JOIN company_profile cp ON ap.symbol = cp.symbol
            WHERE ap.status = 'open' AND ap.quantity > 0
            GROUP BY cp.sector
            HAVING COUNT(DISTINCT ap.symbol) > %s
            ORDER BY COUNT(DISTINCT ap.symbol) DESC
        """

        # CRITICAL FIX: If caller passed a cursor, use it instead of opening new context
        # This prevents nested DatabaseContext from closing the outer cursor
        if cur is not None:
            try:
                cur.execute(query, (max_per_sector,))
                concentrated = cur.fetchall()
                if concentrated:
                    logger.info("\n  [CONCENTRATION ALERT]")
                    for sector, count in concentrated:
                        logger.info(
                            f"    {sector}: {count} positions (>{max_per_sector} is at/above the configured limit)"
                        )
                    return {"status": "HIGH_CONCENTRATION", "sectors": concentrated}
                return {"status": "OK", "sectors": []}
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(
                    f"Sector concentration check failed: {e}. "
                    f"Cannot proceed with position monitoring without valid concentration metrics."
                ) from e
        else:
            # Fallback: open own context if not provided
            with _pm.DatabaseContext("read") as ctx:  # type: ignore[attr-defined]
                try:
                    ctx.execute(query, (max_per_sector,))
                    concentrated = ctx.fetchall()
                    if concentrated:
                        logger.info("\n  [CONCENTRATION ALERT]")
                        for sector, count in concentrated:
                            logger.info(
                                f"    {sector}: {count} positions (>{max_per_sector} is at/above the configured limit)"
                            )
                        return {"status": "HIGH_CONCENTRATION", "sectors": concentrated}
                    return {"status": "OK", "sectors": []}
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    raise RuntimeError(
                        f"Sector concentration check failed: {e}. "
                        f"Cannot proceed with position monitoring without valid concentration metrics."
                    ) from e

    def _check_relative_strength(
        self, symbol: str, current_date: _date | datetime, cur: PsycopgCursor[Any] | None = None
    ) -> str:
        """20-day relative return vs SPY: weakening / neutral / strong.

        Args:
            symbol: Stock symbol to check
            current_date: Date to check from
            cur: Optional cursor to use. If None, opens new DatabaseContext.
                 CRITICAL: If caller has an open DatabaseContext, MUST pass cursor
                 to avoid nested context closing the outer cursor (causes "cursor already closed" errors).
        """
        try:
            stock = self._period_return(symbol, current_date, 20, cur=cur)
        except (ValueError, RuntimeError) as e:
            raise PositionValidationError(
                f"[RS_CALCULATION_FAILED] Cannot evaluate relative strength for {symbol}: {e}. "
                f"Period return calculation failed - cannot proceed without RS data for position health assessment."
            ) from e

        try:
            spy = self._period_return("SPY", current_date, 20, cur=cur)
        except (ValueError, RuntimeError) as e:
            raise PositionValidationError(
                f"[RS_CALCULATION_FAILED] Cannot evaluate market baseline (SPY) for RS: {e}. "
                f"Cannot assess relative strength without market comparison data."
            ) from e
        excess = stock - spy
        if excess < -0.05:
            return "weakening"
        if excess > 0.05:
            return "strong"
        return "neutral"

    def _check_sector_health(  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
        self, symbol: str, current_date: _date | datetime, cur: PsycopgCursor[Any] | None = None
    ) -> str:
        """Is the symbol's sector currently weakening?

        Args:
            symbol: Stock symbol to check
            current_date: Date to check
            cur: Optional cursor to use. If None, opens new DatabaseContext.
                 CRITICAL: If caller has an open DatabaseContext, MUST pass cursor
                 to avoid nested context closing the outer cursor (causes "cursor already closed" errors).
        """
        # Skip sector checks for index/macro ETFs (Session 196: removed unused sector ETFs)
        # Only kept SPY, QQQ, IWM for critical market factors; GLD, TLT for macro
        if symbol in ("SPY", "QQQ", "IWM", "GLD", "TLT", "^GSPC", "^IXIC", "^DJI"):
            return "neutral"

        # CRITICAL FIX: If caller passed a cursor, use it instead of opening new contexts
        # This prevents nested DatabaseContext from closing the outer cursor
        if cur is not None:
            try:
                cur.execute(
                    "SELECT sector FROM company_profile WHERE symbol = %s LIMIT 1",
                    (symbol,),
                )
                srow = cur.fetchone()
                if srow is None or len(srow) < 1:
                    raise ValueError(
                        f"[POSITION MONITOR] Sector data missing for {symbol}. "
                        f"Cannot classify position without sector information for exposure calculations."
                    )
                if srow[0] is None:
                    raise ValueError(
                        f"[POSITION MONITOR] Sector is NULL for {symbol}. "
                        f"Cannot classify position without valid sector for exposure calculations."
                    )
                sector = srow[0]

                # "Other" is a placeholder for unclassified/new symbols without proper sector data
                # These don't have historical sector_ranking records yet; skip trend check and return neutral
                if sector == "Other":
                    logger.debug(f"Skipping sector health check for {symbol}: sector is 'Other' (unclassified)")
                    return "neutral"

                # Use same cursor for sector ranking query
                cur.execute(
                    """
                    SELECT current_rank, rank_4w_ago FROM sector_ranking
                    WHERE sector_name = %s
                      AND date <= %s
                    ORDER BY date DESC LIMIT 1
                    """,
                    (sector, current_date),
                )
                cur_row = cur.fetchone()
                if not cur_row or cur_row[0] is None:
                    raise PositionValidationError(
                        f"[POSITION_MONITOR] Sector ranking data missing for {sector} (may be new sector). "
                        f"Cannot assess sector health for {symbol} without current ranking data. "
                        f"Sector rankings are required for position risk assessment - do not assume 'neutral' on missing data. "
                        f"Add sector to sector_ranking table or exclude from portfolio."
                    )
                if len(cur_row) < 2:
                    raise PositionValidationError(
                        f"[POSITION_MONITOR] Sector ranking query returned insufficient columns ({len(cur_row)} < 2). "
                        f"Database schema may be corrupted or query result malformed."
                    )
                cur_rank = int(cur_row[0])
                old_rank = cur_row[1]

                if old_rank is None:
                    logger.warning(
                        f"[POSITION_MONITOR] Sector ranking baseline missing for {symbol} ({sector}) - "
                        f"using current rank alone without historical trend assessment. "
                        f"This is expected for new sectors or data gaps. Position monitoring continues."
                    )
                    return "neutral"
                old_rank = int(old_rank)
                if cur_rank > old_rank + 3:  # got worse by 3+ ranks
                    return "weakening"
                if cur_rank < old_rank - 3:
                    return "strengthening"
                return "stable"
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(
                    f"Sector health check failed: {e}. "
                    f"Cannot proceed with position monitoring without valid sector health metrics."
                ) from e
        else:
            # Fallback: open own context if not provided
            with _pm.DatabaseContext("read") as fresh_cur:  # type: ignore[attr-defined]
                try:
                    fresh_cur.execute(
                        "SELECT sector FROM company_profile WHERE symbol = %s LIMIT 1",
                        (symbol,),
                    )
                    srow = fresh_cur.fetchone()
                    if srow is None or len(srow) < 1:
                        raise ValueError(
                            f"[POSITION MONITOR] Sector data missing for {symbol}. "
                            f"Cannot classify position without sector information for exposure calculations."
                        )
                    if srow[0] is None:
                        raise ValueError(
                            f"[POSITION MONITOR] Sector is NULL for {symbol}. "
                            f"Cannot classify position without valid sector for exposure calculations."
                        )
                    sector = srow[0]

                    # "Other" is a placeholder for unclassified/new symbols without proper sector data
                    # These don't have historical sector_ranking records yet; skip trend check and return neutral
                    if sector == "Other":
                        logger.debug(f"Skipping sector health check for {symbol}: sector is 'Other' (unclassified)")
                        return "neutral"

                    # CRITICAL FIX: Use same cursor instead of nesting a new context
                    # Nested DatabaseContext closes the parent cursor, causing "cursor already closed" errors
                    fresh_cur.execute(
                        """
                        SELECT current_rank, rank_4w_ago FROM sector_ranking
                        WHERE sector_name = %s
                          AND date <= %s
                        ORDER BY date DESC LIMIT 1
                        """,
                        (sector, current_date),
                    )
                    cur_row = fresh_cur.fetchone()
                    if not cur_row or cur_row[0] is None:
                        raise PositionValidationError(
                            f"[POSITION_MONITOR] Sector ranking data missing for {sector} (may be new sector). "
                            f"Cannot assess sector health for {symbol} without current ranking data. "
                            f"Sector rankings are required for position risk assessment - do not assume 'neutral' on missing data. "
                            f"Add sector to sector_ranking table or exclude from portfolio."
                        )
                    if len(cur_row) < 2:
                        raise PositionValidationError(
                            f"[POSITION_MONITOR] Sector ranking query returned insufficient columns ({len(cur_row)} < 2). "
                            f"Database schema may be corrupted or query result malformed."
                        )
                    cur_rank = int(cur_row[0])
                    old_rank = cur_row[1]

                    if old_rank is None:
                        logger.warning(
                            f"[POSITION_MONITOR] Sector ranking baseline missing for {symbol} ({sector}) - "
                            f"using current rank alone without historical trend assessment. "
                            f"This is expected for new sectors or data gaps. Position monitoring continues."
                        )
                        return "neutral"
                    old_rank = int(old_rank)
                    if cur_rank > old_rank + 3:  # got worse by 3+ ranks
                        return "weakening"
                    if cur_rank < old_rank - 3:
                        return "strengthening"
                    return "stable"
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    raise RuntimeError(
                        f"Sector health check failed: {e}. "
                        f"Cannot proceed with position monitoring without valid sector health metrics."
                    ) from e

    def _max_unrealized_pct(
        self,
        symbol: str,
        trade_date: _date,
        current_date: _date | datetime,
        entry_price: float,
        cur: PsycopgCursor[Any] | None = None,
    ) -> float:
        """Highest closing price since entry, expressed as % gain."""
        if entry_price <= 0:
            raise PositionValidationError(
                f"Invalid entry price for {symbol}: {entry_price} <= 0. Cannot calculate max unrealized %."
            )

        # CRITICAL FIX 2026-08-06: Positions entered today (trade_date >= current_date) have no price history yet
        # When Phase 3 monitors with yesterday's date but positions were entered today, the date range becomes
        # inverted (start > end), causing price queries to return no results. Gracefully handle same-day entries:
        # return 0% peak gain (position has no gains yet, just entered).
        if trade_date >= current_date:
            logger.info(
                f"[POSITION_MONITOR] {symbol}: Entered on {trade_date} (>= monitoring date {current_date}). "
                f"Position too new for peak gain analysis - returning 0%."
            )
            return 0.0

        # CRITICAL FIX 2026-08-01: If caller passed a cursor, use it instead of opening new context
        # Nested DatabaseContext calls close the outer cursor, causing "cursor already closed" errors.
        # This was inverted in a previous attempt - the bug was opening fresh context when cursor was passed.
        if cur is not None:
            try:
                cur.execute(
                    """
                    SELECT MAX(close), bool_or(data_unavailable), MAX(data_unavailable_reason)
                    FROM price_daily
                    WHERE symbol = %s AND date >= %s AND date <= %s
                    AND close IS NOT NULL
                    """,
                    (symbol, trade_date, current_date),
                )
                row = cur.fetchone()
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise PositionValidationError(
                    f"Failed to fetch price data for {symbol}: {e}. Cannot calculate max unrealized gain."
                ) from e
        else:
            with _pm.DatabaseContext("read") as fresh_cur:  # type: ignore[attr-defined]
                fresh_cur.execute(
                    """
                    SELECT MAX(close), bool_or(data_unavailable), MAX(data_unavailable_reason)
                    FROM price_daily
                    WHERE symbol = %s AND date >= %s AND date <= %s
                    AND close IS NOT NULL
                    """,
                    (symbol, trade_date, current_date),
                )
                row = fresh_cur.fetchone()
        if row is None or len(row) != 3:
            raise PositionValidationError(
                f"[VALIDATION] Price query returned malformed result for {symbol} (expected 3 columns, got {len(row) if row else 0}). Schema drift detected."
            )
        if row[0] is None:
            # INTRADAY FALLBACK: During afternoon runs before EOD load completes, price_daily may only have
            # yesterday's data. Use most recent available price instead of halting position monitoring entirely.
            logger.warning(
                f"[POSITION_MONITOR] {symbol}: No price data for current_date {current_date}, using most recent available. "
                f"Normal during intraday: attempting fallback to most recent price..."
            )
            if cur is not None:
                try:
                    cur.execute(
                        """SELECT close, data_unavailable, data_unavailable_reason
                           FROM price_daily
                           WHERE symbol = %s AND date < %s AND close IS NOT NULL
                           ORDER BY date DESC LIMIT 1""",
                        (symbol, current_date),
                    )
                    fallback_row = cur.fetchone()
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    raise PositionValidationError(f"Failed to fetch fallback price for {symbol}: {e}") from e
            else:
                with _pm.DatabaseContext("read") as fresh_cur:  # type: ignore[attr-defined]
                    fresh_cur.execute(
                        """SELECT close, data_unavailable, data_unavailable_reason
                           FROM price_daily
                           WHERE symbol = %s AND date < %s AND close IS NOT NULL
                           ORDER BY date DESC LIMIT 1""",
                        (symbol, current_date),
                    )
                    fallback_row = fresh_cur.fetchone()

            if fallback_row is None or fallback_row[0] is None:
                raise PositionValidationError(
                    f"[POSITION_MONITOR] {symbol}: No price data available (checked current date and fallback). "
                    f"Cannot calculate position metrics. Check price_daily loader status."
                )
            row = fallback_row
            logger.info(f"[POSITION_MONITOR] {symbol}: Using fallback price from prior date: {float(row[0]):.2f}")

        # GOVERNANCE COMPLIANCE: Check data_unavailable flag before using prices
        max_close = float(row[0])
        data_unavailable_flag = bool(row[1]) if row[1] is not None else False
        reason_msg = row[2] if row[2] is not None else None
        if data_unavailable_flag:
            raise PositionValidationError(
                f"Price data marked unavailable for {symbol}: {reason_msg or 'no reason provided'}. "
                f"Cannot calculate position metrics with invalid prices."
            )
        if max_close <= 0:
            raise PositionValidationError(f"Invalid price data for {symbol}: max close {max_close} <= 0")
        return ((max_close - entry_price) / entry_price) * 100.0

    def _days_to_earnings(
        self, symbol: str, current_date: _date | datetime, cur: PsycopgCursor[Any] | None = None
    ) -> int:
        """Get days until next earnings from earnings_calendar.

        Args:
            symbol: Stock symbol to check
            current_date: Date to check from
            cur: Optional cursor to use. If None, opens new DatabaseContext.
                 CRITICAL: If caller has an open DatabaseContext, MUST pass cursor
                 to avoid nested context closing the outer cursor (causes "cursor already closed" errors).

        Raises:
            ValueError: If earnings data unavailable for symbol (fail-fast consistency with advanced_filters)

        Earnings date is CRITICAL for position monitoring - without it, we cannot detect upcoming earnings gaps
        that expose positions to gap risk. Consistent with advanced_filters._estimate_days_to_earnings()
        which also raises ValueError when earnings data missing.
        """
        try:
            # CRITICAL FIX 2026-08-01: If caller passed a cursor, use it instead of opening new context
            # Nested DatabaseContext calls close the outer cursor, causing "cursor already closed" errors.
            # CRITICAL FIX 2026-08-09: exclude data_unavailable rows - load_earnings_calendar.py's
            # _unavailable_record() stamps earnings_date=today (the fetch-attempt date, not a real
            # earnings date) whenever a symbol's fetch fails, so an unfiltered query finds this
            # phantom "today" row instead of raising ValueError below, silently defeating this
            # function's own documented "graceful degradation on missing data" contract and firing
            # a false EARNINGS_IN_0D flag that can force-exit a healthy open position for a reason
            # unrelated to real earnings risk. Live-reproduced 2026-08-09: a mass yfinance fetch
            # failure created 4918 such placeholder rows dated 2026-08-08 across the universe.
            if cur is not None:
                cur.execute(
                    """SELECT earnings_date FROM earnings_calendar
                       WHERE symbol = %s AND earnings_date >= %s
                       AND (data_unavailable IS FALSE OR data_unavailable IS NULL)
                       ORDER BY earnings_date ASC LIMIT 1""",
                    (symbol, current_date),
                )
                row = cur.fetchone()
            else:
                with _pm.DatabaseContext("read") as fresh_cur:  # type: ignore[attr-defined]
                    fresh_cur.execute(
                        """SELECT earnings_date FROM earnings_calendar
                           WHERE symbol = %s AND earnings_date >= %s
                           AND (data_unavailable IS FALSE OR data_unavailable IS NULL)
                           ORDER BY earnings_date ASC LIMIT 1""",
                        (symbol, current_date),
                    )
                    row = fresh_cur.fetchone()
            if row is None or row[0] is None:
                raise ValueError(
                    f"Earnings data unavailable for {symbol}: no future earnings date found in earnings_calendar"
                )
            return int((row[0] - current_date).days)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise ValueError(
                f"Earnings query failed for {symbol}: {e}. Cannot proceed without earnings data for position monitoring."
            ) from e

    def _fetch_market_dist_days(self, current_date: _date | datetime, cur: PsycopgCursor[Any] | None = None) -> int:
        """Get market distribution days from health data.

        Args:
            current_date: Date to check
            cur: Optional cursor to use. If None, opens new DatabaseContext.
                 CRITICAL: If caller has an open DatabaseContext, MUST pass cursor
                 to avoid nested context closing the outer cursor (causes "cursor already closed" errors).

        Raises:
            ValueError: If market health data is unavailable for the date
        """
        # market_health_daily.distribution_days_4w is only populated by the ~2-3am morning
        # loader, which runs before MarketExposure has enough same-day data to compute a real
        # distribution-day count - that row is written with distribution_days_4w=NULL and never
        # refreshed later in the day. market_exposure_daily.distribution_days is the same
        # underlying computation (MarketExposure.compute()), but gets a real value once
        # recomputed later in the trading day/EOD - read from there instead, and skip any NULL
        # rows rather than trusting "most recent date" to also mean "most recent populated
        # value". Same fix as algo/trading/exit_engine.py::_fetch_market_dist_days, which hit
        # this identically for open positions in execution_mode='paper'/'dry' - this method is
        # the equivalent for execution_mode='auto' (Phase 3 short-circuits before reaching it
        # in paper mode, so this path is currently dormant but will hit the same crash the
        # moment auto/live mode runs with an open position).
        # CRITICAL FIX 2026-08-01: If caller passed a cursor, use it instead of opening new context
        # Nested DatabaseContext calls close the outer cursor, causing "cursor already closed" errors.
        if cur is not None:
            cur.execute(
                "SELECT distribution_days, data_unavailable, reason FROM market_exposure_daily "
                "WHERE date <= %s AND distribution_days IS NOT NULL ORDER BY date DESC LIMIT 1",
                (current_date,),
            )
            row = cur.fetchone()
        else:
            with _pm.DatabaseContext("read") as fresh_cur:  # type: ignore[attr-defined]
                fresh_cur.execute(
                    "SELECT distribution_days, data_unavailable, reason FROM market_exposure_daily "
                    "WHERE date <= %s AND distribution_days IS NOT NULL ORDER BY date DESC LIMIT 1",
                    (current_date,),
                )
                row = fresh_cur.fetchone()
        if not row:
            raise ValueError(
                f"Market distribution days not available for {current_date} - market_exposure_daily table missing or empty"
            )
        if len(row) != 3:
            raise ValueError(
                f"[VALIDATION] Market exposure query returned {len(row)} columns, expected 3. Schema drift detected."
            )

        # GOVERNANCE COMPLIANCE: Check data_unavailable flag before using distribution days
        data_unavailable_flag = bool(row[1]) if row[1] is not None else False
        reason_msg = row[2] if row[2] is not None else None
        if data_unavailable_flag:
            raise ValueError(
                f"Market exposure data marked unavailable for {current_date}: {reason_msg or 'no reason provided'}. "
                f"Cannot assess market distribution days with invalid data."
            )

        return int(row[0])

    def _period_return(
        self, symbol: str, end_date: _date, lookback_days: int, cur: PsycopgCursor[Any] | None = None
    ) -> float:
        """Compute simple return over a lookback period.

        Args:
            symbol: Stock symbol to check
            end_date: End date for period
            lookback_days: Number of days to look back
            cur: Optional cursor to use. If None, opens new DatabaseContext.
                 CRITICAL: If caller has an open DatabaseContext, MUST pass cursor
                 to avoid nested context closing the outer cursor (causes "cursor already closed" errors).

        Raises:
            ValueError: If price data is missing or invalid for the period
        """
        from algo.infrastructure.config.sql_intervals import get_interval_sql

        interval_1d = get_interval_sql("1d")
        # CRITICAL FIX 2026-08-01: If caller passed a cursor, use it instead of opening new context
        # Nested DatabaseContext calls close the outer cursor, causing "cursor already closed" errors.
        if cur is not None:
            cur.execute(
                f"""
                WITH bracket AS (
                    SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                    FROM price_daily
                    WHERE symbol = %s AND date <= %s
                      AND date >= %s::date - (%s * {interval_1d})
                )
                SELECT
                    (SELECT close FROM bracket WHERE rn = 1),
                    (SELECT close FROM bracket ORDER BY rn DESC LIMIT 1)
                """,
                (symbol, end_date, end_date, lookback_days + 5),
            )
            row = cur.fetchone()
        else:
            with _pm.DatabaseContext("read") as fresh_cur:  # type: ignore[attr-defined]
                fresh_cur.execute(
                    f"""
                    WITH bracket AS (
                        SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                        FROM price_daily
                        WHERE symbol = %s AND date <= %s
                          AND date >= %s::date - (%s * {interval_1d})
                    )
                    SELECT
                        (SELECT close FROM bracket WHERE rn = 1),
                        (SELECT close FROM bracket ORDER BY rn DESC LIMIT 1)
                    """,
                    (symbol, end_date, end_date, lookback_days + 5),
                )
                row = fresh_cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            raise ValueError(
                f"Period return data missing for {symbol} on {end_date} ({lookback_days}d lookback) - insufficient price history"
            )
        recent, oldest = float(row[0]), float(row[1])
        if oldest <= 0:
            raise ValueError(f"Invalid historical price for {symbol}: oldest close {oldest} <= 0")
        return (recent - oldest) / oldest
