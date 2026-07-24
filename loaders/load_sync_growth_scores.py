#!/usr/bin/env python3
"""Sync growth_score from stock_scores to growth_metrics."""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class SyncGrowthScoresLoader(OptimalLoader):
    """Sync growth_score from stock_scores to growth_metrics."""

    table_name = "growth_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 50.0

    def fetch_incremental(self, symbol: str, since_date: date | None = None) -> list[tuple[Any, ...]]:
        """Fetch growth_score from stock_scores for given symbol."""
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    ss.symbol,
                    ss.growth_score
                FROM stock_scores ss
                WHERE ss.symbol = %s
            """, (symbol,))

            row = cur.fetchone()
            if not row:
                return [({"symbol": symbol, "growth_score": None}, )]

            symbol, growth_score = row
            return [({
                "symbol": symbol,
                "growth_score": growth_score,
            }, )]

    def process(self, symbol: str, row: tuple[Any, ...]) -> dict[str, Any]:
        """Return the fetched growth_score row."""
        data = row[0]
        return {
            "symbol": data["symbol"],
            "growth_score": data["growth_score"],
        }

    def persist(self, cur: Any, symbol: str, row: dict[str, Any]) -> None:
        """Update growth_metrics with growth_score from stock_scores."""
        cur.execute("""
            UPDATE growth_metrics
            SET growth_score = %s, updated_at = NOW()
            WHERE symbol = %s
        """, (row["growth_score"], symbol))

        if cur.rowcount == 0:
            logger.debug(f"[SYNC_GROWTH_SCORES] {symbol}: No growth_metrics row, inserting placeholder")
            cur.execute("""
                INSERT INTO growth_metrics (symbol, growth_score, data_unavailable, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (symbol) DO UPDATE
                SET growth_score = EXCLUDED.growth_score, updated_at = NOW()
            """, (symbol, row["growth_score"], row["growth_score"] is None))


def main() -> int:
    """Run the sync loader."""
    return run_loader(SyncGrowthScoresLoader)


if __name__ == "__main__":
    sys.exit(main())
