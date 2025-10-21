#!/usr/bin/env python3
"""
Unified Sector & Industry Ranking Loader
Consolidates ALL sector and industry loading into one unified module
Populates both sector_ranking and industry_ranking tables with current performance data
"""

import logging
import os
import sys
from datetime import datetime

import psycopg2

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration from environment
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_NAME = os.getenv('DB_NAME', 'stocks')


def get_db_connection():
    """Establish database connection"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)


def populate_sector_ranking(conn):
    """
    Populate sector_ranking table with current sector performance data
    Aggregates data from industry_performance grouped by sector
    """
    logger.info("📊 Populating sector_ranking table with current rankings...")
    cursor = conn.cursor()

    try:
        today = datetime.now().date()

        # Get all sectors from company_profile, aggregated with performance data
        cursor.execute("""
            SELECT DISTINCT cp.sector
            FROM company_profile cp
            WHERE cp.sector IS NOT NULL
            ORDER BY cp.sector
        """)

        sectors = cursor.fetchall()

        if not sectors:
            logger.warning("⚠️ No sectors found in company_profile table")
            cursor.close()
            return

        logger.info(f"Found {len(sectors)} sectors")

        # For each sector, calculate aggregated metrics
        for sector_name, in sectors:
            # Get aggregated performance for this sector
            cursor.execute("""
                SELECT
                    COUNT(DISTINCT ip.industry) as industry_count,
                    AVG(COALESCE(ip.performance_20d, 0)) as avg_performance
                FROM industry_performance ip
                WHERE ip.industry IN (
                    SELECT DISTINCT cp.industry
                    FROM company_profile cp
                    WHERE cp.sector = %s AND cp.industry IS NOT NULL
                )
            """, (sector_name,))

            result = cursor.fetchone()
            industry_count = result[0] if result and result[0] else 0
            avg_performance = result[1] if result and result[1] else 0

            # Determine trend based on performance
            trend = "📈" if avg_performance > 0 else "📉" if avg_performance < 0 else "➡️"

            # Insert into sector_ranking
            cursor.execute("""
                INSERT INTO sector_ranking
                (sector, date, current_rank, rank_1w_ago, rank_4w_ago, rank_8w_ago,
                 momentum_score, industry_count, trend)
                VALUES (%s, %s, NULL, NULL, NULL, NULL, %s, %s, %s)
                ON CONFLICT(sector, date) DO UPDATE SET
                    momentum_score = EXCLUDED.momentum_score,
                    industry_count = EXCLUDED.industry_count,
                    trend = EXCLUDED.trend
            """, (sector_name, today, avg_performance, industry_count, trend))

        conn.commit()
        logger.info(f"✅ Successfully populated sector_ranking table with {len(sectors)} sectors for {today}")

    except Exception as e:
        logger.error(f"Error populating sector_ranking: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()


def populate_industry_ranking(conn):
    """
    Populate industry_ranking table with current industry performance data
    Gets data from industry_performance (current snapshot) and ranks by momentum
    """
    logger.info("📊 Populating industry_ranking table with current rankings...")
    cursor = conn.cursor()

    try:
        today = datetime.now().date()

        # Get all industries from industry_performance, ordered by momentum (highest to lowest)
        cursor.execute("""
            SELECT industry,
                   COALESCE(momentum, '0'),
                   stock_count,
                   performance_20d
            FROM industry_performance
            WHERE industry IS NOT NULL
            ORDER BY COALESCE(performance_20d, 0) DESC
        """)

        industries = cursor.fetchall()

        if not industries:
            logger.warning("⚠️ No industries found in industry_performance table")
            cursor.close()
            return

        logger.info(f"Found {len(industries)} industries to rank")

        # Insert rankings for today
        for current_rank, (industry_name, momentum, stock_count, momentum_score) in enumerate(industries, 1):
            # Determine trend based on momentum indicator
            trend = "📈" if momentum == "Strong" else "📉" if momentum == "Weak" else "➡️"

            # Convert momentum_score to numeric (performance_20d is typically -100 to +100)
            try:
                score = float(momentum_score) if momentum_score else 0
            except (ValueError, TypeError):
                score = 0

            # Insert into industry_ranking
            cursor.execute("""
                INSERT INTO industry_ranking
                (industry, date, current_rank, rank_1w_ago, rank_4w_ago, rank_8w_ago,
                 momentum_score, stock_count, trend)
                VALUES (%s, %s, %s, NULL, NULL, NULL, %s, %s, %s)
                ON CONFLICT(industry, date) DO UPDATE SET
                    current_rank = EXCLUDED.current_rank,
                    momentum_score = EXCLUDED.momentum_score,
                    stock_count = EXCLUDED.stock_count,
                    trend = EXCLUDED.trend
            """, (industry_name, today, current_rank, score, stock_count, trend))

        conn.commit()
        logger.info(f"✅ Successfully populated industry_ranking table with {len(industries)} industries for {today}")

    except Exception as e:
        logger.error(f"Error populating industry_ranking: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()


def main():
    """Main function"""
    logger.info("="*60)
    logger.info("🚀 UNIFIED SECTOR & INDUSTRY RANKING LOADER")
    logger.info("="*60)

    conn = get_db_connection()

    try:
        # Populate sector rankings with aggregated data
        populate_sector_ranking(conn)

        # Populate industry rankings with current data
        populate_industry_ranking(conn)

        logger.info("="*60)
        logger.info("✅ SECTOR & INDUSTRY RANKING LOADING COMPLETE")
        logger.info("="*60)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
