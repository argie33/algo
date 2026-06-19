#!/usr/bin/env python3
"""Data quality checks - NULL anomalies, OHLC sanity, zero values, volume sanity."""

import logging
from typing import List, cast

from ..base import BaseCheck, CheckResult
from ..config import CRIT, ERROR, INFO, WARN


logger = logging.getLogger(__name__)


class QualityChecker(BaseCheck):
    """Check data quality: NULLs, OHLC relationships, zero values, volume."""

    def run(self, cur) -> List[CheckResult]:
        """Execute all quality checks."""
        self.results = []

        self.check_null_anomalies(cur)
        self.check_zero_or_identical(cur)
        self.check_ohlc_sanity(cur)
        self.check_volume_sanity(cur)

        return self.results

    def check_null_anomalies(self, cur) -> None:
        """Check for sudden spike in NULL values."""
        try:
            max_null_pct = cast(int, self.config.get("patrol_max_null_pct_threshold", 5))

            cur.execute("""
                SELECT
                    SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END) FILTER (
                        WHERE date = (SELECT MAX(date) FROM price_daily)) AS today_nulls,
                    COUNT(*) FILTER (WHERE date = (SELECT MAX(date) FROM price_daily)) AS today_total
                FROM price_daily
                WHERE date >= (SELECT MAX(date) FROM price_daily) - INTERVAL '30 days'
            """)
            today_nulls, today_total = cur.fetchone()
            today_nulls = int(today_nulls or 0)
            today_total = int(today_total or 1)
            null_pct = today_nulls / today_total * 100 if today_total else 0

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
        except Exception as e:
            self.log("null_anomaly", ERROR, "price_daily", f"Check failed: {e}", None)

    def check_zero_or_identical(self, cur) -> None:
        """Check for zero values or identical OHLC (sign of API limit hit)."""
        try:
            quality_cfg = self.config.get_quality_config()
            new_zeros_error = quality_cfg["zero_symbols_error"]
            new_zeros_warn = quality_cfg["zero_symbols_warn"]
            ident_threshold = quality_cfg["identical_ohlc_threshold"]

            # Symbols with zero OHLC today
            cur.execute("""
                SELECT DISTINCT symbol FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
                  AND (volume = 0 OR open = 0 OR close = 0)
                ORDER BY symbol
            """)
            today_zero_symbols = {row[0] for row in cur.fetchall()}
            today_zero_count = len(today_zero_symbols)

            # Symbols with zero OHLC yesterday
            cur.execute("""
                SELECT DISTINCT symbol FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily) - INTERVAL '1 day'
                  AND (volume = 0 OR open = 0 OR close = 0)
                ORDER BY symbol
            """)
            yesterday_zero_symbols = {row[0] for row in cur.fetchall()}

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
                        "sample_new": sorted(list(new_zeros))[:5],
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
            ident_symbols = [row[0] for row in cur.fetchall()]
            ident_count = len(ident_symbols)

            # Mark suspicious OHLC in database
            if ident_count > 0:
                try:
                    cur.execute(
                        """
                        UPDATE price_daily
                        SET data_quality_flags = COALESCE(data_quality_flags, '{}')::jsonb || '{"is_suspicious_ohlc": true}'::jsonb
                        WHERE symbol = ANY(%s) AND date = (SELECT MAX(date) FROM price_daily)
                    """,
                        (ident_symbols,),
                    )
                except Exception as e:
                    logger.warning(f"Could not mark suspicious OHLC: {e}")

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
        except Exception as e:
            self.log("zero_data", ERROR, "price_daily", f"Check failed: {e}", None)

    def check_ohlc_sanity(self, cur) -> None:
        """Check OHLC relationships: High >= Open/Close/Low, etc."""
        try:
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE high < open OR high < close OR high < low) AS bad_high,
                       COUNT(*) FILTER (WHERE low > open OR low > close OR low > high) AS bad_low,
                       COUNT(*) FILTER (WHERE open < 0 OR close < 0 OR high < 0 OR low < 0) AS negative
                FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
            """)
            bad_high, bad_low, negative = cur.fetchone()
            bad_high = int(bad_high or 0)
            bad_low = int(bad_low or 0)
            negative = int(negative or 0)

            if negative > 0:
                self.log(
                    "ohlc_sanity",
                    CRIT,
                    "price_daily",
                    f"{negative} rows with NEGATIVE prices — data corruption",
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
        except Exception as e:
            self.log("ohlc_sanity", ERROR, "price_daily", f"Check failed: {e}", None)

    def check_volume_sanity(self, cur) -> None:
        """Check volume within realistic range."""
        try:
            vol_cfg = self.config.get_volume_config()
            low_vol_threshold = vol_cfg["low_threshold"]
            high_vol_threshold = vol_cfg["high_threshold"]
            new_low_alert = vol_cfg["new_low_alert"]

            cur.execute(
                """
                SELECT
                    SUM(CASE WHEN volume < %s THEN 1 ELSE 0 END) FILTER (
                        WHERE date = (SELECT MAX(date) FROM price_daily)
                          AND symbol NOT IN (SELECT symbol FROM price_daily WHERE date = (SELECT MAX(date) FROM price_daily) - INTERVAL '1 day' AND volume < %s)
                    ) AS low_volume_new,
                    SUM(CASE WHEN volume > %s THEN 1 ELSE 0 END) FILTER (
                        WHERE date = (SELECT MAX(date) FROM price_daily)
                    ) AS high_volume,
                    COUNT(*) FILTER (WHERE date = (SELECT MAX(date) FROM price_daily)) AS total
                FROM price_daily
            """,
                (low_vol_threshold, low_vol_threshold, high_vol_threshold),
            )
            low_new, high_vol, total = cur.fetchone()
            low_new = int(low_new or 0)
            high_vol = int(high_vol or 0)
            total = int(total or 1)

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
        except Exception as e:
            self.log("volume_sanity", ERROR, "price_daily", f"Check failed: {e}", None)
