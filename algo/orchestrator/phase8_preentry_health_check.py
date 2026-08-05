#!/usr/bin/env python3
"""Pre-entry health validation for Phase 8.

Prevents positions from being entered that would immediately fail Phase 3
health checks (RS_WEAKENING, SECTOR_WEAK, etc.). Addresses the issue where
15.4% of exits were zero-percent (entry price = exit price due to health flags
triggered the day after entry).

CRITICAL FIX: Health checks must happen BEFORE entry, not after.
Previously: Phase 8 enters position → Phase 3 detects health issues → immediate exit at entry price
Now: Phase 8 checks health BEFORE entry → signals with health issues are rejected

Health checks performed:
1. Relative Strength vs SPY (RS_WEAKENING?)
2. Sector Health (SECTOR_WEAK?)
3. Earnings proximity (EARNINGS_IN_0-3D?)
4. Market distribution stress (MARKET_DISTRIBUTION_STRESS?)
"""

import logging
from datetime import date as _date
from typing import TYPE_CHECKING, Any

from utils.db.context import DatabaseContext

if TYPE_CHECKING:
    from psycopg2.extensions import cursor as PsycopgCursor

logger = logging.getLogger(__name__)


class PreEntryHealthValidator:
    """Validates position health before entry to prevent immediate post-entry exits."""

    def __init__(self, config: dict[str, Any]):
        """Initialize with algo config."""
        self.config = config
        # These match the Phase 3 position_monitor thresholds
        self.halt_flag_count = int(config.get("position_halt_flag_count", 2))
        self.max_distribution_days = int(config.get("max_distribution_days", 4))

    def check_before_entry(self, symbol: str, run_date: _date) -> tuple[bool, str]:
        """Check if symbol has health issues that would trigger immediate exit.

        Returns:
            (is_healthy, rejection_reason)
            - is_healthy=True: safe to enter
            - is_healthy=False: health issues detected, explain why
        """
        try:
            flags = []

            # 1. Check relative strength vs SPY
            rs_state = self._check_relative_strength(symbol, run_date)
            if rs_state == "weakening":
                flags.append("RS_WEAKENING")

            # 2. Check sector health
            sector_state = self._check_sector_health(symbol, run_date)
            if sector_state == "weakening":
                flags.append("SECTOR_WEAK")

            # 3. Check earnings proximity (0-3 days)
            try:
                days_to_earn = self._days_to_earnings(symbol, run_date)
                if days_to_earn is not None and 0 <= days_to_earn <= 3:
                    flags.append(f"EARNINGS_IN_{days_to_earn}D")
            except (ValueError, RuntimeError):
                # Earnings data unavailable - not an error, just skip check
                pass

            # 4. Check market distribution stress
            try:
                market_dist_days = self._fetch_market_dist_days(run_date)
                if market_dist_days is not None and market_dist_days > self.max_distribution_days:
                    flags.append("MARKET_DISTRIBUTION_STRESS")
            except (ValueError, RuntimeError):
                # Distribution data unavailable early in day - skip check
                pass

            # Determine if position is healthy
            if len(flags) >= self.halt_flag_count:
                return False, f"Health check failed: {len(flags)} flags detected: {', '.join(flags)}"

            return True, ""

        except Exception as e:
            # On any error, log but don't block entry (conservative)
            logger.warning(f"[PHASE 8 HEALTH CHECK] Error validating {symbol}: {e} - allowing entry")
            return True, ""

    def _check_relative_strength(self, symbol: str, run_date: _date) -> str:
        """Check if symbol's RS vs SPY is weakening. Returns 'weakening' or 'stable'."""
        try:
            with DatabaseContext("read") as cur:
                # Compare symbol's recent performance vs SPY
                cur.execute(
                    """
                    SELECT
                        (s.close - s.sma_50) / s.sma_50 * 100 as symbol_rs_score,
                        (spy.close - spy.sma_50) / spy.sma_50 * 100 as spy_rs_score
                    FROM (
                        SELECT close,
                               AVG(close) OVER (ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) as sma_50
                        FROM price_daily
                        WHERE symbol = %s AND date <= %s
                        ORDER BY date DESC LIMIT 1
                    ) s,
                    (
                        SELECT close,
                               AVG(close) OVER (ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) as sma_50
                        FROM price_daily
                        WHERE symbol = 'SPY' AND date <= %s
                        ORDER BY date DESC LIMIT 1
                    ) spy
                    """,
                    (symbol, run_date, run_date),
                )
                result = cur.fetchone()
                if result:
                    sym_rs, spy_rs = result
                    # If symbol's RS significantly trails SPY's, consider it weakening
                    if sym_rs is not None and spy_rs is not None and sym_rs < spy_rs - 5:
                        return "weakening"
                return "stable"
        except Exception as e:
            logger.debug(f"[PHASE 8] RS check error for {symbol}: {e} - assuming stable")
            return "stable"

    def _check_sector_health(self, symbol: str, run_date: _date) -> str:
        """Check if symbol's sector is weakening. Returns 'weakening' or 'stable'."""
        try:
            with DatabaseContext("read") as cur:
                # Get symbol's sector and check its recent performance
                cur.execute(
                    """
                    SELECT cs.sector
                    FROM company_profile cs
                    WHERE cs.symbol = %s
                    """,
                    (symbol,),
                )
                sector_row = cur.fetchone()
                if not sector_row:
                    return "stable"  # No sector data available

                sector = sector_row[0]

                # Check if sector has been underperforming
                cur.execute(
                    """
                    SELECT AVG(close / LAG(close) OVER (ORDER BY date) - 1) as recent_return
                    FROM price_daily
                    WHERE symbol IN (
                        SELECT symbol FROM company_profile WHERE sector = %s
                    ) AND date BETWEEN %s - INTERVAL '30 days' AND %s
                    LIMIT 100
                    """,
                    (sector, run_date, run_date),
                )
                result = cur.fetchone()
                if result and result[0] is not None:
                    recent_return = float(result[0])
                    # If sector's recent return is significantly negative, consider it weak
                    if recent_return < -0.02:  # More than 2% down
                        return "weakening"
                return "stable"
        except Exception as e:
            logger.debug(f"[PHASE 8] Sector health check error for {symbol}: {e} - assuming stable")
            return "stable"

    def _days_to_earnings(self, symbol: str, run_date: _date) -> int | None:
        """Days until next earnings for symbol. Returns None if unavailable."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT (earnings_date - %s)
                    FROM sec_earnings_dates
                    WHERE symbol = %s AND earnings_date >= %s
                    ORDER BY earnings_date ASC
                    LIMIT 1
                    """,
                    (run_date, symbol, run_date),
                )
                result = cur.fetchone()
                if result and result[0]:
                    return result[0].days
                return None
        except Exception as e:
            logger.debug(f"[PHASE 8] Earnings check error for {symbol}: {e}")
            raise ValueError(f"Earnings data unavailable: {e}")

    def _fetch_market_dist_days(self, run_date: _date) -> int | None:
        """Fetch count of market distribution days. Returns None if unavailable."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT distribution_day_count
                    FROM market_exposure_daily
                    WHERE date = %s
                    LIMIT 1
                    """,
                    (run_date,),
                )
                result = cur.fetchone()
                if result and result[0] is not None:
                    return int(result[0])
                return None
        except Exception as e:
            logger.debug(f"[PHASE 8] Distribution days check error: {e}")
            raise ValueError(f"Distribution data unavailable: {e}")
