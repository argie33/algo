#!/usr/bin/env python3
"""Market Context Daily Loader - Centralized market macro data fetcher.

CONSOLIDATION: Merges fragmented market data fetchers into single coordinated loader:
  - VIX index (from load_market_health_daily.py VIXFetcher)
  - DXY index (from load_dxy_index.py)
  - Treasury yields (10Y, 2Y) (from load_market_health_daily.py YieldCurveFetcher)
  - Market breadth (advance/decline) (from load_market_health_daily.py BreadthFetcher)

Benefit: Single coordinated fetch, no duplicate API calls, cleaner architecture.
Other loaders READ from market_context_daily table instead of making separate calls.

Run: python3 load_market_context_daily.py
"""

import logging
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)


class MarketContextDailyLoader(OptimalLoader):
    """Load consolidated daily market macro data.

    Fetches all macro data (VIX, DXY, yields, breadth) in single coordinated operation.
    Outputs to market_context_daily table for other loaders/API to consume.
    """

    table_name = "market_context_daily"
    primary_key = ("date",)
    watermark_field = "date"
    LOADER_TYPE = "auxiliary"  # Non-critical if times out
    REQUIRED_SYMBOLS = None  # Global data, not per-symbol

    SCHEMA = {
        "date": "date",
        "vix_close": "numeric",
        "dxy_index": "numeric",
        "yields_10y": "numeric",
        "yields_2y": "numeric",
        "market_advance": "integer",
        "market_decline": "integer",
        "data_unavailable": "boolean",
        "reason": "text",
    }

    def fetch_global(self, since: date | None = None) -> dict[str, Any]:
        """Fetch all market context data for today.

        Returns dict with:
        - rows: List of market context records (one per date)
        - status: 'current' if already loaded, 'fetched' if new data
        """
        today = datetime.now(EASTERN_TZ).date()

        # Check if already loaded for today
        with DatabaseContext("read") as cur:
            cur.execute("SELECT COUNT(*) FROM market_context_daily WHERE date = %s", (today,))
            result = cur.fetchone()
            if result and result[0] > 0:
                logger.info(f"[MARKET_CONTEXT] Data already loaded for {today}")
                return {"rows": [], "status": "current"}

        # Fetch all market data together
        logger.info(f"[MARKET_CONTEXT] Fetching VIX, DXY, yields, breadth for {today}")

        try:
            vix_close = self._fetch_vix(today)
            dxy_index = self._fetch_dxy(today)
            yields_10y, yields_2y = self._fetch_yields(today)
            advance, decline = self._fetch_breadth(today)

            row = {
                "date": today,
                "vix_close": vix_close,
                "dxy_index": dxy_index,
                "yields_10y": yields_10y,
                "yields_2y": yields_2y,
                "market_advance": advance,
                "market_decline": decline,
                "data_unavailable": False,
                "reason": None,
            }

            logger.info(f"[MARKET_CONTEXT] Fetched: VIX={vix_close}, DXY={dxy_index}, 10Y={yields_10y}, 2Y={yields_2y}")
            return {"rows": [row], "status": "fetched"}

        except Exception as e:
            logger.warning(f"[MARKET_CONTEXT] Fetch error: {e}. Marking unavailable.")
            row = {
                "date": today,
                "vix_close": None,
                "dxy_index": None,
                "yields_10y": None,
                "yields_2y": None,
                "market_advance": None,
                "market_decline": None,
                "data_unavailable": True,
                "reason": str(e)[:200],
            }
            return {"rows": [row], "status": "fetched"}

    def _fetch_vix(self, eval_date: date) -> float | None:
        """Fetch VIX close from Yahoo Finance."""
        try:
            import yfinance as yf

            # Fetch last 2 days to ensure we get the eval_date if market is open
            end = eval_date + timedelta(days=1)
            start = eval_date - timedelta(days=2)

            vix = yf.download("^VIX", start=start, end=end, progress=False)
            if vix is None or len(vix) == 0:
                logger.warning(f"[VIX] No data from Yahoo Finance for {eval_date}")
                return None

            # Get latest close
            latest_close = float(vix["Close"].iloc[-1])
            logger.info(f"[VIX] Fetched {latest_close} for {eval_date}")
            return latest_close

        except Exception as e:
            logger.warning(f"[VIX] Fetch failed: {e}")
            return None

    def _fetch_dxy(self, eval_date: date) -> float | None:
        """Fetch DXY (US Dollar Index) from Yahoo Finance."""
        try:
            import yfinance as yf

            end = eval_date + timedelta(days=1)
            start = eval_date - timedelta(days=2)

            dxy = yf.download("DX-Y.NYB", start=start, end=end, progress=False)
            if dxy is None or len(dxy) == 0:
                logger.warning(f"[DXY] No data from Yahoo Finance for {eval_date}")
                return None

            latest_close = float(dxy["Close"].iloc[-1])
            logger.info(f"[DXY] Fetched {latest_close} for {eval_date}")
            return latest_close

        except Exception as e:
            logger.warning(f"[DXY] Fetch failed: {e}")
            return None

    def _fetch_yields(self, eval_date: date) -> tuple[float | None, float | None]:
        """Fetch Treasury yields from FRED API (stub - returns None for now).

        TODO: Implement FRED API integration for 10Y and 2Y yields.
        For now, returns None to indicate unavailable.
        """
        logger.debug("[YIELDS] FRED API integration not yet implemented")
        return None, None

    def _fetch_breadth(self, eval_date: date) -> tuple[int | None, int | None]:
        """Fetch market breadth (advance/decline counts) from Yahoo Finance (stub).

        TODO: Implement breadth data fetch from market data API.
        For now, returns None to indicate unavailable.
        """
        logger.debug("[BREADTH] Market breadth fetch not yet implemented")
        return None, None

    def insert_rows(self, rows: list[dict[str, Any]]) -> int:
        """Insert market context data into database."""
        if not rows:
            logger.info(f"[{self.table_name}] No rows to insert")
            return 0

        try:
            with DatabaseContext("write") as cur:
                for row in rows:
                    cur.execute(
                        """
                        INSERT INTO market_context_daily
                        (date, vix_close, dxy_index, yields_10y, yields_2y,
                         market_advance, market_decline, data_unavailable, reason)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (date) DO UPDATE SET
                            vix_close = EXCLUDED.vix_close,
                            dxy_index = EXCLUDED.dxy_index,
                            yields_10y = EXCLUDED.yields_10y,
                            yields_2y = EXCLUDED.yields_2y,
                            market_advance = EXCLUDED.market_advance,
                            market_decline = EXCLUDED.market_decline,
                            data_unavailable = EXCLUDED.data_unavailable,
                            reason = EXCLUDED.reason
                        """,
                        (
                            row["date"],
                            row["vix_close"],
                            row["dxy_index"],
                            row["yields_10y"],
                            row["yields_2y"],
                            row["market_advance"],
                            row["market_decline"],
                            row["data_unavailable"],
                            row["reason"],
                        ),
                    )

            logger.info(f"[{self.table_name}] Inserted {len(rows)} records")
            return len(rows)

        except Exception as e:
            logger.error(f"[{self.table_name}] Failed to insert {len(rows)} records: {e}")
            raise


if __name__ == "__main__":
    run_loader(MarketContextDailyLoader)
