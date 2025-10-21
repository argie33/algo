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
    Populate sector_ranking table with current sector performance data + historical ranks
    Aggregates data from industry_performance grouped by sector
    Calculates historical ranks from previous snapshots (1w ago, 4w ago, 8w ago)
    """
    logger.info("📊 Populating sector_ranking table with current rankings and historical data...")
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

        # First, calculate current ranks for all sectors based on performance
        cursor.execute("""
            WITH sector_perf AS (
                SELECT
                    cp.sector,
                    AVG(COALESCE(ip.performance_20d, 0)) as avg_performance
                FROM company_profile cp
                LEFT JOIN industry_performance ip ON ip.industry IN (
                    SELECT DISTINCT industry
                    FROM company_profile
                    WHERE sector = cp.sector AND industry IS NOT NULL
                )
                WHERE cp.sector IS NOT NULL
                GROUP BY cp.sector
            )
            SELECT
                sector,
                avg_performance,
                ROW_NUMBER() OVER (ORDER BY avg_performance DESC) as current_rank
            FROM sector_perf
            ORDER BY current_rank
        """)

        rankings = cursor.fetchall()
        sector_current_ranks = {sector: rank for sector, perf, rank in rankings}

        # For each sector, get historical ranks from previous snapshots
        historical_ranks = {}
        for sector_name, in sectors:
            # Get rank from 1 week ago (7 days)
            cursor.execute("""
                SELECT current_rank FROM sector_ranking
                WHERE sector = %s AND date <= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY date DESC LIMIT 1
            """, (sector_name,))
            rank_1w = cursor.fetchone()

            # Get rank from 4 weeks ago (28 days)
            cursor.execute("""
                SELECT current_rank FROM sector_ranking
                WHERE sector = %s AND date <= CURRENT_DATE - INTERVAL '28 days'
                ORDER BY date DESC LIMIT 1
            """, (sector_name,))
            rank_4w = cursor.fetchone()

            # Get rank from 12 weeks ago (84 days)
            cursor.execute("""
                SELECT current_rank FROM sector_ranking
                WHERE sector = %s AND date <= CURRENT_DATE - INTERVAL '84 days'
                ORDER BY date DESC LIMIT 1
            """, (sector_name,))
            rank_12w = cursor.fetchone()

            historical_ranks[sector_name] = {
                'rank_1w_ago': rank_1w[0] if rank_1w else None,
                'rank_4w_ago': rank_4w[0] if rank_4w else None,
                'rank_12w_ago': rank_12w[0] if rank_12w else None,
            }

        # Now insert/update with current ranks and historical data
        for sector_name, in sectors:
            current_rank = sector_current_ranks.get(sector_name)
            hist = historical_ranks.get(sector_name, {})

            # Get performance for trend calculation
            cursor.execute("""
                SELECT AVG(COALESCE(ip.performance_20d, 0))
                FROM industry_performance ip
                WHERE ip.industry IN (
                    SELECT DISTINCT cp.industry
                    FROM company_profile cp
                    WHERE cp.sector = %s AND cp.industry IS NOT NULL
                )
            """, (sector_name,))

            perf_result = cursor.fetchone()
            avg_performance = perf_result[0] if perf_result and perf_result[0] else 0
            trend = "📈" if avg_performance > 0 else "📉" if avg_performance < 0 else "➡️"

            # Calculate performance metrics for different periods
            cursor.execute("""
                WITH perf_data AS (
                    SELECT
                        AVG(COALESCE(ip.performance_1d, 0)) as perf_1d,
                        AVG(COALESCE(ip.performance_5d, 0)) as perf_5d,
                        AVG(COALESCE(ip.performance_20d, 0)) as perf_20d
                    FROM industry_performance ip
                    WHERE ip.industry IN (
                        SELECT DISTINCT cp.industry
                        FROM company_profile cp
                        WHERE cp.sector = %s AND cp.industry IS NOT NULL
                    )
                )
                SELECT perf_1d, perf_5d, perf_20d FROM perf_data
            """, (sector_name,))

            perf_data = cursor.fetchone()
            perf_1d = perf_data[0] if perf_data and perf_data[0] else 0
            perf_5d = perf_data[1] if perf_data and perf_data[1] else 0
            perf_20d = perf_data[2] if perf_data and perf_data[2] else 0

            # Get performance from 1 week ago (would need historical data)
            # For now, using NULL as historical performance data may not be available
            perf_1d_1w_ago = None
            perf_5d_1w_ago = None
            perf_20d_1w_ago = None

            # Insert into sector_ranking with available columns
            cursor.execute("""
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
            """, (
                sector_name,
                today,
                current_rank,
                hist.get('rank_1w_ago'),
                hist.get('rank_4w_ago'),
                hist.get('rank_12w_ago'),
                avg_performance,  # Use avg_performance as momentum_score
                trend
            ))

            hist_ranks_debug = f"✅ Sector: {sector_name}, Ranks (1w/4w/12w): {hist.get('rank_1w_ago')}/{hist.get('rank_4w_ago')}/{hist.get('rank_12w_ago')}, Current: {current_rank}"
            logger.debug(hist_ranks_debug)

        conn.commit()
        logger.info(f"✅ Successfully populated sector_ranking table with {len(sectors)} sectors (with historical ranks) for {today}")

    except Exception as e:
        logger.error(f"Error populating sector_ranking: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()


def populate_industry_ranking(conn):
    """
    Populate industry_ranking table with current industry performance data + historical ranks
    Gets data from industry_performance (current snapshot) and ranks by momentum
    Calculates historical ranks from previous snapshots (1w ago, 4w ago, 8w ago)
    """
    logger.info("📊 Populating industry_ranking table with current rankings and historical data...")
    cursor = conn.cursor()

    try:
        today = datetime.now().date()

        # Get all industries from industry_performance, ordered by performance (highest to lowest)
        cursor.execute("""
            SELECT industry,
                   COALESCE(momentum, '0'),
                   stock_count,
                   performance_20d,
                   ROW_NUMBER() OVER (ORDER BY COALESCE(performance_20d, 0) DESC) as current_rank
            FROM industry_performance
            WHERE industry IS NOT NULL
            ORDER BY current_rank
        """)

        industries = cursor.fetchall()

        if not industries:
            logger.warning("⚠️ No industries found in industry_performance table")
            cursor.close()
            return

        logger.info(f"Found {len(industries)} industries to rank")

        # Build a map of current ranks
        industry_current_ranks = {industry_name: current_rank for industry_name, _, _, _, current_rank in industries}

        # Get historical ranks for all industries
        historical_ranks = {}
        for industry_name, _, _, _, _ in industries:
            # Get rank from 1 week ago (7 days)
            cursor.execute("""
                SELECT current_rank FROM industry_ranking
                WHERE industry = %s AND date <= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY date DESC LIMIT 1
            """, (industry_name,))
            rank_1w = cursor.fetchone()

            # Get rank from 4 weeks ago (28 days)
            cursor.execute("""
                SELECT current_rank FROM industry_ranking
                WHERE industry = %s AND date <= CURRENT_DATE - INTERVAL '28 days'
                ORDER BY date DESC LIMIT 1
            """, (industry_name,))
            rank_4w = cursor.fetchone()

            # Get rank from 8 weeks ago (56 days)
            cursor.execute("""
                SELECT current_rank FROM industry_ranking
                WHERE industry = %s AND date <= CURRENT_DATE - INTERVAL '56 days'
                ORDER BY date DESC LIMIT 1
            """, (industry_name,))
            rank_8w = cursor.fetchone()

            historical_ranks[industry_name] = {
                'rank_1w_ago': rank_1w[0] if rank_1w else None,
                'rank_4w_ago': rank_4w[0] if rank_4w else None,
                'rank_8w_ago': rank_8w[0] if rank_8w else None,
            }

        # Insert/update rankings for today with historical data
        for industry_name, momentum, stock_count, momentum_score, current_rank in industries:
            # Determine trend based on momentum indicator
            trend = "📈" if momentum == "Strong" else "📉" if momentum == "Weak" else "➡️"

            # Convert momentum_score to numeric (performance_20d is typically -100 to +100)
            try:
                score = float(momentum_score) if momentum_score else 0
            except (ValueError, TypeError):
                score = 0

            hist = historical_ranks.get(industry_name, {})

            # Insert into industry_ranking with historical ranks
            cursor.execute("""
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
            """, (
                industry_name,
                today,
                current_rank,
                hist.get('rank_1w_ago'),
                hist.get('rank_4w_ago'),
                hist.get('rank_8w_ago'),
                score,
                stock_count,
                trend
            ))

        conn.commit()
        logger.info(f"✅ Successfully populated industry_ranking table with {len(industries)} industries (with historical ranks) for {today}")

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
