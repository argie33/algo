#!/usr/bin/env python3
"""
Backfill Historical Sector & Industry Rankings
Calculates rankings for past dates (1w, 4w, 12w ago) and stores them
Allows frontend to show historical rank comparisons
"""

import logging
import os
import sys
from datetime import datetime, timedelta

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


def calculate_sector_rankings_for_date(conn, target_date):
    """Calculate sector rankings for a specific date based on price data from that date"""
    logger.info(f"📊 Calculating sector rankings for {target_date}...")
    cursor = conn.cursor()

    try:
        # Get all sectors
        cursor.execute("""
            SELECT DISTINCT sector FROM company_profile
            WHERE sector IS NOT NULL
            ORDER BY sector
        """)
        sectors = cursor.fetchall()

        # Calculate rankings for this date using performance data
        cursor.execute("""
            WITH sector_perf AS (
                SELECT
                    cp.sector,
                    AVG(COALESCE(sp.performance_20d, 0)) as avg_performance
                FROM company_profile cp
                LEFT JOIN (
                    SELECT DISTINCT ON (sector_name)
                        sector_name, performance_20d
                    FROM sector_performance
                    WHERE fetched_at::date <= %s
                    ORDER BY sector_name, fetched_at DESC
                ) sp ON LOWER(cp.sector) = LOWER(sp.sector_name)
                WHERE cp.sector IS NOT NULL
                GROUP BY cp.sector
            )
            SELECT
                sector,
                avg_performance,
                ROW_NUMBER() OVER (ORDER BY avg_performance DESC) as rank
            FROM sector_perf
            ORDER BY rank
        """, (target_date,))

        rankings = cursor.fetchall()
        return {sector: rank for sector, _, rank in rankings}

    except Exception as e:
        logger.error(f"Error calculating sector rankings for {target_date}: {e}")
        return {}


def calculate_industry_rankings_for_date(conn, target_date):
    """Calculate industry rankings for a specific date based on price data from that date"""
    logger.info(f"🏭 Calculating industry rankings for {target_date}...")
    cursor = conn.cursor()

    try:
        # Get all industries with their sectors
        cursor.execute("""
            SELECT DISTINCT cp.industry, cp.sector
            FROM company_profile cp
            WHERE cp.industry IS NOT NULL
            ORDER BY cp.industry
        """)
        industries = cursor.fetchall()

        # Calculate rankings for this date using performance data
        cursor.execute("""
            WITH industry_perf AS (
                SELECT
                    cp.industry,
                    cp.sector,
                    AVG(COALESCE(ip.performance_20d, 0)) as avg_performance,
                    COUNT(DISTINCT cp.ticker) as stock_count
                FROM company_profile cp
                LEFT JOIN (
                    SELECT DISTINCT ON (industry)
                        industry, performance_20d
                    FROM industry_performance
                    WHERE fetched_at::date <= %s
                    ORDER BY industry, fetched_at DESC
                ) ip ON LOWER(cp.industry) = LOWER(ip.industry)
                WHERE cp.industry IS NOT NULL
                GROUP BY cp.industry, cp.sector
            )
            SELECT
                industry,
                sector,
                avg_performance,
                stock_count,
                ROW_NUMBER() OVER (ORDER BY avg_performance DESC) as rank
            FROM industry_perf
            ORDER BY rank
        """, (target_date,))

        rankings = cursor.fetchall()
        return {industry: (rank, sector, stock_count) for industry, sector, _, stock_count, rank in rankings}

    except Exception as e:
        logger.error(f"Error calculating industry rankings for {target_date}: {e}")
        return {}


def insert_sector_rankings(conn, target_date, rankings):
    """Insert calculated sector rankings into sector_ranking table"""
    logger.info(f"💾 Inserting sector rankings for {target_date}...")
    cursor = conn.cursor()

    try:
        for sector, rank in rankings.items():
            # Check if entry already exists
            cursor.execute(
                "SELECT id FROM sector_ranking WHERE sector = %s AND date = %s",
                (sector, target_date)
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing entry
                cursor.execute("""
                    UPDATE sector_ranking
                    SET current_rank = %s
                    WHERE sector = %s AND date = %s
                """, (rank, sector, target_date))
                logger.info(f"  Updated {sector}: Rank #{rank}")
            else:
                # Insert new entry
                cursor.execute("""
                    INSERT INTO sector_ranking (sector, date, current_rank, momentum_score, trend, fetched_at)
                    VALUES (%s, %s, %s, 0, '➡️', NOW())
                """, (sector, target_date, rank))
                logger.info(f"  Inserted {sector}: Rank #{rank}")

        conn.commit()
        logger.info(f"✅ Sector rankings for {target_date} saved")

    except Exception as e:
        conn.rollback()
        logger.error(f"Error inserting sector rankings: {e}")


def insert_industry_rankings(conn, target_date, rankings):
    """Insert calculated industry rankings into industry_ranking table"""
    logger.info(f"💾 Inserting industry rankings for {target_date}...")
    cursor = conn.cursor()

    try:
        for industry, (rank, sector, stock_count) in rankings.items():
            # Check if entry already exists
            cursor.execute(
                "SELECT id FROM industry_ranking WHERE industry = %s AND date = %s",
                (industry, target_date)
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing entry
                cursor.execute("""
                    UPDATE industry_ranking
                    SET current_rank = %s, stock_count = %s
                    WHERE industry = %s AND date = %s
                """, (rank, stock_count, industry, target_date))
                logger.info(f"  Updated {industry}: Rank #{rank}")
            else:
                # Insert new entry
                cursor.execute("""
                    INSERT INTO industry_ranking (industry, date, current_rank, stock_count, momentum_score, trend, fetched_at)
                    VALUES (%s, %s, %s, %s, 0, '➡️', NOW())
                """, (industry, target_date, rank, stock_count))
                logger.info(f"  Inserted {industry}: Rank #{rank}")

        conn.commit()
        logger.info(f"✅ Industry rankings for {target_date} saved")

    except Exception as e:
        conn.rollback()
        logger.error(f"Error inserting industry rankings: {e}")


def main():
    """Main execution"""
    logger.info("🚀 Starting historical ranking backfill...")

    conn = get_db_connection()

    try:
        # Calculate target dates
        today = datetime.now().date()
        dates_to_backfill = [
            today - timedelta(days=7),   # 1 week ago
            today - timedelta(days=28),  # 4 weeks ago
            today - timedelta(days=84),  # 12 weeks ago
        ]

        for target_date in dates_to_backfill:
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing {target_date}")
            logger.info(f"{'='*60}")

            # Calculate and insert rankings
            sector_rankings = calculate_sector_rankings_for_date(conn, target_date)
            if sector_rankings:
                insert_sector_rankings(conn, target_date, sector_rankings)

            industry_rankings = calculate_industry_rankings_for_date(conn, target_date)
            if industry_rankings:
                insert_industry_rankings(conn, target_date, industry_rankings)

        logger.info(f"\n{'='*60}")
        logger.info("✅ Historical ranking backfill complete!")
        logger.info(f"{'='*60}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
