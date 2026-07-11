#!/usr/bin/env python3
"""
Sector Rankings — Rank sectors and industries by composite performance.

PURPOSE: Rank sectors and industries by their average composite stock score
to identify which sectors are in favor. Used by portfolio manager to tilt
position sizing and by Phase 3 sector filtering.

INPUT: 2 tables:
  - stock_scores (composite score 0-100 for each symbol)
  - company_profile (sector and industry for each symbol)
OUTPUT: 2 tables:
  - sector_ranking (average score by sector, with rank 1-N)
  - industry_ranking (average score by industry, with rank 1-N)

SCHEDULE: Step Functions Pipeline, Step 8c (SectorRanking task)
  Timing: ~5:09 PM ET (after buy_sell_daily)
  Dependency: stock_scores must be fresh (>= 95% complete)

COST: CPU=512m, Memory=1024MB, Timeout=900s (15m)
  Runtime: 3-5 minutes (aggregation query, not per-symbol)
  Parallelism: 1

DATA FRESHNESS: Daily
COMPLETENESS: 99%+ (depends on stock_scores being complete)

FAILURE MODE: Graceful degradation (not fail-close).
  If fails, uses prior day's rankings.

CONSOLIDATION: Since sessions 62-63, 2 separate loaders → 1.
  - Eliminates 1 redundant ECS task per run
  - Single query reads stock_scores once, computes both sector + industry rankings

METRICS COMPUTED:
  - Sector ranking: Average composite score by sector, sorted descending
  - Industry ranking: Average composite score by industry, sorted descending
  - Rank positions 1-N per sector/industry

DOWNSTREAM USE:
  - Portfolio manager: Tilt position sizing by sector favorability
  - Phase 3 signal generation: Sector filters and regime determination

NOTE: Formerly load_market_rankings.py (renamed 2026-07 for clarity).
"""

import logging
import sys
from datetime import date
from typing import Any

import psycopg2

from loaders.runner import run_loader
from utils.loaders import execute_query, fetch_latest
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


def main() -> int:
    """Wrapped main with exception handling for data_unavailable markers."""
    try:
        return run_loader(MarketRankingsLoader, global_mode=True)
    except Exception as e:
        logger.error(f"[MARKET_RANKINGS FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


class MarketRankingsLoader(OptimalLoader):
    """Compute sector and industry rankings from stock scores and company profile data.

    Consolidates 2 loaders that both:
    1. Depend on: stock_scores (95%+ completeness) + company_profile (80%+ completeness)
    2. Compute: sector/industry rankings from composite stock scores
    3. Run at: 4:40-4:45 PM ET (after all metrics complete)

    Circuit breaker pattern: Validates upstream dependencies before proceeding.
    Fails fast if stock_scores or company_profile incomplete.
    """

    table_name = "market_rankings"  # Metadata for locking/watermark
    primary_key = ("ranking_type", "ranking_name", "date")
    watermark_field = "date"

    def load_global(self) -> int:
        """Compute and load both sector and industry rankings."""
        try:
            # Circuit breaker: Check upstream dependencies
            self._check_upstream_dependency("stock_scores", min_completion_pct=95)
            self._check_upstream_dependency("company_profile", min_completion_pct=80)

            # Get latest market date
            row = fetch_latest("price_daily", "date")
            latest_date = row["date"] if row else None

            if not latest_date:
                raise ValueError("No price data found in price_daily table. Required for ranking computation.")

            # Load sector rankings
            sector_count = self._load_sector_rankings(latest_date)
            logger.info(f"[MARKET_RANKINGS] Loaded {sector_count} sector rankings")

            # Load industry rankings
            industry_count = self._load_industry_rankings(latest_date)
            logger.info(f"[MARKET_RANKINGS] Loaded {industry_count} industry rankings")

            total = sector_count + industry_count
            if total > 0:
                logger.info(f"[MARKET_RANKINGS] SUCCESS: {total} total rankings loaded")
                return total
            else:
                logger.error("[MARKET_RANKINGS] FAILED: No rankings loaded")
                return 0

        except Exception as e:
            logger.error(f"[MARKET_RANKINGS] Failed to load rankings: {type(e).__name__}: {str(e)}")
            raise

    def _load_sector_rankings(self, latest_date: date) -> int:
        """Load sector rankings from stock scores and company profile data."""
        try:
            rows = execute_query(
                """
                WITH current_ranks AS (
                        SELECT
                            cp.sector AS sector_name,
                            COUNT(DISTINCT cp.ticker) AS stock_count,
                            AVG(ss.composite_score)   AS avg_composite_score,
                            RANK() OVER (ORDER BY AVG(ss.composite_score) DESC NULLS LAST) AS sector_rank
                        FROM company_profile cp
                        LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
                        WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) != ''
                          AND (ss.symbol IS NULL OR ss.data_completeness >= 70)
                        GROUP BY cp.sector
                    ),
                    rank_1w AS (
                        SELECT sector_name, sector_rank AS rank_1w
                        FROM sector_ranking
                        WHERE date = %s - get_interval_sql('7d')
                    ),
                    rank_4w AS (
                        SELECT sector_name, sector_rank AS rank_4w
                        FROM sector_ranking
                        WHERE date = %s - INTERVAL '28 days'
                    ),
                    rank_52w AS (
                        SELECT sector_name, sector_rank AS rank_52w
                        FROM sector_ranking
                        WHERE date = %s - get_interval_sql('52w')
                    )
                SELECT
                    %s AS date,
                    cr.sector_name,
                    cr.stock_count,
                    cr.avg_composite_score,
                    cr.sector_rank,
                    COALESCE(r1w.rank_1w, cr.sector_rank) AS rank_1w_ago,
                    COALESCE(r4w.rank_4w, cr.sector_rank) AS rank_4w_ago,
                    COALESCE(r52w.rank_52w, cr.sector_rank) AS rank_52w_ago
                FROM current_ranks cr
                LEFT JOIN rank_1w r1w ON cr.sector_name = r1w.sector_name
                LEFT JOIN rank_4w r4w ON cr.sector_name = r4w.sector_name
                LEFT JOIN rank_52w r52w ON cr.sector_name = r52w.sector_name
                ORDER BY cr.sector_rank
                """,
                (latest_date, latest_date, latest_date, latest_date),
            )

            with DatabaseContext("write") as cur:
                for row in rows:
                    cur.execute(
                        """
                        INSERT INTO sector_ranking
                          (date, sector_name, stock_count, avg_composite_score, sector_rank,
                           rank_1w_ago, rank_4w_ago, rank_52w_ago)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (sector_name, date) DO UPDATE SET
                          stock_count = EXCLUDED.stock_count,
                          avg_composite_score = EXCLUDED.avg_composite_score,
                          sector_rank = EXCLUDED.sector_rank,
                          rank_1w_ago = EXCLUDED.rank_1w_ago,
                          rank_4w_ago = EXCLUDED.rank_4w_ago,
                          rank_52w_ago = EXCLUDED.rank_52w_ago
                    """,
                        (
                            row[0],  # date
                            row[1],  # sector_name
                            row[2],  # stock_count
                            row[3],  # avg_composite_score
                            row[4],  # sector_rank
                            row[5],  # rank_1w_ago
                            row[6],  # rank_4w_ago
                            row[7],  # rank_52w_ago
                        ),
                    )

            return len(rows)

        except Exception as e:
            logger.error(f"[MARKET_RANKINGS] Failed to load sector rankings: {type(e).__name__}: {str(e)}")
            raise

    def _load_industry_rankings(self, latest_date: date) -> int:
        """Load industry rankings from stock scores and company profile data."""
        try:
            from utils.db.context import DatabaseContext

            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    WITH current_ranks AS (
                        SELECT
                            cp.industry,
                            COUNT(DISTINCT cp.ticker) AS stock_count,
                            AVG(ss.composite_score)   AS avg_composite_score,
                            RANK() OVER (ORDER BY AVG(ss.composite_score) DESC NULLS LAST) AS industry_rank
                        FROM company_profile cp
                        LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
                        WHERE cp.industry IS NOT NULL AND TRIM(cp.industry) != ''
                          AND (ss.symbol IS NULL OR ss.data_completeness >= 70)
                        GROUP BY cp.industry
                    ),
                    rank_1w AS (
                        SELECT industry, industry_rank AS rank_1w
                        FROM industry_ranking
                        WHERE date_recorded = %s::date - get_interval_sql('7d')
                    ),
                    rank_4w AS (
                        SELECT industry, industry_rank AS rank_4w
                        FROM industry_ranking
                        WHERE date_recorded = %s::date - INTERVAL '28 days'
                    ),
                    rank_52w AS (
                        SELECT industry, industry_rank AS rank_52w
                        FROM industry_ranking
                        WHERE date_recorded = %s::date - get_interval_sql('52w')
                    )
                    SELECT
                        %s::date AS date_recorded,
                        cr.industry,
                        cr.stock_count,
                        cr.avg_composite_score,
                        cr.industry_rank,
                        COALESCE(r1w.rank_1w, cr.industry_rank) AS rank_1w_ago,
                        COALESCE(r4w.rank_4w, cr.industry_rank) AS rank_4w_ago,
                        COALESCE(r52w.rank_52w, cr.industry_rank) AS rank_52w_ago
                    FROM current_ranks cr
                    LEFT JOIN rank_1w r1w ON cr.industry = r1w.industry
                    LEFT JOIN rank_4w r4w ON cr.industry = r4w.industry
                    LEFT JOIN rank_52w r52w ON cr.industry = r52w.industry
                    ORDER BY cr.industry_rank
                    """,
                    (latest_date, latest_date, latest_date, latest_date),
                )
                rows = cur.fetchall()

            with DatabaseContext("write") as cur:
                for row in rows:
                    cur.execute(
                        """
                        INSERT INTO industry_ranking
                          (date_recorded, industry, stock_count, avg_composite_score, industry_rank,
                           rank_1w_ago, rank_4w_ago, rank_52w_ago)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (industry, date_recorded) DO UPDATE SET
                          stock_count = EXCLUDED.stock_count,
                          avg_composite_score = EXCLUDED.avg_composite_score,
                          industry_rank = EXCLUDED.industry_rank,
                          rank_1w_ago = EXCLUDED.rank_1w_ago,
                          rank_4w_ago = EXCLUDED.rank_4w_ago,
                          rank_52w_ago = EXCLUDED.rank_52w_ago
                    """,
                        (
                            row[0],  # date_recorded
                            row[1],  # industry
                            row[2],  # stock_count
                            row[3],  # avg_composite_score
                            row[4],  # industry_rank
                            row[5],  # rank_1w_ago
                            row[6],  # rank_4w_ago
                            row[7],  # rank_52w_ago
                        ),
                    )

            return len(rows)

        except Exception as e:
            logger.error(f"[MARKET_RANKINGS] Failed to load industry rankings: {type(e).__name__}: {str(e)}")
            raise


if __name__ == "__main__":
    sys.exit(main())
