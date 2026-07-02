#!/usr/bin/env python3
"""Sector Ranking Loader - Rank sectors by composite stock scores."""

import logging
import sys
from datetime import date
from typing import Any

import psycopg2

from loaders.runner import run_loader
from utils.loaders import execute_query, fetch_latest
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class SectorRankingLoader(OptimalLoader):
    """Rank sectors by composite score from stock_scores + company_profile."""

    table_name = "sector_ranking"
    primary_key = ("sector_name", "date")
    watermark_field = "date"

    def fetch_global(self, since: date | None) -> list[dict[str, Any]]:
        """Compute sector rankings from stock scores and company profile data."""
        try:
            row = fetch_latest("price_daily", "date")
            latest_date = row["date"] if row else None

            if not latest_date:
                raise ValueError("No price data found in price_daily table. Required for sector ranking computation.")

            # Rank sectors by average composite score; pull historical ranks for comparison
            # CRITICAL: Only use composite_score where data_completeness >= 50% (real data, not degraded)
            rows = execute_query("""
                WITH current_ranks AS (
                        SELECT
                            cp.sector AS sector_name,
                            COUNT(DISTINCT cp.ticker) AS stock_count,
                            AVG(ss.composite_score)   AS avg_composite_score,
                            RANK() OVER (ORDER BY AVG(ss.composite_score) DESC NULLS LAST) AS sector_rank
                        FROM company_profile cp
                        LEFT JOIN stock_scores ss ON cp.ticker = ss.symbol
                        WHERE cp.sector IS NOT NULL AND TRIM(cp.sector) != ''
                          AND (ss.symbol IS NULL OR ss.data_completeness >= 50)
                        GROUP BY cp.sector
                    ),
                    rank_1w AS (
                        SELECT sector_name, current_rank AS rank_1w
                        FROM sector_ranking
                        WHERE date = (
                            SELECT date FROM sector_ranking
                            WHERE date <= CURRENT_DATE - INTERVAL '7 days'
                            ORDER BY date DESC LIMIT 1
                        )
                    ),
                    rank_4w AS (
                        SELECT sector_name, current_rank AS rank_4w
                        FROM sector_ranking
                        WHERE date = (
                            SELECT date FROM sector_ranking
                            WHERE date <= CURRENT_DATE - INTERVAL '28 days'
                            ORDER BY date DESC LIMIT 1
                        )
                    ),
                    rank_12w AS (
                        SELECT sector_name, current_rank AS rank_12w
                        FROM sector_ranking
                        WHERE date = (
                            SELECT date FROM sector_ranking
                            WHERE date <= CURRENT_DATE - INTERVAL '84 days'
                            ORDER BY date DESC LIMIT 1
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

            if not rows:
                raise RuntimeError(
                    "Sector ranking data missing: No sectors found in ranking query. "
                    "Check that company_profile and stock_scores tables have data. "
                    "Sectors are critical for portfolio diversification signals."
                )

            valid_rows = []
            for r in rows:
                current_rank = r["current_rank"]
                if current_rank is None:
                    raise ValueError(
                        f"[SECTOR_RANKING] Sector {r['sector_name']} missing required current_rank — "
                        "all sectors must have complete ranking data for signal generation"
                    )
                momentum = r["momentum_score"]
                if momentum is None:
                    raise ValueError(
                        f"[SECTOR_RANKING] Sector {r['sector_name']} missing required momentum_score — "
                        "cannot default momentum to 0.0; signal requires explicit momentum data"
                    )
                # Check for missing historical rank data - log but don't hide with -1 defaults
                missing_history = []
                if r["rank_1w_ago"] is None:
                    missing_history.append("1w")
                if r["rank_4w_ago"] is None:
                    missing_history.append("4w")
                if r["rank_12w_ago"] is None:
                    missing_history.append("12w")

                if missing_history:
                    logger.warning(
                        f"[SECTOR_RANKING] {r['sector_name']}: Missing historical rank data for {', '.join(missing_history)}. "
                        f"Historical comparison may be incomplete. Refusing to use -1 defaults that would hide missing data."
                    )

                valid_rows.append(
                    {
                        "sector_name": r["sector_name"],
                        "date": latest_date,
                        "current_rank": current_rank,
                        "momentum_score": float(momentum),
                        "rank_1w_ago": r["rank_1w_ago"],
                        "rank_4w_ago": r["rank_4w_ago"],
                        "rank_12w_ago": r["rank_12w_ago"],
                        "historical_data_available": all(r[f"rank_{p}_ago"] is not None for p in ["1w", "4w", "12w"]),
                    }
                )

            if not valid_rows:
                raise RuntimeError(
                    "Sector ranking validation failed: No valid sector entries after validation checks. "
                    "All sectors must have required fields (rank, momentum). "
                    "Check database data integrity before proceeding."
                )

            return valid_rows

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e


if __name__ == "__main__":
    sys.exit(run_loader(SectorRankingLoader, global_mode=True))
