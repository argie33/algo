#!/usr/bin/env python3
"""Sync quality_score from stock_scores to quality_metrics."""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class SyncQualityScoresLoader(OptimalLoader):
    """Sync quality_score from stock_scores to quality_metrics."""

    table_name = "quality_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 50.0

    def fetch_incremental(self, symbol: str, since_date: date | None = None) -> list[tuple[Any, ...]]:
        """Fetch quality_score from stock_scores for given symbol."""
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    ss.symbol,
                    ss.quality_score
                FROM stock_scores ss
                WHERE ss.symbol = %s
            """, (symbol,))

            row = cur.fetchone()
            if not row:
                return [({"symbol": symbol, "quality_score": None}, )]

            symbol, quality_score = row
            return [({
                "symbol": symbol,
                "quality_score": quality_score,
            }, )]

    def process(self, symbol: str, row: tuple[Any, ...]) -> dict[str, Any]:
        """Return the fetched quality_score row."""
        data = row[0]
        return {
            "symbol": data["symbol"],
            "quality_score": data["quality_score"],
        }

    def persist(self, cur: Any, symbol: str, row: dict[str, Any]) -> None:
        """Update quality_metrics with quality_score from stock_scores."""
        cur.execute("""
            UPDATE quality_metrics
            SET quality_score = %s, updated_at = NOW()
            WHERE symbol = %s
        """, (row["quality_score"], symbol))

        if cur.rowcount == 0:
            logger.debug(f"[SYNC_QUALITY_SCORES] {symbol}: No quality_metrics row, inserting placeholder")
            cur.execute("""
                INSERT INTO quality_metrics (symbol, quality_score, data_unavailable, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (symbol) DO UPDATE
                SET quality_score = EXCLUDED.quality_score, updated_at = NOW()
            """, (symbol, row["quality_score"], row["quality_score"] is None))


def main() -> int:
    """Run the sync loader."""
    return run_loader(SyncQualityScoresLoader)


if __name__ == "__main__":
    sys.exit(main())
