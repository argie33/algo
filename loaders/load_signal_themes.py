#!/usr/bin/env python3
"""Signal Themes Loader - Identify thematic groups among high-scoring signals."""

import logging
import sys
from datetime import date
from typing import Optional

import psycopg2

from loaders.runner import run_loader
from utils.loaders import execute_query, fetch_latest
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

from loaders.loader_helper import setup_imports

setup_imports()


class SignalThemesLoader(OptimalLoader):
    """Load signal themes from signal quality scores (market-wide aggregate)."""

    table_name = "signal_themes"
    primary_key = ("symbol", "date")
    watermark_field = "created_at"

    def fetch_global(self, since: date | None) -> list[dict] | None:
        """Fetch and group signal themes from quality scores."""
        try:
            # Get the latest price data date
            row = fetch_latest("price_daily", "date")
            latest_date = row["date"] if row else None

            if not latest_date:
                logger.warning("No price data found")
                return None

            # Fetch high-scoring signals grouped by theme
            rows = execute_query(
                """
                SELECT
                    symbol,
                    %s::date as date,
                    'high_momentum'::text AS sector_theme,
                    CASE
                        WHEN composite_sqs > 85 THEN 'Elite'
                        WHEN composite_sqs > 75 THEN 'Premium'
                        WHEN composite_sqs > 65 THEN 'Standard'
                        ELSE 'Monitor'
                    END AS thematic_group,
                    'Primary'::text AS correlation_cluster
                FROM signal_quality_scores
                WHERE date = %s
                AND composite_sqs > 50
                ORDER BY composite_sqs DESC
                LIMIT 500
            """,
                (latest_date, latest_date),
            )

            if not rows:
                return None

            return [
                {
                    "symbol": r["symbol"],
                    "date": r["date"],
                    "sector_theme": r["sector_theme"],
                    "thematic_group": r["thematic_group"],
                    "correlation_cluster": r["correlation_cluster"],
                }
                for r in rows
            ]
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e


if __name__ == "__main__":
    sys.exit(run_loader(SignalThemesLoader, global_mode=True))
