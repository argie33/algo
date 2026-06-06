#!/usr/bin/env python3
"""Signal Quality Scores Loader -â€ Signal strength confirmation from multiple sources.

Computes signal quality scores (0-100) combining buy/sell signal, technical confirmation, and trend.
Required by Phase 1 data freshness check as tier-2 gate for filtering.

Run: python3 load_signal_quality_scores.py [--symbols AAPL,MSFT] [--parallelism 8]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import os
from datetime import date, timedelta
from typing import List, Optional

import pandas as pd

import logging
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

class SignalQualityScoresLoader(OptimalLoader):
    table_name = "signal_quality_scores"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute signal quality scores from buy/sell signals and technical confirmation."""
        from algo.algo_market_calendar import MarketCalendar
        from datetime import datetime, timezone, timedelta as td

        # CRITICAL: Use ET (trading hours), not UTC, to determine end date.
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(timezone(td(hours=-5)))
        end = now_et.date()

        # If today is not a trading day, use yesterday instead
        # (prevents computing scores for non-trading days when no new signals exist)
        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
            end = end - timedelta(days=1)

        # On ECS restart the in-memory watermark is empty, so since=None.
        # Read the actual DB max date to avoid re-querying 5 years of history.
        if since is None:
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    with DatabaseContext('read') as cur:
                        cur.execute(
                            "SELECT MAX(date) FROM signal_quality_scores WHERE symbol = %s",
                            (symbol,),
                        )
                        row = cur.fetchone()
                        if row and row[0]:
                            since = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]))
                        break
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.debug(f"Watermark read failed (attempt {attempt + 1}/{max_retries}), retrying: {e}")
                        continue
                    logger.warning(f"Could not read signal_quality_scores watermark for {symbol} after {max_retries} attempts. Using full history.")
                    break

        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            start = since - timedelta(days=100)

        # ISSUE #8 FIX: Validate buy_sell_daily COMPLETENESS before computing scores
        # If buy_sell_daily loader was incomplete (missed symbols), signal quality becomes
        # incomplete too, causing cascading failures in Phase 5 filtering
        # ENHANCED: Log why scores are skipped to improve morning pipeline observability
        try:
            with DatabaseContext('read') as cur:
                # Check if buy_sell_daily has completed for end date
                cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active=true")
                cur_row = cur.fetchone()
                expected_symbols = cur_row[0] if cur_row else 4500

                cur.execute(
                    "SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily WHERE date = %s AND signal_type IN ('BUY', 'SELL')",
                    (end,)
                )
                cur_row = cur.fetchone()
                actual_symbols = cur_row[0] if cur_row else 0
                coverage = (actual_symbols / expected_symbols * 100) if expected_symbols > 0 else 0

                if coverage < 95:
                    logger.critical(
                        f"[SIGNAL_QUALITY_SKIPPED] {symbol}: buy_sell_daily INCOMPLETE for {end}: "
                        f"{actual_symbols}/{expected_symbols} symbols ({coverage:.1f}%, REQUIRE >95%). "
                        f"signal_quality_scores cannot run until buy_sell_daily is >95% complete. Rejecting scores."
                    )
                    # Emit metric for morning pipeline observability
                    try:
                        from algo.algo_metrics import MetricsPublisher
                        m = MetricsPublisher()
                        m.put_metric('SignalQualityScoresSkipped', 1, unit='Count', dimensions={
                            'symbol': symbol,
                            'date': str(end),
                            'buy_sell_coverage_pct': f'{coverage:.0f}'
                        })
                        m.flush()
                    except Exception:
                        pass
                    return []
        except Exception as e:
            logger.debug(f"Could not validate buy_sell_daily completeness: {e}")

        buy_sell_rows = self._fetch_buy_sell_signals(symbol, start, end)
        if not buy_sell_rows:
            return []

        technical_rows = self._fetch_technical_data(symbol, start, end)
        trend_rows = self._fetch_trend_data(symbol, start, end)

        scores = self._compute_quality_scores(symbol, buy_sell_rows, technical_rows, trend_rows)
        if not scores:
            return []

        # Filter to incremental range using datetime comparison (not string)
        if since is not None:
            from datetime import date as _date
            since_date = since if isinstance(since, _date) else _date.fromisoformat(str(since))
            scores = [s for s in scores if _date.fromisoformat(s["date"]) > since_date]

        return scores

    def _fetch_buy_sell_signals(self, symbol: str, start: date, end: date) -> List[dict]:
        try:
            with DatabaseContext('read') as cur:
                cur.execute(
                    "SELECT date, signal_type FROM buy_sell_daily "
                    "WHERE symbol = %s AND date >= %s AND date <= %s AND signal_type IN ('BUY', 'SELL') ORDER BY date ASC",
                    (symbol, start, end),
                )
                return [{"date": r[0].isoformat(), "signal_type": r[1]} for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to fetch buy/sell signals for {symbol}: {e}")
            return []

    def _fetch_technical_data(self, symbol: str, start: date, end: date) -> List[dict]:
        from utils.database_context import DatabaseContext
        try:
            with DatabaseContext('read') as cur:
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
        except Exception as e:
            logger.error(f"Failed to fetch technical data for {symbol}: {e}")
            return []

    def _fetch_trend_data(self, symbol: str, start: date, end: date) -> List[dict]:
        from utils.database_context import DatabaseContext
        try:
            with DatabaseContext('read') as cur:
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
        except Exception as e:
            logger.error(f"Failed to fetch trend data for {symbol}: {e}")
            return []

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

            # Track max dates from each source for staleness computation
            max_bs_date = bs_df["date"].max() if not bs_df.empty else None
            max_tech_date = tech_df["date"].max() if not tech_df.empty else None
            max_trend_date = trend_df["date"].max() if not trend_df.empty else None

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
                    # Note: minervini_score is for uptrends (BUY), not applicable to SELL

                    score = min(100, score)

                date_val = row.get("date")
                if date_val is not None:
                    date_str = date_val.date().isoformat() if hasattr(date_val, 'date') else str(date_val)
                    signal_date = pd.Timestamp(date_str).date()

                    # Compute staleness: how many days old is the underlying data?
                    bs_age = (signal_date - max_bs_date.date()).days if max_bs_date is not None else None
                    tech_age = (signal_date - max_tech_date.date()).days if max_tech_date is not None else None
                    trend_age = (signal_date - max_trend_date.date()).days if max_trend_date is not None else None

                    results.append({
                        "symbol": symbol,
                        "date": date_str,
                        "composite_sqs": int(score),
                        "buy_sell_daily_age_days": bs_age,
                        "technical_data_age_days": tech_age,
                        "trend_template_age_days": trend_age,
                    })

            return results
        except Exception as e:
            logger.warning(f"Error computing quality scores for {symbol}: {e}")
            return []

def main():
    parser = argparse.ArgumentParser(description="Load signal quality scores")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=int(os.getenv("LOADER_PARALLELISM", "2")), help="Parallel workers")
    parser.add_argument("--timeframe", type=str, default="daily", help="Timeframe (daily/weekly/monthly, ignored for quality scores)")
    parser.add_argument("--asset-class", type=str, default="stock", help="Asset class (stock/etf, ignored for quality scores)")
    args = parser.parse_args()

    try:
        symbols = (args.symbols.split(",") if args.symbols else get_active_symbols(timeout_secs=300))

        logger.info(f"Starting signal_quality_scores loader with {len(symbols)} symbols, parallelism={args.parallelism}")

        # VALIDATION: signal_quality_scores is critical path; parallelism should be 2 per steering doc line 44-48
        # If parallelism > 4, log warning as it may cause RDS connection pool exhaustion
        if args.parallelism > 4:
            logger.warning(
                f"[PARALLELISM] signal_quality_scores: parallelism={args.parallelism} exceeds recommended max (2). "
                f"This may cause RDS connection pool exhaustion. Check ECS task definition and LOADER_PARALLELISM env var."
            )

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
    from utils.database_context import DatabaseContext
    try:
        with DatabaseContext('write') as cur:
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
            if rows > 0:
                logger.info(f"Synced {rows} signal quality scores to buy_sell_daily")
    except Exception as e:
        logger.warning(f"Failed to sync signal quality scores: {e}")

if __name__ == "__main__":
    sys.exit(main())

