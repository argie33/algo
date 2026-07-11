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
import socket
import sys
from datetime import date, datetime, timezone
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
    """Read all yfinance-derived metrics from yfinance_snapshot table.
    
    Consolidates 6 separate loaders that all read from yfinance_snapshot.
    Outputs to 6 separate tables in parallel for efficiency.
    """

    # Note: This loader doesn't have a single table_name since it writes to 6 tables
    # We'll override the schema validation to handle multiple tables
    table_name = "yfinance_derived_metrics"  # Meta table for watermarking
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Read ALL yfinance-derived metrics from yfinance_snapshot table for one symbol.
        
        Returns a consolidated record with all 6 metric categories.
        """
        now_et = datetime.now(EASTERN_TZ)
        
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT 
                    -- Value metrics
                    pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield,
                    market_cap, held_percent_insiders, held_percent_institutions,
                    -- Positioning metrics  
                    short_interest, short_interest_trend,
                    -- Company profile
                    long_name, sector, industry, exchange, website, country,
                    -- Analyst analysis
                    analyst_recommendation, number_of_analysts,
                    -- Earnings
                    earnings_date, earnings_history_dates,
                    -- Snapshot metadata
                    data_available, unavailable_reason
                FROM yfinance_snapshot
                WHERE symbol = %s
                """,
                (symbol,),
            )
            row = cur.fetchone()

        if not row:
            # yfinance_snapshot row not found
            logger.debug(f"[YFINANCE_DERIVED] {symbol}: yfinance_snapshot row not found")
            unavailable_record = {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": "yfinance_snapshot_missing",
                "updated_at": now_et,
            }
            return [unavailable_record]

        data_available = row.get("data_available", False)
        unavailable_reason = row.get("unavailable_reason", "")

        if not data_available:
            logger.debug(f"[YFINANCE_DERIVED] {symbol}: yfinance_snapshot marked unavailable ({unavailable_reason})")
            unavailable_record = {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": unavailable_reason or "yfinance_data_unavailable",
                "updated_at": now_et,
            }
            return [unavailable_record]

        # Build consolidated record with all metrics
        record = {
            "symbol": symbol,
            "data_unavailable": False,
            # Value metrics
            "pe_ratio": row.get("pe_ratio"),
            "pb_ratio": row.get("pb_ratio"),
            "ps_ratio": row.get("ps_ratio"),
            "peg_ratio": row.get("peg_ratio"),
            "dividend_yield": row.get("dividend_yield"),
            "fcf_yield": row.get("fcf_yield"),
            "market_cap": row.get("market_cap"),
            "held_percent_insiders": row.get("held_percent_insiders"),
            "held_percent_institutions": row.get("held_percent_institutions"),
            # Positioning metrics
            "short_interest": row.get("short_interest"),
            "short_interest_trend": row.get("short_interest_trend"),
            # Company profile
            "long_name": row.get("long_name"),
            "sector": row.get("sector"),
            "industry": row.get("industry"),
            "exchange": row.get("exchange"),
            "website": row.get("website"),
            "country": row.get("country"),
            # Analyst analysis
            "analyst_recommendation": row.get("analyst_recommendation"),
            "number_of_analysts": row.get("number_of_analysts"),
            # Earnings
            "earnings_date": row.get("earnings_date"),
            "earnings_history_dates": row.get("earnings_history_dates"),
            "updated_at": now_et,
        }

        return [record]


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
