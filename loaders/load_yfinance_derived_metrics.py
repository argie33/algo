#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DEPRECATED (Session 276): Dashboard Enrichment Loader - NO LONGER USED.

DEPRECATION NOTICE: This loader is NOT called by the orchestrator.
It is kept for historical reference only.

The functionality has been replaced by:
- company_profile → load_company_info_sec.py
- earnings_calendar → load_earnings_calendar_sec.py
- analyst_sentiment → marked data_unavailable (no SEC source)

If you need dashboard enrichment data, use the individual loaders above.

DEPRECATED 2026-07-19 (Session 276): Removed from orchestrator execution.
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


class YfinanceDerivedMetricsLoader(OptimalLoader):
    """Read metrics from SEC sources, write to dashboard-only tables.

    PHASE 2 COMPLETE (Session 275): 100% SEC data sources (no yfinance).

    DASHBOARD ENRICHMENT ONLY:
      - company_profile → reads from company_info_sec (sector, industry, exchange, company name)
      - earnings_calendar → reads from earnings_calendar_sec (SEC filing dates)
      - analyst_sentiment_analysis → marked data_unavailable (no SEC source; requires Bloomberg/Seeking Alpha)

    If this loader fails, dashboard shows "N/A" for company profile/earnings/analyst data.
    Trading logic is unaffected (stock_scores, signals, etc.).
    """

    table_name = "company_profile"
    primary_key = ("ticker",)
    watermark_field = "updated_at"
    exclude_etfs_from_symbols = True

    OUTPUT_TABLES = [
        "company_profile",
        "earnings_calendar",
        "analyst_sentiment_analysis",
    ]

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Read metrics from SEC sources (company_info_sec, earnings_calendar_sec).

        Returns consolidated record with all dashboard enrichment data.
        """
        now_et = datetime.now(EASTERN_TZ)

        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT entity_name, sic_code, sic_description, exchange, sector
                FROM company_info_sec
                WHERE symbol = %s
                ORDER BY filing_date DESC
                LIMIT 1
                """,
                (symbol,),
            )
            company_row = cur.fetchone()

            cur.execute(
                """
                SELECT filing_date
                FROM earnings_calendar_sec
                WHERE symbol = %s
                ORDER BY filing_date DESC
                LIMIT 1
                """,
                (symbol,),
            )
            earnings_row = cur.fetchone()

        if not company_row:
            logger.debug(f"[SEC_DASHBOARD] {symbol}: company_info_sec row not found")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "company_info_sec_missing",
                    "updated_at": now_et,
                }
            ]

        record = {
            "symbol": symbol,
            "data_unavailable": False,
            "long_name": company_row[0],
            "sector": company_row[4],
            "exchange": company_row[3],
            "earnings_date": earnings_row[0] if earnings_row else None,
            "updated_at": now_et,
        }
        return [record]

    def load_symbol(self, symbol: str) -> int:
        """Override to persist to all output tables instead of single table.

        Returns the number of rows processed (1 if data available, 0 if unavailable).
        """
        rows = self.fetch_incremental(symbol, self._batch_context.get("since") if self._batch_context else None)
        if not rows:
            return 0

        for row in rows:
            self._persist_to_all_tables(row)
        return 1

    def _persist_to_all_tables(self, record: dict[str, Any]) -> None:
        """Persist dashboard enrichment from SEC sources to output tables.

        Tables: company_profile, earnings_calendar, analyst_sentiment_analysis.
        Note: analyst_sentiment_analysis marked data_unavailable (no SEC source for analyst recommendations).
        """
        from datetime import timezone

        symbol = record.get("symbol")
        updated_at = record.get("updated_at")

        if updated_at is None:
            updated_at = datetime.now(timezone.utc)

        with DatabaseContext("write") as cur:
            if not record.get("data_unavailable"):
                cur.execute(
                    """
                    INSERT INTO company_profile (ticker, symbol, long_name, sector, exchange, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker) DO UPDATE SET
                      symbol = EXCLUDED.symbol, long_name = EXCLUDED.long_name, sector = EXCLUDED.sector,
                      exchange = EXCLUDED.exchange, updated_at = EXCLUDED.updated_at
                    """,
                    (
                        symbol,
                        symbol,
                        record.get("long_name"),
                        record.get("sector"),
                        record.get("exchange"),
                        updated_at,
                    ),
                )

                earnings_date = record.get("earnings_date")
                if earnings_date:
                    cur.execute(
                        """
                        INSERT INTO earnings_calendar (symbol, earnings_date, updated_at)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (symbol, earnings_date) DO UPDATE SET updated_at = EXCLUDED.updated_at
                        """,
                        (symbol, earnings_date, updated_at),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO earnings_calendar (symbol, earnings_date, data_unavailable, reason, updated_at)
                        VALUES (%s, %s, TRUE, %s, %s)
                        ON CONFLICT (symbol, earnings_date) DO UPDATE SET
                          data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at
                        """,
                        (symbol, updated_at.date(), "no_earnings_in_sec", updated_at),
                    )
            else:
                cur.execute(
                    """
                    INSERT INTO company_profile (ticker, symbol, sector, data_unavailable, reason, updated_at)
                    VALUES (%s, %s, %s, TRUE, %s, %s)
                    ON CONFLICT (ticker) DO UPDATE SET
                      data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at
                    """,
                    (symbol, symbol, "Unknown", record.get("reason", "unknown"), updated_at),
                )

                cur.execute(
                    """
                    INSERT INTO earnings_calendar (symbol, earnings_date, data_unavailable, reason, updated_at)
                    VALUES (%s, %s, TRUE, %s, %s)
                    ON CONFLICT (symbol, earnings_date) DO UPDATE SET
                      data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at
                    """,
                    (symbol, updated_at.date(), record.get("reason", "unknown"), updated_at),
                )

            today = updated_at.date()
            cur.execute(
                """
                INSERT INTO analyst_sentiment_analysis (symbol, date, data_unavailable, reason, updated_at)
                VALUES (%s, %s, TRUE, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                  data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at
                """,
                (symbol, today, "no_sec_source_for_analyst_data", updated_at),
            )


def main() -> int:
    """Wrapped main with exception handling."""
    try:
        return run_loader(YfinanceDerivedMetricsLoader)
    except Exception as e:
        logger.error(f"[SEC_DASHBOARD] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        try:
            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            today = datetime.now(EASTERN_TZ).date()
            now = datetime.now(EASTERN_TZ)

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    cur.execute(
                        """
                        INSERT INTO company_profile (ticker, symbol, sector, data_unavailable, reason, updated_at)
                        VALUES (%s, %s, %s, TRUE, %s, %s)
                        ON CONFLICT (ticker) DO NOTHING
                        """,
                        (symbol, symbol, "Unknown", f"loader_crash:{type(e).__name__}", now),
                    )
                    cur.execute(
                        """
                        INSERT INTO earnings_calendar (symbol, earnings_date, data_unavailable, reason, updated_at)
                        VALUES (%s, %s, TRUE, %s, %s)
                        ON CONFLICT (symbol, earnings_date) DO NOTHING
                        """,
                        (symbol, today, f"loader_crash:{type(e).__name__}", now),
                    )
                    cur.execute(
                        """
                        INSERT INTO analyst_sentiment_analysis (symbol, date, data_unavailable, reason, updated_at)
                        VALUES (%s, %s, TRUE, %s, %s)
                        ON CONFLICT (symbol, date) DO NOTHING
                        """,
                        (symbol, today, f"loader_crash:{type(e).__name__}", now),
                    )
        except Exception as inner_e:
            logger.error(f"[SEC_DASHBOARD] Failed to mark tables unavailable: {inner_e}", exc_info=True)

        return 1


if __name__ == "__main__":
    sys.exit(main())
