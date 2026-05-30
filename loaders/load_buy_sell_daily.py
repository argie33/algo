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

from utils.structured_logger import get_logger
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from utils.database_context import DatabaseContext

logger = get_logger(__name__)


class SignalsDailyLoader(OptimalLoader):
    """Daily signals loader that generates buy/sell signals from technical indicators."""

    table_name = "buy_sell_daily"
    primary_key = ("symbol", "timeframe", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Generate signals from technical data."""
        from algo.algo_market_calendar import MarketCalendar

        end = date.today()
        # If today is not a trading day, use yesterday instead
        # (prevents generating signals for non-trading days when no new data exists)
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
            end = end - timedelta(days=1)

        # On ECS restart the in-memory watermark is empty, so since=None.
        # Read the actual DB max date to avoid re-fetching old data and causing constraint violations.
        if since is None:
            try:
                conn = self._connect()
                cur = conn.cursor()
                cur.execute(
                    "SELECT MAX(date) FROM buy_sell_daily WHERE symbol = %s",
                    (symbol,),
                )
                row = cur.fetchone()
                cur.close()
                if row and row[0]:
                    since = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]))
            except Exception as e:
                logger.warning(f"Could not read buy_sell_daily watermark for {symbol}: {e}")

        if since is None:
            start = end - timedelta(days=30)
        else:
            # FIXED Issue #22: Use since - 1 day for watermark (standard across all loaders)
            # This ensures we get overlap data for cross-checking and prevents gaps
            start = since - timedelta(days=1)

        # FIXED Issue #20: Validate technical data is fresh before generating signals
        conn = self._connect()
        cur = conn.cursor()
        try:
            # Check if technical data exists for end date, fall back to most recent available date
            cur.execute(
                "SELECT COUNT(*) FROM technical_data_daily WHERE symbol = %s AND date = %s",
                (symbol, end)
            )
            if cur.fetchone()[0] == 0:
                # Fall back: find most recent date with technical data for this symbol
                cur.execute(
                    "SELECT MAX(date) FROM technical_data_daily WHERE symbol = %s AND date < %s",
                    (symbol, end)
                )
                fallback_date = cur.fetchone()[0]
                if fallback_date:
                    end = fallback_date
                else:
                    logger.warning(f"{symbol}: Technical data missing for {end} — signals cannot be generated")
                    return []
        finally:
            cur.close()

        # Fetch required data for signal generation
        rows = self._fetch_signal_data(symbol, start, end)
        if not rows:
            logger.warning(f"{symbol}: No technical data found between {start} and {end}")
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
                """SELECT t.date, t.rsi, t.macd, t.macd_signal,
                          t.sma_50, t.sma_200, t.ema_12, t.ema_21, t.atr,
                          t.adx, t.mansfield_rs,
                          p.close, p.volume, p.open, p.high, p.low
                   FROM technical_data_daily t
                   LEFT JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
                   WHERE t.symbol = %s AND t.date >= %s AND t.date <= %s
                   ORDER BY t.date ASC""",
                (symbol, start, end),
            )
            rows = []
            for r in cur.fetchall():
                if r[0] is None or r[11] is None:
                    continue
                rows.append({
                    "date": r[0].isoformat() if r[0] else None,
                    "rsi": float(r[1]) if r[1] is not None else None,
                    "macd": float(r[2]) if r[2] is not None else None,
                    "macd_signal": float(r[3]) if r[3] is not None else None,
                    "sma_50": float(r[4]) if r[4] is not None else None,
                    "sma_200": float(r[5]) if r[5] is not None else None,
                    "ema_12": float(r[6]) if r[6] is not None else None,
                    "ema_21": float(r[7]) if r[7] is not None else None,
                    "atr": float(r[8]) if r[8] is not None else None,
                    "adx": float(r[9]) if r[9] is not None else None,
                    "mansfield_rs": float(r[10]) if r[10] is not None else None,
                    "close": float(r[11]) if r[11] is not None else None,
                    "volume": int(r[12]) if r[12] is not None else None,
                    "open": float(r[13]) if r[13] is not None else None,
                    "high": float(r[14]) if r[14] is not None else None,
                    "low": float(r[15]) if r[15] is not None else None,
                })
            return rows
        finally:
            cur.close()

    def _generate_signals(self, symbol: str, rows: List[dict]) -> List[dict]:
        """Generate buy/sell signals from technical indicators with volume and volatility confirmation."""
        if not rows:
            return []

        signals = []
        for i, row in enumerate(rows):
            rsi = row.get("rsi")
            macd = row.get("macd")
            macd_signal = row.get("macd_signal")
            sma_50 = row.get("sma_50")
            sma_200 = row.get("sma_200")
            close = row.get("close")
            volume = row.get("volume")
            atr = row.get("atr")
            ema_21 = row.get("ema_21")
            adx = row.get("adx")
            mansfield_rs = row.get("mansfield_rs")

            # Skip if missing critical data
            if any(v is None for v in [rsi, macd, macd_signal, close]):
                continue

            signal_type = None
            strength = 0.0
            reason = ""

            # Calculate volume confirmation (compare to previous bar average)
            vol_confirmed = True
            if volume is not None and i > 0:
                prev_vol = rows[i-1].get("volume", volume)
                vol_confirmed = volume >= prev_vol * 0.8  # At least 80% of prior bar

            # Calculate volatility (ATR-based, require meaningful moves)
            has_volatility = True
            if atr is not None and close is not None and sma_50 is not None:
                volatility_pct = (atr / close) * 100 if close > 0 else 0
                # Require at least 0.5% volatility to avoid whipsaws in low-vol environments
                has_volatility = volatility_pct >= 0.5

            # Enhanced signal rules with volume and volatility confirmation
            if rsi < 30 and macd > macd_signal and vol_confirmed and has_volatility:
                signal_type = "BUY"
                strength = (30 - rsi) / 30 * (1.0 if vol_confirmed else 0.7)
                reason = "Oversold with bullish MACD + volume confirmation"
            elif rsi > 70 and macd < macd_signal and vol_confirmed and has_volatility:
                signal_type = "SELL"
                strength = (rsi - 70) / 30 * (1.0 if vol_confirmed else 0.7)
                reason = "Overbought with bearish MACD + volume confirmation"
            elif sma_50 and sma_200 and close > sma_50 > sma_200 and macd > macd_signal and vol_confirmed:
                signal_type = "BUY"
                strength = 0.6 * (1.0 if vol_confirmed else 0.7)
                reason = "Bullish alignment + volume confirmation"
            elif sma_50 and sma_200 and close < sma_50 < sma_200 and macd < macd_signal and vol_confirmed:
                signal_type = "SELL"
                strength = 0.6 * (1.0 if vol_confirmed else 0.7)
                reason = "Bearish alignment + volume confirmation"

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
                    "rsi": float(rsi) if rsi is not None else None,
                    "sma_50": float(sma_50) if sma_50 is not None else None,
                    "sma_200": float(sma_200) if sma_200 is not None else None,
                    "ema_21": float(ema_21) if ema_21 is not None else None,
                    "atr": float(atr) if atr is not None else None,
                    "adx": float(adx) if adx is not None else None,
                    "mansfield_rs": float(mansfield_rs) if mansfield_rs is not None else None,
                    "macd": float(macd) if macd is not None else None,
                    "macd_signal": float(macd_signal) if macd_signal is not None else None,
                    "stage_number": None,
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": float(close) if close is not None else None,
                    "volume": row.get("volume"),
                })

        return signals


def main():
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
