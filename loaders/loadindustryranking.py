#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
loadindustryranking.py — Compute industry_ranking from constituent stock momentum

Computes 4-week momentum per industry by averaging 4-week returns of all
stocks in that industry. Ranks all 197+ industries by momentum.

Pure SQL — uses company_profile.industry to group, price_daily for returns.
Run after loadpricedaily.py and loadcompanyprofile.py.

USAGE:
  python3 loadindustryranking.py
"""

import sys
from datetime import date, timedelta
from typing import Optional, List
from utils.structured_logger import get_logger
from utils.db_connection import get_db_connection
from config.env_loader import load_env

logger = get_logger(__name__)


def compute_industry_ranking():
    """Compute industry momentum ranking from price_daily + company_profile."""
    load_env()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Compute 4-week momentum per industry, rank them
            cur.execute("""
                WITH recent_prices AS (
                    SELECT symbol, close,
                           LAG(close, 20) OVER (PARTITION BY symbol ORDER BY date) AS close_4w_ago,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM price_daily
                    WHERE date >= CURRENT_DATE - INTERVAL '60 days'
                      AND close > 0
                ),
                latest_prices AS (
                    SELECT symbol, close, close_4w_ago
                    FROM recent_prices
                    WHERE rn = 1 AND close_4w_ago > 0
                ),
                stock_returns AS (
                    SELECT cp.industry,
                           lp.symbol,
                           (lp.close - lp.close_4w_ago) / lp.close_4w_ago * 100 AS return_4w
                    FROM latest_prices lp
                    JOIN company_profile cp ON cp.ticker = lp.symbol
                    WHERE cp.industry IS NOT NULL AND cp.industry <> ''
                ),
                industry_momentum AS (
                    SELECT industry,
                           COUNT(*) AS stock_count,
                           AVG(return_4w) AS momentum_score,
                           CURRENT_DATE AS date_recorded
                    FROM stock_returns
                    GROUP BY industry
                    HAVING COUNT(*) >= 2
                ),
                ranked AS (
                    SELECT industry,
                           momentum_score,
                           date_recorded,
                           RANK() OVER (ORDER BY momentum_score DESC) AS current_rank,
                           LAG(RANK() OVER (ORDER BY momentum_score DESC))
                                OVER (ORDER BY industry) AS rank_4w_ago
                    FROM industry_momentum
                )
                DELETE FROM industry_ranking
                WHERE date_recorded = CURRENT_DATE;

                INSERT INTO industry_ranking (industry, current_rank, rank_4w_ago, momentum_score, date_recorded)
                SELECT industry, current_rank, rank_4w_ago, momentum_score, date_recorded
                FROM ranked;
            """)
            conn.commit()
            logger.info("Industry ranking computed successfully")
            return 0
    except Exception as e:
        logger.error(f"Error computing industry ranking: {e}")
        conn.rollback()
        return 1
    finally:
        conn.close()


def main():
    return compute_industry_ranking()


if __name__ == "__main__":
    sys.exit(main())

