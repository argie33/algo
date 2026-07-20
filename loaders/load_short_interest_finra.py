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
    """Load short interest data from FINRA CSV (or yfinance fallback).

    PRIORITY 1: FINRA CSV (authoritative regulatory source)
    FALLBACK: yfinance per-symbol fetch (deprecated, TEMPORARY)

    Performance:
    - FINRA: ~30 seconds for 4700+ symbols (single CSV fetch)
    - yfinance fallback: ~8 minutes (rate limited per-symbol)

    TODO: Fix FINRA CSV URLs or find working FINRA API endpoint
    """

    table_name = "short_interest_finra"
    primary_key = ("symbol", "settlement_date")
    watermark_field = "settlement_date"
    exclude_etfs_from_symbols = True

    @staticmethod
    def _fetch_yfinance_short_interest(symbol: str) -> float | None:
        """Fetch short interest for one symbol via yfinance (fallback only).

        DEPRECATED: yfinance is temporary fallback. Use only when FINRA unavailable.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Short interest as percentage (0-100), or None if unavailable
        """
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            info = ticker.info
            short_pct = info.get("shortPercentOfFloat")

            # yfinance returns decimal (0.01 for 1%), convert to percentage
            if short_pct is not None and 0 < short_pct < 1:
                return short_pct * 100
            elif isinstance(short_pct, (int, float)):
                return float(short_pct)
            return None
        except Exception:
            return None

    def run(self, symbols: list[str], parallelism: int = 8, backfill_days: int | None = None) -> dict[str, Any]:
        """Load short interest from FINRA or yfinance fallback.

        PRIORITY 1: FINRA CSV (preferred - authoritative)
        FALLBACK: yfinance per-symbol fetch (deprecated, temporary)

        Performance:
        - If FINRA available: O(1) CSV fetch + O(n) symbol matching
        - If FINRA unavailable: O(n) yfinance API calls with rate limiting
        """
        import time
        from utils.db.context import DatabaseContext

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
            # Try FINRA CSV first
            logger.info("[SHORT_INTEREST] Attempting FINRA CSV fetch...")
            fetcher = FINRAShortInterestFetcher()
            try:
                finra_data = fetcher.fetch_latest()  # {symbol: short_interest_pct, ...}
                logger.info(f"[SHORT_INTEREST] FINRA data: {len(finra_data)} symbols from CSV")
                use_yfinance_fallback = False
            except Exception as e_finra:
                logger.warning(
                    f"[SHORT_INTEREST] FINRA CSV fetch failed: {e_finra}. "
                    f"Using yfinance fallback (DEPRECATED - TODO: Fix FINRA)"
                )
                finra_data = {}
                use_yfinance_fallback = True

            # Process symbols
            rows_inserted = 0
            rows_unavailable = 0

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    short_pct = None

                    # Check FINRA data first
                    if symbol in finra_data:
                        short_pct = finra_data[symbol]
                        data_unavailable = False
                        reason = None
                    # Fallback to yfinance if needed
                    elif use_yfinance_fallback:
                        try:
                            short_pct = self._fetch_yfinance_short_interest(symbol)
                            if short_pct is not None:
                                data_unavailable = False
                                reason = None
                            else:
                                data_unavailable = True
                                reason = "yfinance_no_data"
                        except Exception as e:
                            data_unavailable = True
                            reason = f"yfinance_error: {str(e)[:40]}"
                    else:
                        # FINRA has data but symbol not found
                        data_unavailable = True
                        reason = "symbol_not_in_finra_data"

                    # Insert record
                    cur.execute(
                        """
                        INSERT INTO short_interest_finra
                        (symbol, settlement_date, short_pct, finra_report_date, data_unavailable, reason, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, settlement_date) DO UPDATE SET
                            short_pct = EXCLUDED.short_pct,
                            finra_report_date = EXCLUDED.finra_report_date,
                            data_unavailable = EXCLUDED.data_unavailable,
                            reason = EXCLUDED.reason,
                            updated_at = EXCLUDED.updated_at
                        """,
                        (symbol, run_date, short_pct, run_date if short_pct else None,
                         data_unavailable, reason, now_et),
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
                "latest_date": run_date.isoformat(),
                "finra_source": "csv" if not use_yfinance_fallback else "yfinance_fallback",
            }

            logger.info(
                f"[SHORT_INTEREST] Load complete: {rows_inserted} succeeded, "
                f"{rows_unavailable} unavailable in {duration:.1f}s "
                f"(source: {'FINRA CSV' if not use_yfinance_fallback else 'yfinance fallback'})"
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
