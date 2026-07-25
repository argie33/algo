#!/usr/bin/env python3
"""Sync value_score from stock_scores to value_metrics.

This loader copies the value_score computed by load_stock_scores into value_metrics
for API convenience (so value_metrics is self-contained without requiring stock_scores join).

Dependency: Requires load_stock_scores to run first (value_score must be computed).

Data flow:
  1. load_stock_scores computes value_score → stock_scores.value_score
  2. load_sync_value_scores (THIS LOADER) copies → value_metrics.value_score
  3. API can query value_metrics directly without joining stock_scores
"""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class SyncValueScoresLoader(OptimalLoader):
    """Sync value_score from stock_scores to value_metrics."""

    table_name = "value_metrics"
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 50.0

    def fetch_incremental(self, symbol: str, since_date: date | None = None) -> list[tuple[Any, ...]]:
        """Fetch value_score from stock_scores for given symbol."""
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT
                    ss.symbol,
                    ss.value_score,
                    CASE WHEN ss.value_score IS NULL THEN 'no_value_score_computed'::VARCHAR
                         ELSE NULL::VARCHAR
                    END AS unavailable_reason
                FROM stock_scores ss
                WHERE ss.symbol = %s
                AND ss.value_score IS NOT NULL
            """,
                (symbol,),
            )

            row = cur.fetchone()
            if not row:
                # Symbol has no value_score in stock_scores
                return [({"symbol": symbol, "value_score": None, "unavailable_reason": "no_stock_score_available"},)]

            symbol, value_score, unavailable_reason = row
            return [
                (
                    {
                        "symbol": symbol,
                        "value_score": value_score,
                        "unavailable_reason": unavailable_reason,
                    },
                )
            ]

    def process(self, symbol: str, row: tuple[Any, ...]) -> dict[str, Any]:
        """Return the fetched value_score row."""
        data = row[0]
        return {
            "symbol": data["symbol"],
            "value_score": data["value_score"],
            "unavailable_reason": data["unavailable_reason"],
        }

    def persist(self, cur: Any, symbol: str, row: dict[str, Any]) -> None:
        """Update value_metrics with value_score from stock_scores."""
        cur.execute(
            """
            UPDATE value_metrics
            SET value_score = %s, updated_at = NOW()
            WHERE symbol = %s
        """,
            (row["value_score"], symbol),
        )

        if cur.rowcount == 0:
            # No row exists, insert placeholder
            logger.debug(f"[SYNC_VALUE_SCORES] {symbol}: No value_metrics row, inserting placeholder")
            cur.execute(
                """
                INSERT INTO value_metrics (symbol, value_score, data_unavailable, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (symbol) DO UPDATE
                SET value_score = EXCLUDED.value_score, updated_at = NOW()
            """,
                (symbol, row["value_score"], row["value_score"] is None),
            )


def main() -> int:
    """Run the sync loader."""
    return run_loader(SyncValueScoresLoader)


if __name__ == "__main__":
    sys.exit(main())
