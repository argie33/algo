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

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Read analyst ratings from yfinance_snapshot table.

        Governance: Fail-fast on missing data. No silent fallbacks.

        Raises RuntimeError if yfinance_snapshot data unavailable (upstream loader dependency).
        """
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT recommendation_key, number_of_analysts, analysts_overweight,
                       analysts_hold, analysts_underweight, data_available, unavailable_reason
                FROM yfinance_snapshot
                WHERE symbol = %s
                """,
                (symbol,),
            )
            row = cur.fetchone()

        if not row:
            raise RuntimeError(
                f"[ANALYST_UPGRADE_DOWNGRADE] {symbol}: yfinance_snapshot row not found. "
                f"Upstream loader (load_yfinance_snapshot) must run first. "
                f"Cannot fetch analyst upgrade/downgrade ratings without snapshot data."
            )

        if not row.get("data_available"):
            raise RuntimeError(
                f"[ANALYST_UPGRADE_DOWNGRADE] {symbol}: yfinance_snapshot data marked unavailable. "
                f"Reason: {row.get('unavailable_reason', 'unknown')}. "
                f"Upstream loader failed or API unavailable. Cannot proceed without yfinance data."
            )

        if not row.get("number_of_analysts"):
            raise RuntimeError(
                f"[ANALYST_UPGRADE_DOWNGRADE] {symbol}: No analyst opinions available in yfinance. "
                f"This is legitimate for micro-cap stocks; data is missing but loader succeeded. "
                f"Cannot compute upgrade/downgrade metrics without analyst coverage data."
            )

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


if __name__ == "__main__":
    sys.exit(run_loader(AnalystUpgradeDowngradeLoader))
