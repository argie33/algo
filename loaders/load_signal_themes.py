#!/usr/bin/env python3
"""
Load signal themes from signal_quality_scores data.
Identifies thematic groups among high-scoring signals.
"""
import logging
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

def load_signal_themes():
    """Load signal themes from scoring data."""
    try:
        with DatabaseContext('write') as cur:
            # Get the latest price data date
            cur.execute("""
                SELECT MAX(date) FROM price_daily
            """)
            latest_date = cur.fetchone()[0]

            if not latest_date:
                logger.warning("No price data found")
                return 0

            # Clear old signal themes
            cur.execute("""
                DELETE FROM signal_themes
                WHERE created_at < NOW() - INTERVAL '90 days'
            """)

            # Insert signal themes based on top stock scores
            # Group high-scoring stocks by patterns
            cur.execute("""
                INSERT INTO signal_themes (symbol, date, sector_theme, thematic_group, correlation_cluster, created_at)
                SELECT
                    sqs.symbol,
                    %s::date,
                    'high_momentum'::text AS sector_theme,
                    CASE
                        WHEN sqs.composite_sqs > 85 THEN 'Elite'
                        WHEN sqs.composite_sqs > 75 THEN 'Premium'
                        WHEN sqs.composite_sqs > 65 THEN 'Standard'
                        ELSE 'Monitor'
                    END AS thematic_group,
                    'Primary'::text AS correlation_cluster,
                    NOW()
                FROM signal_quality_scores sqs
                WHERE sqs.date = %s
                AND sqs.composite_sqs > 50
                ORDER BY sqs.composite_sqs DESC
                LIMIT 500
                ON CONFLICT (symbol, date) DO UPDATE SET
                    sector_theme = EXCLUDED.sector_theme,
                    thematic_group = EXCLUDED.thematic_group
            """, (latest_date, latest_date))

            inserted = cur.rowcount
            logger.info(f"Loaded {inserted} signal themes")
            return inserted
    except Exception as e:
        logger.error(f"Error loading signal themes: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    load_signal_themes()
