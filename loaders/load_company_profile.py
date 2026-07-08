#!/usr/bin/env python3
"""Company Profile Loader - reads from yfinance_snapshot table (not API).

CRITICAL FIX 2026-07-02: Consolidated yfinance calls into single yfinance_snapshot loader.
This loader reads sector, industry, exchange, website from yfinance_snapshot table
instead of making direct yfinance API calls.

Result: Eliminates 5000 redundant yfinance API calls per run.
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class CompanyProfileLoader(OptimalLoader):
    """Read company profiles from yfinance_snapshot table (cached snapshot, not API)."""

    table_name = "company_profile"
    primary_key = ("ticker",)
    watermark_field = "created_at"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Read company profile from yfinance_snapshot table.

        Governance: Mark unavailable data explicitly. No silent fallbacks or exceptions.
        Returns data_unavailable marker instead of raising exceptions per GOVERNANCE.md.

        yfinance_snapshot loader (run BEFORE this) fetches all yfinance data once per symbol
        and stores in yfinance_snapshot table. This loader reads from that table.

        Returns:
            list[dict]: Either company profile data or data_unavailable marker
        """
        # Get current timestamp in Eastern timezone for created_at watermark
        now_utc = datetime.now(EASTERN_TZ)

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
            # yfinance_snapshot row not found — upstream loader dependency missing
            logger.debug(f"[COMPANY_PROFILE] {symbol}: yfinance_snapshot row not found (upstream dependency)")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "yfinance_snapshot_missing",
                    "created_at": now_utc,
                }
            ]

        if not row.get("data_available"):
            # yfinance data explicitly marked unavailable
            reason = row.get("unavailable_reason", "yfinance_api_unavailable")
            logger.debug(f"[COMPANY_PROFILE] {symbol}: yfinance_snapshot marked unavailable ({reason})")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"yfinance_snapshot_unavailable:{reason}",
                    "created_at": now_utc,
                }
            ]

        company_name = row["long_name"]
        exchange = row["exchange"]
        sector = row["sector"]
        industry = row["industry"]

        # Check for missing required fields (legitimate for micro-caps, foreign stocks, delisted)
        missing_fields = []
        if not company_name:
            missing_fields.append("company_name")
        if not exchange:
            missing_fields.append("exchange")
        if not sector:
            missing_fields.append("sector")
        if not industry:
            missing_fields.append("industry")

        if missing_fields:
            # Some stocks don't have complete classification (micro-caps, foreign, delisted)
            logger.debug(
                f"[COMPANY_PROFILE] {symbol}: Missing classification fields: {', '.join(missing_fields)} "
                f"(legitimate for micro-caps, foreign stocks, or delisted)"
            )
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"missing_fields:{','.join(missing_fields)}",
                    "created_at": now_utc,
                }
            ]

        logger.debug(
            f"[COMPANY_PROFILE] {symbol}: Loaded profile (name={company_name}, sector={sector}, industry={industry})"
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
                "data_unavailable": False,
                "created_at": now_utc,
            }
        ]


def main() -> int:
    """Wrapped main with exception handling for data_unavailable markers."""
    try:
        return run_loader(CompanyProfileLoader)
    except Exception as e:
        logger.error(f"[COMPANY_PROFILE FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        # Mark data unavailable for all symbols
        try:
            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    cur.execute(
                        """
                        INSERT INTO company_profile (symbol, data_unavailable, reason, updated_at)
                        VALUES (%s, TRUE, %s, NOW())
                        ON CONFLICT (symbol) DO UPDATE SET
                          data_unavailable = TRUE,
                          reason = EXCLUDED.reason,
                          updated_at = NOW()
                    """,
                        (symbol, f"loader_crash:{type(e).__name__}"),
                    )
        except Exception as mark_err:
            logger.error(f"Failed to mark company_profile data unavailable: {mark_err}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
