#!/usr/bin/env python3
"""Sector Ranking Loader - Rank sectors by composite stock scores."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)


class SectorRankingLoader(OptimalLoader):
    """Rank sectors by composite score from stock_scores + company_profile."""

    table_name = "sector_ranking"
    primary_key = ("sector_name", "date_recorded")
    watermark_field = "date_recorded"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Compute sector rankings from stock scores and company profile data."""
        try:
            with DatabaseContext('read') as cur:
                cur.execute("SELECT date FROM price_daily ORDER BY date DESC LIMIT 1")
                row = cur.fetchone()
                latest_date = row['date'] if row else None

                if not latest_date:
                    logger.warning("No price data found — skipping sector ranking")
                    return None

                # Rank sectors by average composite score; pull historical ranks for comparison
                cur.execute("""
                    WITH current_ranks AS (
                        SELECT
                            cp.sector AS sector_name,
                            COUNT(DISTINCT cp.ticker) AS stock_count,
                            AVG(ss.composite_score)   AS avg_composite_score,
                            RANK() OVER (ORDER BY AVG(ss.composite_score) DESC NULLS LAST) AS sector_rank
                        FROM company_profile cp
                        LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
                        WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) != ''
                        GROUP BY cp.sector
                    ),
                    rank_1w AS (
                        SELECT sector_name, current_rank AS rank_1w
                        FROM sector_ranking
                        WHERE date_recorded = (
                            SELECT date_recorded FROM sector_ranking
                            WHERE date_recorded <= CURRENT_DATE - INTERVAL '7 days'
                            ORDER BY date_recorded DESC LIMIT 1
                        )
                    ),
                    rank_4w AS (
                        SELECT sector_name, current_rank AS rank_4w
                        FROM sector_ranking
                        WHERE date_recorded = (
                            SELECT date_recorded FROM sector_ranking
                            WHERE date_recorded <= CURRENT_DATE - INTERVAL '28 days'
                            ORDER BY date_recorded DESC LIMIT 1
                        )
                    ),
                    rank_12w AS (
                        SELECT sector_name, current_rank AS rank_12w
                        FROM sector_ranking
                        WHERE date_recorded = (
                            SELECT date_recorded FROM sector_ranking
                            WHERE date_recorded <= CURRENT_DATE - INTERVAL '84 days'
                            ORDER BY date_recorded DESC LIMIT 1
                        )
                    )
                    SELECT
                        cr.sector_name,
                        cr.sector_rank          AS current_rank,
                        cr.avg_composite_score  AS momentum_score,
                        r1.rank_1w              AS rank_1w_ago,
                        r4.rank_4w              AS rank_4w_ago,
                        r12.rank_12w            AS rank_12w_ago
                    FROM current_ranks cr
                    LEFT JOIN rank_1w  r1  ON r1.sector_name  = cr.sector_name
                    LEFT JOIN rank_4w  r4  ON r4.sector_name  = cr.sector_name
                    LEFT JOIN rank_12w r12 ON r12.sector_name = cr.sector_name
                    ORDER BY cr.sector_rank
                """)

                rows = cur.fetchall()
                if not rows:
                    logger.warning("No sector ranking data computed — check company_profile and stock_scores tables")
                    return None

                return [
                    {
                        'sector_name':    r['sector_name'],
                        'date_recorded':  latest_date,
                        'current_rank':   r['current_rank'],
                        'momentum_score': float(r['momentum_score']) if r['momentum_score'] is not None else None,
                        'rank_1w_ago':    r['rank_1w_ago'],
                        'rank_4w_ago':    r['rank_4w_ago'],
                        'rank_12w_ago':   r['rank_12w_ago'],
                    }
                    for r in rows
                ]

        except Exception as e:
            logger.error(f"Failed to compute sector rankings: {e}")
            return None


def main():
    loader = SectorRankingLoader()
    result = loader.load_global()

    if result > 0:
        logger.info(f"SUCCESS: {result} sectors ranked")
        return 0
    else:
        logger.warning("COMPLETED: No sector rankings computed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
