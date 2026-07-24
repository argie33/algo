#!/usr/bin/env python3
"""Sync positioning_score from stock_scores to positioning_metrics."""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class SyncPositioningScoresLoader(OptimalLoader):
    """Sync positioning_score from stock_scores to positioning_metrics."""

    table_name = "positioning_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 50.0

    def fetch_incremental(self, symbol: str, since_date: date | None = None) -> list[tuple[Any, ...]]:
        """Fetch positioning_score from stock_scores for given symbol."""
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    ss.symbol,
                    ss.positioning_score
                FROM stock_scores ss
                WHERE ss.symbol = %s
            """, (symbol,))

            row = cur.fetchone()
            if not row:
                return [({"symbol": symbol, "positioning_score": None}, )]

            symbol, positioning_score = row
            return [({
                "symbol": symbol,
                "positioning_score": positioning_score,
            }, )]

    def process(self, symbol: str, row: tuple[Any, ...]) -> dict[str, Any]:
        """Return the fetched positioning_score row."""
        data = row[0]
        return {
            "symbol": data["symbol"],
            "positioning_score": data["positioning_score"],
        }

    def persist(self, cur: Any, symbol: str, row: dict[str, Any]) -> None:
        """Update positioning_metrics with positioning_score from stock_scores."""
        cur.execute("""
            UPDATE positioning_metrics
            SET positioning_score = %s, updated_at = NOW()
            WHERE symbol = %s
        """, (row["positioning_score"], symbol))

        if cur.rowcount == 0:
            logger.debug(f"[SYNC_POSITIONING_SCORES] {symbol}: No positioning_metrics row, inserting placeholder")
            cur.execute("""
                INSERT INTO positioning_metrics (symbol, positioning_score, data_unavailable, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (symbol) DO UPDATE
                SET positioning_score = EXCLUDED.positioning_score, updated_at = NOW()
            """, (symbol, row["positioning_score"], row["positioning_score"] is None))


def main() -> int:
    """Run the sync loader."""
    return run_loader(SyncPositioningScoresLoader)


if __name__ == "__main__":
    sys.exit(main())
