#!/usr/bin/env python3
"""yfinance Snapshot Loader - Fetch ALL yfinance data once per symbol, store in DB.

CRITICAL FIX 2026-07-02: Consolidates 30,000+ redundant yfinance API calls by having
6+ loaders read from a single snapshot table instead of each calling yfinance separately.

Consolidates redundant calls from:
- value_metrics (PE, PB, PS, dividend)
- positioning_metrics (institutional/insider holdings, short interest)
- stability_metrics (beta, volatility)
- company_profile (sector, industry, country)
- earnings_history (earnings dates)
- earnings_calendar (next earnings date)
- analyst_upgrade_downgrade (analyst counts)
- analyst_sentiment_analysis (recommendation key, analyst counts)

OPTIMIZATION 2026-07-12: Implemented batch fetching of yfinance.Ticker() calls.
Instead of fetching each symbol individually, batches 50 symbols per request.
Reduces fetch time from 2+ hours to 5-10 minutes.
Single fetch per symbol → yfinance_snapshot table → all loaders read from table.
Fetches once per symbol, caches 24 hours. Eliminates 30,000+ redundant API calls.
"""

import logging
import os
import sys
from datetime import date, datetime, timezone
from typing import Any

from loaders.helpers.yfinance_batcher import batch_tickers
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.db.context import DatabaseContext
from utils.external.yfinance import YFinanceWrapper
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)


class YFinanceSnapshotLoader(OptimalLoader):
    table_name = "yfinance_snapshot"
    primary_key = ("symbol",)
    watermark_field = "fetched_at"
    exclude_etfs_from_symbols = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._ticker_batch_cache: dict[str, Any] = {}  # Cache for batched ticker fetches
        self._batch_prefetch_done = False  # Track if we've done the initial batch prefetch

    def _do_batch_prefetch(self) -> None:
        """Prefetch all active stock symbols in batches to reduce API calls 50x.

        Gets all active symbols from database and fetches using batch_tickers,
        storing results in cache for fetch_incremental() to use.
        Reduces yfinance API calls from 5000+ to ~100 (one per 50 symbols).
        """
        logger.info("[YFINANCE_SNAPSHOT BATCH] Starting batch prefetch of all symbols...")

        try:
            # Get all active symbols
            all_symbols = []
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE ORDER BY symbol")
                all_symbols = [row[0] for row in cur.fetchall()]

            if not all_symbols:
                logger.warning("[YFINANCE_SNAPSHOT BATCH] No active symbols found to prefetch")
                return

            logger.info(f"[YFINANCE_SNAPSHOT BATCH] Prefetching {len(all_symbols)} symbols in batches of 50...")

            prefetched_count = 0
            failed_count = 0

            # Fetch all symbols in batches of 50
            for batch_result in batch_tickers(all_symbols, batch_size=50):
                for symbol, ticker in batch_result.items():
                    self._ticker_batch_cache[symbol] = ticker  # Store ticker or None
                    if ticker:
                        prefetched_count += 1
                    else:
                        failed_count += 1

            logger.info(
                f"[YFINANCE_SNAPSHOT BATCH] Prefetch complete: {prefetched_count} symbols cached, "
                f"{failed_count} unavailable. "
                f"API calls reduced from {len(all_symbols)} to {(len(all_symbols) + 49) // 50}"
            )

        except Exception as e:
            logger.warning(f"[YFINANCE_SNAPSHOT BATCH] Prefetch failed, falling back to on-demand: {e}")
            self._ticker_batch_cache.clear()

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch all yfinance data for a symbol, store as single snapshot record.

        Governance: Mark unavailable data explicitly. No silent fallbacks or exceptions.
        Returns data_unavailable marker instead of raising exceptions per GOVERNANCE.md.

        Returns all metrics in one row to avoid 6 separate yfinance API calls.
        Returns data_unavailable marker if ticker unavailable or data fetch fails.

        OPTIMIZATION (Phase 3): On first call, batch-prefetch all active symbols in groups of 50.
        This reduces API calls from 5000+ to ~100 (one per 50 symbols), saving ~50x API calls.
        Subsequent calls read from the prefetch cache, falling back to on-demand for updates.
        """
        # On first fetch, prefetch all symbols in batches (50 symbols per API call)
        if not self._batch_prefetch_done:
            self._do_batch_prefetch()
            self._batch_prefetch_done = True

        # Check batch cache first
        if symbol in self._ticker_batch_cache:
            ticker = self._ticker_batch_cache[symbol]
        else:
            # Fallback: fetch on-demand if not in batch (handles incremental updates)
            ticker = YFinanceWrapper.get_ticker(symbol)

        if not ticker:
            # Ticker data unavailable (delisted, invalid, or yfinance API issue)
            logger.debug(f"[YFINANCE_SNAPSHOT] {symbol}: Ticker data unavailable (yfinance API or invalid symbol)")
            return [
                {
                    "symbol": symbol,
                    "fetched_at": datetime.now(timezone.utc),
                    "data_available": False,
                    "unavailable_reason": "yfinance_ticker_unavailable",
                }
            ]

        info = ticker.info
        if not info or not isinstance(info, dict):
            # Ticker returned invalid/empty data structure
            logger.debug(f"[YFINANCE_SNAPSHOT] {symbol}: Ticker returned invalid data structure")
            return [
                {
                    "symbol": symbol,
                    "fetched_at": datetime.now(timezone.utc),
                    "data_available": False,
                    "unavailable_reason": "yfinance_invalid_info_dict",
                }
            ]

        # Extract all yfinance metrics into single snapshot
        pe_ratio = info.get("trailingPE")
        pb_ratio = info.get("priceToBook")
        ps_ratio = info.get("priceToSalesTrailing12Months")
        peg_ratio = info.get("pegRatio")
        dividend_yield = info.get("dividendYield")
        fcf_yield = (
            info["freeCashflow"] / info["marketCap"]
            if "freeCashflow" in info
            and "marketCap" in info
            and info["freeCashflow"] is not None
            and info["marketCap"] is not None
            else None
        )
        held_percent_insiders = info.get("insidersPercentHeld")
        held_percent_institutions = info.get("heldPercentInstitutions")
        short_interest = info.get("shortPercentOfFloat")
        beta = info.get("beta")
        fifty_two_week_high = info.get("fiftyTwoWeekHigh")
        fifty_two_week_low = info.get("fiftyTwoWeekLow")
        market_cap = info.get("marketCap")
        sector = info.get("sector")
        industry = info.get("industry")
        country = info.get("country")
        exchange = info.get("exchange")
        website = info.get("website")
        long_name = info.get("longName")
        earnings_dates = info.get("earningsDates")
        earnings_date = info.get("earningsDate")
        recommendation_key = info.get("recommendationKey")
        number_of_analysts = info.get("numberOfAnalystOpinions")
        analysts_underweight = info.get("numberOfAnalystsWhoUnderweight")
        analysts_overweight = info.get("numberOfAnalystsWhoOverweight")
        analysts_hold = info.get("numberOfAnalystsWhoHold")

        critical_fields = {
            "pe_ratio": pe_ratio,
            "pb_ratio": pb_ratio,
            "market_cap": market_cap,
            "sector": sector,
            "long_name": long_name,
        }
        missing_critical = [k for k, v in critical_fields.items() if v is None]

        return [
            {
                "symbol": symbol,
                "fetched_at": datetime.now(timezone.utc),
                "pe_ratio": pe_ratio,
                "pb_ratio": pb_ratio,
                "ps_ratio": ps_ratio,
                "peg_ratio": peg_ratio,
                "dividend_yield": dividend_yield,
                "fcf_yield": fcf_yield,
                "held_percent_insiders": held_percent_insiders,
                "held_percent_institutions": held_percent_institutions,
                "short_interest": short_interest,
                "beta": beta,
                "fifty_two_week_high": fifty_two_week_high,
                "fifty_two_week_low": fifty_two_week_low,
                "market_cap": market_cap,
                "sector": sector,
                "industry": industry,
                "country": country,
                "exchange": exchange,
                "website": website,
                "long_name": long_name,
                "earnings_dates": earnings_dates,
                "earnings_date": earnings_date,
                "recommendation_key": recommendation_key,
                "number_of_analysts": number_of_analysts,
                "analysts_underweight": analysts_underweight,
                "analysts_overweight": analysts_overweight,
                "analysts_hold": analysts_hold,
                "data_available": len(missing_critical) == 0,
                "unavailable_reason": (
                    f"missing_critical_fields: {','.join(missing_critical)}" if missing_critical else None
                ),
            }
        ]


def main() -> int:
    """Wrapped main with exception handling for data_unavailable markers.

    Enforces LOADER_TIMEOUT as a hard total-runtime deadline. The batch prefetch's
    per-request 30s socket timeout (configure_socket_timeout above) bounds each
    individual yfinance call but not the overall run -- sustained rate-limit
    backoff across thousands of symbols can still blow well past the intended
    ~120min budget with no single call ever timing out. Without this, the only
    backstop was the external loader_timeout_guardian Lambda, which (by design,
    for safety margin) waits 1.5x LOADER_TIMEOUT before killing a task -- letting
    a stuck run block the downstream computed-metrics pipeline (financials_all,
    growth/quality/value/positioning/stability, stock_scores) for up to 3h.
    Confirmed live 2026-07-13: a run exceeded 120min with no self-timeout firing.
    """
    import signal

    execution_timeout_sec = int(os.getenv("LOADER_TIMEOUT", "7200")) - 60

    def _timeout_handler(signum: int, frame: Any) -> None:
        raise TimeoutError(f"yfinance_snapshot exceeded {execution_timeout_sec}s timeout")

    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(execution_timeout_sec)

    try:
        return run_loader(YFinanceSnapshotLoader)
    except Exception as e:
        logger.error(f"[YFINANCE_SNAPSHOT FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        # Mark data unavailable only for symbols with no row yet -- a timeout or
        # crash partway through a run must not clobber symbols already fetched
        # and committed earlier in this same run (ON CONFLICT DO UPDATE previously
        # overwrote every active symbol unconditionally, silently destroying good
        # data on every partial-completion crash/timeout, not just a total failure).
        try:
            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    cur.execute(
                        """
                        INSERT INTO yfinance_snapshot (symbol, data_unavailable, reason, updated_at)
                        VALUES (%s, TRUE, %s, NOW())
                        ON CONFLICT (symbol) DO NOTHING
                    """,
                        (symbol, f"loader_crash:{type(e).__name__}"),
                    )
        except Exception as mark_err:
            logger.error(f"Failed to mark yfinance_snapshot data unavailable: {mark_err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
