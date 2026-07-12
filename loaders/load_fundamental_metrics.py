#!/usr/bin/env python3
"""Consolidated Yfinance Derived Metrics Loader - reads from yfinance_snapshot once, outputs to 6 tables.

CONSOLIDATION: Merges 6 separate loaders into one:
  - load_value_metrics.py → value_metrics table
  - load_positioning_metrics.py → positioning_metrics table
  - load_company_profile.py → company_profile table
  - load_analyst_analysis.py → analyst_sentiment_analysis + analyst_upgrade_downgrade tables
  - load_earnings_calendar.py → earnings_calendar table
  - load_earnings_history.py → earnings_history table

All 6 loaders read from the same upstream table (yfinance_snapshot).
This consolidation:
  - Eliminates 5 redundant ECS tasks per run
  - Reduces 4:20 PM pipeline bottleneck
  - Parallelizes output writes to 6 tables
  - Single point of failure vs 6

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
    """Read all yfinance-derived metrics from yfinance_snapshot table and persist to 7 tables.

    Consolidates 6 separate loaders into one, writing to 7 output tables in parallel:
      - value_metrics (1 table)
      - positioning_metrics (1 table)
      - company_profile (1 table)
      - analyst_sentiment_analysis (1 table)
      - analyst_upgrade_downgrade (1 table)
      - earnings_calendar (1 table)
      - earnings_history (1 table)
    """

    table_name = "yfinance_derived_metrics"  # Meta table for watermarking & locking
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    exclude_etfs_from_symbols = True

    OUTPUT_TABLES = [
        "value_metrics",
        "positioning_metrics",
        "company_profile",
        "analyst_sentiment_analysis",
        "analyst_upgrade_downgrade",
        "earnings_calendar",
        "earnings_history",
    ]

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Read ALL yfinance-derived metrics from yfinance_snapshot table for one symbol.

        Returns a consolidated record with all metric categories.
        """
        now_et = datetime.now(EASTERN_TZ)

        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT
                    pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield,
                    market_cap, held_percent_insiders, held_percent_institutions,
                    short_interest, short_interest_trend,
                    long_name, sector, industry, exchange, website, country,
                    analyst_recommendation, number_of_analysts,
                    earnings_date, earnings_history_dates,
                    data_available, unavailable_reason
                FROM yfinance_snapshot
                WHERE symbol = %s
                """,
                (symbol,),
            )
            row = cur.fetchone()

        if not row:
            logger.debug(f"[YFINANCE_DERIVED] {symbol}: yfinance_snapshot row not found")
            return [{"symbol": symbol, "data_unavailable": True, "reason": "yfinance_snapshot_missing", "updated_at": now_et}]

        data_available = row.get("data_available", False)
        unavailable_reason = row.get("unavailable_reason", "")

        if not data_available:
            logger.debug(f"[YFINANCE_DERIVED] {symbol}: yfinance_snapshot marked unavailable ({unavailable_reason})")
            return [{"symbol": symbol, "data_unavailable": True, "reason": unavailable_reason or "yfinance_data_unavailable", "updated_at": now_et}]

        # Build consolidated record with all metrics
        record = {
            "symbol": symbol,
            "data_unavailable": False,
            "pe_ratio": row.get("pe_ratio"),
            "pb_ratio": row.get("pb_ratio"),
            "ps_ratio": row.get("ps_ratio"),
            "peg_ratio": row.get("peg_ratio"),
            "dividend_yield": row.get("dividend_yield"),
            "fcf_yield": row.get("fcf_yield"),
            "market_cap": row.get("market_cap"),
            "held_percent_insiders": row.get("held_percent_insiders"),
            "held_percent_institutions": row.get("held_percent_institutions"),
            "short_interest": row.get("short_interest"),
            "short_interest_trend": row.get("short_interest_trend"),
            "long_name": row.get("long_name"),
            "sector": row.get("sector"),
            "industry": row.get("industry"),
            "exchange": row.get("exchange"),
            "website": row.get("website"),
            "country": row.get("country"),
            "analyst_recommendation": row.get("analyst_recommendation"),
            "number_of_analysts": row.get("number_of_analysts"),
            "earnings_date": row.get("earnings_date"),
            "earnings_history_dates": row.get("earnings_history_dates"),
            "updated_at": now_et,
        }
        return [record]

    def load_symbol(self, symbol: str) -> None:
        """Override to persist to all 7 output tables instead of single table."""
        rows = self.fetch_incremental(symbol, self._batch_context.get("since") if self._batch_context else None)
        if not rows:
            return

        for row in rows:
            self._persist_to_all_tables(row)

    def _persist_to_all_tables(self, record: dict[str, Any]) -> None:
        """Persist consolidated record to all 7 output tables."""
        symbol = record.get("symbol")
        updated_at = record.get("updated_at")

        with DatabaseContext("write") as cur:
            # 1. value_metrics
            if not record.get("data_unavailable"):
                cur.execute(
                    """
                    INSERT INTO value_metrics
                    (symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield,
                     market_cap, held_percent_insiders, held_percent_institutions, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                      pe_ratio = EXCLUDED.pe_ratio, pb_ratio = EXCLUDED.pb_ratio,
                      ps_ratio = EXCLUDED.ps_ratio, peg_ratio = EXCLUDED.peg_ratio,
                      dividend_yield = EXCLUDED.dividend_yield, fcf_yield = EXCLUDED.fcf_yield,
                      market_cap = EXCLUDED.market_cap, held_percent_insiders = EXCLUDED.held_percent_insiders,
                      held_percent_institutions = EXCLUDED.held_percent_institutions, updated_at = EXCLUDED.updated_at
                    """,
                    (symbol, record.get("pe_ratio"), record.get("pb_ratio"), record.get("ps_ratio"),
                     record.get("peg_ratio"), record.get("dividend_yield"), record.get("fcf_yield"),
                     record.get("market_cap"), record.get("held_percent_insiders"),
                     record.get("held_percent_institutions"), updated_at),
                )
            else:
                cur.execute(
                    "INSERT INTO value_metrics (symbol, data_unavailable, reason, updated_at) VALUES (%s, TRUE, %s, %s) ON CONFLICT (symbol) DO UPDATE SET data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at",
                    (symbol, record.get("reason", "unknown"), updated_at),
                )

            # 2. positioning_metrics
            if not record.get("data_unavailable"):
                cur.execute(
                    """
                    INSERT INTO positioning_metrics (symbol, short_interest, short_interest_trend, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                      short_interest = EXCLUDED.short_interest, short_interest_trend = EXCLUDED.short_interest_trend,
                      updated_at = EXCLUDED.updated_at
                    """,
                    (symbol, record.get("short_interest"), record.get("short_interest_trend"), updated_at),
                )
            else:
                cur.execute(
                    "INSERT INTO positioning_metrics (symbol, data_unavailable, reason, updated_at) VALUES (%s, TRUE, %s, %s) ON CONFLICT (symbol) DO UPDATE SET data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at",
                    (symbol, record.get("reason", "unknown"), updated_at),
                )

            # 3. company_profile
            if not record.get("data_unavailable"):
                cur.execute(
                    """
                    INSERT INTO company_profile (symbol, long_name, sector, industry, exchange, website, country, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                      long_name = EXCLUDED.long_name, sector = EXCLUDED.sector, industry = EXCLUDED.industry,
                      exchange = EXCLUDED.exchange, website = EXCLUDED.website, country = EXCLUDED.country,
                      updated_at = EXCLUDED.updated_at
                    """,
                    (symbol, record.get("long_name"), record.get("sector"), record.get("industry"),
                     record.get("exchange"), record.get("website"), record.get("country"), updated_at),
                )
            else:
                cur.execute(
                    "INSERT INTO company_profile (symbol, data_unavailable, reason, updated_at) VALUES (%s, TRUE, %s, %s) ON CONFLICT (symbol) DO UPDATE SET data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at",
                    (symbol, record.get("reason", "unknown"), updated_at),
                )

            # 4. analyst_sentiment_analysis
            if not record.get("data_unavailable"):
                cur.execute(
                    """
                    INSERT INTO analyst_sentiment_analysis (symbol, analyst_recommendation, number_of_analysts, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                      analyst_recommendation = EXCLUDED.analyst_recommendation, number_of_analysts = EXCLUDED.number_of_analysts,
                      updated_at = EXCLUDED.updated_at
                    """,
                    (symbol, record.get("analyst_recommendation"), record.get("number_of_analysts"), updated_at),
                )
            else:
                cur.execute(
                    "INSERT INTO analyst_sentiment_analysis (symbol, data_unavailable, reason, updated_at) VALUES (%s, TRUE, %s, %s) ON CONFLICT (symbol) DO UPDATE SET data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at",
                    (symbol, record.get("reason", "unknown"), updated_at),
                )

            # 5. analyst_upgrade_downgrade
            if not record.get("data_unavailable"):
                cur.execute(
                    """
                    INSERT INTO analyst_upgrade_downgrade (symbol, analyst_recommendation, number_of_analysts, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                      analyst_recommendation = EXCLUDED.analyst_recommendation, number_of_analysts = EXCLUDED.number_of_analysts,
                      updated_at = EXCLUDED.updated_at
                    """,
                    (symbol, record.get("analyst_recommendation"), record.get("number_of_analysts"), updated_at),
                )
            else:
                cur.execute(
                    "INSERT INTO analyst_upgrade_downgrade (symbol, data_unavailable, reason, updated_at) VALUES (%s, TRUE, %s, %s) ON CONFLICT (symbol) DO UPDATE SET data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at",
                    (symbol, record.get("reason", "unknown"), updated_at),
                )

            # 6. earnings_calendar
            if not record.get("data_unavailable"):
                cur.execute(
                    """
                    INSERT INTO earnings_calendar (symbol, earnings_date, updated_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                      earnings_date = EXCLUDED.earnings_date, updated_at = EXCLUDED.updated_at
                    """,
                    (symbol, record.get("earnings_date"), updated_at),
                )
            else:
                cur.execute(
                    "INSERT INTO earnings_calendar (symbol, data_unavailable, reason, updated_at) VALUES (%s, TRUE, %s, %s) ON CONFLICT (symbol) DO UPDATE SET data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at",
                    (symbol, record.get("reason", "unknown"), updated_at),
                )

            # 7. earnings_history
            if not record.get("data_unavailable"):
                cur.execute(
                    """
                    INSERT INTO earnings_history (symbol, earnings_dates, updated_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                      earnings_dates = EXCLUDED.earnings_dates, updated_at = EXCLUDED.updated_at
                    """,
                    (symbol, record.get("earnings_history_dates"), updated_at),
                )
            else:
                cur.execute(
                    "INSERT INTO earnings_history (symbol, data_unavailable, reason, updated_at) VALUES (%s, TRUE, %s, %s) ON CONFLICT (symbol) DO UPDATE SET data_unavailable = TRUE, reason = EXCLUDED.reason, updated_at = EXCLUDED.updated_at",
                    (symbol, record.get("reason", "unknown"), updated_at),
                )


def main() -> int:
    """Wrapped main with exception handling."""
    try:
        return run_loader(YfinanceDerivedMetricsLoader)
    except Exception as e:
        logger.error(
            f"[YFINANCE_DERIVED FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}",
            exc_info=True
        )
        # Mark all 6 output tables unavailable
        try:
            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            tables = [
                "value_metrics",
                "positioning_metrics",
                "company_profile",
                "analyst_sentiment_analysis",
                "analyst_upgrade_downgrade",
                "earnings_calendar",
                "earnings_history",
            ]

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    for table in tables:
                        cur.execute(
                            f"""
                            INSERT INTO {table} (symbol, data_unavailable, reason, updated_at)
                            VALUES (%s, TRUE, %s, NOW())
                            ON CONFLICT (symbol) DO UPDATE SET
                              data_unavailable = TRUE,
                              reason = EXCLUDED.reason,
                              updated_at = NOW()
                            """,
                            (symbol, f"loader_crash:{type(e).__name__}"),
                        )
        except Exception as inner_e:
            logger.error(f"[YFINANCE_DERIVED] Failed to mark tables unavailable: {inner_e}", exc_info=True)

        return 1


if __name__ == "__main__":
    sys.exit(main())
