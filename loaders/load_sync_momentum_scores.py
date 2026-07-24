#!/usr/bin/env python3
"""Sync momentum_score from stock_scores to momentum_metrics."""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class SyncMomentumScoresLoader(OptimalLoader):
    """Sync momentum_score from stock_scores to momentum_metrics."""

    table_name = "momentum_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 50.0

    def fetch_incremental(self, symbol: str, since_date: date | None = None) -> list[tuple[Any, ...]]:
        """Fetch momentum_score from stock_scores for given symbol."""
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT
                    ss.symbol,
                    ss.momentum_score
                FROM stock_scores ss
                WHERE ss.symbol = %s
            """, (symbol,))

            row = cur.fetchone()
            if not row:
                return [({"symbol": symbol, "momentum_score": None}, )]

            symbol, momentum_score = row
            return [({
                "symbol": symbol,
                "momentum_score": momentum_score,
            }, )]

    def process(self, symbol: str, row: tuple[Any, ...]) -> dict[str, Any]:
        """Return the fetched momentum_score row."""
        data = row[0]
        return {
            "symbol": data["symbol"],
            "momentum_score": data["momentum_score"],
        }

    def persist(self, cur: Any, symbol: str, row: dict[str, Any]) -> None:
        """Update momentum_metrics with momentum_score from stock_scores."""
        cur.execute("""
            UPDATE momentum_metrics
            SET momentum_score = %s, updated_at = NOW()
            WHERE symbol = %s
        """, (row["momentum_score"], symbol))

        if cur.rowcount == 0:
            logger.debug(f"[SYNC_MOMENTUM_SCORES] {symbol}: No momentum_metrics row, inserting placeholder")
            cur.execute("""
                INSERT INTO momentum_metrics (symbol, momentum_score, data_unavailable, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (symbol) DO UPDATE
                SET momentum_score = EXCLUDED.momentum_score, updated_at = NOW()
            """, (symbol, row["momentum_score"], row["momentum_score"] is None))


def main() -> int:
    """Run the sync loader."""
    return run_loader(SyncMomentumScoresLoader)


if __name__ == "__main__":
    sys.exit(main())
