#!/usr/bin/env python3
"""Earnings date awareness and blackout enforcement.

Prevents entries ±N days around earnings announcements to avoid whipsaws.
Default: ±7 days from earnings date is a blackout period.
"""

import logging
from datetime import date as _date
from datetime import timedelta
from typing import Any

import psycopg2
import psycopg2.errors

from algo.infrastructure import MarketCalendar
from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class EarningsBlackout:
    """Enforce earnings date blackout windows."""

    def __init__(self, config: Any) -> None:
        if config is None:
            raise ValueError("EarningsBlackout requires explicit config parameter (dependency injection)")
        self.config = config
        days_before_val = self.config.get("earnings_blackout_days_before")
        if days_before_val is None:
            raise ValueError(
                "CRITICAL: earnings_blackout_days_before config missing. "
                "Cannot enforce earnings blackout without explicit days-before threshold."
            )
        days_after_val = self.config.get("earnings_blackout_days_after")
        if days_after_val is None:
            raise ValueError(
                "CRITICAL: earnings_blackout_days_after config missing. "
                "Cannot enforce earnings blackout without explicit days-after threshold."
            )
        self.days_before = int(days_before_val)
        self.days_after = int(days_after_val)

    def run(self, symbol: str, eval_date: _date) -> dict[str, Any]:
        """Check if eval_date is in earnings blackout window (Issue #27: trading day aware).

        Uses MarketCalendar to compute trading days, not calendar days.
        Raises ValueError if earnings_calendar table doesn't exist (explicit halt).
        """
        try:
            with DatabaseContext("read") as cur:
                # CRITICAL FIX (Session 79): Check if earnings data is CURRENT before allowing entries
                # RATIONALE: Trades were entering without earnings knowledge (2026-08-07 entries
                # for 2026-08-08 earnings that weren't in DB yet). Loader didn't have loaded Aug 8 earnings yet.
                # SOLUTION: Verify earnings_calendar was refreshed recently (within 24-48 hours).
                # If the last load was 2+ days ago, we're missing recent earnings announcements.

                from datetime import datetime, timezone

                # BUG FIX (2026-08-10): was MAX(created_at), which for an upserted table only
                # reflects a row's ORIGINAL insertion, never its subsequent refreshes -
                # load_earnings_calendar.py explicitly sets updated_at=now() on every write
                # (both INSERT and UPDATE branches) specifically so freshness consumers can
                # tell "was this recently refreshed", with its own comment warning that an
                # UPDATE branch not touching updated_at "would silently reintroduce the same
                # bug" - phase1_data_freshness.py already correctly keys off MAX(updated_at)
                # for this same table; this was the one consumer left checking the wrong
                # column. Live-reproduced: MSA's created_at was 2026-08-05 (5 days old) while
                # its updated_at was today (refreshed hours earlier) - genuinely fresh data
                # was incorrectly reported as "123h stale" and used to BLOCK a real entry.
                # In one live run this was directly responsible for 5 of 7 signal rejections
                # (the majority) - a real, active over-blocking bug, not just log noise.
                # Check when this symbol's earnings_calendar was last refreshed
                cur.execute(
                    """SELECT MAX(updated_at) as last_load
                       FROM earnings_calendar
                       WHERE symbol = %s
                       AND updated_at >= (NOW() - interval '7 days')""",
                    (symbol,),
                )
                last_load_row = cur.fetchone()
                last_load_time = last_load_row[0] if last_load_row and last_load_row[0] else None

                if last_load_time is None:
                    # No earnings_calendar data for this symbol in last 7 days - loader is stale
                    logger.warning(
                        f"[EARNINGS_BLACKOUT] {symbol}: earnings_calendar not refreshed in 7+ days. "
                        f"Loader may be broken or symbol never loaded. BLOCKING ENTRY as safety measure."
                    )
                    return {
                        "pass": False,
                        "reason": "Earnings data not refreshed in 7+ days - cannot verify earnings",
                    }

                # Check staleness: if last load was 2+ days ago, we may be missing recent earnings
                # BUG (found Session 81): previously computed now_et = datetime.now(EASTERN_TZ) then
                # did now_et.replace(tzinfo=timezone.utc) - .replace() relabels the tzinfo without
                # converting the clock value, so an Eastern wall-clock reading (UTC-4/-5) got treated
                # as if it were already UTC. That understated hours_since_last_load by 4-5 hours,
                # silently letting the "48-hour" staleness gate tolerate ~52-53 hours of stale earnings
                # data - undermining the exact safety check this function exists to enforce. Comparing
                # against UTC directly avoids the ET round-trip entirely.
                now_utc = datetime.now(timezone.utc)
                hours_since_last_load = (now_utc - last_load_time.replace(tzinfo=timezone.utc)).total_seconds() / 3600

                if hours_since_last_load > 48:
                    # Earnings data is 2+ days old - loader may have missed recent announcements
                    logger.warning(
                        f"[EARNINGS_BLACKOUT] {symbol}: earnings_calendar last refreshed {hours_since_last_load:.0f}h ago. "
                        f"May be missing recent earnings announcements. BLOCKING ENTRY as safety measure."
                    )
                    return {
                        "pass": False,
                        "reason": f"Earnings data is {hours_since_last_load:.0f}h stale - cannot verify upcoming earnings",
                    }

                # Issue #27: Compute trading day windows instead of calendar days
                # Count back N trading days before, forward N trading days after
                # CRITICAL FIX: Look far enough ahead (365 days) to capture real future earnings
                # Previously: days_after * 2 (only 6 days) meant future earnings > 6 days out got missed
                # Result: query returned old past earnings dates instead of upcoming dates, blocking trades unnecessarily
                lookback_date = eval_date - timedelta(days=max(self.days_before * 2, 30))  # At least 30 days back
                lookahead_date = eval_date + timedelta(days=365)  # Full year ahead for all future earnings

                # CRITICAL FIX (Session 70): INCLUDE data_unavailable=TRUE in blackout check
                # Previously: filtered out (data_unavailable IS FALSE OR data_unavailable IS NULL)
                # This caused trades on earnings days to be APPROVED when data was marked unavailable,
                # resulting in -19%, -9%, -8% losses on 2026-08-08 (5 trades with earnings that day).
                # NEW APPROACH: Fail-closed design - unavailable data = ASSUME RISKY, block the trade
                # Only query earnings regardless of data_unavailable status, treating incomplete data
                # as "potentially risky" rather than "safe because missing".
                #
                # CRITICAL FIX 2026-08-09: rank data_unavailable rows BELOW real ones, not equally.
                # load_earnings_calendar.py's _unavailable_record() stamps earnings_date=today (the
                # fetch-attempt date, not a real earnings date) on any outright fetch failure. The
                # old tiering ("any future date beats any past date, regardless of data quality") let
                # that phantom "today" placeholder outrank a symbol's own real, already-past earnings
                # date whenever the real next cycle (~90 days out) hadn't been fetched yet - live-
                # reproduced 2026-08-09: WPM/BDX/DAC/GAIN/ERO all have real earnings_date rows days in
                # the past (correctly outside the blackout window) but were blocked anyway on "earnings
                # tomorrow", sourced entirely from a same-day mass yfinance fetch-failure event (4918
                # placeholder rows in one run). Real dates (future, then past) now always outrank
                # unavailable placeholders; a placeholder is only used as a fail-closed fallback signal
                # when NO real earnings_date exists for this symbol anywhere in the window - preserving
                # the original incident's protection for genuinely never-confirmed symbols.
                cur.execute(
                    """SELECT earnings_date, data_unavailable FROM earnings_calendar
                       WHERE symbol = %s
                       AND earnings_date >= %s
                       AND earnings_date <= %s
                       ORDER BY CASE
                                  WHEN data_unavailable IS NOT TRUE AND earnings_date >= %s THEN 0
                                  WHEN data_unavailable IS NOT TRUE THEN 1
                                  ELSE 2
                                END,
                                ABS(earnings_date - %s::date) ASC
                       LIMIT 1""",
                    (symbol, lookback_date, lookahead_date, eval_date, eval_date),
                )
                row = cur.fetchone()

            if row:
                earnings_date = row[0]
                # Note: data_unavailable flag is in row[1] if we queried it above
                # Count trading days between eval_date and earnings_date (excluding earnings date itself)
                is_earnings_day = eval_date == earnings_date
                direction = 1 if earnings_date >= eval_date else -1  # 1=future, -1=past

                # Count TDs from the day AFTER earnings (if in future) or
                # from earnings FORWARD (if in past), up to eval_date
                if direction > 0:
                    # Pre-earnings: count from eval to the day before earnings
                    trading_days_away = 0
                    current = eval_date
                    while current < earnings_date:
                        current += timedelta(days=1)
                        if current < earnings_date and MarketCalendar.is_trading_day(current):
                            trading_days_away += 1
                else:
                    # Post-earnings: count from day after earnings forward to eval_date
                    trading_days_away = 0
                    current = earnings_date
                    while current < eval_date:
                        current += timedelta(days=1)
                        if MarketCalendar.is_trading_day(current) and current != earnings_date:
                            trading_days_away += 1

                # Check if within blackout window (in trading days, not calendar days).
                # direction > 0 means earnings is still upcoming (pre-earnings window, days_before);
                # direction < 0 means earnings already happened (post-earnings window, days_after).
                # CRITICAL: Use < not <= - days_after=1 should allow trading 1 day after (trading_days_away >= 1).
                if is_earnings_day or trading_days_away < (self.days_before if direction > 0 else self.days_after):
                    return {
                        "pass": False,
                        "reason": f"Earnings on {earnings_date} ({trading_days_away} trading days away)",
                    }

            return {
                "pass": True,
                "reason": f"No earnings in ±{self.days_before}/{self.days_after} trading days",
            }
        except psycopg2.errors.UndefinedTable as e:
            raise ValueError(
                f"Earnings calendar table missing for {symbol} - explicit halt (table infrastructure failure)"
            ) from e
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise ValueError(f"Earnings blackout check error for {symbol}: {str(e)[:50]} - explicit halt") from e
