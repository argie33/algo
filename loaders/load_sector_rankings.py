#!/usr/bin/env python3
"""Sector Rankings Loader - compute sector rankings from stock scores."""

import logging
import sys
from datetime import date

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class SectorRankingLoader(OptimalLoader):
    """Compute sector rankings from stock scores."""

    table_name = "sector_ranking"
    primary_key = ("sector_name", "date")
    watermark_field = "date"

    def load_global(self) -> int:
        """Compute and load sector rankings for today."""
        try:
            with DatabaseContext("write") as cur:
                # Delete stale data (keep last 90 days)
                cur.execute(
                    """
                    DELETE FROM sector_ranking
                    WHERE date < NOW()::date - INTERVAL '90 days'
                    """
                )

                # Compute sector rankings from stock scores
                cur.execute(
                    """
                    WITH sector_stats AS (
                        SELECT
                            cp.sector AS sector_name,
                            COUNT(DISTINCT ss.symbol) AS stock_count,
                            AVG(COALESCE(ss.composite_score, 50)) AS avg_score,
                            RANK() OVER (ORDER BY AVG(COALESCE(ss.composite_score, 50)) DESC) AS current_rank
                        FROM company_profile cp
                        LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
                        WHERE cp.sector IS NOT NULL
                          AND cp.sector != ''
                          AND cp.sector != 'Unknown'
                        GROUP BY cp.sector
                    ),
                    prior_ranks AS (
                        SELECT
                            sector_name,
                            current_rank AS rank_1w_ago
                        FROM sector_ranking
                        WHERE date = NOW()::date - INTERVAL '7 days'
                    )
                    INSERT INTO sector_ranking
                      (sector_name, date, current_rank, momentum_score, rank_1w_ago)
                    SELECT
                        ss.sector_name,
                        NOW()::date,
                        ss.current_rank,
                        COALESCE(ss.current_rank - COALESCE(pr.rank_1w_ago, ss.current_rank), 0),
                        COALESCE(pr.rank_1w_ago, ss.current_rank)
                    FROM sector_stats ss
                    LEFT JOIN prior_ranks pr ON ss.sector_name = pr.sector_name
                    ON CONFLICT (sector_name, date) DO UPDATE SET
                        current_rank = EXCLUDED.current_rank,
                        momentum_score = EXCLUDED.momentum_score,
                        rank_1w_ago = EXCLUDED.rank_1w_ago,
                        updated_at = NOW()
                    """
                )
                inserted = cur.rowcount

            logger.info(f"[SECTOR_RANKING] Loaded {inserted} sector rankings")
            return inserted

        except Exception as e:
            logger.error(f"[SECTOR_RANKING] Failed: {type(e).__name__}: {e!s}")
            raise


def main() -> int:
    """Wrapped main with exception handling."""
    try:
        return run_loader(SectorRankingLoader, global_mode=True)
    except Exception as e:
        logger.error(
            f"[SECTOR_RANKING FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}",
            exc_info=True,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
