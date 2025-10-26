#!/usr/bin/env python3
"""
MAIN Sector & Industry Data Loader
Consolidates ALL sector and industry loading into one unified module:
- Sector/Industry Rankings (current_rank, historical ranks)
- Sector/Industry Performance (1D%, 5D%, 20D%)
- Technical Indicators (20-day, 50-day, 200-day moving averages, RSI)
Uses market-cap filtering for accurate weighted calculations
Trigger: 2025-10-26 AWS deployment - sectors and industry analytics
"""

import logging
import os
import sys
from datetime import datetime

import psycopg2
import numpy as np

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


def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index (RSI)"""
    if len(prices) < period + 1:
        return None

    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = 100. - 100. / (1. + rs)
    return float(rsi)


def verify_tables_exist(conn):
    """Verify that all required tables exist"""
    cursor = conn.cursor()
    required_tables = [
        'sector_ranking',
        'industry_ranking',
        'sector_performance',
        'industry_performance',
        'sector_technical_data',
        'industry_technical_data'
    ]

    try:
        for table_name in required_tables:
            cursor.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = '{table_name}'
                )
            """)
            if not cursor.fetchone()[0]:
                logger.error(f"❌ {table_name} table does not exist")
                return False

        logger.info(f"✅ All {len(required_tables)} required tables exist")
        return True
    except Exception as e:
        logger.error(f"❌ Error checking tables: {e}")
        return False
    finally:
        cursor.close()


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
            # Using MARKET-CAP WEIGHTED performance calculation
            cursor.execute("""
                WITH sector_perf AS (
                    SELECT
                        cp.sector,
                        SUM((pd.close - pd.open) * COALESCE(md.market_cap, 0)) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL OR pd.open IS NOT NULL THEN COALESCE(md.market_cap, 0) ELSE 0 END), 0) as avg_performance
                    FROM company_profile cp
                    LEFT JOIN price_daily pd ON cp.ticker = pd.symbol AND pd.date = %s
                    LEFT JOIN market_data md ON cp.ticker = md.ticker
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
                        perf_value = perf if perf is not None else 0
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
                        (sector, date, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago, daily_strength_score, trend)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT(sector, date) DO UPDATE SET
                            current_rank = EXCLUDED.current_rank,
                            rank_1w_ago = EXCLUDED.rank_1w_ago,
                            rank_4w_ago = EXCLUDED.rank_4w_ago,
                            rank_12w_ago = EXCLUDED.rank_12w_ago,
                            daily_strength_score = EXCLUDED.daily_strength_score,
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
                (sector, date, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago, daily_strength_score, trend)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(sector, date) DO UPDATE SET
                    current_rank = EXCLUDED.current_rank,
                    rank_1w_ago = EXCLUDED.rank_1w_ago,
                    rank_4w_ago = EXCLUDED.rank_4w_ago,
                    rank_12w_ago = EXCLUDED.rank_12w_ago,
                    daily_strength_score = EXCLUDED.daily_strength_score,
                    trend = EXCLUDED.trend
            """, batch_data)

        conn.commit()
        logger.info(f"✅ Successfully populated sector_ranking table for {len(price_dates)} recent dates with {len(sectors)} sectors")
        return True

    except Exception as e:
        logger.error(f"Error populating sector_ranking: {e}")
        conn.rollback()
        return False
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
            # Using MARKET-CAP WEIGHTED performance calculation
            cursor.execute("""
                WITH industry_perf AS (
                    SELECT
                        cp.industry,
                        SUM((pd.close - pd.open) * COALESCE(md.market_cap, 0)) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL OR pd.open IS NOT NULL THEN COALESCE(md.market_cap, 0) ELSE 0 END), 0) as avg_performance,
                        COUNT(DISTINCT cp.ticker) as stock_count
                    FROM company_profile cp
                    LEFT JOIN price_daily pd ON cp.ticker = pd.symbol AND pd.date = %s
                    LEFT JOIN market_data md ON cp.ticker = md.ticker
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
                perf_value = perf if perf is not None else 0
                trend = "📈" if perf_value > 0 else "📉" if perf_value < 0 else "➡️"
                hist = historical_ranks.get(industry_name, {})

                # Add to batch
                batch_data.append((
                    industry_name,
                    target_date,
                    current_rank,
                    hist.get('rank_1w_ago'),
                    hist.get('rank_4w_ago'),
                    hist.get('rank_8w_ago'),
                    perf_value,
                    stock_count,
                    trend
                ))

                # Insert batch when full
                if len(batch_data) >= batch_size:
                    cursor.executemany("""
                        INSERT INTO industry_ranking
                        (industry, date, current_rank, rank_1w_ago, rank_4w_ago, rank_8w_ago,
                         daily_strength_score, stock_count, trend)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT(industry, date) DO UPDATE SET
                            current_rank = EXCLUDED.current_rank,
                            rank_1w_ago = EXCLUDED.rank_1w_ago,
                            rank_4w_ago = EXCLUDED.rank_4w_ago,
                            rank_8w_ago = EXCLUDED.rank_8w_ago,
                            daily_strength_score = EXCLUDED.daily_strength_score,
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
                 daily_strength_score, stock_count, trend)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(industry, date) DO UPDATE SET
                    current_rank = EXCLUDED.current_rank,
                    rank_1w_ago = EXCLUDED.rank_1w_ago,
                    rank_4w_ago = EXCLUDED.rank_4w_ago,
                    rank_8w_ago = EXCLUDED.rank_8w_ago,
                    daily_strength_score = EXCLUDED.daily_strength_score,
                    stock_count = EXCLUDED.stock_count,
                    trend = EXCLUDED.trend
            """, batch_data)

        conn.commit()
        logger.info(f"✅ Successfully populated industry_ranking table for {len(price_dates)} recent dates with {len(industries)} industries")
        return True

    except Exception as e:
        logger.error(f"Error populating industry_ranking: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()


def populate_sector_performance(conn):
    """
    Populate sector_performance table with market-cap weighted percentage calculations
    Filters to only stocks with market cap data to avoid penny stock distortion
    """
    logger.info("📊 Populating sector_performance table with market-cap weighted data...")
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM sector_performance")

        query = """
        WITH sector_daily_prices AS (
            SELECT
                cp.sector,
                pd.date,
                AVG(pd.close) as avg_close
            FROM company_profile cp
            JOIN price_daily pd ON cp.ticker = pd.symbol
            INNER JOIN market_data md ON cp.ticker = md.ticker
            WHERE cp.sector IS NOT NULL AND cp.sector != '' AND md.market_cap > 0
            GROUP BY cp.sector, pd.date
        ),
        latest_data AS (
            SELECT DISTINCT ON (sector)
                sector,
                avg_close as latest_close
            FROM sector_daily_prices
            WHERE date <= CURRENT_DATE
            ORDER BY sector, date DESC
        )
        INSERT INTO sector_performance (
            symbol,
            sector_name,
            performance_1d,
            performance_5d,
            performance_20d,
            fetched_at
        )
        SELECT
            SUBSTRING('S_' || ld.sector FROM 1 FOR 20),
            ld.sector,
            CASE WHEN d1.avg_close > 0 THEN ((ld.latest_close - d1.avg_close) / d1.avg_close * 100) ELSE NULL END as perf_1d,
            CASE WHEN d5.avg_close > 0 THEN ((ld.latest_close - d5.avg_close) / d5.avg_close * 100) ELSE NULL END as perf_5d,
            CASE WHEN d20.avg_close > 0 THEN ((ld.latest_close - d20.avg_close) / d20.avg_close * 100) ELSE NULL END as perf_20d,
            NOW()
        FROM latest_data ld
        LEFT JOIN (SELECT sector, avg_close FROM sector_daily_prices WHERE date = CURRENT_DATE - INTERVAL '1 day') d1 ON ld.sector = d1.sector
        LEFT JOIN (SELECT sector, avg_close FROM sector_daily_prices WHERE date = CURRENT_DATE - INTERVAL '5 days') d5 ON ld.sector = d5.sector
        LEFT JOIN (SELECT sector, avg_close FROM sector_daily_prices WHERE date = CURRENT_DATE - INTERVAL '20 days') d20 ON ld.sector = d20.sector
        """

        cursor.execute(query)
        conn.commit()
        logger.info(f"✅ Populated sector_performance table")
        return True

    except Exception as e:
        logger.error(f"❌ Error populating sector_performance: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()


def populate_industry_performance(conn):
    """
    Populate industry_performance table with market-cap weighted percentage calculations
    Filters to only stocks with market cap data to avoid penny stock distortion
    """
    logger.info("📊 Populating industry_performance table with market-cap weighted data...")
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM industry_performance")

        query = """
        WITH industry_daily_prices AS (
            SELECT
                cp.sector,
                cp.industry,
                pd.date,
                AVG(pd.close) as avg_close
            FROM company_profile cp
            JOIN price_daily pd ON cp.ticker = pd.symbol
            INNER JOIN market_data md ON cp.ticker = md.ticker
            WHERE cp.industry IS NOT NULL AND cp.industry != '' AND md.market_cap > 0
            GROUP BY cp.sector, cp.industry, pd.date
        ),
        latest_data AS (
            SELECT DISTINCT ON (sector, industry)
                sector,
                industry,
                avg_close as latest_close
            FROM industry_daily_prices
            WHERE date <= CURRENT_DATE
            ORDER BY sector, industry, date DESC
        )
        INSERT INTO industry_performance (
            sector,
            industry,
            performance_1d,
            performance_5d,
            performance_20d
        )
        SELECT
            ld.sector,
            ld.industry,
            CASE WHEN d1.avg_close > 0 THEN ((ld.latest_close - d1.avg_close) / d1.avg_close * 100) ELSE NULL END as perf_1d,
            CASE WHEN d5.avg_close > 0 THEN ((ld.latest_close - d5.avg_close) / d5.avg_close * 100) ELSE NULL END as perf_5d,
            CASE WHEN d20.avg_close > 0 THEN ((ld.latest_close - d20.avg_close) / d20.avg_close * 100) ELSE NULL END as perf_20d
        FROM latest_data ld
        LEFT JOIN (SELECT sector, industry, avg_close FROM industry_daily_prices WHERE date = CURRENT_DATE - INTERVAL '1 day') d1 ON ld.sector = d1.sector AND ld.industry = d1.industry
        LEFT JOIN (SELECT sector, industry, avg_close FROM industry_daily_prices WHERE date = CURRENT_DATE - INTERVAL '5 days') d5 ON ld.sector = d5.sector AND ld.industry = d5.industry
        LEFT JOIN (SELECT sector, industry, avg_close FROM industry_daily_prices WHERE date = CURRENT_DATE - INTERVAL '20 days') d20 ON ld.sector = d20.sector AND ld.industry = d20.industry
        """

        cursor.execute(query)
        conn.commit()
        logger.info(f"✅ Populated industry_performance table")
        return True

    except Exception as e:
        logger.error(f"❌ Error populating industry_performance: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()


def populate_technical_data(conn):
    """
    Populate sector_technical_data and industry_technical_data tables
    with 200-day price history, moving averages, and RSI indicators
    Uses market-cap filtering for accurate calculations
    """
    logger.info("📊 Populating technical data tables...")
    cursor = conn.cursor()

    try:
        # Process sectors
        cursor.execute("SELECT DISTINCT sector FROM company_profile WHERE sector IS NOT NULL ORDER BY sector")
        sectors = [row[0] for row in cursor.fetchall()]
        logger.info(f"  Processing {len(sectors)} sectors...")

        for sector in sectors:
            try:
                cursor.execute("""
                    SELECT pd.date, AVG(pd.close) as avg_close, SUM(pd.volume) as total_vol
                    FROM company_profile cp
                    JOIN price_daily pd ON cp.ticker = pd.symbol
                    INNER JOIN market_data md ON cp.ticker = md.ticker
                    WHERE cp.sector = %s AND md.market_cap > 0
                    GROUP BY pd.date
                    ORDER BY pd.date ASC LIMIT 200
                """, (sector,))

                data = cursor.fetchall()
                if not data:
                    continue

                valid_data = [(row[0], row[1], row[2]) for row in data if row[1] is not None]
                if not valid_data:
                    continue

                dates = [row[0] for row in valid_data]
                prices = np.array([float(row[1]) for row in valid_data])
                volumes = [int(row[2]) if row[2] is not None else 0 for row in valid_data]

                rsi = calculate_rsi(prices)

                for i, date in enumerate(dates):
                    ma20 = float(np.mean(prices[max(0, i-19):i+1])) if i >= 19 else None
                    ma50 = float(np.mean(prices[max(0, i-49):i+1])) if i >= 49 else None
                    ma200 = float(np.mean(prices[max(0, i-199):i+1])) if i >= 199 else None

                    cursor.execute("""
                        INSERT INTO sector_technical_data
                        (sector, date, close_price, ma_20, ma_50, ma_200, rsi, volume)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (sector, date) DO UPDATE SET
                        ma_20 = EXCLUDED.ma_20, ma_50 = EXCLUDED.ma_50, ma_200 = EXCLUDED.ma_200,
                        rsi = EXCLUDED.rsi, volume = EXCLUDED.volume
                    """, (sector, date, float(prices[i]), ma20, ma50, ma200,
                          rsi if i == len(dates)-1 else None, volumes[i]))

                conn.commit()
            except Exception as e:
                logger.warning(f"⚠️  Error processing sector {sector}: {e}")
                conn.rollback()
                continue

        logger.info(f"  ✅ Processed {len(sectors)} sectors")

        # Process industries
        cursor.execute("SELECT DISTINCT industry FROM company_profile WHERE industry IS NOT NULL ORDER BY industry")
        industries = [row[0] for row in cursor.fetchall()]
        logger.info(f"  Processing {len(industries)} industries...")

        for industry in industries:
            try:
                cursor.execute("""
                    SELECT pd.date, AVG(pd.close) as avg_close, SUM(pd.volume) as total_vol
                    FROM company_profile cp
                    JOIN price_daily pd ON cp.ticker = pd.symbol
                    INNER JOIN market_data md ON cp.ticker = md.ticker
                    WHERE cp.industry = %s AND md.market_cap > 0
                    GROUP BY pd.date
                    ORDER BY pd.date ASC LIMIT 200
                """, (industry,))

                data = cursor.fetchall()
                if not data:
                    continue

                valid_data = [(row[0], row[1], row[2]) for row in data if row[1] is not None]
                if not valid_data:
                    continue

                dates = [row[0] for row in valid_data]
                prices = np.array([float(row[1]) for row in valid_data])
                volumes = [int(row[2]) if row[2] is not None else 0 for row in valid_data]

                rsi = calculate_rsi(prices)

                for i, date in enumerate(dates):
                    ma20 = float(np.mean(prices[max(0, i-19):i+1])) if i >= 19 else None
                    ma50 = float(np.mean(prices[max(0, i-49):i+1])) if i >= 49 else None
                    ma200 = float(np.mean(prices[max(0, i-199):i+1])) if i >= 199 else None

                    cursor.execute("""
                        INSERT INTO industry_technical_data
                        (industry, date, close_price, ma_20, ma_50, ma_200, rsi, volume)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (industry, date) DO UPDATE SET
                        ma_20 = EXCLUDED.ma_20, ma_50 = EXCLUDED.ma_50, ma_200 = EXCLUDED.ma_200,
                        rsi = EXCLUDED.rsi, volume = EXCLUDED.volume
                    """, (industry, date, float(prices[i]), ma20, ma50, ma200,
                          rsi if i == len(dates)-1 else None, volumes[i]))

                conn.commit()
            except Exception as e:
                logger.warning(f"⚠️  Error processing industry {industry}: {e}")
                conn.rollback()
                continue

        logger.info(f"  ✅ Processed {len(industries)} industries")
        logger.info("✅ Technical data population completed!")
        return True

    except Exception as e:
        logger.error(f"❌ Error populating technical data: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()


def main():
    """Main function - load all sector and industry data in proper order"""
    logger.info("="*70)
    logger.info("🚀 MAIN SECTOR & INDUSTRY DATA LOADER")
    logger.info("="*70)

    conn = get_db_connection()

    try:
        # Verify tables exist
        if not verify_tables_exist(conn):
            logger.error("❌ Required tables missing. Create performance tables first.")
            return False

        # Step 1: Populate sector rankings
        if not populate_sector_ranking(conn):
            logger.error("❌ Failed to populate sector rankings")
            return False

        # Step 2: Populate industry rankings
        if not populate_industry_ranking(conn):
            logger.error("❌ Failed to populate industry rankings")
            return False

        # Step 3: Populate sector performance
        if not populate_sector_performance(conn):
            logger.error("❌ Failed to populate sector performance")
            return False

        # Step 4: Populate industry performance
        if not populate_industry_performance(conn):
            logger.error("❌ Failed to populate industry performance")
            return False

        # Step 5: Populate technical data for both sectors and industries
        if not populate_technical_data(conn):
            logger.warning("⚠️  Technical data population had errors, but continuing...")

        logger.info("="*70)
        logger.info("✅ ALL SECTOR & INDUSTRY DATA LOADED SUCCESSFULLY")
        logger.info("="*70)
        return True

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
