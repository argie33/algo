#!/usr/bin/env python3
"""Sync stability_score from stock_scores to stability_metrics."""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class SyncStabilityScoresLoader(OptimalLoader):
    """Sync stability_score from stock_scores to stability_metrics."""

    table_name = "stability_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 50.0

    def fetch_incremental(self, symbol: str, since_date: date | None = None) -> list[tuple[Any, ...]]:
        """Fetch stability_score from stock_scores for given symbol."""
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    ss.symbol,
                    ss.stability_score
                FROM stock_scores ss
                WHERE ss.symbol = %s
            """, (symbol,))

            row = cur.fetchone()
            if not row:
                return [({"symbol": symbol, "stability_score": None}, )]

            symbol, stability_score = row
            return [({
                "symbol": symbol,
                "stability_score": stability_score,
            }, )]

    def process(self, symbol: str, row: tuple[Any, ...]) -> dict[str, Any]:
        """Return the fetched stability_score row."""
        data = row[0]
        return {
            "symbol": data["symbol"],
            "stability_score": data["stability_score"],
        }

    def persist(self, cur: Any, symbol: str, row: dict[str, Any]) -> None:
        """Update stability_metrics with stability_score from stock_scores."""
        cur.execute("""
            UPDATE stability_metrics
            SET stability_score = %s, updated_at = NOW()
            WHERE symbol = %s
        """, (row["stability_score"], symbol))

        if cur.rowcount == 0:
            logger.debug(f"[SYNC_STABILITY_SCORES] {symbol}: No stability_metrics row, inserting placeholder")
            cur.execute("""
                INSERT INTO stability_metrics (symbol, stability_score, data_unavailable, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (symbol) DO UPDATE
                SET stability_score = EXCLUDED.stability_score, updated_at = NOW()
            """, (symbol, row["stability_score"], row["stability_score"] is None))


def main() -> int:
    """Run the sync loader."""
    return run_loader(SyncStabilityScoresLoader)


if __name__ == "__main__":
    sys.exit(main())
