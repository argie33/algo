#!/usr/bin/env python3
"""VCP (Volatility Contraction Pattern) Loader.

Detects volatility contraction patterns in technical data and populates the vcp_patterns table.
This is CRITICAL: signal_quality_scorer depends on this data to compute quality scores.

VCP Detection Logic:
- VCP = recent volatility significantly lower than historical average
- Measured as: recent_atr (14d) / historical_atr (50d) ratio
- VCP_strength = how much volatility has contracted (0-100 scale)
- VCP_pattern_score = combined score with price action confirmation

This loader is a DEPENDENCY for signal quality score computation.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class VCPPatternsLoader:
    """Load VCP pattern data for all symbols."""

    def __init__(self) -> None:
        self.symbols_processed = 0
        self.symbols_failed = 0
        self.patterns_found = 0

    def run(self, end_date: datetime | None = None) -> dict[str, Any]:
        """Load VCP patterns for all symbols.

        Args:
            end_date: End date for analysis (default: today)

        Returns:
            Summary of patterns loaded
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

            # Get all symbols with technical data
            cur.execute(
                "SELECT DISTINCT symbol FROM technical_data_daily "
                "WHERE date >= %s AND atr_14 IS NOT NULL AND atr_50 IS NOT NULL "
                "ORDER BY symbol",
                (end_date - timedelta(days=100),),
            )
            symbols = [row[0] for row in cur.fetchall()]

            logger.info(f"[VCP_LOADER] Processing {len(symbols)} symbols for VCP patterns")

            for symbol in symbols:
                try:
                    self._process_symbol(cur, symbol, end_date)
                    self.symbols_processed += 1
                except Exception as e:
                    logger.warning(f"[VCP_LOADER] {symbol}: {e}")
                    self.symbols_failed += 1

            cur.connection.commit()

        return {
            "symbols_processed": self.symbols_processed,
            "symbols_failed": self.symbols_failed,
            "patterns_found": self.patterns_found,
        }

    def _process_symbol(self, cur: Any, symbol: str, end_date: datetime) -> None:
        """Calculate and store VCP pattern for a symbol.

        Args:
            cur: Database cursor
            symbol: Stock symbol
            end_date: Analysis end date
        """
        # Get recent ATR (14-day) and historical ATR (50-day)
        cur.execute(
            "SELECT atr_14, atr_50, close FROM technical_data_daily "
            "WHERE symbol = %s AND date = %s",
            (symbol, end_date),
        )
        row = cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            return

        atr_14 = float(row[0])
        atr_50 = float(row[1])
        close = float(row[2]) if row[2] else None

        if atr_50 == 0:
            return

        # Calculate VCP strength: how much has volatility contracted
        # atr_14 / atr_50 ratio: <0.7 = strong contraction, >1.0 = expansion
        vcp_ratio = atr_14 / atr_50

        # VCP strength (0-100): 0=expansion, 100=maximum contraction
        if vcp_ratio >= 1.0:
            vcp_strength = 0  # No contraction
        else:
            # Map 0.3-1.0 range to 0-100 scale
            vcp_strength = max(0, min(100, int((1.0 - vcp_ratio) / 0.7 * 100)))

        # Calculate pattern score (0-100)
        # Combines VCP strength with price action
        vcp_pattern_score = self._calculate_pattern_score(cur, symbol, end_date, vcp_strength, atr_14, close)

        # Store VCP pattern
        cur.execute(
            "INSERT INTO vcp_patterns (symbol, date, atr_14, atr_50, vcp_ratio, vcp_strength, vcp_pattern_score) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (symbol, date) DO UPDATE SET "
            "  vcp_strength = EXCLUDED.vcp_strength, "
            "  vcp_pattern_score = EXCLUDED.vcp_pattern_score",
            (symbol, end_date, atr_14, atr_50, vcp_ratio, vcp_strength, vcp_pattern_score),
        )

        if vcp_strength > 50:
            self.patterns_found += 1
            logger.debug(f"[VCP] {symbol}: VCP strength={vcp_strength}, score={vcp_pattern_score}")

    def _calculate_pattern_score(
        self, cur: Any, symbol: str, end_date: datetime, vcp_strength: int, atr_14: float, close: float | None
    ) -> int:
        """Calculate VCP pattern score (0-100) based on multiple factors.

        Args:
            cur: Database cursor
            symbol: Stock symbol
            end_date: Analysis end date
            vcp_strength: VCP contraction strength (0-100)
            atr_14: Recent ATR (14-day)
            close: Current close price

        Returns:
            Pattern score (0-100)
        """
        score = vcp_strength  # Start with VCP strength

        # Bonus: Price above 200-day SMA (uptrend support)
        cur.execute(
            "SELECT sma_200 FROM technical_data_daily WHERE symbol = %s AND date = %s",
            (symbol, end_date),
        )
        row = cur.fetchone()
        if row and row[0] and close:
            sma_200 = float(row[0])
            if close > sma_200:
                score = min(100, score + 10)

        # Bonus: Recent uptrend (close > sma_50)
        cur.execute(
            "SELECT sma_50 FROM technical_data_daily WHERE symbol = %s AND date = %s",
            (symbol, end_date),
        )
        row = cur.fetchone()
        if row and row[0] and close:
            sma_50 = float(row[0])
            if close > sma_50:
                score = min(100, score + 5)

        return min(100, score)


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
