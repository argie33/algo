#!/usr/bin/env python3
"""Data quality checks - NULL anomalies, OHLC sanity, zero values, volume sanity."""

import logging
from typing import Any

import psycopg2

from algo.infrastructure.config.sql_intervals import get_interval_sql

from ..base import BaseCheck, CheckResult
from ..config import CRIT, ERROR, INFO, WARN

logger = logging.getLogger(__name__)


class QualityChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        """Execute all quality checks."""
        self.results = []

        self.check_null_anomalies(cur)
        self.check_zero_or_identical(cur)
        self.check_ohlc_sanity(cur)
        self.check_volume_sanity(cur)

        return self.results

    def check_null_anomalies(self, cur: Any) -> None:
        try:
            # EXPLICIT THRESHOLD: price_daily NULL values should never exceed 5%
            # This is a fixed contract, not a configurable setting
            max_null_pct = 5
            interval_30d = get_interval_sql("30d")

            cur.execute(f"""
                SELECT
                    SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END) FILTER (
                        WHERE date = (SELECT MAX(date) FROM price_daily)) AS today_nulls,
                    COUNT(*) FILTER (WHERE date = (SELECT MAX(date) FROM price_daily)) AS today_total
                FROM price_daily
                WHERE date >= (SELECT MAX(date) FROM price_daily) - {interval_30d}
            """)
            row = cur.fetchone()
            if row is None:
                raise ValueError("NULL anomaly check query returned no results - database state corrupted")
            # BUG FOUND 2026-08-11: DictRow (what DictCursor actually returns) is dict-LIKE
            # but not a `dict` subclass - isinstance(row, dict) was always False here,
            # unconditionally crashing this checker on every real row. Same fix as
            # coverage.py/alignment.py/specialized.py's other instances.
            if isinstance(row, dict) or hasattr(row, "keys"):
                today_nulls, today_total = row.get("today_nulls"), row.get("today_total")
            else:
                raise TypeError(
                    f"Expected dict-like row from DictCursor, got {type(row).__name__}. "
                    f"This indicates cursor configuration mismatch. Check data_patrol cursor factory."
                )
            if today_total is None or today_total == 0:
                logger.warning(
                    "price_daily today_total is 0 or NULL - skipping null anomaly check (no records for today)"
                )
                return
            if today_nulls is None:
                today_nulls = 0
            today_nulls = int(today_nulls)
            today_total = int(today_total)
            null_pct = today_nulls / today_total * 100

            if null_pct > max_null_pct:
                self.log(
                    "null_anomaly",
                    ERROR,
                    "price_daily",
                    f"{null_pct:.1f}% NULL closes on latest date (threshold {max_null_pct}%)",
                    {
                        "today_nulls": today_nulls,
                        "today_total": today_total,
                        "threshold_pct": max_null_pct,
                    },
                )
            else:
                self.log(
                    "null_anomaly",
                    INFO,
                    "price_daily",
                    f"NULL rate {null_pct:.2f}% acceptable (threshold {max_null_pct}%)",
                    {
                        "today_nulls": today_nulls,
                        "today_total": today_total,
                        "threshold_pct": max_null_pct,
                    },
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log("null_anomaly", ERROR, "price_daily", f"Check failed: {e}", None)

    def check_zero_or_identical(self, cur: Any) -> None:
        try:
            quality_cfg = self.config.get_quality_config()
            new_zeros_error = quality_cfg["zero_symbols_error"]
            new_zeros_warn = quality_cfg["zero_symbols_warn"]
            ident_threshold = quality_cfg["identical_ohlc_threshold"]

            # Symbols with zero OHLC today
            cur.execute("""
                SELECT MAX(date) FROM price_daily
            """)
            max_date_row = cur.fetchone()
            max_date = max_date_row.get("max") if hasattr(max_date_row, "get") else max_date_row[0]

            cur.execute("""
                SELECT DISTINCT symbol FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
                  AND (volume = 0 OR open = 0 OR close = 0)
                ORDER BY symbol
            """)
            today_zero_symbols = {row.get("symbol") if hasattr(row, "keys") else row[0] for row in cur.fetchall()}
            today_zero_count = len(today_zero_symbols)

            # BUG FOUND 2026-08-11: "yesterday" was `MAX(date) - 1 calendar day`, not the
            # previous TRADING day. On a Monday (or the day after any holiday), that lands on
            # a weekend/holiday date with zero rows in price_daily at all - so
            # yesterday_zero_symbols came back empty every single time, and every symbol that
            # is persistently zero-volume by nature (SPACs at NAV, thinly-traded shells) got
            # misclassified as "new" instead of "recurring", inflating new_zeros and risking a
            # false ERROR on the first trading day after every weekend/holiday. Same bug class
            # already fixed for signal-age checks in phase8 - use the market calendar, not raw
            # date arithmetic.
            from datetime import timedelta

            from algo.infrastructure.market_calendar import MarketCalendar

            prev_trading_day = MarketCalendar.get_previous_trading_day(from_date=max_date - timedelta(days=1))

            yesterday_zero_symbols: set[Any] = set()
            if prev_trading_day is not None:
                cur.execute(
                    """
                    SELECT DISTINCT symbol FROM price_daily
                    WHERE date = %s
                      AND (volume = 0 OR open = 0 OR close = 0)
                    ORDER BY symbol
                """,
                    (prev_trading_day,),
                )
                yesterday_zero_symbols = {
                    row.get("symbol") if hasattr(row, "keys") else row[0] for row in cur.fetchall()
                }

            new_zeros = today_zero_symbols - yesterday_zero_symbols
            recurring_zeros = today_zero_symbols & yesterday_zero_symbols

            if len(new_zeros) > new_zeros_error:
                self.log(
                    "zero_data",
                    ERROR,
                    "price_daily",
                    f"{len(new_zeros)} NEW symbols with zero OHLC/volume (threshold {new_zeros_error})",
                    {
                        "new_zeros": len(new_zeros),
                        "today_total": today_zero_count,
                        "recurring": len(recurring_zeros),
                        "threshold": new_zeros_error,
                        "sample_new": sorted(new_zeros)[:5],
                    },
                )
            elif len(new_zeros) > new_zeros_warn:
                self.log(
                    "zero_data",
                    WARN,
                    "price_daily",
                    f"{len(new_zeros)} new zero-volume symbols (warn threshold {new_zeros_warn})",
                    {
                        "new_zeros": len(new_zeros),
                        "today_total": today_zero_count,
                        "recurring": len(recurring_zeros),
                        "threshold": new_zeros_warn,
                    },
                )
            else:
                self.log(
                    "zero_data",
                    INFO,
                    "price_daily",
                    f"{today_zero_count} zero-volume symbols ({len(recurring_zeros)} recurring, {len(new_zeros)} new)",
                    {
                        "today_total": today_zero_count,
                        "recurring": len(recurring_zeros),
                        "new": len(new_zeros),
                    },
                )

            # Identical OHLC check
            cur.execute("""
                SELECT symbol FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
                  AND open = high AND high = low AND low = close
                  AND volume > 0
                ORDER BY symbol
            """)
            ident_symbols = [row.get("symbol") if hasattr(row, "keys") else row[0] for row in cur.fetchall()]
            ident_count = len(ident_symbols)

            if ident_count > ident_threshold:
                self.log(
                    "identical_ohlc",
                    WARN,
                    "price_daily",
                    f"{ident_count} symbols with identical OHLC (threshold {ident_threshold})",
                    {
                        "count": ident_count,
                        "threshold": ident_threshold,
                        "marked_symbols": ident_symbols[:20],
                    },
                )
            else:
                self.log(
                    "identical_ohlc",
                    INFO,
                    "price_daily",
                    f"{ident_count} symbols with identical OHLC (threshold {ident_threshold})",
                    {"count": ident_count, "threshold": ident_threshold},
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log("zero_data", ERROR, "price_daily", f"Check failed: {e}", None)

    def check_ohlc_sanity(self, cur: Any) -> None:
        try:
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE high < open OR high < close OR high < low) AS bad_high,
                       COUNT(*) FILTER (WHERE low > open OR low > close OR low > high) AS bad_low,
                       COUNT(*) FILTER (WHERE open < 0 OR close < 0 OR high < 0 OR low < 0) AS negative
                FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
            """)
            row = cur.fetchone()
            if row is None:
                raise ValueError("OHLC sanity check query returned no results - database state corrupted")
            bad_high, bad_low, negative = row
            if bad_high is None or bad_low is None or negative is None:
                raise ValueError("OHLC COUNT(*) FILTER returned NULL - cannot determine OHLC violations")
            bad_high = int(bad_high)
            bad_low = int(bad_low)
            negative = int(negative)

            if negative > 0:
                self.log(
                    "ohlc_sanity",
                    CRIT,
                    "price_daily",
                    f"{negative} rows with NEGATIVE prices - data corruption",
                    {"negative_count": negative},
                )
            elif bad_high > 0 or bad_low > 0:
                self.log(
                    "ohlc_sanity",
                    ERROR,
                    "price_daily",
                    f"OHLC violation: {bad_high} high<OHLC, {bad_low} low>OHLC",
                    {"bad_high": bad_high, "bad_low": bad_low},
                )
            else:
                self.log(
                    "ohlc_sanity",
                    INFO,
                    "price_daily",
                    "OHLC relationships valid",
                    None,
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log("ohlc_sanity", ERROR, "price_daily", f"Check failed: {e}", None)

    def check_volume_sanity(self, cur: Any) -> None:
        try:
            vol_cfg = self.config.get_volume_config()
            low_vol_threshold = vol_cfg["low_threshold"]
            high_vol_threshold = vol_cfg["high_threshold"]
            new_low_alert = vol_cfg["new_low_alert"]

            # BUG FOUND 2026-08-11: same bug class as check_zero_or_identical's "yesterday" -
            # this "NOT IN (... date = MAX(date) - 1 calendar day ...)" exclusion landed on a
            # weekend/holiday date with zero rows on the first trading day after any gap, so
            # the exclusion subquery was always empty and EVERY low-volume symbol (not just
            # newly-low ones) counted toward low_volume_new - inflating it to ~all low-volume
            # symbols in the universe (confirmed live: 3171 vs a threshold of 50) instead of
            # genuinely new ones. Use the previous TRADING day, not raw calendar arithmetic.
            from datetime import timedelta

            from algo.infrastructure.market_calendar import MarketCalendar

            cur.execute("SELECT MAX(date) FROM price_daily")
            max_date_row = cur.fetchone()
            max_date = max_date_row.get("max") if hasattr(max_date_row, "get") else max_date_row[0]
            prev_trading_day = MarketCalendar.get_previous_trading_day(from_date=max_date - timedelta(days=1))

            cur.execute(
                """
                SELECT
                    SUM(CASE WHEN volume < %s THEN 1 ELSE 0 END) FILTER (
                        WHERE date = (SELECT MAX(date) FROM price_daily)
                          AND symbol NOT IN (SELECT symbol FROM price_daily WHERE date = %s AND volume < %s)
                    ) AS low_volume_new,
                    SUM(CASE WHEN volume > %s THEN 1 ELSE 0 END) FILTER (
                        WHERE date = (SELECT MAX(date) FROM price_daily)
                    ) AS high_volume,
                    COUNT(*) FILTER (WHERE date = (SELECT MAX(date) FROM price_daily)) AS total
                FROM price_daily
            """,
                (low_vol_threshold, prev_trading_day, low_vol_threshold, high_vol_threshold),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError("Volume sanity check query returned no results - database state corrupted")
            low_new, high_vol, total = row
            if low_new is None:
                raise ValueError("Low volume COUNT returned NULL - cannot determine volume anomalies")
            if high_vol is None:
                raise ValueError("High volume COUNT returned NULL - cannot determine volume anomalies")
            if total is None:
                raise ValueError("price_daily COUNT(*) returned NULL - loader may be stalled")
            low_new = int(low_new)
            high_vol = int(high_vol)
            total = int(total)

            if low_new > new_low_alert:
                self.log(
                    "volume_sanity",
                    WARN,
                    "price_daily",
                    f"{low_new} symbols with <{low_vol_threshold} volume (threshold {new_low_alert})",
                    {
                        "new_low_volume": low_new,
                        "total": total,
                        "threshold": new_low_alert,
                    },
                )
            elif high_vol > 5:
                self.log(
                    "volume_sanity",
                    INFO,
                    "price_daily",
                    f"{high_vol} symbols with >{high_vol_threshold} volume",
                    {"extreme_count": high_vol, "threshold": high_vol_threshold},
                )
            else:
                self.log(
                    "volume_sanity",
                    INFO,
                    "price_daily",
                    f"Volume patterns normal (low<{low_vol_threshold}, high>{high_vol_threshold})",
                    {
                        "low_threshold": low_vol_threshold,
                        "high_threshold": high_vol_threshold,
                    },
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log("volume_sanity", ERROR, "price_daily", f"Check failed: {e}", None)
