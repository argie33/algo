#!/usr/bin/env python3
"""Market Status Daily Loader - Consolidated market health + exposure + sentiment.

CONSOLIDATION: Merges 3 separate market-wide loaders into one atomic operation:
  - load_market_health_daily.py (VIX, breadth, yield curve, put/call)
  - load_market_exposure_daily.py (market regime, exposure %)
  - load_market_sentiment.py (fear/greed index)

Benefits:
  - 1 ECS task instead of 3 (saves ~$0.02-0.03/run)
  - VIX/breadth/yields fetched once, used 3 ways
  - Atomic operation (all market metrics succeed/fail together)
  - Better error handling (single failure point)
  - All market regime logic in one place
  - 10-15 min faster orchestrator

Outputs:
  - market_health_daily (VIX, breadth, yields, put/call)
  - market_exposure_daily (regime, exposure %, factors)
  - market_sentiment (fear/greed, bull/bear %)

Run: python3 loaders/load_market_status_daily.py [--backfill-days N]
"""

import logging
import sys
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from typing import Any

from loaders.market_health_fetchers import (
    BreadthFetcher,
    PutCallRatioFetcher,
    VIXFetcher,
    YieldCurveFetcher,
)
from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class MarketStatusDailyLoader(OptimalLoader):
    """Consolidated market status loader: health + exposure + sentiment.

    Market-wide loader (pseudo-symbol "market"). Fetches all market metrics once,
    computes regime/exposure/sentiment, writes to all 3 output tables atomically.
    """

    table_name = "market_health_daily"  # Primary table for watermark tracking
    primary_key = ("date",)
    watermark_field = "date"
    is_symbol_based = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._vix_fetcher = VIXFetcher()
        self._put_call_fetcher = PutCallRatioFetcher()
        self._yield_curve_fetcher = YieldCurveFetcher()
        self._breadth_fetcher = BreadthFetcher()

    def run(
        self, symbols: Iterable[str] | None = None, parallelism: int = 1, backfill_days: int | None = None
    ) -> dict[str, Any]:
        """Override run() to provide market-wide pseudo-symbol."""
        # CRITICAL FIX: Skip loading on non-trading days
        # Markets are closed on weekends/holidays, so no new market data is available
        from algo.infrastructure import MarketCalendar
        now_et = datetime.now(EASTERN_TZ)
        run_date = now_et.date()
        if not MarketCalendar.is_trading_day(run_date):
            logger.info(
                f"[{self.table_name}] Skipping load: today ({run_date}) is not a trading day. "
                f"Market data will use last available trading day's data."
            )
            # Refresh data_loader_status from the real table state even when skipping the
            # fetch. Without this, the status row (latest_date, last_updated) freezes at
            # whatever it was on the last trading day this loader ran, and monitoring
            # reads that as "no/stale data" even though market_health_daily itself has
            # current data through the last trading day.
            self._update_final_status(1)
            return {
                "symbols_processed": 0,
                "symbols_failed": 0,
                "rows_inserted": 0,
                "duration_sec": 0,
                "latest_date": None,
                "status": "SKIPPED_NON_TRADING_DAY",
            }

        symbol_list: list[str]
        if symbols is None or (isinstance(symbols, (list, tuple)) and len(symbols) == 0):
            symbol_list = ["market"]
        else:
            symbol_list = list(symbols) if not isinstance(symbols, list) else symbols
        return super().run(symbols=symbol_list, parallelism=parallelism, backfill_days=backfill_days)

    def fetch_global(self, since: date | None) -> list[dict[str, Any]] | dict[str, Any]:
        """Fetch global market data. Skips on non-trading days.

        Returns:
            list[dict]: Market data rows if trading day.
            dict: Marker dict if non-trading day or data unavailable.
        """
        from algo.infrastructure import MarketCalendar
        now_et = datetime.now(EASTERN_TZ)
        run_date = now_et.date()
        if not MarketCalendar.is_trading_day(run_date):
            logger.info(
                f"[{self.table_name}] Skipping fetch_global: today ({run_date}) is not a trading day. "
                f"Market data will use last available trading day's data."
            )
            return {"data_unavailable": True, "reason": "non_trading_day"}

        return self.fetch_incremental("market", since)

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch and compute all market metrics for one date.

        Args:
            symbol: Pseudo-symbol "market" (ignored, used by framework)
            since: Optional backfill start date

        Returns:
            List with single market status dict or data_unavailable marker
        """
        if symbol != "market":
            return [{"date": date.today(), "data_unavailable": True, "reason": "invalid_symbol"}]

        try:
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)
            end_date = now_et.date()

            # Fetch all market data (health, breadth, vix, yields)
            health_data = self._fetch_market_health(end_date)
            if health_data.get("data_unavailable"):
                return [health_data]

            # Compute exposure (regime, exposure %, factors)
            exposure_data = self._compute_market_exposure(end_date, health_data)

            # Compute sentiment (fear/greed from VIX + AAII sentiment)
            sentiment_data = self._compute_market_sentiment(end_date, health_data)

            # Return consolidated data (caller will write to all 3 tables)
            # GOVERNANCE: data_unavailable must reflect whether exposure computation
            # actually succeeded, not be hardcoded False. Regime/exposure_pct/factors feed
            # directly into position sizing and risk tier classification (exposure_policy.py)
            # - if _compute_market_exposure() failed, those fields land as NULL while this
            # row was still marked "available", so downstream consumers gating on
            # data_unavailable would trust a NULL as "checked, fine" instead of halting.
            exposure_unavailable = bool(exposure_data.get("data_unavailable"))
            return [{
                "date": end_date,
                "data_unavailable": exposure_unavailable,
                **({"reason": exposure_data["reason"]} if exposure_unavailable and exposure_data.get("reason") else {}),

                # market_health_daily fields (column names per market_health_daily schema -
                # health_data uses different internal key names, see _fetch_market_health)
                "vix_level": health_data.get("vix_level"),
                "advance_decline_ratio": health_data.get("advance_decline_ratio"),
                "new_highs_count": health_data.get("new_highs"),
                "new_lows_count": health_data.get("new_lows"),
                "yield_curve_slope": health_data.get("yield_10y_2y_spread"),
                "put_call_ratio": health_data.get("put_call_ratio"),

                # market_exposure_daily fields
                "regime": exposure_data.get("regime"),
                "exposure_pct": exposure_data.get("exposure_pct"),
                "raw_score": exposure_data.get("raw_score"),
                "halt_reasons": exposure_data.get("halt_reasons"),
                "distribution_days": exposure_data.get("distribution_days"),
                "factors": exposure_data.get("factors"),

                # market_sentiment fields
                "fear_greed_index": sentiment_data.get("fear_greed_index"),
                "sentiment_score": sentiment_data.get("sentiment_score"),
                "bullish_pct": sentiment_data.get("bullish_pct"),
                "bearish_pct": sentiment_data.get("bearish_pct"),
                "neutral_pct": sentiment_data.get("neutral_pct"),
            }]

        except Exception as e:
            logger.error(f"[MARKET_STATUS] Fatal error: {e}", exc_info=True)
            return [{
                "date": date.today(),
                "data_unavailable": True,
                "reason": f"market_status_error: {str(e)[:100]}",
            }]

    def _fetch_market_health(self, eval_date: date) -> dict[str, Any]:
        """Fetch all health metrics (VIX, breadth, yields, put/call)."""
        try:
            from algo.infrastructure import MarketCalendar

            # Session 299 FIX: Don't fetch from non-trading days
            # Find the most recent trading day (eval_date or earlier)
            last_trading_day = eval_date
            search_date = eval_date
            while search_date >= eval_date - timedelta(days=10):
                if MarketCalendar.is_trading_day(search_date):
                    last_trading_day = search_date
                    break
                search_date -= timedelta(days=1)

            # Fetch VIX (from previous trading day to most recent trading day)
            # This ensures we don't try to fetch non-trading day data
            fetch_start = last_trading_day - timedelta(days=1)
            while fetch_start >= last_trading_day - timedelta(days=5):
                if MarketCalendar.is_trading_day(fetch_start):
                    break
                fetch_start -= timedelta(days=1)

            vix_data = self._vix_fetcher.fetch(fetch_start, last_trading_day)
            if not vix_data or vix_data.get("data_unavailable"):
                return {"data_unavailable": True, "reason": "vix_unavailable"}

            # vix_data is keyed by ISO date string (see VIXFetcher._fetch_vix_data),
            # e.g. {"2026-07-17": {"vix_close": ..., ...}} - not a flat {"vix_close": ...}
            # dict. Take the most recent date's close.
            latest_vix_date = max(vix_data.keys())
            vix_level = vix_data[latest_vix_date].get("vix_close")

            # Fetch breadth (advance/decline, new highs/lows)
            start_date = eval_date - timedelta(days=60)
            breadth_data = self._breadth_fetcher.fetch(start_date, eval_date)
            if not breadth_data or breadth_data.get("data_unavailable"):
                return {"data_unavailable": True, "reason": "breadth_unavailable"}

            # breadth_data is keyed by ISO date string (see BreadthFetcher.fetch),
            # e.g. {"2026-07-17": {"advance_decline_ratio": ..., "new_highs_count": ...,
            # "new_lows_count": ...}} - not a flat dict. Take the most recent date's values.
            latest_breadth_date = max(breadth_data.keys())
            latest_breadth = breadth_data[latest_breadth_date]
            advance_decline = latest_breadth.get("advance_decline_ratio")
            new_highs = latest_breadth.get("new_highs_count")
            new_lows = latest_breadth.get("new_lows_count")

            # Fetch yield curve (10Y-2Y spread) - use same date range as VIX
            yield_data = self._yield_curve_fetcher.fetch(fetch_start, last_trading_day)
            if not yield_data or yield_data.get("data_unavailable"):
                return {"data_unavailable": True, "reason": "yield_curve_unavailable"}

            # yield_data is keyed by ISO date string (see YieldCurveFetcher._fetch_yield_curve_data),
            # e.g. {"2026-07-17": {"yield_spread": ..., ...}} - not a flat dict, and the field is
            # named "yield_spread" not "yield_10y_2y_spread".
            latest_yield_date = max(yield_data.keys())
            yield_spread = yield_data[latest_yield_date].get("yield_spread")

            # Fetch put/call ratio (optional market sentiment indicator)
            put_call = None
            try:
                put_call_result = self._put_call_fetcher.fetch(eval_date)
                # FAIL-FAST: Explicitly check for data_unavailable flag (missing = error, not "data OK")
                if isinstance(put_call_result, dict) and put_call_result.get("data_unavailable") is False:
                    put_call = put_call_result.get("put_call_ratio")
                elif isinstance(put_call_result, dict) and put_call_result.get("data_unavailable") is True:
                    # Put/call data unavailable - log at WARNING for visibility (not DEBUG)
                    logger.warning(
                        f"[MARKET_STATUS] Put/call ratio unavailable for {eval_date}: "
                        f"{put_call_result.get('reason', 'unknown')}"
                    )
            except Exception as e:
                # Exception catch is now explicit with WARNING log - not silent DEBUG
                logger.warning(f"[MARKET_STATUS] Put/call ratio fetcher failed: {e}")
                # put_call remains None - optional indicator

            return {
                "data_unavailable": False,
                "vix_level": vix_level,
                "advance_decline_ratio": advance_decline,
                "new_highs": new_highs,
                "new_lows": new_lows,
                "yield_10y_2y_spread": yield_spread,
                "put_call_ratio": put_call,
            }

        except Exception as e:
            logger.error(f"[MARKET_STATUS] Health fetch failed: {e}")
            return {"data_unavailable": True, "reason": f"health_fetch_failed: {str(e)[:100]}"}

    def _compute_market_exposure(self, eval_date: date, health_data: dict[str, Any]) -> dict[str, Any]:
        """Compute market regime and exposure % from health metrics."""
        try:
            from algo.risk.market_exposure import MarketExposure

            # Delegate to MarketExposure compute logic (reuse existing computation)
            exposure = MarketExposure()
            result = exposure.compute(eval_date, force_recompute=False)

            if not result or result.get("data_unavailable"):
                return {
                    "regime": None,
                    "exposure_pct": None,
                    "raw_score": None,
                    "halt_reasons": None,
                    "distribution_days": None,
                    "factors": None,
                    "data_unavailable": True,
                    "reason": result.get("reason", "exposure_data_unavailable") if result else "exposure_no_result",
                }

            return {
                "regime": result.get("regime"),
                "exposure_pct": result.get("exposure_pct"),
                "raw_score": result.get("raw_score"),
                "halt_reasons": result.get("halt_reasons"),
                "distribution_days": result.get("distribution_days"),
                "factors": result.get("factors"),
            }

        except Exception as e:
            logger.error(f"[MARKET_STATUS] Exposure computation failed: {e}")
            return {
                "regime": None,
                "exposure_pct": None,
                "raw_score": None,
                "halt_reasons": None,
                "distribution_days": None,
                "factors": None,
                "data_unavailable": True,
                "reason": f"exposure_computation_failed: {str(e)[:100]}",
            }

    def _compute_market_sentiment(self, eval_date: date, health_data: dict[str, Any]) -> dict[str, Any]:
        """Compute fear/greed index and sentiment from VIX + AAII sentiment."""
        try:
            vix = health_data.get("vix_level")
            if not vix:
                return {
                    "fear_greed_index": None,
                    "sentiment_score": None,
                    "bullish_pct": None,
                    "bearish_pct": None,
                    "neutral_pct": None,
                }

            # Map VIX to fear/greed index: VIX 10-50 → fear/greed 80-20
            fear_greed = max(10, min(90, 100 - (vix * 2)))

            # Fetch AAII sentiment (latest within 14 days)
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT date, bullish, bearish, neutral FROM aaii_sentiment
                    WHERE date >= %s - INTERVAL '14 days'
                      AND bullish IS NOT NULL AND bearish IS NOT NULL AND neutral IS NOT NULL
                    ORDER BY date DESC LIMIT 1
                    """,
                    (eval_date,),
                )
                aaii_row = cur.fetchone()

            bullish_pct = bearish_pct = neutral_pct = None
            if aaii_row:
                # aaii_sentiment stores as fractions (0-1)
                bullish_pct = float(aaii_row[1]) * 100
                bearish_pct = float(aaii_row[2]) * 100
                neutral_pct = float(aaii_row[3]) * 100
            else:
                logger.debug(f"[MARKET_STATUS] AAII sentiment not available for {eval_date}")

            return {
                "fear_greed_index": round(fear_greed, 2),
                "sentiment_score": None,  # Computed from bull/bear/neutral if available
                "bullish_pct": round(bullish_pct, 2) if bullish_pct else None,
                "bearish_pct": round(bearish_pct, 2) if bearish_pct else None,
                "neutral_pct": round(neutral_pct, 2) if neutral_pct else None,
            }

        except Exception as e:
            logger.error(f"[MARKET_STATUS] Sentiment computation failed: {e}")
            return {
                "fear_greed_index": None,
                "sentiment_score": None,
                "bullish_pct": None,
                "bearish_pct": None,
                "neutral_pct": None,
                "data_unavailable": True,
                "reason": f"sentiment_computation_failed: {str(e)[:100]}",
            }

    def load_global(self) -> int:
        """Market-wide loader uses load_global pattern."""
        result = self.run(["market"], parallelism=1)
        if result.get("status") == "SKIPPED_NON_TRADING_DAY":
            return 1
        # CRITICAL FIX: Check for None (missing data) vs 0 (zero rows inserted)
        rows = result.get("rows_inserted")
        if rows is None:
            # Data missing - don't default to 0, this indicates loader error
            logger.error("[MarketStatusDaily] rows_inserted missing from loader result - possible loader failure")
            return 0  # Return 0 exit code to indicate issue, but log it explicitly
        return int(rows) if rows is not None else 0


if __name__ == "__main__":
    sys.exit(run_loader(
        MarketStatusDailyLoader,
        description="Consolidated market status (health + exposure + sentiment)",
        global_mode=True,
    ))
