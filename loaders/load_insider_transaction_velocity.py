#!/usr/bin/env python3
"""Insider Transaction Velocity Loader - SEC Form 3/4/5 via official bulk data sets.

GOVERNANCE: No yfinance fallback. Only official SEC sources or explicit
data_unavailable.

Uses utils.external.sec_form345_transaction_velocity.Form345TransactionVelocityAggregator,
which extracts BUY/SELL transaction counts and volumes from SEC's official
"Insider Transactions Data Sets" quarterly ZIPs.

Computes insider confidence score based on buy/sell ratio and transaction
velocity metrics (30-day and 90-day rolling windows).

Run:
    python3 loaders/load_insider_transaction_velocity.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_form345_transaction_velocity_cached import CachedForm345Aggregator
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class InsiderTransactionVelocityLoader(OptimalLoader):
    """Load insider transaction velocity from SEC's official Form 3/4/5 bulk data sets."""

    table_name = "insider_transaction_velocity"
    primary_key = ("symbol", "measurement_date")
    watermark_field = "measurement_date"
    exclude_etfs_from_symbols = True
    max_fail_rate = 70.0  # SEC bulk data schema changes; allow partial data writes

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        # BUGFIX 2026-07-27: was 300s, then 900s - both still too short. Two live
        # 12-quarter downloads measured ~900s and ~1013s end to end (real-world
        # variance, not a fixed cost) - the first bump to 900s still left the first
        # symbol queued each run (e.g. AAPL) timed out with Form345_download_timeout
        # on the slower of the two runs. There's no benefit to giving up early here:
        # every symbol in this process shares the same download, so a timed-out
        # symbol doesn't unblock anything else - it just guarantees lost data. The
        # only real ceiling is this loader's 1200s ECS task timeout (terraform/
        # modules/loaders/main.tf) - waiting right up to that (minus a small buffer
        # for the first symbol's own fetch+write once the download completes) is
        # strictly better than giving up sooner.
        self._aggregator = CachedForm345Aggregator(lookback_quarters=12, timeout_seconds=1080)

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        measurement_date = since or datetime.now(EASTERN_TZ).date()

        try:
            # BUGFIX 2026-07-27: was hardcoded False under the assumption a later
            # run would find the download "cached" - but CachedForm345Aggregator only
            # caches in-memory for the life of one process (its CACHE_DIR constant is
            # declared but never written/read anywhere), so every scheduled run starts
            # a fresh 2-5 min background download and any symbol processed before it
            # finishes got data_unavailable="Form345_download_in_progress" forever.
            # Confirmed live: insider_transaction_velocity had never once stored a real
            # row across this loader's whole life. wait_for_download=True blocks only
            # the first symbol in a run (up to timeout_seconds); _build_complete is
            # already set for every symbol after that, so this costs nothing beyond
            # the one download this loader always needed to do anyway.
            metrics = self._aggregator.get_velocity_metrics(symbol, measurement_date, wait_for_download=True)
        except (TimeoutError, Exception) as e:
            # SEC bulk data downloads can be slow; fail gracefully
            logger.debug(f"[{symbol}] Insider velocity fetch error: {type(e).__name__}: {e}")
            return self._unavailable_record(symbol, measurement_date, "sec_form345_bulk_data_unavailable")

        if metrics.data_unavailable:
            return self._unavailable_record(symbol, measurement_date, metrics.reason or "no_data")

        confidence_30d = self._compute_confidence_score(metrics.buy_transactions_30d, metrics.sell_transactions_30d)
        confidence_90d = self._compute_confidence_score(metrics.buy_transactions_90d, metrics.sell_transactions_90d)
        insider_confidence_score = int(0.6 * confidence_90d + 0.4 * confidence_30d)

        record = {
            "symbol": symbol,
            "measurement_date": measurement_date,
            "buy_transactions_30d": metrics.buy_transactions_30d,
            "sell_transactions_30d": metrics.sell_transactions_30d,
            "net_buy_transactions_30d": metrics.buy_transactions_30d - metrics.sell_transactions_30d,
            "buy_transactions_90d": metrics.buy_transactions_90d,
            "sell_transactions_90d": metrics.sell_transactions_90d,
            "net_buy_transactions_90d": metrics.buy_transactions_90d - metrics.sell_transactions_90d,
            "total_buy_shares_30d": metrics.total_buy_shares_30d,
            "total_sell_shares_30d": metrics.total_sell_shares_30d,
            "net_buy_shares_30d": metrics.total_buy_shares_30d - metrics.total_sell_shares_30d,
            "total_buy_shares_90d": metrics.total_buy_shares_90d,
            "total_sell_shares_90d": metrics.total_sell_shares_90d,
            "net_buy_shares_90d": metrics.total_buy_shares_90d - metrics.total_sell_shares_90d,
            "buy_sell_ratio_30d": (
                round(metrics.buy_transactions_30d / metrics.sell_transactions_30d, 2)
                if metrics.sell_transactions_30d > 0
                else None
            ),
            "buy_sell_ratio_90d": (
                round(metrics.buy_transactions_90d / metrics.sell_transactions_90d, 2)
                if metrics.sell_transactions_90d > 0
                else None
            ),
            "insider_confidence_score": insider_confidence_score,
            "data_unavailable": False,
        }

        return [record]

    @staticmethod
    def _compute_confidence_score(buy_count: int, sell_count: int) -> int:
        total = buy_count + sell_count
        if total == 0:
            return 50
        buy_ratio = buy_count / total
        confidence = int(buy_ratio * 100)
        return max(0, min(100, confidence))

    @staticmethod
    def _unavailable_record(symbol: str, measurement_date: date, reason: str) -> list[dict[str, Any]]:
        # All value fields NULL (not 0/50) to match the data_unavailable=True flag: a
        # consumer that reads the flag AND the values without checking both would previously
        # see a plausible-looking "0 transactions, 50 confidence" row indistinguishable from a
        # genuinely quiet insider-activity period, instead of no data at all.
        return [
            {
                "symbol": symbol,
                "measurement_date": measurement_date,
                "data_unavailable": True,
                "data_unavailable_reason": reason,
                "buy_transactions_30d": None,
                "sell_transactions_30d": None,
                "net_buy_transactions_30d": None,
                "buy_transactions_90d": None,
                "sell_transactions_90d": None,
                "net_buy_transactions_90d": None,
                "total_buy_shares_30d": None,
                "total_sell_shares_30d": None,
                "net_buy_shares_30d": None,
                "total_buy_shares_90d": None,
                "total_sell_shares_90d": None,
                "net_buy_shares_90d": None,
                "buy_sell_ratio_30d": None,
                "buy_sell_ratio_90d": None,
                "insider_confidence_score": None,
            }
        ]


def main() -> int:
    """Entry point for load_insider_transaction_velocity.py."""
    try:
        return run_loader(InsiderTransactionVelocityLoader)
    except Exception as e:
        logger.error(f"[INSIDER_VELOCITY FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
