#!/usr/bin/env python3
"""Consolidated Analyst Analysis Loader - reads analyst sentiment and ratings from yfinance_snapshot.

Consolidates 2 separate loaders into one:
  - load_analyst_sentiment_analysis.py (reads analyst sentiment from yfinance_snapshot)
  - load_analyst_upgrade_downgrade.py (reads analyst ratings from yfinance_snapshot)

Both loaders read from the same upstream table (yfinance_snapshot), so consolidation
eliminates redundant ECS tasks and improves scheduling efficiency.

CRITICAL FIX 2026-07-02: Consolidated yfinance calls. Both loaders read analyst data
from yfinance_snapshot table instead of making direct yfinance API calls.

Run:
    python3 load_analyst_analysis.py [--symbols AAPL,MSFT] [--parallelism 2]
"""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


def main() -> int:
    """Wrapped main with exception handling for data_unavailable markers."""
    try:
        return run_loader(AnalystAnalysisLoader)
    except Exception as e:
        logger.error(f"[ANALYST_ANALYSIS FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        try:
            symbols = set()
            with DatabaseContext("read") as cur:
                cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE active = TRUE")
                symbols = {row[0] for row in cur.fetchall()}

            with DatabaseContext("write") as cur:
                for symbol in symbols:
                    # Mark both tables unavailable
                    for table in ["analyst_sentiment_analysis", "analyst_upgrade_downgrade"]:
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
        except Exception as mark_err:
            logger.error(f"Failed to mark analyst data unavailable: {mark_err}")
        return 1


class AnalystAnalysisLoader(OptimalLoader):
    """Load analyst sentiment AND upgrade/downgrade ratings from yfinance_snapshot.

    Consolidates 2 loaders that both read from yfinance_snapshot:
    1. Analyst Sentiment Analysis: recommendation_key, number_of_analysts
    2. Analyst Upgrade/Downgrade: analysts_overweight, analysts_hold, analysts_underweight

    This loader handles both, reducing ECS task count and improving parallelism.
    """

    # Claim both tables as "owned" by this loader (for locking/watermark tracking)
    table_name = "analyst_analysis"  # Metadata table for coordination
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Read both sentiment and upgrade/downgrade data from yfinance_snapshot.

        Governance: Mark unavailable data explicitly. No silent fallbacks or exceptions.
        Returns data_unavailable marker instead of raising exceptions per GOVERNANCE.md.

        Returns:
            list[dict]: Either real analyst data or data_unavailable marker
        """
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT
                  recommendation_key,
                  number_of_analysts,
                  analysts_overweight,
                  analysts_hold,
                  analysts_underweight,
                  data_available,
                  unavailable_reason
                FROM yfinance_snapshot
                WHERE symbol = %s
                """,
                (symbol,),
            )
            row = cur.fetchone()

        if not row:
            logger.debug(f"[ANALYST_ANALYSIS] {symbol}: yfinance_snapshot row not found (upstream dependency)")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "yfinance_snapshot_dependency_missing",
                }
            ]

        recommendation_key = row[0]
        number_of_analysts = row[1]
        analysts_overweight = row[2]
        analysts_hold = row[3]
        analysts_underweight = row[4]
        data_available = row[5]
        unavailable_reason = row[6]

        if not data_available:
            logger.debug(f"[ANALYST_ANALYSIS] {symbol}: yfinance data unavailable ({unavailable_reason})")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": unavailable_reason,
                }
            ]

        # Parse recommendation_key: format is typically "2.5" → average rating
        # CRITICAL: Only return real analyst data if we have valid metrics
        if not recommendation_key or not number_of_analysts:
            logger.debug(f"[ANALYST_ANALYSIS] {symbol}: Missing analyst metrics (no ratings/analysts)")
            return [
                {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "incomplete_analyst_data",
                }
            ]

        return [
            {
                "symbol": symbol,
                "recommendation_key": recommendation_key,
                "number_of_analysts": number_of_analysts,
                "analysts_overweight": analysts_overweight or 0,
                "analysts_hold": analysts_hold or 0,
                "analysts_underweight": analysts_underweight or 0,
                "data_unavailable": False,
                "reason": None,
            }
        ]

    def store(self, transformed_rows: list[dict[str, Any]]) -> None:
        """Store analyst sentiment and upgrade/downgrade data separately.

        Since this loader consolidates 2 tables, we need to upsert to both.
        """
        if not transformed_rows:
            return

        with DatabaseContext("write") as cur:
            for row in transformed_rows:
                symbol = row["symbol"]

                # Upsert to analyst_sentiment_analysis
                cur.execute(
                    """
                    INSERT INTO analyst_sentiment_analysis
                      (symbol, recommendation_key, number_of_analysts, data_unavailable, reason, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (symbol) DO UPDATE SET
                      recommendation_key = EXCLUDED.recommendation_key,
                      number_of_analysts = EXCLUDED.number_of_analysts,
                      data_unavailable = EXCLUDED.data_unavailable,
                      reason = EXCLUDED.reason,
                      updated_at = NOW()
                """,
                    (
                        symbol,
                        row.get("recommendation_key"),
                        row.get("number_of_analysts"),
                        row.get("data_unavailable", False),
                        row.get("reason"),
                    ),
                )

                # Upsert to analyst_upgrade_downgrade
                cur.execute(
                    """
                    INSERT INTO analyst_upgrade_downgrade
                      (symbol, analysts_overweight, analysts_hold, analysts_underweight,
                       data_unavailable, reason, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (symbol) DO UPDATE SET
                      analysts_overweight = EXCLUDED.analysts_overweight,
                      analysts_hold = EXCLUDED.analysts_hold,
                      analysts_underweight = EXCLUDED.analysts_underweight,
                      data_unavailable = EXCLUDED.data_unavailable,
                      reason = EXCLUDED.reason,
                      updated_at = NOW()
                """,
                    (
                        symbol,
                        row.get("analysts_overweight", 0),
                        row.get("analysts_hold", 0),
                        row.get("analysts_underweight", 0),
                        row.get("data_unavailable", False),
                        row.get("reason"),
                    ),
                )


if __name__ == "__main__":
    sys.exit(main())
