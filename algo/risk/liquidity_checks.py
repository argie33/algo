#!/usr/bin/env python3
"""
Liquidity checks for Tier 5 portfolio health filtering.
Ensures entry can be executed with adequate liquidity and reasonable spreads.
"""

import logging
from datetime import date as _date
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
        min_market_cap_millions_val = config.get("min_market_cap_millions")
        if min_adv_shares_val is None:
            raise ValueError("CRITICAL: min_adv_shares config missing. Cannot enforce liquidity checks.")
        if min_adv_dollars_val is None:
            raise ValueError("CRITICAL: min_adv_dollars config missing. Cannot enforce liquidity checks.")
        if min_market_cap_millions_val is None:
            raise ValueError("CRITICAL: min_market_cap_millions config missing. Cannot enforce liquidity checks.")
        self.min_adv_shares = min_adv_shares_val
        self.min_adv_dollars = min_adv_dollars_val
        self.min_market_cap_millions = min_market_cap_millions_val

    def run_all(self, symbol: str, entry_price: float, signal_date: _date | None = None) -> tuple[bool, str]:
        if signal_date is None:
            # Every other unavailable-data path in this class fails closed (blocks the
            # trade) rather than fails open. A missing signal_date is no different - it
            # means we cannot verify ADV/dollar-volume/IPO-age, so silently passing here
            # would let an unvetted symbol through liquidity gating entirely.
            logger.error(
                f"Liquidity checks unavailable for {symbol}: no signal_date provided - blocking as safety measure"
            )
            return False, "Liquidity checks unavailable (no signal_date) - blocking as safety measure"
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

            market_cap_passed, market_cap_reason = self._check_market_cap(symbol)
            if not market_cap_passed:
                return False, f"Market cap check failed: {market_cap_reason}"

            return True, "All liquidity checks passed"

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Liquidity check unavailable for {symbol}: {e} - blocking as safety measure")
            return (
                False,
                f"Liquidity checks unavailable ({type(e).__name__}) - blocking as safety measure",
            )

    def _check_adv(self, symbol: str, signal_date: _date) -> tuple[bool, str]:
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
            logger.error(f"ADV check failed for {symbol}: {e} - blocking as safety measure")
            return (
                False,
                f"ADV check unavailable ({type(e).__name__}) - blocking as safety measure",
            )

    def _check_dollar_volume(self, symbol: str, signal_date: _date) -> tuple[bool, str]:
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
            logger.error(f"Dollar volume check failed for {symbol}: {e} - blocking as safety measure")
            return (
                False,
                f"Dollar volume check unavailable ({type(e).__name__}) - blocking as safety measure",
            )

    def _check_market_cap(self, symbol: str) -> tuple[bool, str]:
        """Enforce the investability floor (min_market_cap_millions, default $300M).

        ADDED 2026-09-13: `min_market_cap_millions` has been a seeded, schema-validated
        algo_config value since migration 005 (default 300.0, "Liquidity Requirements"
        category, same $300M standard micro-cap/small-cap boundary the dashboard/API scores
        display already floors at) - but was never actually wired into any real trade-entry
        check. `trading_config.py`'s `get_stock_filter_config()` built a dict including this
        key but is itself dead code (`.vulture_whitelist.py` marks it "unused method").
        Concretely: Phase 7/8 candidate qualification had a liquidity (dollar-volume) floor
        but NO size floor, so a symbol could clear ADV/dollar-volume purely on volatility-
        driven trading activity while still being a nanocap the rest of this system already
        treats as uninvestable everywhere else. Reuses `value_metrics.market_cap` (the same
        column the scoring pillars/API already read) rather than introducing a new source.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SELECT market_cap FROM value_metrics WHERE symbol = %s", (symbol,))
                row = cur.fetchone()
                if not row or row[0] is None:
                    return False, "No market_cap data available"

                market_cap = float(row[0])
                min_market_cap = float(self.min_market_cap_millions) * 1_000_000.0
                if market_cap < min_market_cap:
                    return (
                        False,
                        f"Market cap ${market_cap:,.0f} < minimum ${min_market_cap:,.0f}",
                    )

                return True, f"Market cap ${market_cap:,.0f} ok"

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Market cap check unavailable for {symbol}: {e} - blocking as safety measure")
            return (
                False,
                f"Market cap check unavailable ({type(e).__name__}) - blocking as safety measure",
            )
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"Market cap check failed for {symbol}: {e} - blocking as safety measure")
            return (
                False,
                f"Market cap check unavailable ({type(e).__name__}) - blocking as safety measure",
            )

    def _check_price_history_age(self, symbol: str, signal_date: _date) -> tuple[bool, str]:
        """
        Require minimum price history before trading (Minervini/IBD IPO age rule).

        New stocks lack institutional sponsorship track record, established bases,
        and earnings history needed for high-quality trend following. Minervini
        specifically avoids stocks in their first year of trading.

        Uses price_daily row count as a proxy for trading age (no IPO date column
        needed). 200 trading days ≈ 10 months - long enough for a first proper base.

        Config key: min_price_history_days (default 200)

        Returns:
            Tuple[bool, str]: (passed, reason)
        """
        try:
            min_days_val = self.config.get("min_price_history_days")
            if min_days_val is None:
                raise ValueError(
                    "[LIQUIDITY] min_price_history_days config required. "
                    "Cannot proceed with trade entry validation without explicit IPO age threshold."
                )
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
            logger.error(f"Price history age check failed for {symbol}: {e} - blocking as safety measure")
            return (
                False,
                f"Price history age check unavailable ({type(e).__name__}) - blocking as safety measure",
            )
