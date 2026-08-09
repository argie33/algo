#!/usr/bin/env python3

"""Pre-entry health validation for Phase 8 trades.

Before executing ANY trade, validate that the entry signal passes basic health checks:
1. Relative strength not weakening vs SPY
2. Sector is not weak/declining
3. No earnings announcement in next 3 days
4. Market not in distribution stress

Signals failing 2+ health checks are rejected before entry, preventing immediate exits.

ROOT CAUSE FIXED: Phase 8 entered positions without validating the same health flags that
Phase 3 checks the next day. Positions would be entered and immediately flagged for exit,
causing 15.4% of exits at exact entry price (0% return).
"""

import logging

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

# Health check flags documented in memory as causing phase3-initiated exits
HEALTH_CHECKS = {
    "RS_WEAKENING": "Relative strength deteriorating vs SPY",
    "SECTOR_WEAK": "Sector health declining",
    "EARNINGS_IN_0-3D": "Earnings announcement within 0-3 days",
    "MARKET_DISTRIBUTION_STRESS": "Market in distribution phase",
}


def _check_rs_weakening(ticker: str, signal_date: str) -> bool:
    """Check if price is not above SMA50 (proxy for RS weakening)."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT price_above_sma50
                FROM trend_template_data
                WHERE symbol = %s AND date = %s
                """,
                (ticker, signal_date),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                return False

            # If price is NOT above SMA50, RS is weakening
            return not row[0]
    except Exception as e:
        logger.debug(f"[PREENTRY] RS check failed for {ticker}: {e}")
        return False


def _check_sector_weak(ticker: str, signal_date: str) -> bool:
    """Check if sector has a negative signal."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT sector FROM company_profile WHERE symbol = %s", (ticker,)
            )
            sector_row = cur.fetchone()
            if sector_row is None:
                return False

            sector = sector_row[0]

            cur.execute(
                """
                SELECT signal
                FROM sector_rotation_signal
                WHERE sector = %s AND date = %s
                """,
                (sector, signal_date),
            )
            sector_row = cur.fetchone()
            if sector_row is None:
                return False

            signal = sector_row[0]
            return signal and signal.lower() in ("weak", "decline", "warning", "negative")
    except Exception as e:
        logger.debug(f"[PREENTRY] Sector check failed for {ticker}: {e}")
        return False


def _check_earnings_in_3d(ticker: str, signal_date: str) -> bool:
    """Check if earnings announcement within 0-3 days."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM earnings_calendar
                WHERE symbol = %s
                AND earnings_date >= %s::date
                AND earnings_date <= %s::date + interval '3 days'
                """,
                (ticker, signal_date, signal_date),
            )
            row = cur.fetchone()
            count = row[0] if row else 0
            return bool(count > 0)
    except Exception as e:
        logger.debug(f"[PREENTRY] Earnings check failed for {ticker}: {e}")
        return False


def _check_market_distribution_stress(signal_date: str) -> bool:
    """Check if market has >=3 distribution days (stress)."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT distribution_days
                FROM market_exposure_daily
                WHERE date = %s
                """,
                (signal_date,),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                return False

            dist_days = int(row[0])
            return dist_days >= 3
    except Exception as e:
        logger.debug(f"[PREENTRY] Market distribution check failed: {e}")
        return False


class PreEntryHealthValidator:
    """Validates signal health before Phase 8 entry execution."""

    @staticmethod
    def validate(ticker: str, signal_date: str) -> tuple[bool, list[str]]:
        """Check if signal passes pre-entry health validation.

        Args:
            ticker: Stock ticker symbol
            signal_date: Date signal was generated (YYYY-MM-DD)

        Returns:
            (passes_validation, failed_checks)
            - passes_validation: True if <=1 health check fails (>=2 pass minimum)
            - failed_checks: List of failed health check names
        """
        failed_checks = []

        # Check 1: Relative Strength vs SPY
        if _check_rs_weakening(ticker, signal_date):
            failed_checks.append("RS_WEAKENING")

        # Check 2: Sector Health
        if _check_sector_weak(ticker, signal_date):
            failed_checks.append("SECTOR_WEAK")

        # Check 3: Earnings Proximity
        if _check_earnings_in_3d(ticker, signal_date):
            failed_checks.append("EARNINGS_IN_0-3D")

        # Check 4: Market Distribution Stress
        if _check_market_distribution_stress(signal_date):
            failed_checks.append("MARKET_DISTRIBUTION_STRESS")

        # PASS if <=1 checks fail (>= 3 pass minimum)
        # RESTORED (2026-08-08 Session 70): Aug 5 relaxation caused Aug 7-8 losses (8 of 14 entries
        # had earnings risk AT ENTRY but weren't blocked). Earnings_calendar loader was RUNNING
        # (incomplete) when pre-entry checks ran, so earnings_in_3d check failed silently.
        # Restored strict threshold to block entries failing >1 health check while data quality improves.
        # This prevents entries like "earnings risk + weakening RS" which immediately exit next day.
        #
        # EARNINGS_IN_0-3D standalone hard gate (2026-08-09): the <=1-of-4 vote still let earnings-
        # imminent entries through whenever it was the ONLY failing check (RS/sector/market all
        # clean). Real trade data from 2026-08-07 showed this exact pattern: 14 of 20 trades were
        # forced to flatten within 1-2 days of entry via position_monitor's earnings-blackout exit
        # (net realized loss on those 14 alone), because the position had earnings 0-1 days away
        # at entry and this was the only failed check. A trade that's guaranteed to be flattened
        # within days by the SAME earnings-blackout logic (algo/monitoring/position_monitor.py)
        # has no time for its thesis to play out - entering it is pure cost with no edge, regardless
        # of how the other three checks read. Earnings proximity is no longer votable against.
        passes = len(failed_checks) <= 1 and "EARNINGS_IN_0-3D" not in failed_checks
        return passes, failed_checks
