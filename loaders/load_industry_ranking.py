#!/usr/bin/env python3
"""Industry Ranking Loader - Rank industries by composite stock scores."""

import logging
import sys
from datetime import date
from typing import Any

from loaders.loader_helper import setup_imports
from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

setup_imports()

logger = logging.getLogger(__name__)


class IndustryRankingLoader(OptimalLoader):
    """Rank industries by composite score from stock_scores + company_profile."""

    table_name = "industry_ranking"
    primary_key = ("industry", "date_recorded")
    watermark_field = "date_recorded"

    def fetch_global(self, since: date | None) -> list[dict[str, Any]] | None:
        """Compute industry rankings from stock scores and company profile data."""
        try:
            with DatabaseContext("read") as cur:
                # VALIDATION: Ensure price data exists (required for industry ranking computation)
                cur.execute("SELECT date FROM price_daily ORDER BY date DESC LIMIT 1")
                row = cur.fetchone()
                latest_date = row["date"] if row else None

                if not latest_date:
                    raise ValueError(
                        "[CRITICAL] No price data found in price_daily table. Required for industry ranking computation."
                    )

                # Rank industries by average composite score; pull historical ranks for comparison
                # CRITICAL: Only use composite_score where data_completeness >= 50% (real data, not degraded)
                cur.execute("""
                    WITH current_ranks AS (
                        SELECT
                            cp.industry,
                            COUNT(DISTINCT cp.ticker) AS stock_count,
                            AVG(ss.composite_score)   AS avg_composite_score,
                            RANK() OVER (ORDER BY AVG(ss.composite_score) DESC NULLS LAST) AS industry_rank
                        FROM company_profile cp
                        LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
                        WHERE cp.industry IS NOT NULL AND TRIM(cp.industry) != ''
                          AND (ss.symbol IS NULL OR ss.data_completeness >= 50)
                        GROUP BY cp.industry
                    ),
                    rank_1w AS (
                        SELECT industry, current_rank AS rank_1w
                        FROM industry_ranking
                        WHERE date_recorded = (
                            SELECT date_recorded FROM industry_ranking
                            WHERE date_recorded <= CURRENT_DATE - INTERVAL '7 days'
                            ORDER BY date_recorded DESC LIMIT 1
                        )
                    ),
                    rank_4w AS (
                        SELECT industry, current_rank AS rank_4w
                        FROM industry_ranking
                        WHERE date_recorded = (
                            SELECT date_recorded FROM industry_ranking
                            WHERE date_recorded <= CURRENT_DATE - INTERVAL '28 days'
                            ORDER BY date_recorded DESC LIMIT 1
                        )
                    ),
                    rank_12w AS (
                        SELECT industry, current_rank AS rank_12w
                        FROM industry_ranking
                        WHERE date_recorded = (
                            SELECT date_recorded FROM industry_ranking
                            WHERE date_recorded <= CURRENT_DATE - INTERVAL '84 days'
                            ORDER BY date_recorded DESC LIMIT 1
                        )
                    )
                    SELECT
                        cr.industry,
                        cr.industry_rank        AS current_rank,
                        cr.avg_composite_score  AS momentum_score,
                        r1.rank_1w              AS rank_1w_ago,
                        r4.rank_4w              AS rank_4w_ago,
                        r12.rank_12w            AS rank_12w_ago
                    FROM current_ranks cr
                    LEFT JOIN rank_1w  r1  ON r1.industry  = cr.industry
                    LEFT JOIN rank_4w  r4  ON r4.industry  = cr.industry
                    LEFT JOIN rank_12w r12 ON r12.industry = cr.industry
                    ORDER BY cr.industry_rank
                """)

                rows = cur.fetchall()
                if not rows:
                    logger.error(
                        "No industry ranking data computed — company_profile or stock_scores empty. "
                        "Returning explicit data_unavailable marker."
                    )
                    return [{"data_unavailable": True, "reason": "no_ranking_data_computed"}]

                # Validate and build results
                results = []
                for r in rows:
                    # VALIDATION: Ensure required fields are present
                    if r["industry"] is None or r["current_rank"] is None:
                        logger.error(
                            f"Skipping invalid industry ranking record: industry={r['industry']}, rank={r['current_rank']}"
                        )
                        continue

                    # Convert momentum_score to float; mark as unavailable if null
                    momentum_score = None
                    if r["momentum_score"] is not None:
                        try:
                            momentum_score = float(r["momentum_score"])
                        except (ValueError, TypeError) as e:
                            logger.error(
                                f"Failed to convert momentum_score for {r['industry']}: {e}. Skipping record."
                            )
                            continue

                    results.append({
                        "industry": r["industry"],
                        "date_recorded": latest_date,
                        "current_rank": r["current_rank"],
                        "momentum_score": momentum_score,
                        "rank_1w_ago": r["rank_1w_ago"],  # May be None if < 7 days of history
                        "rank_4w_ago": r["rank_4w_ago"],  # May be None if < 28 days of history
                        "rank_12w_ago": r["rank_12w_ago"],  # May be None if < 84 days of history
                    })

                if not results:
                    logger.error(
                        "All industry ranking records failed validation. Returning explicit data_unavailable marker."
                    )
                    return [{"data_unavailable": True, "reason": "all_records_failed_validation"}]

                return results

        except ValueError as e:
            logger.error(f"[CRITICAL] Validation error in industry ranking computation: {e}")
            raise RuntimeError(f"Validation failed: {e}") from e
        except (ZeroDivisionError, TypeError) as e:
            logger.error(f"[CRITICAL] Computation error in industry ranking: {e}")
            raise RuntimeError(f"Computation failed: {e}") from e


if __name__ == "__main__":
    sys.exit(run_loader(IndustryRankingLoader, global_mode=True))
