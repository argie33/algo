#!/usr/bin/env python3
"""Signal Quality Scores Loader â€” Signal strength confirmation from multiple sources.

Computes signal quality scores (0-100) combining buy/sell signal, technical confirmation, and trend.
Required by Phase 1 data freshness check as tier-2 gate for filtering.

Run: python3 load_signal_quality_scores.py [--symbols AAPL,MSFT] [--parallelism 8]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from datetime import date, timedelta
from typing import List, Optional

import pandas as pd

from config.env_loader import load_env
from utils.structured_logger import get_logger
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader

logger = get_logger(__name__)


class SignalQualityScoresLoader(OptimalLoader):
    table_name = "signal_quality_scores"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute signal quality scores from buy/sell signals and technical confirmation."""
        from algo.algo_market_calendar import MarketCalendar

        end = date.today()
        # If today is not a trading day, use yesterday instead
        # (prevents computing scores for non-trading days when no new signals exist)
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
            end = end - timedelta(days=1)

        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            start = since - timedelta(days=100)

        buy_sell_rows = self._fetch_buy_sell_signals(symbol, start, end)
        if not buy_sell_rows:
            return []

        technical_rows = self._fetch_technical_data(symbol, start, end)
        trend_rows = self._fetch_trend_data(symbol, start, end)

        scores = self._compute_quality_scores(symbol, buy_sell_rows, technical_rows, trend_rows)
        if not scores:
            return []

        if since is not None:
            since_str = since.isoformat()
            scores = [s for s in scores if s["date"] > since_str]

        return scores

    def _fetch_buy_sell_signals(self, symbol: str, start: date, end: date) -> List[dict]:
        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT date, signal_type FROM buy_sell_daily "
                "WHERE symbol = %s AND date >= %s AND date <= %s AND signal_type IN ('BUY', 'SELL') ORDER BY date ASC",
                (symbol, start, end),
            )
            return [{"date": r[0].isoformat(), "signal_type": r[1]} for r in cur.fetchall()]
        finally:
            cur.close()

    def _fetch_technical_data(self, symbol: str, start: date, end: date) -> List[dict]:
        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT date, rsi, macd, macd_signal FROM technical_data_daily "
                "WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                (symbol, start, end),
            )
            return [
                {
                    "date": r[0].isoformat(),
                    "rsi": float(r[1]) if r[1] is not None else None,
                    "macd": float(r[2]) if r[2] is not None else None,
                    "macd_signal": float(r[3]) if r[3] is not None else None,
                }
                for r in cur.fetchall()
            ]
        finally:
            cur.close()

    def _fetch_trend_data(self, symbol: str, start: date, end: date) -> List[dict]:
        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT date, minervini_trend_score, weinstein_stage FROM trend_template_data "
                "WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                (symbol, start, end),
            )
            return [
                {
                    "date": r[0].isoformat(),
                    "minervini_score": float(r[1]) if r[1] is not None else 0,
                    "weinstein_stage": r[2],
                }
                for r in cur.fetchall()
            ]
        finally:
            cur.close()

    def _compute_quality_scores(self, symbol: str, buy_sell_rows: List[dict],
                                technical_rows: List[dict], trend_rows: List[dict]) -> List[dict]:
        if not buy_sell_rows:
            return []

        try:
            bs_df = pd.DataFrame(buy_sell_rows)
            if bs_df.empty:
                return []
            bs_df["date"] = pd.to_datetime(bs_df["date"])

            tech_df = pd.DataFrame(technical_rows) if technical_rows else pd.DataFrame()
            if not tech_df.empty:
                tech_df["date"] = pd.to_datetime(tech_df["date"])

            trend_df = pd.DataFrame(trend_rows) if trend_rows else pd.DataFrame()
            if not trend_df.empty:
                trend_df["date"] = pd.to_datetime(trend_df["date"])

            # Merge with left join to keep all buy/sell rows
            merged = bs_df
            if not tech_df.empty:
                merged = merged.merge(tech_df, on="date", how="left")
            if not trend_df.empty:
                merged = merged.merge(trend_df, on="date", how="left")

            results = []
            for _, row in merged.iterrows():
                score = 40
                signal_type = row.get("signal_type")
                if not signal_type:
                    continue

                if signal_type == "BUY":
                    rsi = row.get("rsi")
                    macd = row.get("macd")
                    macd_signal = row.get("macd_signal")
                    minervini = row.get("minervini_score", 0)

                    if rsi and 40 < float(rsi) < 80:
                        score += 10
                    if macd is not None and macd_signal is not None and float(macd) > float(macd_signal):
                        score += 10
                    if minervini and float(minervini) >= 3:
                        score += 15

                    score = min(100, score)

                elif signal_type == "SELL":
                    rsi = row.get("rsi")
                    macd = row.get("macd")
                    macd_signal = row.get("macd_signal")

                    if rsi and 20 < float(rsi) < 60:
                        score += 10
                    if macd is not None and macd_signal is not None and float(macd) < float(macd_signal):
                        score += 10

                    score = min(100, score)

                date_val = row.get("date")
                if date_val is not None:
                    date_str = date_val.date().isoformat() if hasattr(date_val, 'date') else str(date_val)
                    results.append({
                        "symbol": symbol,
                        "date": date_str,
                        "composite_sqs": int(score),
                    })

            return results
        except Exception as e:
            logger.warning(f"Error computing quality scores for {symbol}: {e}")
            return []


def main():
    load_env()
    parser = argparse.ArgumentParser(description="Load signal quality scores")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=4, help="Parallel workers")
    parser.add_argument("--timeframe", type=str, default="daily", help="Timeframe (daily/weekly/monthly, ignored for quality scores)")
    parser.add_argument("--asset-class", type=str, default="stock", help="Asset class (stock/etf, ignored for quality scores)")
    args = parser.parse_args()

    try:
        symbols = (args.symbols.split(",") if args.symbols else get_active_symbols(timeout_secs=60))
        loader = SignalQualityScoresLoader()
        loader.run(symbols, parallelism=args.parallelism)
        logger.info("Signal quality scores load completed")

        # Sync composite_sqs back to buy_sell_daily for consistency
        _sync_scores_to_buy_sell()

        return 0
    except Exception as e:
        logger.error(f"Signal quality scores load failed: {e}")
        return 1


def _sync_scores_to_buy_sell():
    """Sync composite_sqs from signal_quality_scores to buy_sell_daily.signal_quality_score."""
    from utils.db_connection import get_db_connection
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE buy_sell_daily bsd
            SET signal_quality_score = COALESCE(sqs.composite_sqs, bsd.signal_quality_score)
            FROM signal_quality_scores sqs
            WHERE bsd.symbol = sqs.symbol
            AND bsd.date = sqs.date
            AND bsd.signal_quality_score IS NULL
            AND sqs.composite_sqs IS NOT NULL
        """)
        rows = cur.rowcount
        conn.commit()
        cur.close()
        if rows > 0:
            logger.info(f"Synced {rows} signal quality scores to buy_sell_daily")
    except Exception as e:
        logger.warning(f"Failed to sync signal quality scores: {e}")

if __name__ == "__main__":
    sys.exit(main())

