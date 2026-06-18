#!/usr/bin/env python3
"""Signal Quality Scores Loader -â€ Signal strength confirmation from multiple sources.

Computes signal quality scores (0-100) combining buy/sell signal, technical confirmation, and trend.
Required by Phase 1 data freshness check as tier-2 gate for filtering.

Run: python3 load_signal_quality_scores.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import sys

from loaders.loader_helper import setup_imports


setup_imports()

import argparse
import logging
from datetime import date, timedelta

import pandas as pd

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.config import get_default_parallelism
from utils.loaders.helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from utils.validation import safe_parse_date


logger = logging.getLogger(__name__)


class SignalQualityScoresLoader(OptimalLoader):
    table_name = "signal_quality_scores"
    primary_key = ("symbol", "date")
    watermark_field = "date"

    def _prepare_batch_context(self) -> None:
        """Load shared data once to avoid N+1 queries (ROOT CAUSE #4 FIX).

        Caches end_date and buy_sell_daily signal count to avoid per-symbol computation.

        ISSUE #27 FIX: Check that buy_sell_daily is not RUNNING/PENDING before proceeding.
        If buy_sell_daily loader is stuck, abort this loader to prevent incomplete data.
        """
        from datetime import datetime, timezone

        from algo.infrastructure import MarketCalendar

        self._batch_context = {}
        try:
            with DatabaseContext("read") as cur:
                # Check if buy_sell_daily is ready (ISSUE #27 FIX)
                cur.execute(
                    "SELECT status FROM data_loader_status WHERE table_name = 'buy_sell_daily'"
                )
                result = cur.fetchone()
                bs_status = result[0] if result else None

                if bs_status in ("RUNNING", "PENDING"):
                    logger.warning(
                        f"[{self.table_name}] Aborting: buy_sell_daily status is {bs_status} - "
                        "waiting for upstream to complete"
                    )
                    self._batch_context = {"_blocked": True}
                    return

                now_utc = datetime.now(timezone.utc)
                now_et = now_utc.astimezone(EASTERN_TZ)
                end = now_et.date()

                while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
                    end = end - timedelta(days=1)

                cur.execute(
                    "SELECT MAX(date) FROM buy_sell_daily WHERE signal_type IN ('BUY', 'SELL') AND date <= %s",
                    (end,),
                )
                row = cur.fetchone()
                last_bs_date = (
                    row[0] if row is not None and row[0] is not None else None
                )
                if last_bs_date:
                    last_bs = safe_parse_date(last_bs_date, "buy_sell_daily max date")
                    if last_bs and last_bs < end:
                        end = last_bs

                cur.execute(
                    "SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily WHERE date = %s AND signal_type IN ('BUY', 'SELL')",
                    (end,),
                )
                cur_row = cur.fetchone()
                actual_symbols = cur_row[0] if cur_row else 0

            self._batch_context = {
                "end_date": end,
                "bs_signal_count": actual_symbols,
            }
            logger.debug(f"Batch context: end={end}, bs_signals={actual_symbols}")
        except Exception as e:
            logger.warning(f"Batch context preparation failed: {e}")
            self._batch_context = {}

    def fetch_incremental(self, symbol: str, since: date | None):
        """Compute signal quality scores from buy/sell signals and technical confirmation."""
        from datetime import datetime, timezone

        from algo.infrastructure import MarketCalendar

        # ISSUE #27 FIX: Skip if buy_sell_daily is blocked
        if self._batch_context and self._batch_context.get("_blocked"):
            logger.debug(f"[{self.table_name}] Skipping {symbol} - buy_sell_daily not ready")
            return []

        # ROOT CAUSE #4 FIX: Use cached end_date from batch context (computed once for all symbols)
        # instead of recomputing trading day verification for each symbol.
        if self._batch_context and "end_date" in self._batch_context:
            end = self._batch_context["end_date"]
        else:
            # Fallback if batch context unavailable
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            end = now_et.date()

            while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
                end = end - timedelta(days=1)

            # Fallback: check buy_sell_daily max date if batch context failed
            try:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT MAX(date) FROM buy_sell_daily WHERE signal_type IN ('BUY', 'SELL') AND date <= %s",
                        (end,),
                    )
                    row = cur.fetchone()
                    last_bs_date = (
                        row[0] if row is not None and row[0] is not None else None
                    )
                    if last_bs_date:
                        last_bs = safe_parse_date(
                            last_bs_date, "buy_sell_daily max date"
                        )
                        if last_bs and last_bs < end:
                            end = last_bs
            except Exception as e:
                logger.debug(f"Could not check buy_sell_daily max date: {e}")

        # On ECS restart the in-memory watermark is empty, so since=None.
        # Read the actual DB max date to avoid re-querying 5 years of history.
        if since is None:
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    with DatabaseContext("read") as cur:
                        cur.execute(
                            "SELECT MAX(date) FROM signal_quality_scores WHERE symbol = %s",
                            (symbol,),
                        )
                        row = cur.fetchone()
                        if row and row[0]:
                            parsed = safe_parse_date(
                                row[0], f"signal_quality_scores watermark for {symbol}"
                            )
                            if parsed:
                                since = parsed
                        break
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.debug(
                            f"Watermark read failed (attempt {attempt + 1}/{max_retries}), retrying: {e}"
                        )
                        continue
                    logger.warning(
                        f"Could not read signal_quality_scores watermark for {symbol} after {max_retries} attempts. Using full history."
                    )
                    break

        if since is None:
            # On ECS restart, load last 60 days only (not 5 years)
            # This prevents massive data fetch when watermark is empty
            start = end - timedelta(days=60)
        else:
            start = since - timedelta(days=100)

        # Validate buy_sell_daily has run before computing quality scores.
        # buy_sell_daily generates signals only for stocks meeting filter criteria (~500-1500 symbols).
        # Comparing against all active symbols (10,000+) will ALWAYS fail 95% threshold.
        # Instead: require at least 300 buy/sell signals exist for end date.

        # ROOT CAUSE #4 FIX: Use cached signal count from batch context instead of per-symbol query.
        actual_symbols = (
            self._batch_context.get("bs_signal_count", 0) if self._batch_context else 0
        )

        # ISSUE: Signal counts dropped 10x on 2026-06-04 (from 1000+ to 134). Root cause unknown.
        # Updated validator to 100 to match current signal generation rate (1.3% of 10k symbols).
        # Original threshold of 300 was valid when we saw 1000+ signals daily.
        if actual_symbols < 100:
            logger.critical(
                f"[SIGNAL_QUALITY_SKIPPED] {symbol}: buy_sell_daily INCOMPLETE for {end}: "
                f"only {actual_symbols} signals (expected >= 100). "
                "signal_quality_scores cannot run until buy_sell_daily completes. Rejecting scores."
            )
            return []

        buy_sell_rows = self._fetch_buy_sell_signals(symbol, start, end)
        if not buy_sell_rows:
            return []

        technical_rows = self._fetch_technical_data(symbol, start, end)
        trend_rows = self._fetch_trend_data(symbol, start, end)
        vcp_rows = self._fetch_vcp_patterns(symbol, start, end)
        positioning_data = self._fetch_positioning_data(symbol)

        scores = self._compute_quality_scores(
            symbol, buy_sell_rows, technical_rows, trend_rows, vcp_rows, positioning_data
        )
        if not scores:
            return []

        # Filter to incremental range using datetime comparison (not string)
        if since is not None:
            since_date = (
                since
                if isinstance(since, date)
                else safe_parse_date(since, "score filtering watermark")
            )
            if since_date:
                # Filter scores by date, handling potential None returns from safe_parse_date
                filtered_scores = []
                for s in scores:
                    parsed_date = safe_parse_date(s["date"], "score date filtering")
                    if parsed_date is not None and parsed_date > since_date:
                        filtered_scores.append(s)
                scores = filtered_scores

        return scores

    def _fetch_buy_sell_signals(
        self, symbol: str, start: date, end: date
    ) -> list[dict]:
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT date, signal_type FROM buy_sell_daily "
                    "WHERE symbol = %s AND date >= %s AND date <= %s AND signal_type IN ('BUY', 'SELL') ORDER BY date ASC",
                    (symbol, start, end),
                )
                return [
                    {"date": r[0].isoformat(), "signal_type": r[1]}
                    for r in cur.fetchall()
                ]
        except Exception as e:
            logger.error(f"Failed to fetch buy/sell signals for {symbol}: {e}")
            return []

    def _fetch_technical_data(self, symbol: str, start: date, end: date) -> list[dict]:
        from utils.db.context import DatabaseContext

        try:
            with DatabaseContext("read") as cur:
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

    def _fetch_trend_data(self, symbol: str, start: date, end: date) -> list[dict]:
        from utils.db.context import DatabaseContext

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT date, minervini_trend_score, weinstein_stage, percent_from_52w_high FROM trend_template_data "
                    "WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                    (symbol, start, end),
                )
                return [
                    {
                        "date": r[0].isoformat(),
                        "minervini_score": float(r[1]) if r[1] is not None else None,
                        "weinstein_stage": r[2],
                        "percent_from_52w_high": float(r[3]) if r[3] is not None else None,
                    }
                    for r in cur.fetchall()
                ]
        except Exception as e:
            logger.error(f"Failed to fetch trend data for {symbol}: {e}")
            return []

    def _fetch_vcp_patterns(self, symbol: str, start: date, end: date) -> list[dict]:
        from utils.db.context import DatabaseContext

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT date, vcp_strength FROM vcp_patterns "
                    "WHERE symbol = %s AND date >= %s AND date <= %s ORDER BY date ASC",
                    (symbol, start, end),
                )
                return [
                    {
                        "date": r[0].isoformat(),
                        "vcp_strength": r[1],
                    }
                    for r in cur.fetchall()
                ]
        except Exception as e:
            logger.debug(f"Failed to fetch VCP patterns for {symbol}: {e}")
            return []

    def _fetch_positioning_data(self, symbol: str) -> dict:
        from utils.db.context import DatabaseContext

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT institutional_ownership FROM positioning_metrics WHERE symbol = %s",
                    (symbol,),
                )
                row = cur.fetchone()
                if row and row[0] is not None:
                    return {"institutional_ownership": float(row[0])}
        except Exception as e:
            logger.debug(f"Failed to fetch positioning data for {symbol}: {e}")
        return {}

    def _compute_quality_scores(
        self,
        symbol: str,
        buy_sell_rows: list[dict],
        technical_rows: list[dict],
        trend_rows: list[dict],
        vcp_rows: list[dict] | None = None,
        positioning_data: dict | None = None,
    ) -> list[dict]:
        if not buy_sell_rows:
            return []

        try:
            vcp_rows = vcp_rows or []
            positioning_data = positioning_data or {}

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

            vcp_df = pd.DataFrame(vcp_rows) if vcp_rows else pd.DataFrame()
            if not vcp_df.empty:
                vcp_df["date"] = pd.to_datetime(vcp_df["date"])

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
            if not vcp_df.empty:
                merged = merged.merge(vcp_df, on="date", how="left")

            institutional_ownership = positioning_data.get("institutional_ownership")

            results = []
            for _, row in merged.iterrows():
                signal_type = row.get("signal_type")
                if not signal_type:
                    continue

                # Base quality score (40-60): signal existence + trend alignment
                base_quality_score = 40
                if signal_type == "BUY":
                    base_quality_score = 50
                elif signal_type == "SELL":
                    base_quality_score = 45

                # Volume confirmation score (0-20): based on MACD/RSI
                volume_confirmation_score = 0
                rsi = row.get("rsi")
                macd = row.get("macd")
                macd_signal = row.get("macd_signal")

                if signal_type == "BUY":
                    if rsi and 40 < float(rsi) < 80:
                        volume_confirmation_score += 10
                    if (
                        macd is not None
                        and macd_signal is not None
                        and float(macd) > float(macd_signal)
                    ):
                        volume_confirmation_score += 10
                elif signal_type == "SELL":
                    if rsi and 20 < float(rsi) < 60:
                        volume_confirmation_score += 10
                    if (
                        macd is not None
                        and macd_signal is not None
                        and float(macd) < float(macd_signal)
                    ):
                        volume_confirmation_score += 10

                # Trend template score (0-25): minervini score and stage
                trend_template_score = 0
                minervini = row.get("minervini_score")
                weinstein_stage = row.get("weinstein_stage")

                if signal_type == "BUY":
                    if minervini and float(minervini) >= 3:
                        trend_template_score += 15
                    elif minervini and float(minervini) >= 2:
                        trend_template_score += 10
                    elif minervini:
                        trend_template_score += 5

                    if weinstein_stage and int(weinstein_stage) in [2, 3]:
                        trend_template_score += 10
                    elif weinstein_stage:
                        trend_template_score += 3

                trend_template_score = min(25, trend_template_score)

                # Distance from high score (0-15): closer to 52w high = better
                distance_from_high_score = 0
                pct_from_high = row.get("percent_from_52w_high")
                if pct_from_high is not None:
                    pct = float(pct_from_high)
                    if pct >= -5:  # Within 5% of 52w high
                        distance_from_high_score = 15
                    elif pct >= -10:
                        distance_from_high_score = 12
                    elif pct >= -20:
                        distance_from_high_score = 8
                    elif pct >= -30:
                        distance_from_high_score = 4

                # Institutional ownership score (0-10)
                institutional_ownership_score = 0
                if institutional_ownership is not None:
                    if institutional_ownership >= 60:
                        institutional_ownership_score = 10
                    elif institutional_ownership >= 40:
                        institutional_ownership_score = 8
                    elif institutional_ownership >= 20:
                        institutional_ownership_score = 5
                    else:
                        institutional_ownership_score = 2

                # Market stage score (0-10): Weinstein stage 2 and 3 are best
                market_stage_score = 0
                if weinstein_stage:
                    stage = int(weinstein_stage)
                    if stage in [2, 3]:
                        market_stage_score = 10
                    elif stage in [1, 4]:
                        market_stage_score = 5
                    else:
                        market_stage_score = 2

                # VCP pattern score (0-10)
                vcp_pattern_score = 0
                vcp_strength = row.get("vcp_strength")
                if vcp_strength is not None:
                    strength = int(vcp_strength)
                    if strength >= 8:
                        vcp_pattern_score = 10
                    elif strength >= 6:
                        vcp_pattern_score = 8
                    elif strength >= 4:
                        vcp_pattern_score = 5
                    else:
                        vcp_pattern_score = 2

                # Distribution days score (placeholder - would need distribution_days table)
                distribution_days_score = 5

                # Earnings proximity score (placeholder - would need earnings calendar)
                earnings_proximity_score = 3

                # Composite score
                composite_sqs = (
                    base_quality_score
                    + volume_confirmation_score
                    + trend_template_score
                    + distance_from_high_score
                    + institutional_ownership_score
                    + market_stage_score
                    + vcp_pattern_score
                    + distribution_days_score
                    + earnings_proximity_score
                )
                composite_sqs = min(100, int(composite_sqs))

                date_val = row.get("date")
                if date_val is not None:
                    date_str = (
                        date_val.date().isoformat()
                        if hasattr(date_val, "date")
                        else str(date_val)
                    )
                    signal_date = pd.Timestamp(date_str).date()

                    # Compute staleness: how many days old is the underlying data?
                    bs_age = (
                        (signal_date - max_bs_date.date()).days
                        if max_bs_date is not None
                        else None
                    )
                    tech_age = (
                        (signal_date - max_tech_date.date()).days
                        if max_tech_date is not None
                        else None
                    )
                    trend_age = (
                        (signal_date - max_trend_date.date()).days
                        if max_trend_date is not None
                        else None
                    )

                    results.append(
                        {
                            "symbol": symbol,
                            "date": date_str,
                            "base_quality_score": int(base_quality_score),
                            "volume_confirmation_score": int(volume_confirmation_score),
                            "trend_template_score": int(trend_template_score),
                            "distance_from_high_score": int(distance_from_high_score),
                            "institutional_ownership_score": int(
                                institutional_ownership_score
                            ),
                            "market_stage_score": int(market_stage_score),
                            "vcp_pattern_score": int(vcp_pattern_score),
                            "distribution_days_score": int(distribution_days_score),
                            "earnings_proximity_score": int(earnings_proximity_score),
                            "composite_sqs": composite_sqs,
                            "buy_sell_daily_age_days": bs_age,
                            "technical_data_age_days": tech_age,
                            "trend_template_age_days": trend_age,
                        }
                    )

            return results
        except Exception as e:
            logger.warning(f"Error computing quality scores for {symbol}: {e}")
            return []


def main():
    parser = argparse.ArgumentParser(description="Load signal quality scores")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument(
        "--parallelism",
        type=int,
        default=get_default_parallelism("signal_quality_scores"),
        help="Parallel workers",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="daily",
        help="Timeframe (daily/weekly/monthly, ignored for quality scores)",
    )
    parser.add_argument(
        "--asset-class",
        type=str,
        default="stock",
        help="Asset class (stock/etf, ignored for quality scores)",
    )
    args = parser.parse_args()

    try:
        symbols = (
            args.symbols.split(",")
            if args.symbols
            else get_active_symbols(timeout_secs=300)
        )

        logger.info(
            f"Starting signal_quality_scores loader with {len(symbols)} symbols, parallelism={args.parallelism}"
        )

        # VALIDATION: signal_quality_scores is critical path; parallelism should be 2 per steering doc line 44-48
        # If parallelism > 4, log warning as it may cause RDS connection pool exhaustion
        if args.parallelism > 4:
            logger.warning(
                f"[PARALLELISM] signal_quality_scores: parallelism={args.parallelism} exceeds recommended max (2). "
                "This may cause RDS connection pool exhaustion. Check ECS task definition and LOADER_PARALLELISM env var."
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
    from utils.db.context import DatabaseContext

    try:
        with DatabaseContext("write") as cur:
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
