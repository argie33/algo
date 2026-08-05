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
from typing import Any

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
    """Check if RS vs SPY is weakening."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT relative_strength_vs_spy
                FROM trend_template_data
                WHERE symbol = %s AND date = %s
                """,
                (ticker, signal_date),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                return False

            rs_score = float(row[0])
            return rs_score < 40
    except Exception as e:
        logger.debug(f"[PREENTRY] RS check failed for {ticker}: {e}")
        return False


def _check_sector_weak(ticker: str, signal_date: str) -> bool:
    """Check if sector is weak/declining."""
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
                SELECT sector_direction
                FROM sector_rotation_signal
                WHERE sector = %s AND date = %s
                """,
                (sector, signal_date),
            )
            sector_row = cur.fetchone()
            if sector_row is None:
                return False

            direction = sector_row[0]
            return direction and direction.lower() in ("weak", "declining", "warning")
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
                WHERE ticker = %s
                AND announcement_date >= %s::date
                AND announcement_date <= %s::date + interval '3 days'
                """,
                (ticker, signal_date),
            )
            count = cur.fetchone()[0]
            return count > 0
    except Exception as e:
        logger.debug(f"[PREENTRY] Earnings check failed for {ticker}: {e}")
        return False


def _check_market_distribution_stress(signal_date: str) -> bool:
    """Check if market is in distribution phase (stress)."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT distribution_day_count
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

        # PASS if <=1 check fails (>=2 pass minimum)
        passes = len(failed_checks) <= 1
        return passes, failed_checks
