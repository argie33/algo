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
        """Fetch positioning metrics for a symbol from authoritative sources with fallback.

        DATA SOURCE HIERARCHY:
        - short_interest: (1) FINRA Reg SHO, (2) yfinance_snapshot fallback
        - institutional_ownership: (1) SEC 13F filings, (2) yfinance_snapshot fallback
        - insider_ownership: (1) SEC Form 4/5 filings, (2) yfinance_snapshot fallback

        Returns positioning data with source tracking, or data_unavailable only if ALL sources fail.
        """
        now_et = datetime.now(EASTERN_TZ)

        # Fetch short interest: FINRA first, then yfinance fallback
        short_interest_pct = None
        short_interest_source = None

        with DatabaseContext("read") as cur:
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
            short_interest_pct = short_row[0]
            short_interest_source = "finra"
        else:
            # FINRA missing - fallback to yfinance
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT short_interest
                    FROM yfinance_snapshot
                    WHERE symbol = %s AND short_interest IS NOT NULL
                    ORDER BY fetched_at DESC LIMIT 1
                    """,
                    (symbol,),
                )
                yf_short = cur.fetchone()
            if yf_short and yf_short[0] is not None:
                short_interest_pct = yf_short[0]
                short_interest_source = "yfinance"
            else:
                short_interest_source = "unavailable"

        # Fetch institutional ownership: SEC 13F first, then yfinance fallback
        institutional_pct = None
        institutional_source = None

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
            institutional_source = "sec_13f"
        else:
            # SEC 13F missing - fallback to yfinance
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT held_percent_institutions
                    FROM yfinance_snapshot
                    WHERE symbol = %s AND held_percent_institutions IS NOT NULL
                    ORDER BY fetched_at DESC LIMIT 1
                    """,
                    (symbol,),
                )
                yf_inst = cur.fetchone()
            if yf_inst and yf_inst[0] is not None:
                institutional_pct = yf_inst[0]
                institutional_source = "yfinance"
            else:
                institutional_source = "unavailable"

        # Fetch insider ownership: SEC Form 4/5 first, then yfinance fallback
        insider_pct = None
        insider_source = None

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
            insider_source = "sec_form4"
        else:
            # SEC Form 4/5 missing - fallback to yfinance
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT held_percent_insiders
                    FROM yfinance_snapshot
                    WHERE symbol = %s AND held_percent_insiders IS NOT NULL
                    ORDER BY fetched_at DESC LIMIT 1
                    """,
                    (symbol,),
                )
                yf_insider = cur.fetchone()
            if yf_insider and yf_insider[0] is not None:
                insider_pct = yf_insider[0]
                insider_source = "yfinance"
            else:
                insider_source = "unavailable"

        # Mark unavailable only if ALL three sources missing (any one source makes data available)
        all_unavailable = (
            short_interest_source == "unavailable"
            and institutional_source == "unavailable"
            and insider_source == "unavailable"
        )

        return [
            {
                "symbol": symbol,
                "institutional_ownership": institutional_pct,
                "insider_ownership": insider_pct,
                "short_interest_pct": short_interest_pct,
                "data_unavailable": all_unavailable,
                "reason": (
                    f"short_interest:{short_interest_source};institutional:{institutional_source};insider:{insider_source}"
                    if all_unavailable
                    else None
                ),
                "data_source": (
                    short_interest_source if short_interest_source != "unavailable"
                    else institutional_source if institutional_source != "unavailable"
                    else insider_source if insider_source != "unavailable"
                    else "none"
                ),
                "updated_at": now_et,
            }
        ]


if __name__ == "__main__":
    sys.exit(run_loader(PositioningMetricsLoader, description="Load positioning metrics from SEC + yfinance"))
