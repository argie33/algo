#!/usr/bin/env python3
"""Positioning Metrics Loader - CRITICAL for stock scoring (institutional/insider/short data).

PURPOSE:
- Fetch positioning metrics (institutional ownership %, insider ownership %, short interest %)
- These are REQUIRED by load_stock_scores.py (minimum 30% coverage needed)
- Previously bundled with dashboard-only data in load_yfinance_derived_metrics.py

DATA SOURCES (Phase 1 Optimization - Session 225):
- short_interest: FINRA Reg SHO Transparency Data (load_short_interest_finra.py) ✅ PRIMARY
- institutional_ownership: yfinance_snapshot (temporary; will replace with SEC 13F in Phase 2)
- insider_ownership: yfinance_snapshot (temporary; will replace with SEC insider filings in Phase 2)
- Writes to: positioning_metrics table (READ BY stock_scores.py)

DEPENDENCIES:
- load_short_interest_finra.py must run FIRST (populates short_interest_finra table)
- load_yfinance_snapshot.py must run for institutional/insider data (temporary)

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
        """Fetch positioning metrics for a symbol from multiple sources (Phase 1 optimization).

        PHASE 1 (Session 225): Short interest from FINRA (authoritative), institutional/insider from yfinance (temporary)
        PHASE 2 (planned): Institutional from SEC 13F, insider from SEC insider filings

        Returns positioning data (institutional %, insider %, short interest %) or
        data_unavailable marker if sources missing/unavailable.
        """
        now_et = datetime.now(EASTERN_TZ)

        # PHASE 1: Fetch short interest from FINRA (primary), fallback to yfinance
        short_interest_pct = None
        short_interest_unavailable = False
        short_interest_reason = None

        with DatabaseContext("read") as cur:
            # Try FINRA first
            cur.execute(
                """
                SELECT short_pct, data_unavailable, reason
                FROM short_interest_finra
                WHERE symbol = %s AND data_unavailable = FALSE
                ORDER BY settlement_date DESC LIMIT 1
                """,
                (symbol,),
            )
            short_row = cur.fetchone()

        if short_row and short_row[0] is not None:
            # Successfully got from FINRA
            short_interest_pct = short_row[0]
            short_interest_unavailable = False
            short_interest_reason = None
        else:
            # FINRA unavailable or null; try yfinance as fallback
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT short_interest FROM yfinance_snapshot WHERE symbol = %s",
                    (symbol,),
                )
                yf_row = cur.fetchone()

            if yf_row and yf_row[0] is not None:
                short_interest_pct = yf_row[0]
                short_interest_unavailable = False
                short_interest_reason = None
            else:
                short_interest_unavailable = True
                short_interest_reason = "finra_and_yfinance_unavailable"

        # PHASE 2 (Session 234): Fetch institutional/insider from SEC sources (13F/Form 4), fallback to yfinance
        institutional_pct = None
        insider_pct = None
        sec_unavailable = False
        yfinance_unavailable = False
        sec_reason = None
        yfinance_reason = None

        # Try SEC 13F for institutional holdings (Phase 2)
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT institutional_ownership_pct, data_unavailable, reason
                FROM institutional_holdings_13f
                WHERE symbol = %s AND data_unavailable = FALSE
                ORDER BY filing_date DESC LIMIT 1
                """,
                (symbol,),
            )
            sec_inst_row = cur.fetchone()

        if sec_inst_row and sec_inst_row[0] is not None:
            institutional_pct = sec_inst_row[0]
        else:
            sec_unavailable = True
            sec_reason = "sec_13f_unavailable"

        # Try SEC Form 4/5 for insider holdings (Phase 2)
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT insider_ownership_pct, data_unavailable, reason
                FROM insider_holdings_sec
                WHERE symbol = %s AND data_unavailable = FALSE
                ORDER BY filing_date DESC LIMIT 1
                """,
                (symbol,),
            )
            sec_insider_row = cur.fetchone()

        if sec_insider_row and sec_insider_row[0] is not None:
            insider_pct = sec_insider_row[0]
        else:
            sec_unavailable = True

        # Fallback to yfinance if SEC data unavailable
        if institutional_pct is None or insider_pct is None:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT
                        held_percent_institutions,
                        held_percent_insiders,
                        data_available,
                        unavailable_reason
                    FROM yfinance_snapshot
                    WHERE symbol = %s
                    """,
                    (symbol,),
                )
                yfinance_row = cur.fetchone()

            if yfinance_row:
                if institutional_pct is None:
                    institutional_pct = yfinance_row[0]
                if insider_pct is None:
                    insider_pct = yfinance_row[1]
                yfinance_unavailable = not yfinance_row[2] if len(yfinance_row) > 2 else False
                yfinance_reason = yfinance_row[3] if len(yfinance_row) > 3 else None
            else:
                yfinance_unavailable = True
                yfinance_reason = "yfinance_snapshot_missing"

        # Combine metrics: if any source has data, mark as available
        all_unavailable = short_interest_unavailable and yfinance_unavailable

        return [
            {
                "symbol": symbol,
                "institutional_ownership_pct": institutional_pct,
                "insider_ownership_pct": insider_pct,
                "short_interest_pct": short_interest_pct,
                "data_unavailable": all_unavailable,
                "reason": (
                    f"short_interest_reason:{short_interest_reason};yfinance_reason:{yfinance_reason}"
                    if all_unavailable
                    else None
                ),
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
