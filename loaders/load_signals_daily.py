#!/usr/bin/env python3
"""Daily buy/sell signals generator.

Generates daily trading signals from technical indicators and quality scores.
Populates the buy_sell_daily table.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import date, timedelta
from typing import List, Optional

from config.env_loader import load_env
from utils.structured_logger import get_logger
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from utils.db_connection import get_db_connection

logger = get_logger(__name__)


class SignalsDailyLoader(OptimalLoader):
    """Daily signals loader that generates buy/sell signals from technical indicators."""

    table_name = "buy_sell_daily"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Generate signals from technical data."""
        from algo.algo_market_calendar import MarketCalendar

        end = date.today()
        # If today is not a trading day, use yesterday instead
        # (prevents generating signals for non-trading days when no new data exists)
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
            end = end - timedelta(days=1)

        if since is None:
            start = end - timedelta(days=30)
        else:
            start = since - timedelta(days=1)

        # Fetch required data for signal generation
        rows = self._fetch_signal_data(symbol, start, end)
        if not rows:
            return []

        # Generate signals
        signals = self._generate_signals(symbol, rows)

        # Filter to incremental range if needed
        if since is not None:
            since_str = since.isoformat()
            signals = [s for s in signals if s["date"] > since_str]

        return signals

    def _fetch_signal_data(self, symbol: str, start: date, end: date) -> List[dict]:
        """Fetch technical and price data needed for signal generation."""
        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute(
                """SELECT t.date, t.rsi_14, t.macd, t.macd_signal,
                          t.sma_50, t.sma_200, t.ema_12, t.atr_14,
                          p.close, p.volume
                   FROM technical_data_daily t
                   LEFT JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
                   WHERE t.symbol = %s AND t.date >= %s AND t.date <= %s
                   ORDER BY t.date ASC""",
                (symbol, start, end),
            )
            rows = []
            for r in cur.fetchall():
                if r[0] is None or r[8] is None:
                    continue
                rows.append({
                    "date": r[0].isoformat() if r[0] else None,
                    "rsi": float(r[1]) if r[1] is not None else None,
                    "macd": float(r[2]) if r[2] is not None else None,
                    "macd_signal": float(r[3]) if r[3] is not None else None,
                    "sma_50": float(r[4]) if r[4] is not None else None,
                    "sma_200": float(r[5]) if r[5] is not None else None,
                    "ema_12": float(r[6]) if r[6] is not None else None,
                    "atr": float(r[7]) if r[7] is not None else None,
                    "close": float(r[8]) if r[8] is not None else None,
                    "volume": int(r[9]) if r[9] is not None else None,
                })
            return rows
        finally:
            cur.close()

    def _generate_signals(self, symbol: str, rows: List[dict]) -> List[dict]:
        """Generate simple buy/sell signals from technical indicators."""
        if not rows:
            return []

        signals = []
        for row in rows:
            rsi = row.get("rsi")
            macd = row.get("macd")
            macd_signal = row.get("macd_signal")
            sma_50 = row.get("sma_50")
            sma_200 = row.get("sma_200")
            close = row.get("close")

            # Skip if missing critical data
            if any(v is None for v in [rsi, macd, macd_signal, close]):
                continue

            signal_type = None
            strength = 0.0
            reason = ""

            # Simple signal rules
            if rsi < 30 and macd > macd_signal:
                signal_type = "BUY"
                strength = (30 - rsi) / 30
                reason = "Oversold with bullish MACD crossover"
            elif rsi > 70 and macd < macd_signal:
                signal_type = "SELL"
                strength = (rsi - 70) / 30
                reason = "Overbought with bearish MACD crossover"
            elif sma_50 and sma_200 and close > sma_50 > sma_200 and macd > macd_signal:
                signal_type = "BUY"
                strength = 0.6
                reason = "Bullish alignment"
            elif sma_50 and sma_200 and close < sma_50 < sma_200 and macd < macd_signal:
                signal_type = "SELL"
                strength = 0.6
                reason = "Bearish alignment"

            if signal_type:
                signals.append({
                    "symbol": symbol,
                    "date": row["date"],
                    "timeframe": "1d",
                    "signal": signal_type,
                    "signal_type": signal_type,
                    "strength": float(strength),
                    "reason": reason,
                    "entry_quality_score": None,
                    "signal_quality_score": None,
                    "volume_surge_pct": None,
                    "risk_reward_ratio": None,
                    "rsi": float(rsi) if rsi else None,
                    "sma_50": row.get("sma_50"),
                    "sma_200": row.get("sma_200"),
                    "ema_21": None,
                    "atr": row.get("atr"),
                    "adx": None,
                    "macd": float(macd) if macd else None,
                    "macd_signal": float(macd_signal) if macd_signal else None,
                    "stage_number": None,
                })

        return signals


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Load daily trading signals")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=4, help="Parallel workers")
    args = parser.parse_args()

    try:
        if args.symbols:
            symbols = args.symbols.split(",")
        else:
            symbols = get_active_symbols(timeout_secs=300)
            if not symbols:
                logger.warning("No symbols found in stock_symbols table - exiting")
                return 1
    except Exception as e:
        logger.error(f"Failed to get symbols: {e}")
        return 1

    loader = SignalsDailyLoader()
    try:
        result = loader.run(symbols, parallelism=args.parallelism)
        logger.info("Daily signals load completed")
        return 0
    except Exception as e:
        logger.error(f"Daily signals load failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
