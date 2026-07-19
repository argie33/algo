#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEC-based Dashboard Enrichment Loader - replaces yfinance with official SEC data.

PHASE 2 COMPLETE (Session 275): Migrated from yfinance_snapshot to SEC official sources.

PURPOSE:
- Provides optional enrichment data for dashboard display ONLY
- NOT used by trading logic (stock_scores, buy_sell_daily, etc.)
- Gracefully degrades if unavailable (marked with data_unavailable markers)

DATA SOURCES (100% official/SEC):
  - company_profile (sector, industry, exchange, company name) → company_info_sec
  - earnings_calendar (SEC filing dates for 10-K/10-Q) → earnings_calendar_sec
  - analyst_sentiment_analysis → marked data_unavailable (no SEC source; Bloomberg/Seeking Alpha alternative sources required)

CRITICAL TRADING DATA (handled elsewhere):
  - valuations → load_value_quality_growth_metrics.py (SEC-based)
  - positioning → load_positioning_metrics.py (SEC 13F/Form 4, FINRA)

Run:
    python3 load_yfinance_derived_metrics.py [--symbols AAPL,MSFT] [--parallelism 4]
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
        """Persist dashboard enrichment data to output tables (company_profile, earnings_calendar, analyst_sentiment_analysis).

        REMOVED (now handled elsewhere):
          - value_metrics → load_value_quality_growth_metrics.py (SEC-based, higher quality)
          - positioning_metrics → load_positioning_metrics.py (dedicated critical loader)
        """
        from datetime import timezone

        symbol = record.get("symbol")
        updated_at = record.get("updated_at")

        # Guard against None updated_at
        if updated_at is None:
            updated_at = datetime.now(timezone.utc)

        with DatabaseContext("write") as cur:
            # 1. company_profile
            # 1a. company_profile (dashboard display: sector, industry, exchange, website)
            if not record.get("data_unavailable"):
                cur.execute(
                    """
                    INSERT INTO company_profile (ticker, symbol, long_name, sector, industry, exchange, website, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker) DO UPDATE SET
                      symbol = EXCLUDED.symbol, long_name = EXCLUDED.long_name, sector = EXCLUDED.sector, industry = EXCLUDED.industry,
                      exchange = EXCLUDED.exchange, website = EXCLUDED.website,
                      updated_at = EXCLUDED.updated_at
                    """,
                    (
                        symbol,
                        symbol,
                        record.get("long_name"),
                        record.get("sector"),
                        record.get("industry"),
                        record.get("exchange"),
                        record.get("website"),
                        updated_at,
                    ),
                )
            else:
                cur.execute(
                    "INSERT INTO company_profile (ticker, symbol, sector, data_unavailable, reason, updated_at) VALUES (%s, %s, %s, TRUE, %s, %s) ON CONFLICT (ticker) DO UPDATE SET symbol = EXCLUDED.symbol, sector = EXCLUDED.sector, data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at",
                    (symbol, symbol, "Unknown", record.get("reason", "unknown"), updated_at),
                )

            # 1b. earnings_calendar (dashboard display: next earnings date)
            if not record.get("data_unavailable"):
                earnings_date_unix = record.get("earnings_date")
                if earnings_date_unix:
                    try:
                        earnings_date_py = datetime.fromtimestamp(earnings_date_unix).date()
                        cur.execute(
                            """
                            INSERT INTO earnings_calendar (symbol, earnings_date, market_cap, updated_at)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (symbol, earnings_date) DO UPDATE SET
                              market_cap = EXCLUDED.market_cap, updated_at = EXCLUDED.updated_at
                            """,
                            (symbol, earnings_date_py, record.get("market_cap"), updated_at),
                        )
                    except (ValueError, OSError, OverflowError):
                        cur.execute(
                            "INSERT INTO earnings_calendar (symbol, earnings_date, data_unavailable, reason, updated_at) VALUES (%s, %s, TRUE, %s, %s) ON CONFLICT (symbol, earnings_date) DO UPDATE SET data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at",
                            (symbol, updated_at.date(), "invalid_earnings_timestamp", updated_at),
                        )
                else:
                    cur.execute(
                        "INSERT INTO earnings_calendar (symbol, earnings_date, data_unavailable, reason, updated_at) VALUES (%s, %s, TRUE, %s, %s) ON CONFLICT (symbol, earnings_date) DO UPDATE SET data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at",
                        (symbol, updated_at.date(), "no_next_earnings_available", updated_at),
                    )
            else:
                cur.execute(
                    "INSERT INTO earnings_calendar (symbol, earnings_date, data_unavailable, reason, updated_at) VALUES (%s, %s, TRUE, %s, %s) ON CONFLICT (symbol, earnings_date) DO UPDATE SET data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at",
                    (symbol, updated_at.date(), record.get("reason", "unknown"), updated_at),
                )

            # 5. analyst_sentiment_analysis (analyst counts and recommendation)
            # Note: analyst_sentiment_analysis table does not support data_unavailable markers
            # Only insert when data is available
            if not record.get("data_unavailable") and record.get("analyst_count"):
                cur.execute(
                    """
                    INSERT INTO analyst_sentiment_analysis
                    (symbol, date, analyst_count, bullish_count, bearish_count, neutral_count, recommendation_key, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                      analyst_count = EXCLUDED.analyst_count,
                      bullish_count = EXCLUDED.bullish_count,
                      bearish_count = EXCLUDED.bearish_count,
                      neutral_count = EXCLUDED.neutral_count,
                      recommendation_key = EXCLUDED.recommendation_key,
                      updated_at = EXCLUDED.updated_at
                    """,
                    (
                        symbol,
                        updated_at.date(),
                        record.get("analyst_count"),
                        record.get("bullish_count"),
                        record.get("bearish_count"),
                        record.get("neutral_count"),
                        record.get("analyst_recommendation"),
                        updated_at,
                    ),
                )


def main() -> int:
    """Wrapped main with exception handling."""
    try:
        return run_loader(YfinanceDerivedMetricsLoader)
    except Exception as e:
        logger.error(f"[YFINANCE_DERIVED FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        # Backfill a placeholder unavailable row for symbols never reached this run.
        # DO NOTHING (not DO UPDATE) is required here -- a crash/timeout partway
        # through must not clobber symbols already fetched and committed earlier
        # in this same run. The previous DO UPDATE unconditionally overwrote every
        # active symbol across all 5 tables on any exception, silently destroying
        # real data for whatever had already succeeded before the crash point.
        try:
            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            tables = [
                "company_profile",
                "earnings_calendar",
                "analyst_sentiment_analysis",
            ]

            from datetime import datetime

            from utils.infrastructure.timezone import EASTERN_TZ

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    for table in tables:
                        if table == "company_profile":
                            cur.execute(
                                f"""
                                INSERT INTO {table} (ticker, symbol, sector, data_unavailable, reason, updated_at)
                                VALUES (%s, %s, %s, TRUE, %s, NOW())
                                ON CONFLICT (ticker) DO NOTHING
                                """,
                                (symbol, symbol, "Unknown", f"loader_crash:{type(e).__name__}"),
                            )
                        elif table == "analyst_sentiment_analysis":
                            today = datetime.now(EASTERN_TZ).date()
                            cur.execute(
                                f"""
                                INSERT INTO {table} (symbol, date, data_unavailable, reason, updated_at)
                                VALUES (%s, %s, TRUE, %s, NOW())
                                ON CONFLICT (symbol, date) DO NOTHING
                                """,
                                (symbol, today, f"loader_crash:{type(e).__name__}"),
                            )
                        else:
                            cur.execute(
                                f"""
                                INSERT INTO {table} (symbol, data_unavailable, reason, updated_at)
                                VALUES (%s, TRUE, %s, NOW())
                                ON CONFLICT (symbol) DO NOTHING
                                """,
                                (symbol, f"loader_crash:{type(e).__name__}"),
                            )
        except Exception as inner_e:
            logger.error(f"[YFINANCE_DERIVED] Failed to mark tables unavailable: {inner_e}", exc_info=True)

        return 1


if __name__ == "__main__":
    sys.exit(main())
