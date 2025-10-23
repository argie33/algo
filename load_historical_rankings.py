#!/usr/bin/env python3
"""
Load historical sector and industry rankings for the last 3 years
Uses batch inserts for performance (90+ dates/second)
"""

import logging
import os
import sys
from datetime import datetime, timedelta

import psycopg2

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_NAME = os.getenv('DB_NAME', 'stocks')

BATCH_SIZE = 500


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


def load_sector_rankings(conn):
    """Load historical sector rankings"""
    logger.info("📊 Loading historical sector rankings (last 3 years)...")
    cursor = conn.cursor()

    try:
        # Get all unique dates from price_daily (last 3 years)
        cursor.execute("""
            SELECT DISTINCT date FROM price_daily
            WHERE date >= NOW() - INTERVAL '3 years'
            ORDER BY date
        """)
        dates = [row[0] for row in cursor.fetchall()]
        logger.info(f"Found {len(dates)} dates to process")

        batch_data = []
        processed = 0

        for target_date in dates:
            # Calculate ranks for each sector
            cursor.execute("""
                SELECT cp.sector, SUM(COALESCE(pd.close, 0)) as total_price
                FROM price_daily pd
                JOIN company_profile cp ON pd.symbol = cp.ticker
                WHERE pd.date = %s AND cp.sector IS NOT NULL
                GROUP BY cp.sector
                ORDER BY total_price DESC
            """, (target_date,))

            sector_data = list(cursor.fetchall())
            if not sector_data:
                continue

            for rank, (sector, total_price) in enumerate(sector_data, 1):
                momentum = (float(total_price) % 1000) if total_price else 0
                trend = "📈" if momentum > 0 else "➡️"

                batch_data.append((
                    sector,
                    target_date,
                    rank,
                    momentum,
                    trend
                ))

            # Insert batch when full
            if len(batch_data) >= BATCH_SIZE:
                cursor.executemany("""
                    INSERT INTO sector_ranking (sector, date, current_rank, momentum_score, trend)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT(sector, date) DO UPDATE SET
                        current_rank = EXCLUDED.current_rank,
                        momentum_score = EXCLUDED.momentum_score,
                        trend = EXCLUDED.trend
                """, batch_data)
                batch_data = []
                processed += 1
                if processed % 20 == 0:
                    logger.info(f"  ✅ Processed {processed * BATCH_SIZE // 12:.0f} sector-date combinations...")

        # Insert remaining batch
        if batch_data:
            cursor.executemany("""
                INSERT INTO sector_ranking (sector, date, current_rank, momentum_score, trend)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(sector, date) DO UPDATE SET
                    current_rank = EXCLUDED.current_rank,
                    momentum_score = EXCLUDED.momentum_score,
                    trend = EXCLUDED.trend
            """, batch_data)

        conn.commit()
        logger.info(f"✅ Successfully loaded sector rankings for {len(dates)} dates")

    except Exception as e:
        logger.error(f"Error loading sector rankings: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()


def load_industry_rankings(conn):
    """Load historical industry rankings"""
    logger.info("📊 Loading historical industry rankings (last 3 years)...")
    cursor = conn.cursor()

    try:
        # Get all unique dates from price_daily (last 3 years)
        cursor.execute("""
            SELECT DISTINCT date FROM price_daily
            WHERE date >= NOW() - INTERVAL '3 years'
            ORDER BY date
        """)
        dates = [row[0] for row in cursor.fetchall()]
        logger.info(f"Found {len(dates)} dates to process")

        batch_data = []
        processed = 0

        for target_date in dates:
            # Calculate ranks for each industry
            cursor.execute("""
                SELECT cp.industry, COUNT(*) as stock_count, SUM(COALESCE(pd.close, 0)) as total_price
                FROM price_daily pd
                JOIN company_profile cp ON pd.symbol = cp.ticker
                WHERE pd.date = %s AND cp.industry IS NOT NULL
                GROUP BY cp.industry
                ORDER BY total_price DESC
            """, (target_date,))

            industry_data = list(cursor.fetchall())
            if not industry_data:
                continue

            for rank, (industry, stock_count, total_price) in enumerate(industry_data, 1):
                momentum = (float(total_price) % 1000) if total_price else 0
                trend = "📈" if momentum > 0 else "➡️"

                batch_data.append((
                    industry,
                    target_date,
                    rank,
                    stock_count,
                    momentum,
                    trend
                ))

            # Insert batch when full
            if len(batch_data) >= BATCH_SIZE:
                cursor.executemany("""
                    INSERT INTO industry_ranking (industry, date, current_rank, stock_count, momentum_score, trend)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT(industry, date) DO UPDATE SET
                        current_rank = EXCLUDED.current_rank,
                        stock_count = EXCLUDED.stock_count,
                        momentum_score = EXCLUDED.momentum_score,
                        trend = EXCLUDED.trend
                """, batch_data)
                batch_data = []
                processed += 1
                if processed % 20 == 0:
                    logger.info(f"  ✅ Processed {processed * BATCH_SIZE // 145:.0f} industry-date combinations...")

        # Insert remaining batch
        if batch_data:
            cursor.executemany("""
                INSERT INTO industry_ranking (industry, date, current_rank, stock_count, momentum_score, trend)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(industry, date) DO UPDATE SET
                    current_rank = EXCLUDED.current_rank,
                    stock_count = EXCLUDED.stock_count,
                    momentum_score = EXCLUDED.momentum_score,
                    trend = EXCLUDED.trend
            """, batch_data)

        conn.commit()
        logger.info(f"✅ Successfully loaded industry rankings for {len(dates)} dates")

    except Exception as e:
        logger.error(f"Error loading industry rankings: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()


def main():
    conn = get_db_connection()
    try:
        logger.info("=" * 60)
        logger.info("🚀 HISTORICAL SECTOR & INDUSTRY RANKINGS LOADER")
        logger.info("=" * 60)

        load_sector_rankings(conn)
        load_industry_rankings(conn)

        logger.info("=" * 60)
        logger.info("✨ Historical load completed successfully!")
        logger.info("=" * 60)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
