#!/usr/bin/env python3
"""Analyst Sentiment Loader - reads from yfinance_snapshot table (not API).

CRITICAL FIX 2026-07-02: Consolidated yfinance calls. Reads analyst sentiment
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


class AnalystSentimentAnalysisLoader(OptimalLoader):
    """Read analyst sentiment from yfinance_snapshot table."""

    table_name = "analyst_sentiment_analysis"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Read analyst sentiment from yfinance_snapshot table.

        Governance: Fail-fast on missing data. No silent fallbacks.

        Raises RuntimeError if yfinance_snapshot data unavailable (upstream loader dependency).
        """
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT recommendation_key, number_of_analysts, data_available
                FROM yfinance_snapshot
                WHERE symbol = %s
                """,
                (symbol,),
            )
            row = cur.fetchone()

        if not row:
            raise RuntimeError(
                f"[ANALYST_SENTIMENT] {symbol}: yfinance_snapshot row not found. "
                f"Upstream loader (load_yfinance_snapshot) must run first. "
                f"Check: SELECT * FROM yfinance_snapshot WHERE symbol = '{symbol}';"
            )

        if not row.get("data_available"):
            raise RuntimeError(
                f"[ANALYST_SENTIMENT] {symbol}: yfinance_snapshot data marked unavailable. "
                f"Reason: {row.get('unavailable_reason', 'unknown')}. "
                f"Upstream loader failed or API unavailable. Cannot proceed without yfinance data."
            )

        if not row.get("number_of_analysts"):
            raise RuntimeError(
                f"[ANALYST_SENTIMENT] {symbol}: No analyst opinions available in yfinance. "
                f"This is legitimate for micro-cap stocks; data is missing but loader succeeded. "
                f"Explicitly mark in database or skip symbol for analyst metrics."
            )

        return [
            {
                "symbol": symbol,
                "recommendation_key": row["recommendation_key"],
                "number_of_analysts": row["number_of_analysts"],
                "updated_at": date.today().isoformat(),
            }
        ]


if __name__ == "__main__":
    sys.exit(run_loader(AnalystSentimentAnalysisLoader))
