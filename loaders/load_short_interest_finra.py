#!/usr/bin/env python3
"""Short Interest Loader - FINRA Consolidated Short Interest Query API (No yfinance).

Provides short interest % for stock scoring from FINRA's authoritative
Regulation SHO short interest data (bi-weekly, settlement dates the 15th and
last day of each month; published ~2-3 weeks after settlement).

Data source: FINRA Query API "Consolidated Short Interest" dataset
  (https://api.finra.org/data/group/otcMarket/name/ConsolidatedShortInterest)
Coverage: NYSE, Nasdaq, and OTC (verified against live data, not OTC-only
  despite the "otcMarket" API namespace).
FINRA reports raw share counts, not a percentage. short_pct is computed here
as short_shares / shares_outstanding (from company_info_sec, SEC EDGAR DEI
facts) * 100. Symbols without a shares_outstanding figure are marked
data_unavailable rather than guessing.

Run:
    python3 loaders/load_short_interest_finra.py [--symbols AAPL,MSFT]
"""

import logging
import sys
import time
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from algo.infrastructure import MarketCalendar  # noqa: E402
from loaders.runner import run_loader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.finra_short_interest import FINRAShortInterestFetcher  # noqa: E402
from utils.infrastructure.timezone import EASTERN_TZ  # noqa: E402
from utils.loaders.status_manager import LoaderStatusManager  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

logger = logging.getLogger(__name__)


class ShortInterestFinraLoader(OptimalLoader):
    """Load short interest data from FINRA's Consolidated Short Interest API only.

    GOVERNANCE: Only official sources. No silent fallbacks.
    - PRIORITY 1: FINRA Query API (authoritative regulatory source, NYSE/Nasdaq/OTC)
    - NO FALLBACK: If FINRA unavailable, mark data_unavailable=TRUE (fail-fast)

    short_pct requires an independent shares_outstanding figure (company_info_sec,
    SEC EDGAR). Symbols FINRA reports but company_info_sec doesn't cover are marked
    data_unavailable rather than reporting a raw share count as if it were a percent.
    """

    table_name = "short_interest_finra"
    primary_key = ("symbol", "settlement_date")
    watermark_field = "settlement_date"
    exclude_etfs_from_symbols = True
    # DB-verified 2026-08-10 (most recent 2 settlement dates): ~9.5-9.8% of symbols land in
    # data_unavailable (no FINRA row, or FINRA row but no shares_outstanding from
    # company_info_sec) - a real, structural coverage gap, not a bug. 15% gives margin above
    # the observed rate without masking a genuine regression.
    max_fail_rate = 15.0

    def run(self, symbols: Iterable[str], parallelism: int = 8, backfill_days: int | None = None) -> dict[str, Any]:
        """Load short interest from FINRA, computing short_pct via shares_outstanding.

        Performance: O(1) FINRA fetch (paginated bulk pull, ~5 requests) + O(1)
        shares_outstanding bulk query, then O(n) in-memory symbol matching.
        """
        symbols = list(symbols)
        now_et = datetime.now(EASTERN_TZ)
        run_date = now_et.date()
        status_mgr = LoaderStatusManager(self.table_name)

        # FIX 2026-08-10: this run() fully overrides OptimalLoader.run() and never called
        # LoaderStatusManager itself - relying entirely on runner.py's generic post-run
        # mark_completed()/mark_failed() call. DB-verified live: data_loader_status stayed
        # frozen at execution_completed=2026-07-18/status=HEALTHY (a health-sweep label, not
        # something this loader's own completion logic produced) while short_interest_finra
        # itself had real fresh rows through 2026-08-05 - status fully decoupled from what
        # actually happened each run, so a real failure wouldn't reliably surface. Marking
        # status directly here makes it self-sufficient regardless of the caller.
        status_mgr.mark_running()

        # Skip on non-trading days (short interest data not updated)
        if not MarketCalendar.is_trading_day(run_date):
            logger.info(f"[SHORT_INTEREST] Skipping: {run_date} is not a trading day")
            # BUG FIX 2026-08-17: bare mark_completed() falls back to re-reading symbol_count/
            # symbols_loaded from the DB row, which this run never touches (0 symbols processed
            # on a legitimate skip) - live-reproduced: this computed 0/4920 = 0% and got
            # overridden to FAILED by mark_completed()'s own completion-threshold safety check,
            # so every single non-trading day (i.e. every weekend) marked this loader FAILED and
            # incremented consecutive_failures, even though skipping was correct behavior.
            # load_prices.py hit and fixed the identical bug (see its non-trading-day skip
            # branch) with the same "1/1 = no-op success" convention - mirrored here.
            status_mgr.mark_completed(current_run_symbols_loaded=1, current_run_symbol_count=1)
            return {
                "symbols_succeeded": 0,
                "symbols_failed": 0,
                "rows_inserted": 0,
                "status": "SKIPPED_NON_TRADING_DAY",
            }

        start_time = time.time()

        try:
            logger.info("[SHORT_INTEREST] Fetching FINRA Consolidated Short Interest...")
            fetcher = FINRAShortInterestFetcher()
            try:
                finra_data, settlement_date = fetcher.fetch_latest()
                logger.info(
                    f"[SHORT_INTEREST] FINRA data: {len(finra_data)} symbols for settlement date {settlement_date}"
                )
            except Exception as e_finra:
                logger.warning(
                    f"[SHORT_INTEREST] FINRA fetch failed: {e_finra}. "
                    f"Will mark all data unavailable (no fallback per GOVERNANCE)"
                )
                finra_data, settlement_date = {}, None

            shares_outstanding = self._load_shares_outstanding()
            logger.info(f"[SHORT_INTEREST] shares_outstanding available for {len(shares_outstanding)} symbols")

            rows_inserted = 0
            rows_unavailable = 0

            # primary_key is (symbol, settlement_date). When FINRA is unreachable,
            # settlement_date is None and every symbol would otherwise fall back to
            # today's date - a fresh PK, so a fresh duplicate row, on every failed
            # run instead of updating one persistent marker (same bug class fixed in
            # company_info_sec/institutional_holdings_13f/earnings_calendar_sec).
            # Reuse each symbol's existing unavailable-marker date instead.
            existing_marker_dates: dict[str, Any] = {}
            if settlement_date is None:
                with DatabaseContext("read") as cur:
                    cur.execute(
                        "SELECT symbol, settlement_date FROM short_interest_finra "
                        "WHERE symbol = ANY(%s) AND data_unavailable = true",
                        (symbols,),
                    )
                    existing_marker_dates = dict(cur.fetchall())

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    finra_row = finra_data.get(symbol)
                    outstanding = shares_outstanding.get(symbol)
                    record_date = settlement_date or existing_marker_dates.get(symbol, run_date)

                    # days_to_cover/avg_daily_volume are fetched from FINRA alongside
                    # short_shares regardless of whether shares_outstanding is available -
                    # they don't depend on it (unlike short_pct), so extract them whenever
                    # finra_row exists.
                    days_to_cover = finra_row.get("days_to_cover") if finra_row else None
                    avg_daily_volume = finra_row.get("avg_daily_volume") if finra_row else None

                    if finra_row is None:
                        short_pct = None
                        short_shares = None
                        data_unavailable = True
                        reason = "finra_data_unavailable" if finra_data else "finra_api_unreachable"
                    elif not outstanding or outstanding <= 1000:
                        short_pct = None
                        short_shares = finra_row["short_shares"]
                        data_unavailable = True
                        reason = "shares_outstanding_unavailable" if not outstanding else "shares_outstanding_invalid"
                    else:
                        short_shares = finra_row["short_shares"]
                        # No upper clamp: short interest CAN legitimately exceed 100% of float
                        # (naked shorting, ETF create/redeem mechanics - well-documented, e.g.
                        # GME repeatedly reported >100%). Clamping to 100.0 fabricated a lower
                        # number and masked exactly the extreme readings that matter most for
                        # squeeze/risk assessment, with no flag indicating a clamp occurred.
                        # DECIMAL(6,2) allows up to 9999.99, comfortably above any real reading.
                        short_pct = round((short_shares / outstanding) * 100, 2)
                        data_unavailable = False
                        reason = None

                    cur.execute(
                        """
                        INSERT INTO short_interest_finra
                        (symbol, settlement_date, short_shares, short_pct, finra_report_date,
                         days_to_cover, avg_daily_volume, data_unavailable, reason, data_source, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, settlement_date) DO UPDATE SET
                            short_shares = EXCLUDED.short_shares,
                            short_pct = EXCLUDED.short_pct,
                            finra_report_date = EXCLUDED.finra_report_date,
                            days_to_cover = EXCLUDED.days_to_cover,
                            avg_daily_volume = EXCLUDED.avg_daily_volume,
                            data_unavailable = EXCLUDED.data_unavailable,
                            reason = EXCLUDED.reason,
                            data_source = EXCLUDED.data_source,
                            updated_at = EXCLUDED.updated_at
                        """,
                        (
                            symbol,
                            record_date,
                            short_shares,
                            short_pct,
                            run_date if finra_row else None,
                            days_to_cover,
                            avg_daily_volume,
                            data_unavailable,
                            reason,
                            "finra_query_api",
                            now_et,
                        ),
                    )

                    if data_unavailable:
                        rows_unavailable += 1
                    else:
                        rows_inserted += 1

            duration = time.time() - start_time

            result = {
                "symbols_succeeded": rows_inserted,
                "symbols_failed": rows_unavailable,
                "rows_inserted": rows_inserted,
                "status": "ok" if rows_inserted > 0 else "partial",
                "duration_sec": round(duration, 2),
                "settlement_date": settlement_date.isoformat() if settlement_date else None,
                "finra_source": "finra_query_api" if finra_data else "finra_unavailable",
            }

            logger.info(
                f"[SHORT_INTEREST] Load complete: {rows_inserted} succeeded, "
                f"{rows_unavailable} unavailable in {duration:.1f}s "
                f"(settlement_date={settlement_date})"
            )

            total = max(len(symbols), 1)
            fail_rate_pct = (rows_unavailable / total) * 100
            if fail_rate_pct > self.max_fail_rate:
                status_mgr.mark_failed(
                    error_message=f"{rows_unavailable}/{total} symbols data_unavailable "
                    f"({fail_rate_pct:.1f}% exceeds max_fail_rate {self.max_fail_rate:.0f}%)",
                    completion_pct=(rows_inserted / total) * 100,
                )
            else:
                status_mgr.mark_completed(
                    execution_duration_sec=duration,
                    current_run_symbol_count=total,
                    current_run_symbols_loaded=rows_inserted,
                    min_completion_pct=max(0.0, 100.0 - self.max_fail_rate),
                )
            return result

        except Exception as e:
            logger.error(f"[SHORT_INTEREST] Fatal error: {type(e).__name__}: {e!s}", exc_info=True)
            status_mgr.mark_failed(error_message=f"{type(e).__name__}: {str(e)[:200]}")
            # CRITICAL: Fail-fast on fatal errors (no silent fallback to empty result dict)
            # Returning a dict with status="error" masks the failure from orchestrator.
            # Re-raise to ensure orchestrator detects the failure and marks data unavailable.
            raise RuntimeError(f"[SHORT_INTEREST] Fatal loader error: {type(e).__name__}: {str(e)[:200]}") from e

    @staticmethod
    def _load_shares_outstanding() -> dict[str, int]:
        """Bulk-load the latest shares_outstanding per symbol from company_info_sec."""
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT DISTINCT ON (symbol) symbol, shares_outstanding
                FROM company_info_sec
                WHERE shares_outstanding IS NOT NULL AND shares_outstanding > 0
                ORDER BY symbol, filing_date DESC
                """)
            return {row[0]: row[1] for row in cur.fetchall()}


def main() -> int:
    """Entry point for load_short_interest_finra.py."""
    try:
        return run_loader(ShortInterestFinraLoader)
    except Exception as e:
        logger.error(f"[SHORT_INTEREST FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
