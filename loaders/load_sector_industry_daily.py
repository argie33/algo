#!/usr/bin/env python3
"""Consolidated Sector + Industry Performance & Rankings Loader.

CONSOLIDATION: Merges 2 separate sector loaders into one:
  - load_sector_performance.py (BaseLoader legacy, daily % returns)
  - load_sector_rankings.py (OptimalLoader modern, rankings + momentum)

Into unified OptimalLoader framework:
  - Computes: daily sector/industry performance (% return, weighted by market cap)
  - Computes: sector/industry rankings (average score, momentum vs 1w/4w/12w ago)
  - Outputs: sector_performance + sector_ranking + industry_ranking (3 tables)
  - Framework: Modern OptimalLoader (consistent with rest of pipeline)

Benefits:
  - Unified OptimalLoader framework (consistency)
  - 1 ECS task instead of 2 (saves ~$0.01-0.02/run + 5-10 min runtime)
  - Single transaction for atomic updates to all 3 tables
  - Easier maintenance (one framework, one error handler)
  - Better integration with pipeline infrastructure

Run: python3 loaders/load_sector_industry_daily.py
"""

import logging
import sys
from datetime import date, timedelta
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class SectorIndustryDailyLoader(OptimalLoader):
    """Consolidated sector + industry daily loader: performance + rankings.

    Market-wide loader (pseudo-symbol "market"). Computes:
    1. Sector/industry performance (daily % return from price changes)
    2. Sector/industry rankings (average score + momentum history)
    """

    table_name = "sector_performance"  # Primary table for watermarking
    primary_key = ("sector", "date")
    watermark_field = "date"
    is_symbol_based = False

    def run(
        self, symbols: list[str] | None = None, parallelism: int = 1, backfill_days: int | None = None
    ) -> dict[str, Any]:
        """Override run() to use market-wide pseudo-symbol."""
        if symbols is None or (isinstance(symbols, list) and len(symbols) == 0):
            symbols = ["market"]
        return super().run(symbols=symbols, parallelism=parallelism, backfill_days=backfill_days)

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute sector/industry metrics for today.

        Args:
            symbol: Pseudo-symbol "market" (ignored)
            since: Optional backfill start date

        Returns:
            List of consolidated metric dicts (empty = write to all 3 tables via side effects)
        """
        if symbol != "market":
            return []

        try:
            target_date = date.today()
            prev_date = target_date - timedelta(days=1)

            with DatabaseContext("write") as cur:
                # ===== SECTOR PERFORMANCE =====
                # Calculate daily % return per sector (weighted by price as market cap proxy)
                cur.execute(
                    """
                    WITH daily_changes AS (
                        SELECT
                            cp.sector,
                            pd_today.symbol,
                            (pd_today.close - pd_prev.close) / NULLIF(pd_prev.close, 0) as daily_return,
                            pd_today.close as market_cap_proxy
                        FROM price_daily pd_today
                        INNER JOIN price_daily pd_prev
                            ON pd_today.symbol = pd_prev.symbol
                            AND pd_prev.date = %s
                        INNER JOIN company_profile cp ON pd_today.symbol = cp.symbol
                        WHERE pd_today.date = %s
                            AND cp.sector IS NOT NULL
                            AND cp.sector != ''
                    ),
                    sector_weighted_avg AS (
                        SELECT
                            sector,
                            SUM(daily_return * market_cap_proxy) / NULLIF(SUM(market_cap_proxy), 0) as return_pct,
                            COUNT(DISTINCT symbol) as stock_count
                        FROM daily_changes
                        GROUP BY sector
                    )
                    INSERT INTO sector_performance (sector, date, return_pct, relative_strength, created_at, updated_at)
                    SELECT
                        sector,
                        %s as date,
                        COALESCE(return_pct, 0) as return_pct,
                        1.0 as relative_strength,
                        NOW() as created_at,
                        NOW() as updated_at
                    FROM sector_weighted_avg
                    ON CONFLICT (sector, date) DO UPDATE SET
                        return_pct = EXCLUDED.return_pct,
                        updated_at = NOW()
                    """,
                    (prev_date, target_date, target_date),
                )
                perf_count = cur.rowcount
                logger.info(f"[SECTOR_INDUSTRY] Inserted {perf_count} sector performance rows")

                # ===== SECTOR RANKINGS =====
                # Rank sectors by average composite score + compute momentum
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
                    """,
                )
                rank_count = cur.rowcount
                logger.info(f"[SECTOR_INDUSTRY] Inserted {rank_count} sector ranking rows")

                # ===== INDUSTRY RANKINGS =====
                # Same ranking logic but for industries
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
                        GROUP BY cp.industry
                    )
                    INSERT INTO industry_ranking
                      (industry_name, date_recorded, current_rank, momentum_score,
                       rank_1w_ago, rank_4w_ago, rank_12w_ago)
                    SELECT
                        i_stats.industry_name,
                        NOW()::date,
                        i_stats.current_rank,
                        COALESCE(i_stats.current_rank - COALESCE(r1.rank, i_stats.current_rank), 0),
                        COALESCE(r1.rank, i_stats.current_rank),
                        COALESCE(r4.rank, i_stats.current_rank),
                        COALESCE(r12.rank, i_stats.current_rank)
                    FROM industry_stats i_stats
                    LEFT JOIN LATERAL (
                        SELECT ir.current_rank AS rank FROM industry_ranking ir
                        WHERE ir.industry_name = i_stats.industry_name
                          AND ir.date_recorded <= NOW()::date - INTERVAL '7 days'
                        ORDER BY ir.date_recorded DESC LIMIT 1
                    ) r1 ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT ir.current_rank AS rank FROM industry_ranking ir
                        WHERE ir.industry_name = i_stats.industry_name
                          AND ir.date_recorded <= NOW()::date - INTERVAL '28 days'
                        ORDER BY ir.date_recorded DESC LIMIT 1
                    ) r4 ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT ir.current_rank AS rank FROM industry_ranking ir
                        WHERE ir.industry_name = i_stats.industry_name
                          AND ir.date_recorded <= NOW()::date - INTERVAL '84 days'
                        ORDER BY ir.date_recorded DESC LIMIT 1
                    ) r12 ON TRUE
                    ON CONFLICT (industry_name, date_recorded) DO UPDATE SET
                        current_rank = EXCLUDED.current_rank,
                        momentum_score = EXCLUDED.momentum_score,
                        rank_1w_ago = EXCLUDED.rank_1w_ago,
                        rank_4w_ago = EXCLUDED.rank_4w_ago,
                        rank_12w_ago = EXCLUDED.rank_12w_ago,
                        updated_at = NOW()
                    """,
                )
                ind_count = cur.rowcount
                logger.info(f"[SECTOR_INDUSTRY] Inserted {ind_count} industry ranking rows")

                # Delete stale data (keep 90 days)
                cur.execute("DELETE FROM sector_performance WHERE date < NOW()::date - INTERVAL '90 days'")
                cur.execute("DELETE FROM sector_ranking WHERE date < NOW()::date - INTERVAL '90 days'")
                cur.execute("DELETE FROM industry_ranking WHERE date_recorded < NOW()::date - INTERVAL '90 days'")

        except Exception as e:
            logger.error(f"[SECTOR_INDUSTRY] Computation failed: {e}", exc_info=True)
            raise

        # Return empty list (all writes handled via side effects)
        return []

    def load_global(self) -> int:
        """Market-wide loader uses load_global pattern."""
        result = self.run(["market"], parallelism=1)
        return 0


if __name__ == "__main__":
    sys.exit(run_loader(
        SectorIndustryDailyLoader,
        description="Consolidated sector + industry daily (performance + rankings)",
        global_mode=True,
    ))
