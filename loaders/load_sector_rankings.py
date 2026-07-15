#!/usr/bin/env python3
"""Sector & Industry Rankings Loader - compute rankings from stock scores in single pass."""

import logging
import sys

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class SectorRankingLoader(OptimalLoader):
    """Compute sector and industry rankings from stock scores in single SQL pass.

    Consolidates sector + industry ranking into one loader (both read same company_profile+stock_scores).
    Writes to both sector_ranking and industry_ranking tables in parallel.
    """

    table_name = "sector_ranking"  # Primary table for watermarking
    primary_key = ("sector_name", "date")
    watermark_field = "date"

    def load_global(self) -> int:
        try:
            with DatabaseContext("write") as cur:
                # Delete stale data (keep last 90 days) for both tables
                cur.execute(
                    """
                    DELETE FROM sector_ranking
                    WHERE date < NOW()::date - INTERVAL '90 days'
                    """
                )
                cur.execute(
                    """
                    DELETE FROM industry_ranking
                    WHERE date_recorded < NOW()::date - INTERVAL '90 days'
                    """
                )

                # Compute sector rankings from stock scores.
                # rank_1w/4w/12w_ago use the nearest row at-or-before the lookback date
                # (loader gaps/weekends leave no exact-date row) and bootstrap to
                # current_rank when history is missing - sector_rotation.py hard-requires
                # all three to be non-NULL for market regime computation.
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
                    )
                    INSERT INTO sector_ranking
                      (sector_name, date, current_rank, momentum_score,
                       rank_1w_ago, rank_4w_ago, rank_12w_ago)
                    SELECT
                        ss.sector_name,
                        NOW()::date,
                        ss.current_rank,
                        COALESCE(ss.current_rank - COALESCE(r1.rank, ss.current_rank), 0),
                        COALESCE(r1.rank, ss.current_rank),
                        COALESCE(r4.rank, ss.current_rank),
                        COALESCE(r12.rank, ss.current_rank)
                    FROM sector_stats ss
                    LEFT JOIN LATERAL (
                        SELECT sr.current_rank AS rank FROM sector_ranking sr
                        WHERE sr.sector_name = ss.sector_name
                          AND sr.date <= NOW()::date - INTERVAL '7 days'
                        ORDER BY sr.date DESC LIMIT 1
                    ) r1 ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT sr.current_rank AS rank FROM sector_ranking sr
                        WHERE sr.sector_name = ss.sector_name
                          AND sr.date <= NOW()::date - INTERVAL '28 days'
                        ORDER BY sr.date DESC LIMIT 1
                    ) r4 ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT sr.current_rank AS rank FROM sector_ranking sr
                        WHERE sr.sector_name = ss.sector_name
                          AND sr.date <= NOW()::date - INTERVAL '84 days'
                        ORDER BY sr.date DESC LIMIT 1
                    ) r12 ON TRUE
                    ON CONFLICT (sector_name, date) DO UPDATE SET
                        current_rank = EXCLUDED.current_rank,
                        momentum_score = EXCLUDED.momentum_score,
                        rank_1w_ago = EXCLUDED.rank_1w_ago,
                        rank_4w_ago = EXCLUDED.rank_4w_ago,
                        rank_12w_ago = EXCLUDED.rank_12w_ago,
                        updated_at = NOW()
                    """
                )
                sector_count = int(cur.rowcount) if cur.rowcount is not None else 0

                # Compute industry rankings (same pattern as sector rankings)
                cur.execute(
                    """
                    WITH industry_stats AS (
                        SELECT
                            cp.industry AS industry_name,
                            COUNT(DISTINCT ss.symbol) AS stock_count,
                            AVG(COALESCE(ss.composite_score, 50)) AS avg_score,
                            RANK() OVER (ORDER BY AVG(COALESCE(ss.composite_score, 50)) DESC) AS current_rank
                        FROM company_profile cp
                        LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
                        WHERE cp.industry IS NOT NULL
                          AND cp.industry != ''
                          AND cp.industry != 'Unknown'
                        GROUP BY cp.industry
                    )
                    INSERT INTO industry_ranking
                      (industry, date_recorded, current_rank, momentum_score, rank_1w_ago, rank_4w_ago)
                    SELECT
                        ist.industry_name,
                        NOW()::date,
                        ist.current_rank,
                        COALESCE(ist.current_rank - COALESCE(r1.rank, ist.current_rank), 0),
                        COALESCE(r1.rank, ist.current_rank),
                        COALESCE(r4.rank, ist.current_rank)
                    FROM industry_stats ist
                    LEFT JOIN LATERAL (
                        SELECT ir.current_rank AS rank FROM industry_ranking ir
                        WHERE ir.industry = ist.industry_name
                          AND ir.date_recorded <= NOW()::date - INTERVAL '7 days'
                        ORDER BY ir.date_recorded DESC LIMIT 1
                    ) r1 ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT ir.current_rank AS rank FROM industry_ranking ir
                        WHERE ir.industry = ist.industry_name
                          AND ir.date_recorded <= NOW()::date - INTERVAL '28 days'
                        ORDER BY ir.date_recorded DESC LIMIT 1
                    ) r4 ON TRUE
                    ON CONFLICT (industry, date_recorded) DO UPDATE SET
                        current_rank = EXCLUDED.current_rank,
                        momentum_score = EXCLUDED.momentum_score,
                        rank_1w_ago = EXCLUDED.rank_1w_ago,
                        rank_4w_ago = EXCLUDED.rank_4w_ago,
                        updated_at = NOW()
                    """
                )
                industry_count = int(cur.rowcount) if cur.rowcount is not None else 0

            logger.info(f"[SECTOR_RANKING] Loaded {sector_count} sector + {industry_count} industry rankings")
            return sector_count + industry_count

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
