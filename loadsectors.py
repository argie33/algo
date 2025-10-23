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
    Populate sector_ranking table with sector rankings for RECENT dates only (last 3 years)
    Calculates rankings based on price_daily data for each date
    Stores historical ranks from previous snapshots
    Uses batch inserts for fast performance (~90+ dates/second)
    """
    logger.info("📊 Populating sector_ranking table for recent dates (last 3 years) with batch inserts...")
    cursor = conn.cursor()

    try:
        # Get RECENT dates only (last 3 years for fast loading)
        cursor.execute("""
            SELECT DISTINCT date
            FROM price_daily
            WHERE date >= NOW() - INTERVAL '3 years'
            ORDER BY date
        """)

        price_dates = [row[0] for row in cursor.fetchall()]
        logger.info(f"Found {len(price_dates)} dates with price data")

        if not price_dates:
            logger.warning("⚠️ No price data found")
            cursor.close()
            return

        # Get all sectors from company_profile
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

        # Batch insert setup
        batch_data = []
        batch_size = 500
        processed_dates = 0

        # Process each date
        for target_date in price_dates:

            # Calculate current ranks for all sectors based on price_daily data for this date
            cursor.execute("""
                WITH sector_perf AS (
                    SELECT
                        cp.sector,
                        AVG(COALESCE(pd.close - pd.open, 0)) as avg_performance
                    FROM company_profile cp
                    LEFT JOIN price_daily pd ON cp.ticker = pd.symbol AND pd.date = %s
                    WHERE cp.sector IS NOT NULL
                    GROUP BY cp.sector
                )
                SELECT
                    sector,
                    avg_performance,
                    ROW_NUMBER() OVER (ORDER BY avg_performance DESC) as current_rank
                FROM sector_perf
                ORDER BY current_rank
            """, (target_date,))

            rankings = cursor.fetchall()
            sector_current_ranks = {sector: rank for sector, perf, rank in rankings}

            # For each sector, get historical ranks from previous snapshots
            # CRITICAL: These are ACTUAL historical ranks stored in the table
            historical_ranks = {}
            for sector_name, in sectors:
                # Get rank from 1 week ago (7 days)
                cursor.execute("""
                    SELECT current_rank FROM sector_ranking
                    WHERE sector = %s AND date = %s - INTERVAL '7 days'
                    LIMIT 1
                """, (sector_name, target_date))
                rank_1w = cursor.fetchone()

                # Get rank from 4 weeks ago (28 days)
                cursor.execute("""
                    SELECT current_rank FROM sector_ranking
                    WHERE sector = %s AND date = %s - INTERVAL '28 days'
                    LIMIT 1
                """, (sector_name, target_date))
                rank_4w = cursor.fetchone()

                # Get rank from 12 weeks ago (84 days)
                cursor.execute("""
                    SELECT current_rank FROM sector_ranking
                    WHERE sector = %s AND date = %s - INTERVAL '84 days'
                    LIMIT 1
                """, (sector_name, target_date))
                rank_12w = cursor.fetchone()

                historical_ranks[sector_name] = {
                    'rank_1w_ago': rank_1w[0] if rank_1w else None,
                    'rank_4w_ago': rank_4w[0] if rank_4w else None,
                    'rank_12w_ago': rank_12w[0] if rank_12w else None,
                }

            # Batch insert for this date
            for sector_name, in sectors:
                current_rank = sector_current_ranks.get(sector_name)
                hist = historical_ranks.get(sector_name, {})

                # Calculate trend based on performance
                perf_value = 0  # Default performance
                for sector, perf, rank in rankings:
                    if sector == sector_name:
                        perf_value = perf
                        break

                trend = "📈" if perf_value > 0 else "📉" if perf_value < 0 else "➡️"

                # Add to batch
                batch_data.append((
                    sector_name,
                    target_date,
                    current_rank,
                    hist.get('rank_1w_ago'),
                    hist.get('rank_4w_ago'),
                    hist.get('rank_12w_ago'),
                    perf_value,
                    trend
                ))

                # Insert batch when full
                if len(batch_data) >= batch_size:
                    cursor.executemany("""
                        INSERT INTO sector_ranking
                        (sector, date, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago, momentum_score, trend)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT(sector, date) DO UPDATE SET
                            current_rank = EXCLUDED.current_rank,
                            rank_1w_ago = EXCLUDED.rank_1w_ago,
                            rank_4w_ago = EXCLUDED.rank_4w_ago,
                            rank_12w_ago = EXCLUDED.rank_12w_ago,
                            momentum_score = EXCLUDED.momentum_score,
                            trend = EXCLUDED.trend
                    """, batch_data)
                    batch_data = []
                    processed_dates += 1
                    if processed_dates % 20 == 0:
                        logger.info(f"  ✅ Processed {processed_dates * batch_size // 12:.0f} sector-date combinations...")

        # Insert remaining batch
        if batch_data:
            cursor.executemany("""
                INSERT INTO sector_ranking
                (sector, date, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago, momentum_score, trend)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(sector, date) DO UPDATE SET
                    current_rank = EXCLUDED.current_rank,
                    rank_1w_ago = EXCLUDED.rank_1w_ago,
                    rank_4w_ago = EXCLUDED.rank_4w_ago,
                    rank_12w_ago = EXCLUDED.rank_12w_ago,
                    momentum_score = EXCLUDED.momentum_score,
                    trend = EXCLUDED.trend
            """, batch_data)

        conn.commit()
        logger.info(f"✅ Successfully populated sector_ranking table for {len(price_dates)} recent dates with {len(sectors)} sectors")

    except Exception as e:
        logger.error(f"Error populating sector_ranking: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()


def populate_industry_ranking(conn):
    """
    Populate industry_ranking table with industry rankings for RECENT dates only (last 3 years)
    Calculates rankings based on price_daily data for each date
    Stores historical ranks from previous snapshots
    Uses batch inserts for fast performance (~90+ dates/second)
    """
    logger.info("📊 Populating industry_ranking table for recent dates (last 3 years) with batch inserts...")
    cursor = conn.cursor()

    try:
        # Get RECENT dates only (last 3 years for fast loading)
        cursor.execute("""
            SELECT DISTINCT date
            FROM price_daily
            WHERE date >= NOW() - INTERVAL '3 years'
            ORDER BY date
        """)

        price_dates = [row[0] for row in cursor.fetchall()]
        logger.info(f"Found {len(price_dates)} dates with price data")

        if not price_dates:
            logger.warning("⚠️ No price data found")
            cursor.close()
            return

        # Get all industries from company_profile
        cursor.execute("""
            SELECT DISTINCT industry
            FROM company_profile
            WHERE industry IS NOT NULL
            ORDER BY industry
        """)

        industries = [row[0] for row in cursor.fetchall()]

        if not industries:
            logger.warning("⚠️ No industries found in company_profile table")
            cursor.close()
            return

        logger.info(f"Found {len(industries)} industries")

        # Batch insert setup
        batch_data = []
        batch_size = 500
        processed_dates = 0

        # Process each date
        for target_date in price_dates:
            # Calculate industry rankings based on price_daily data for this date
            cursor.execute("""
                WITH industry_perf AS (
                    SELECT
                        cp.industry,
                        AVG(COALESCE(pd.close - pd.open, 0)) as avg_performance,
                        COUNT(DISTINCT cp.ticker) as stock_count
                    FROM company_profile cp
                    LEFT JOIN price_daily pd ON cp.ticker = pd.symbol AND pd.date = %s
                    WHERE cp.industry IS NOT NULL
                    GROUP BY cp.industry
                )
                SELECT
                    industry,
                    avg_performance,
                    stock_count,
                    ROW_NUMBER() OVER (ORDER BY avg_performance DESC) as current_rank
                FROM industry_perf
                ORDER BY current_rank
            """, (target_date,))

            rankings = cursor.fetchall()
            industry_current_ranks = {industry: rank for industry, perf, count, rank in rankings}

            # For each industry, get historical ranks from previous snapshots
            historical_ranks = {}
            for industry_name in industries:
                # Get rank from 1 week ago (7 days)
                cursor.execute("""
                    SELECT current_rank FROM industry_ranking
                    WHERE industry = %s AND date = %s - INTERVAL '7 days'
                    LIMIT 1
                """, (industry_name, target_date))
                rank_1w = cursor.fetchone()

                # Get rank from 4 weeks ago (28 days)
                cursor.execute("""
                    SELECT current_rank FROM industry_ranking
                    WHERE industry = %s AND date = %s - INTERVAL '28 days'
                    LIMIT 1
                """, (industry_name, target_date))
                rank_4w = cursor.fetchone()

                # Get rank from 8 weeks ago (56 days)
                cursor.execute("""
                    SELECT current_rank FROM industry_ranking
                    WHERE industry = %s AND date = %s - INTERVAL '56 days'
                    LIMIT 1
                """, (industry_name, target_date))
                rank_8w = cursor.fetchone()

                historical_ranks[industry_name] = {
                    'rank_1w_ago': rank_1w[0] if rank_1w else None,
                    'rank_4w_ago': rank_4w[0] if rank_4w else None,
                    'rank_8w_ago': rank_8w[0] if rank_8w else None,
                }

            # Batch insert for this date
            for industry_name, perf, stock_count, current_rank in rankings:
                trend = "📈" if perf > 0 else "📉" if perf < 0 else "➡️"
                hist = historical_ranks.get(industry_name, {})

                # Add to batch
                batch_data.append((
                    industry_name,
                    target_date,
                    current_rank,
                    hist.get('rank_1w_ago'),
                    hist.get('rank_4w_ago'),
                    hist.get('rank_8w_ago'),
                    perf,
                    stock_count,
                    trend
                ))

                # Insert batch when full
                if len(batch_data) >= batch_size:
                    cursor.executemany("""
                        INSERT INTO industry_ranking
                        (industry, date, current_rank, rank_1w_ago, rank_4w_ago, rank_8w_ago,
                         momentum_score, stock_count, trend)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT(industry, date) DO UPDATE SET
                            current_rank = EXCLUDED.current_rank,
                            rank_1w_ago = EXCLUDED.rank_1w_ago,
                            rank_4w_ago = EXCLUDED.rank_4w_ago,
                            rank_8w_ago = EXCLUDED.rank_8w_ago,
                            momentum_score = EXCLUDED.momentum_score,
                            stock_count = EXCLUDED.stock_count,
                            trend = EXCLUDED.trend
                    """, batch_data)
                    batch_data = []
                    processed_dates += 1
                    if processed_dates % 20 == 0:
                        logger.info(f"  ✅ Processed {processed_dates * batch_size // 145:.0f} industry-date combinations...")

        # Insert remaining batch
        if batch_data:
            cursor.executemany("""
                INSERT INTO industry_ranking
                (industry, date, current_rank, rank_1w_ago, rank_4w_ago, rank_8w_ago,
                 momentum_score, stock_count, trend)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(industry, date) DO UPDATE SET
                    current_rank = EXCLUDED.current_rank,
                    rank_1w_ago = EXCLUDED.rank_1w_ago,
                    rank_4w_ago = EXCLUDED.rank_4w_ago,
                    rank_8w_ago = EXCLUDED.rank_8w_ago,
                    momentum_score = EXCLUDED.momentum_score,
                    stock_count = EXCLUDED.stock_count,
                    trend = EXCLUDED.trend
            """, batch_data)

        conn.commit()
        logger.info(f"✅ Successfully populated industry_ranking table for {len(price_dates)} recent dates with {len(industries)} industries")

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
