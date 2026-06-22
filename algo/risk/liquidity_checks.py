#!/usr/bin/env python3
"""
Liquidity checks for Tier 5 portfolio health filtering.
Ensures entry can be executed with adequate liquidity and reasonable spreads.
"""

import logging
from datetime import timedelta
from typing import Any

import psycopg2

from algo.infrastructure.config import AlgoConfig
from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class LiquidityChecks:
    """Verify sufficient liquidity and spreads for trade execution."""

    def __init__(self, config: AlgoConfig | dict[str, Any]):
        self.config = config
        min_adv_shares_val = config.get("min_adv_shares")
        min_adv_dollars_val = config.get("min_adv_dollars")
        if min_adv_shares_val is None:
            raise ValueError("CRITICAL: min_adv_shares config missing. Cannot enforce liquidity checks.")
        if min_adv_dollars_val is None:
            raise ValueError("CRITICAL: min_adv_dollars config missing. Cannot enforce liquidity checks.")
        self.min_adv_shares = min_adv_shares_val
        self.min_adv_dollars = min_adv_dollars_val

    def run_all(self, symbol: str, entry_price: float, signal_date=None) -> tuple:
        if signal_date is None:
            return True, "Liquidity checks skipped (no signal_date)"
        try:
            age_passed, age_reason = self._check_price_history_age(symbol, signal_date)
            if not age_passed:
                return False, f"IPO age check failed: {age_reason}"

            adv_passed, adv_reason = self._check_adv(symbol, signal_date)
            if not adv_passed:
                return False, f"ADV check failed: {adv_reason}"

            dollar_vol_passed, dollar_reason = self._check_dollar_volume(symbol, signal_date)
            if not dollar_vol_passed:
                return False, f"Dollar volume check failed: {dollar_reason}"

            return True, "All liquidity checks passed"

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Liquidity check unavailable for {symbol}: {e} — blocking as safety measure")
            return (
                False,
                f"Liquidity checks unavailable ({type(e).__name__}) — blocking as safety measure",
            )

    def _check_adv(self, symbol: str, signal_date) -> tuple:
        """
        Check average daily volume (20-day average).

        Returns:
            Tuple[bool, str]: (passed, reason)
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT AVG(volume) as avg_vol
                    FROM (
                        SELECT volume FROM price_daily
                        WHERE symbol = %s
                          AND date >= %s
                          AND date < %s
                        ORDER BY date DESC
                        LIMIT 20
                    ) recent
                    """,
                    (
                        symbol,
                        signal_date - timedelta(days=25),
                        signal_date,
                    ),
                )
                row = cur.fetchone()
                if not row or row[0] is None:
                    return False, "No volume data available"

                avg_vol = float(row[0])
                if avg_vol < self.min_adv_shares:
                    return (
                        False,
                        f"ADV {avg_vol:,.0f} < minimum {self.min_adv_shares:,.0f}",
                    )

                return True, f"ADV {avg_vol:,.0f} ok"

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"ADV check failed for {symbol}: {e} — blocking as safety measure")
            return (
                False,
                f"ADV check unavailable ({type(e).__name__}) — blocking as safety measure",
            )

    def _check_dollar_volume(self, symbol: str, signal_date) -> tuple:
        """
        Check average dollar volume (volume * price) for position sizing.

        Returns:
            Tuple[bool, str]: (passed, reason)
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT AVG(volume * close) as avg_dollar_vol
                    FROM (
                        SELECT volume, close FROM price_daily
                        WHERE symbol = %s
                          AND date >= %s
                          AND date < %s
                        ORDER BY date DESC
                        LIMIT 20
                    ) recent
                    """,
                    (
                        symbol,
                        signal_date - timedelta(days=25),
                        signal_date,
                    ),
                )
                row = cur.fetchone()
                if not row or row[0] is None:
                    return False, "No price data available"

                avg_dollar_vol = float(row[0])
                if avg_dollar_vol < self.min_adv_dollars:
                    return (
                        False,
                        f"Dollar vol ${avg_dollar_vol:,.0f} < minimum ${self.min_adv_dollars:,.0f}",
                    )

                return True, f"Dollar vol ${avg_dollar_vol:,.0f} ok"

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"Dollar volume check failed for {symbol}: {e} — blocking as safety measure")
            return (
                False,
                f"Dollar volume check unavailable ({type(e).__name__}) — blocking as safety measure",
            )

    def _check_price_history_age(self, symbol: str, signal_date) -> tuple:
        """
        Require minimum price history before trading (Minervini/IBD IPO age rule).

        New stocks lack institutional sponsorship track record, established bases,
        and earnings history needed for high-quality trend following. Minervini
        specifically avoids stocks in their first year of trading.

        Uses price_daily row count as a proxy for trading age (no IPO date column
        needed). 200 trading days ≈ 10 months — long enough for a first proper base.

        Config key: min_price_history_days (default 200)

        Returns:
            Tuple[bool, str]: (passed, reason)
        """
        try:
            min_days_val = self.config.get("min_price_history_days")
            if min_days_val is None:
                logger.error("CRITICAL: min_price_history_days config missing. Using safe default 200.")
                min_days = 200
            else:
                min_days = int(min_days_val)
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) as trading_days, MIN(date) as first_date
                    FROM price_daily
                    WHERE symbol = %s AND date <= %s
                    """,
                    (symbol, signal_date),
                )
                row = cur.fetchone()
                if not row or row[0] is None or int(row[0]) == 0:
                    return False, "No price history (new listing or data missing)"

                trading_days = int(row[0])
                first_date = row[1]
                if trading_days < min_days:
                    return (
                        False,
                        f"Only {trading_days} trading days of history (need {min_days}; listed ~{first_date})",
                    )

                return True, f"{trading_days} trading days of history ok"

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"Price history age check failed for {symbol}: {e} — blocking as safety measure")
            return (
                False,
                f"Price history age check unavailable ({type(e).__name__}) — blocking as safety measure",
            )
