#!/usr/bin/env python3
"""Short Interest Loader - FINRA Reg SHO Direct API (No yfinance).

Provides short interest % for stock scoring from FINRA's authoritative
Regulation SHO short interest reports (bi-weekly CSV publication).

Performance Improvement: Eliminates yfinance rate limit (2000 req/hr).
- OLD: ~8 minutes for 4,711 symbols (sequential, 0.1s per symbol)
- NEW: <30 seconds for all symbols (single CSV fetch + parse)

Data source: FINRA Reg SHO CSV (https://www.finra.org/filing-and/)
Update frequency: Bi-weekly (published Sundays at 9 AM ET)
Data delay: 2 business days (settlement)
Quality: FINRA is authoritative regulatory source

Run:
    python3 loaders/load_short_interest_finra.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from loaders.runner import run_loader  # noqa: E402
from utils.finra_short_interest import FINRAShortInterestFetcher  # noqa: E402
from utils.infrastructure.timezone import EASTERN_TZ  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402

logger = logging.getLogger(__name__)


class ShortInterestFinraLoader(OptimalLoader):
    """Load short interest data directly from FINRA Reg SHO CSV files.

    CRITICAL IMPROVEMENT (Session 265):
    - Replaced yfinance per-symbol fetch (8+ min) with single FINRA CSV fetch (<30 sec)
    - No rate limiting (authoritative regulatory source)
    - Batch-load all symbols in single operation
    - Fail-fast with explicit data_unavailable markers per GOVERNANCE
    """

    table_name = "short_interest_finra"
    primary_key = ("symbol", "settlement_date")
    watermark_field = "settlement_date"
    exclude_etfs_from_symbols = True

    def run(self, symbols: list[str], parallelism: int = 8, backfill_days: int | None = None) -> dict[str, Any]:
        """Load short interest from FINRA (single batch fetch, no rate limiting).

        CRITICAL FIX (Session 265): Fetch FINRA CSV once, match all symbols.
        This eliminates yfinance's per-symbol API calls and rate limiting.

        Performance: O(1) FINRA CSV fetch + O(n) symbol matching
        vs O(n) yfinance API calls with throttling.
        """
        import time
        from utils.db import DatabaseContext

        now_et = datetime.now(EASTERN_TZ)
        run_date = now_et.date()

        from algo.infrastructure import MarketCalendar

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
            # SINGLE OPERATION: Fetch FINRA CSV once (no per-symbol rate limiting)
            logger.info("[SHORT_INTEREST] Fetching FINRA Reg SHO data (single CSV)...")
            fetcher = FINRAShortInterestFetcher()
            finra_data = fetcher.fetch_latest()  # {symbol: short_interest_pct, ...}
            logger.info(f"[SHORT_INTEREST] FINRA data: {len(finra_data)} symbols from latest report")

            # BATCH INSERT: Match symbols and insert all at once
            rows_inserted = 0
            rows_unavailable = 0
            symbols_processed = 0

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    symbols_processed += 1

                    if symbol in finra_data:
                        # Symbol found in FINRA data
                        short_pct = finra_data[symbol]
                        cur.execute(
                            """
                            INSERT INTO short_interest_finra
                            (symbol, settlement_date, short_pct, finra_report_date, data_unavailable, updated_at)
                            VALUES (%s, %s, %s, %s, FALSE, %s)
                            ON CONFLICT (symbol, settlement_date) DO UPDATE SET
                                short_pct = EXCLUDED.short_pct,
                                finra_report_date = EXCLUDED.finra_report_date,
                                data_unavailable = FALSE,
                                updated_at = EXCLUDED.updated_at
                            """,
                            (symbol, run_date, short_pct, run_date, now_et),
                        )
                        rows_inserted += 1
                    else:
                        # Symbol not in FINRA data (rare small-cap or delisted)
                        cur.execute(
                            """
                            INSERT INTO short_interest_finra
                            (symbol, settlement_date, short_pct, finra_report_date, data_unavailable, reason, updated_at)
                            VALUES (%s, %s, NULL, NULL, TRUE, %s, %s)
                            ON CONFLICT (symbol, settlement_date) DO UPDATE SET
                                short_pct = NULL,
                                finra_report_date = NULL,
                                data_unavailable = TRUE,
                                reason = EXCLUDED.reason,
                                updated_at = EXCLUDED.updated_at
                            """,
                            (symbol, run_date, "symbol_not_in_finra_data", now_et),
                        )
                        rows_unavailable += 1

            duration = time.time() - start_time

            result = {
                "symbols_succeeded": rows_inserted,
                "symbols_failed": rows_unavailable,
                "rows_inserted": rows_inserted,
                "status": "ok",
                "duration_sec": round(duration, 2),
                "latest_date": run_date.isoformat(),
            }

            logger.info(
                f"[SHORT_INTEREST] Load complete: {rows_inserted} succeeded, "
                f"{rows_unavailable} unavailable in {duration:.1f}s"
            )
            return result

        except Exception as e:
            logger.error(f"[SHORT_INTEREST] Fatal error: {type(e).__name__}: {str(e)}", exc_info=True)
            # CRITICAL: Fail-fast on fatal errors (no silent fallback to empty result dict)
            # Returning a dict with status="error" masks the failure from orchestrator.
            # Re-raise to ensure orchestrator detects the failure and marks data unavailable.
            raise RuntimeError(
                f"[SHORT_INTEREST] Fatal loader error: {type(e).__name__}: {str(e)[:200]}"
            ) from e


def main() -> int:
    """Entry point for load_short_interest_finra.py."""
    try:
        return run_loader(ShortInterestFinraLoader)
    except Exception as e:
        logger.error(f"[SHORT_INTEREST FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
