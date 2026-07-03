#!/usr/bin/env python3
"""Company Profile Loader - reads from yfinance_snapshot table (not API).

CRITICAL FIX 2026-07-02: Consolidated yfinance calls into single yfinance_snapshot loader.
This loader reads sector, industry, exchange, website from yfinance_snapshot table
instead of making direct yfinance API calls.

Result: Eliminates 5000 redundant yfinance API calls per run.
"""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class CompanyProfileLoader(OptimalLoader):
    """Read company profiles from yfinance_snapshot table (cached snapshot, not API)."""

    table_name = "company_profile"
    primary_key = ("ticker",)
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Read company profile from yfinance_snapshot table.

        Governance: Fail-fast on missing data. No silent fallbacks.

        yfinance_snapshot loader (run BEFORE this) fetches all yfinance data once per symbol
        and stores in yfinance_snapshot table. This loader reads from that table.

        Raises RuntimeError if snapshot data unavailable (upstream loader dependency).
        """
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT long_name, sector, industry, exchange, website, market_cap,
                       country, data_available, unavailable_reason
                FROM yfinance_snapshot
                WHERE symbol = %s
                """,
                (symbol,),
            )
            row = cur.fetchone()

        if not row:
            raise RuntimeError(
                f"[COMPANY_PROFILE] {symbol}: yfinance_snapshot row not found. "
                f"Upstream loader (load_yfinance_snapshot) must run first. "
                f"Cannot fetch company profile without snapshot data."
            )

        if not row.get("data_available"):
            raise RuntimeError(
                f"[COMPANY_PROFILE] {symbol}: yfinance_snapshot data marked unavailable. "
                f"Reason: {row.get('unavailable_reason', 'unknown')}. "
                f"Cannot proceed without company profile data from yfinance."
            )

        company_name = row["long_name"]
        exchange = row["exchange"]
        sector = row["sector"]
        industry = row["industry"]

        # REQUIRED fields - fail-fast if missing
        if not company_name or not exchange or not sector or not industry:
            raise RuntimeError(
                f"[COMPANY_PROFILE] {symbol}: Missing required fields from snapshot. "
                f"Got: name={company_name}, exchange={exchange}, sector={sector}, industry={industry}. "
                f"Cannot compute portfolio metrics without complete company classification."
            )

        logger.info(
            f"[COMPANY_PROFILE] {symbol}: Successfully loaded profile from snapshot "
            f"(name={company_name}, exchange={exchange}, sector={sector}, industry={industry})"
        )

        return [
            {
                "symbol": symbol,
                "ticker": symbol,
                "short_name": company_name,
                "long_name": company_name,
                "display_name": company_name,
                "sector": sector,
                "industry": industry,
                "exchange": exchange,
                "website": row["website"],
                "country": row["country"],
                "market_cap": (int(row["market_cap"]) if row["market_cap"] and row["market_cap"] > 0 else None),
            }
        ]


if __name__ == "__main__":
    sys.exit(run_loader(CompanyProfileLoader))
