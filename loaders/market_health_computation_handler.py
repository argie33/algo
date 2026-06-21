#!/usr/bin/env python3
"""Market health metrics computation handler extracted from MarketHealthDailyLoader.

Handles phased execution: date determination, price fetch, metrics computation, enrichment.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any, cast

import psycopg2

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ


logger = logging.getLogger(__name__)


class MarketHealthComputationHandler:
    """Handles multi-phase market health computation and data enrichment."""

    def __init__(self, loader: Any) -> None:
        """Initialize with reference to MarketHealthDailyLoader."""
        self.loader = loader

    def run(self, symbol: str = "SPY", since: date | None = None) -> list[dict]:
        """Execute phased market health computation with enrichment.

        Returns list of market health metrics dicts with indicators + enrichment.
        """
        start, end, since = self._phase_determine_dates(since)
        rows = self._phase_fetch_prices(symbol, start, end)
        health_metrics = self._phase_compute_metrics(rows)
        self._phase_enrich_breadth(health_metrics, start, end)
        self._phase_enrich_vix(health_metrics, start, end)
        self._phase_enrich_put_call(health_metrics, end)
        self._phase_enrich_yield_curve(health_metrics, start, end)

        if since is not None:
            since_str = since.isoformat()
            before = len(health_metrics)
            health_metrics = [m for m in health_metrics if m["date"] >= since_str]
            logger.info(f"Filtered: {before} → {len(health_metrics)} (dates >= {since_str})")

        return health_metrics

    def _phase_determine_dates(self, since: date | None) -> tuple[date, date, date | None]:
        """Determine date range and read watermark from database."""
        now_et = datetime.now(EASTERN_TZ).astimezone(EASTERN_TZ)
        end = now_et.date()

        from algo.infrastructure import MarketCalendar

        while end > date(2020, 1, 1) and not MarketCalendar.is_trading_day(end):
            end = end - timedelta(days=1)

        if since is None:
            try:
                with DatabaseContext("read") as cur:
                    cur.execute("SELECT MAX(date), COUNT(*) FROM market_health_daily")
                    row = cur.fetchone()
                    row_count = row[1] if row else 0
                    if row and row[0]:
                        if row_count < 5:
                            logger.info(f"market_health_daily has {row_count} rows (< 5), backfilling")
                            since = None
                        else:
                            since = row[0] if isinstance(row[0], date) else date.fromisoformat(str(row[0]))
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(f"[MARKET_HEALTH] Failed to read watermark: {e}") from None

        start = end - timedelta(days=5 * 365) if since is None else since - timedelta(days=100)
        return start, end, since

    def _phase_fetch_prices(self, symbol: str, start: date, end: date) -> list[dict]:
        """Fetch SPY price data."""
        rows = self.loader._fetch_price_daily(symbol, start, end)
        if not rows:
            raise RuntimeError(f"[MARKET_HEALTH] No SPY price data for {start} to {end}")
        return cast(list[dict], rows)

    def _phase_compute_metrics(self, rows: list[dict]) -> list[dict]:
        """Compute market health metrics from prices."""
        metrics = self.loader._compute_market_health(rows)
        if not metrics:
            raise RuntimeError(f"[MARKET_HEALTH] Failed to compute metrics from {len(rows)} rows")
        logger.info(
            f"Computed {len(metrics)} metrics from {len(rows)} rows: {metrics[0]['date']} to {metrics[-1]['date']}"
        )
        return cast(list[dict], metrics)

    def _phase_enrich_breadth(self, metrics: list[dict], start: date, end: date) -> None:
        """Merge breadth data (A/D ratio, new highs/lows)."""
        breadth = self.loader._fetch_breadth_data(start, end)
        for m in metrics:
            b = breadth.get(m["date"])
            if b:
                m["advance_decline_ratio"] = b.get("advance_decline_ratio")
                m["new_highs_count"] = b.get("new_highs_count")
                m["new_lows_count"] = b.get("new_lows_count")
            else:
                m["advance_decline_ratio"] = m["new_highs_count"] = m["new_lows_count"] = None

    def _phase_enrich_vix(self, metrics: list[dict], start: date, end: date) -> None:
        """Merge VIX data (OPTIONAL)."""
        from utils.infrastructure.circuit_breaker import DataImportance

        vix = self.loader._vix_breaker.execute(
            fetch_func=lambda: self.loader._fetch_vix_data(start, end),
            importance=DataImportance.OPTIONAL,
            fallback_value={},
        )
        matched = 0
        for m in metrics:
            m["vix_level"] = vix.get(m["date"])
            if m["vix_level"] is not None:
                matched += 1
        if matched > 0:
            logger.info(f"VIX enrichment: matched {matched}/{len(metrics)} dates")

    def _phase_enrich_put_call(self, metrics: list[dict], end: date) -> None:
        """Merge put/call ratio (OPTIONAL)."""
        from utils.infrastructure.circuit_breaker import DataImportance

        pc = self.loader._put_call_breaker.execute(
            fetch_func=lambda: self.loader._fetch_put_call_ratio(end),
            importance=DataImportance.OPTIONAL,
            fallback_value=None,
        )
        end_str = end.isoformat()
        for m in metrics:
            m["put_call_ratio"] = pc if m["date"] == end_str else None
        if pc is not None:
            logger.info(f"Put/call ratio: {pc:.3f}")

    def _phase_enrich_yield_curve(self, metrics: list[dict], start: date, end: date) -> None:
        """Merge yield curve slope (OPTIONAL)."""
        from utils.infrastructure.circuit_breaker import DataImportance

        yc = self.loader._yield_curve_breaker.execute(
            fetch_func=lambda: self.loader._fetch_yield_curve_data(start, end),
            importance=DataImportance.OPTIONAL,
            fallback_value={},
        )
        matched = 0
        for m in metrics:
            m["yield_curve_slope"] = yc.get(m["date"])
            if m["yield_curve_slope"] is not None:
                matched += 1
        if matched > 0:
            logger.info(f"Yield curve enrichment: matched {matched}/{len(metrics)} dates")
