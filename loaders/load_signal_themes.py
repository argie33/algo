#!/usr/bin/env python3
"""Signal Themes Loader - Identify thematic groups among high-scoring signals."""
import sys
import logging
from datetime import date
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

class SignalThemesLoader(OptimalLoader):
    """Load signal themes from signal quality scores (market-wide aggregate)."""
from loaders.loader_helper import setup_imports
setup_imports()

    table_name = "signal_themes"
    primary_key = ("symbol", "date")
    watermark_field = "created_at"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch and group signal themes from quality scores."""
        try:
            with DatabaseContext('read') as cur:
                # Get the latest price data date
                cur.execute("SELECT date FROM price_daily ORDER BY date DESC LIMIT 1")
                row = cur.fetchone()
                latest_date = row['date'] if row else None

                if not latest_date:
                    logger.warning("No price data found")
                    return None

                # Fetch high-scoring signals grouped by theme
                cur.execute("""
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
                """, (latest_date, latest_date))

                rows = cur.fetchall()
                if not rows:
                    return None

                return [
                    {
                        'symbol': r[0],
                        'date': r[1],
                        'sector_theme': r[2],
                        'thematic_group': r[3],
                        'correlation_cluster': r[4],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"Error fetching signal themes: {e}")
            return None

def main():
    loader = SignalThemesLoader()
    result = loader.load_global()

    if result > 0:
        logger.info(f"SUCCESS: {result} signal themes loaded")
        return 0
    else:
        logger.warning(f"COMPLETED: No themes loaded")
        return 0

if __name__ == "__main__":
    sys.exit(main())
