#!/usr/bin/env python3
"""VCP (Volatility Contraction Pattern) Loader.

Detects volatility contraction patterns in technical data and populates the vcp_patterns table.
This is CRITICAL: signal_quality_scorer depends on this data to compute quality scores.

VCP Detection Logic:
- VCP = recent ATR significantly lower than 30-day average
- Measured as: current_atr / atr_30d_avg ratio
- atr_compression_pct = how much volatility has contracted (0-100 scale)
- vcp_strength = composite score combining ATR and range compression

This loader is a DEPENDENCY for signal quality score computation.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class VCPPatternsLoader:
    """Load VCP pattern data for all symbols."""

    def __init__(self) -> None:
        self.symbols_processed = 0
        self.symbols_failed = 0
        self.patterns_found = 0

    def run(self, end_date: date | None = None) -> dict[str, Any]:
        """Load VCP patterns for all symbols across all historical dates.

        Args:
            end_date: End date for analysis (default: today)

        Returns:
            Summary of patterns loaded, includes data_unavailable flag if any failures occur
        """
        if end_date is None:
            end_date = datetime.now(timezone.utc).date()

        with DatabaseContext("write") as cur:
            # Verify technical_data_daily exists
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'technical_data_daily')"
            )
            if not cur.fetchone()[0]:
                raise RuntimeError(
                    "[VCP_LOADER] technical_data_daily table missing. "
                    "Cannot load VCP patterns without technical data. "
                    "Run load_technical_data_daily.py first."
                )

            # Verify vcp_patterns table exists
            cur.execute(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'vcp_patterns')"
            )
            if not cur.fetchone()[0]:
                raise RuntimeError(
                    "[VCP_LOADER] vcp_patterns table missing. "
                    "Cannot load VCP patterns without target table. "
                    "Run database migrations first."
                )

            # Get all unique dates from technical_data_daily
            cur.execute("SELECT DISTINCT date FROM technical_data_daily WHERE atr_14 IS NOT NULL ORDER BY date")
            dates = [row[0] for row in cur.fetchall()]

            if not dates:
                logger.warning("[VCP_LOADER] No technical data available with atr_14")
                return {
                    "symbols_processed": 0,
                    "symbols_failed": 0,
                    "patterns_found": 0,
                    "data_unavailable": True,
                    "reason": "no_technical_data_available",
                }

            logger.info(f"[VCP_LOADER] Processing VCP patterns for {len(dates)} dates")

            # Get all symbols with technical data
            cur.execute("SELECT DISTINCT symbol FROM technical_data_daily WHERE atr_14 IS NOT NULL ORDER BY symbol")
            symbols = [row[0] for row in cur.fetchall()]

            # Process each date for all symbols
            for process_date in dates:
                for symbol in symbols:
                    try:
                        self._process_symbol(cur, symbol, process_date)
                        self.symbols_processed += 1
                    except Exception as e:
                        logger.warning(
                            f"[VCP_LOADER] WARN: VCP processing failed for {symbol} {process_date}: {e}. "
                            f"signal_quality_scorer depends on complete VCP data; this symbol's quality score may be incomplete."
                        )
                        self.symbols_failed += 1

            cur.connection.commit()

        result: dict[str, Any] = {
            "symbols_processed": self.symbols_processed,
            "symbols_failed": self.symbols_failed,
            "patterns_found": self.patterns_found,
        }

        # Mark data unavailable if any failures occurred (signal_quality_scorer needs complete data)
        if self.symbols_failed > 0:
            result["data_unavailable"] = True
            result["reason"] = f"{self.symbols_failed} symbol(s) failed VCP processing"
            logger.error(
                f"[VCP_LOADER] CRITICAL: {self.symbols_failed} VCP processing failures. "
                f"signal_quality_scorer will have incomplete data. Check logs for per-symbol errors."
            )

        return result

    def _process_symbol(self, cur: Any, symbol: str, end_date: date) -> None:
        """Calculate and store VCP pattern for a symbol. Fail-fast on data quality issues.

        Args:
            cur: Database cursor
            symbol: Stock symbol
            end_date: Analysis end date
        """
        # Fetch the last 30 days of ATR data for the symbol
        cur.execute(
            "SELECT date, atr_14 FROM technical_data_daily "
            "WHERE symbol = %s AND date >= %s AND date <= %s AND atr_14 IS NOT NULL "
            "ORDER BY date DESC LIMIT 30",
            (symbol, end_date - timedelta(days=30), end_date),
        )
        rows = cur.fetchall()
        if not rows:
            logger.error(f"[VCP] {symbol} {end_date}: No ATR data found for last 30 days")
            raise RuntimeError(f"VCP pattern calculation failed: no ATR data for {symbol} on {end_date}")

        # Current ATR is the most recent value
        current_atr = float(rows[0][1])

        # Calculate 30-day average ATR
        atrs = [float(row[1]) for row in rows]
        atr_30d_avg = sum(atrs) / len(atrs)

        if atr_30d_avg == 0:
            logger.error(f"[VCP] {symbol} {end_date}: Average ATR is 0 (data corruption?)")
            raise RuntimeError(f"VCP pattern calculation failed: zero average ATR for {symbol} on {end_date}")

        # Calculate ATR compression percentage (how much lower current is vs average)
        atr_compression_pct = max(0, (1.0 - (current_atr / atr_30d_avg)) * 100)

        # Fetch price range data (high - low) for last 30 days
        cur.execute(
            "SELECT date, (high - low) as range FROM price_daily "
            "WHERE symbol = %s AND date >= %s AND date <= %s "
            "ORDER BY date DESC LIMIT 30",
            (symbol, end_date - timedelta(days=30), end_date),
        )
        range_rows = cur.fetchall()

        if not range_rows:
            logger.error(f"[VCP] {symbol} {end_date}: No price range data found for last 30 days")
            raise RuntimeError(f"VCP pattern calculation failed: no price data for {symbol} on {end_date}")

        # Fail-fast if price range data is missing (NULL indicates upstream data quality issue)
        if any(row[1] is None for row in range_rows):
            logger.error(f"[VCP] {symbol} {end_date}: Price range data contains NULL values in price_daily")
            raise RuntimeError(f"VCP pattern calculation failed: NULL price ranges for {symbol} on {end_date}")

        ranges = [float(row[1]) for row in range_rows]
        range_30d_avg = sum(ranges) / len(ranges)
        range_current = float(range_rows[0][1])

        # Calculate range compression
        range_compression_pct: float = 0.0
        if range_30d_avg > 0:
            range_compression_pct = max(0.0, (1.0 - (range_current / range_30d_avg)) * 100)

        # Calculate volume ratio for breakout confirmation
        cur.execute(
            "SELECT date, volume FROM price_daily "
            "WHERE symbol = %s AND date >= %s AND date <= %s "
            "ORDER BY date DESC LIMIT 30",
            (symbol, end_date - timedelta(days=30), end_date),
        )
        vol_rows = cur.fetchall()

        if not vol_rows:
            logger.error(f"[VCP] {symbol} {end_date}: No volume data found for last 30 days")
            raise RuntimeError(f"VCP pattern calculation failed: no volume data for {symbol} on {end_date}")

        # Fail-fast if volume data is missing (NULL indicates upstream data quality issue)
        if any(row[1] is None for row in vol_rows):
            logger.error(f"[VCP] {symbol} {end_date}: Volume data contains NULL values in price_daily")
            raise RuntimeError(f"VCP pattern calculation failed: NULL volume values for {symbol} on {end_date}")

        current_vol = float(vol_rows[0][1])
        vols = [float(row[1]) for row in vol_rows[1:]]
        avg_vol = sum(vols) / len(vols) if vols else 0
        if avg_vol <= 0:
            logger.error(f"[VCP] {symbol} {end_date}: Average volume is 0 or negative (data corruption?)")
            raise RuntimeError(f"VCP pattern calculation failed: invalid average volume for {symbol} on {end_date}")
        breakout_volume_ratio = current_vol / avg_vol

        # Calculate VCP strength (0-100 scale)
        # Strong VCP: ATR compression > 30% and range compression > 20%
        avg_compression = (atr_compression_pct + range_compression_pct) / 2
        vcp_strength = min(100, max(0, int(avg_compression)))

        # Store VCP pattern
        cur.execute(
            "INSERT INTO vcp_patterns "
            "(symbol, date, atr_30d_avg, atr_current, atr_compression_pct, "
            "range_30d_avg, range_current, vcp_strength, breakout_volume_ratio) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (symbol, date) DO UPDATE SET "
            "  atr_compression_pct = EXCLUDED.atr_compression_pct, "
            "  vcp_strength = EXCLUDED.vcp_strength, "
            "  breakout_volume_ratio = EXCLUDED.breakout_volume_ratio",
            (
                symbol,
                end_date,
                atr_30d_avg,
                current_atr,
                atr_compression_pct,
                range_30d_avg,
                range_current,
                vcp_strength,
                breakout_volume_ratio,
            ),
        )

        if vcp_strength > 50:
            self.patterns_found += 1
            logger.debug(f"[VCP] {symbol}: strength={vcp_strength}, atr_compression={atr_compression_pct:.1f}%")


def load_vcp_patterns(end_date: datetime | None = None) -> dict[str, Any]:
    """Load VCP patterns for all symbols.

    Args:
        end_date: End date for analysis (default: today)

    Returns:
        Summary of patterns loaded
    """
    loader = VCPPatternsLoader()
    return loader.run(end_date)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = load_vcp_patterns()
    logger.info(f"VCP Patterns Load Summary: {result}")
