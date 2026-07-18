#!/usr/bin/env python3
"""Positioning Metrics Loader - CRITICAL for stock scoring (institutional/insider/short data).

PURPOSE:
- Fetch positioning metrics from yfinance (institutional ownership %, insider ownership %, short interest %)
- These are REQUIRED by load_stock_scores.py (minimum 30% coverage needed)
- Previously bundled with dashboard-only data in load_yfinance_derived_metrics.py

DATA SOURCE:
- Reads from: yfinance_snapshot table (populated by load_yfinance_snapshot.py)
- Writes to: positioning_metrics table (READ BY stock_scores.py)

DEPENDENCIES:
- load_yfinance_snapshot.py must run FIRST (populates yfinance_snapshot table)

Run:
    python3 loaders/load_positioning_metrics.py [--symbols AAPL,MSFT] [--parallelism 4]
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)


class PositioningMetricsLoader(OptimalLoader):
    """Load positioning metrics from yfinance_snapshot.

    CRITICAL LOADER: Stock scores require 30% coverage of positioning metrics.
    Without this data, stock scoring fails pre-flight validation.

    Reads from yfinance_snapshot (populated by load_yfinance_snapshot.py).
    Writes to positioning_metrics table (read by stock_scores.py).
    """

    table_name = "positioning_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch positioning metrics for a symbol from yfinance_snapshot.

        Returns positioning data (institutional %, insider %, short interest %) or
        data_unavailable marker if yfinance_snapshot row missing/unavailable.
        """
        now_et = datetime.now(EASTERN_TZ)

        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT
                    held_percent_institutions,
                    held_percent_insiders,
                    short_interest,
                    data_available,
                    unavailable_reason
                FROM yfinance_snapshot
                WHERE symbol = %s
                """,
                (symbol,),
            )
            row = cur.fetchone()

        if not row:
            logger.debug(f"[POSITIONING] {symbol}: yfinance_snapshot row not found")
            return [
                {
                    "symbol": symbol,
                    "institutional_ownership_pct": None,
                    "insider_ownership_pct": None,
                    "short_interest_pct": None,
                    "data_unavailable": True,
                    "reason": "yfinance_snapshot_missing",
                    "updated_at": now_et,
                }
            ]

        # CRITICAL FIX: row is a psycopg2 tuple, not dict
        # SELECT columns: institutions(0), insiders(1), short(2), data_available(3), unavailable_reason(4)
        data_available = row[3] if len(row) > 3 else False
        unavailable_reason = row[4] if len(row) > 4 else ""

        if not data_available:
            logger.debug(f"[POSITIONING] {symbol}: yfinance_snapshot marked unavailable ({unavailable_reason})")
            return [
                {
                    "symbol": symbol,
                    "institutional_ownership_pct": None,
                    "insider_ownership_pct": None,
                    "short_interest_pct": None,
                    "data_unavailable": True,
                    "reason": unavailable_reason or "yfinance_snapshot_unavailable",
                    "updated_at": now_et,
                }
            ]

        return [
            {
                "symbol": symbol,
                "institutional_ownership_pct": row[0],  # held_percent_institutions
                "insider_ownership_pct": row[1],  # held_percent_insiders
                "short_interest_pct": row[2],  # short_interest
                "data_unavailable": False,
                "updated_at": now_et,
            }
        ]


def main() -> int:
    """Wrapped main with exception handling for data_unavailable markers."""
    try:
        return run_loader(PositioningMetricsLoader)
    except Exception as e:
        logger.error(f"[POSITIONING FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        # Mark data unavailable only for symbols with no row yet -- a crash partway through
        # must not clobber symbols already fetched and committed earlier in this same run
        try:
            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    cur.execute(
                        """
                        INSERT INTO positioning_metrics (symbol, data_unavailable, reason, updated_at)
                        VALUES (%s, TRUE, %s, NOW())
                        ON CONFLICT (symbol) DO NOTHING
                        """,
                        (symbol, f"loader_crash:{type(e).__name__}"),
                    )
        except Exception as mark_err:
            logger.error(f"[POSITIONING] Failed to mark positioning_metrics data unavailable: {mark_err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
