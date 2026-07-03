#!/usr/bin/env python3
"""Analyst Upgrade/Downgrade Loader - reads from yfinance_snapshot table (not API).

CRITICAL FIX 2026-07-02: Consolidated yfinance calls. Reads analyst ratings
from yfinance_snapshot table instead of making direct yfinance API calls.
"""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class AnalystUpgradeDowngradeLoader(OptimalLoader):
    """Read analyst ratings from yfinance_snapshot table."""

    table_name = "analyst_upgrade_downgrade"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]] | None:
        """Read analyst ratings from yfinance_snapshot table."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT recommendation_key, number_of_analysts, analysts_overweight,
                           analysts_hold, analysts_underweight, data_available
                    FROM yfinance_snapshot
                    WHERE symbol = %s
                    """,
                    (symbol,),
                )
                row = cur.fetchone()

            if not row or not row.get("data_available"):
                logger.debug(f"[ANALYST_UPGRADE_DOWNGRADE] No analyst data for {symbol}")
                return None

            if not row.get("number_of_analysts"):
                logger.debug(f"[ANALYST_UPGRADE_DOWNGRADE] No analyst opinions for {symbol}")
                return None

            return [
                {
                    "symbol": symbol,
                    "recommendation_key": row["recommendation_key"],
                    "number_of_analysts": row["number_of_analysts"],
                    "analysts_overweight": row["analysts_overweight"],
                    "analysts_hold": row["analysts_hold"],
                    "analysts_underweight": row["analysts_underweight"],
                    "updated_at": date.today().isoformat(),
                }
            ]

        except Exception as e:
            logger.debug(f"[ANALYST_UPGRADE_DOWNGRADE] Error reading snapshot for {symbol}: {e}")
            return None


if __name__ == "__main__":
    sys.exit(run_loader(AnalystUpgradeDowngradeLoader))
