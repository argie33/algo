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

    def run(self, symbols: Iterable[str], parallelism: int = 8, backfill_days: int | None = None) -> dict[str, Any]:
        """Load short interest from FINRA, computing short_pct via shares_outstanding.

        Performance: O(1) FINRA fetch (paginated bulk pull, ~5 requests) + O(1)
        shares_outstanding bulk query, then O(n) in-memory symbol matching.
        """
        symbols = list(symbols)
        now_et = datetime.now(EASTERN_TZ)
        run_date = now_et.date()

        # Skip on non-trading days (short interest data not updated)
        if not MarketCalendar.is_trading_day(run_date):
            logger.info(f"[SHORT_INTEREST] Skipping: {run_date} is not a trading day")
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
                    f"[SHORT_INTEREST] FINRA data: {len(finra_data)} symbols "
                    f"for settlement date {settlement_date}"
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

                    if finra_row is None:
                        short_pct = None
                        short_shares = None
                        data_unavailable = True
                        reason = "finra_data_unavailable" if finra_data else "finra_api_unreachable"
                    elif not outstanding:
                        short_pct = None
                        short_shares = finra_row["short_shares"]
                        data_unavailable = True
                        reason = "shares_outstanding_unavailable"
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
                         data_unavailable, reason, data_source, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, settlement_date) DO UPDATE SET
                            short_shares = EXCLUDED.short_shares,
                            short_pct = EXCLUDED.short_pct,
                            finra_report_date = EXCLUDED.finra_report_date,
                            data_unavailable = EXCLUDED.data_unavailable,
                            reason = EXCLUDED.reason,
                            data_source = EXCLUDED.data_source,
                            updated_at = EXCLUDED.updated_at
                        """,
                        (symbol, record_date, short_shares, short_pct,
                         run_date if finra_row else None, data_unavailable, reason,
                         "finra_query_api", now_et),
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
            return result

        except Exception as e:
            logger.error(f"[SHORT_INTEREST] Fatal error: {type(e).__name__}: {e!s}", exc_info=True)
            # CRITICAL: Fail-fast on fatal errors (no silent fallback to empty result dict)
            # Returning a dict with status="error" masks the failure from orchestrator.
            # Re-raise to ensure orchestrator detects the failure and marks data unavailable.
            raise RuntimeError(
                f"[SHORT_INTEREST] Fatal loader error: {type(e).__name__}: {str(e)[:200]}"
            ) from e

    @staticmethod
    def _load_shares_outstanding() -> dict[str, int]:
        """Bulk-load the latest shares_outstanding per symbol from company_info_sec."""
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (symbol) symbol, shares_outstanding
                FROM company_info_sec
                WHERE shares_outstanding IS NOT NULL AND shares_outstanding > 0
                ORDER BY symbol, filing_date DESC
                """
            )
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
