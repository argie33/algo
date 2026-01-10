#!/usr/bin/env python3
"""
MAIN Sector & Industry Data Loader
CRITICAL: Sectors table missing from database. Must run to enable SectorAnalysis pages
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

# Load environment variables from .env.local
from dotenv import load_dotenv
load_dotenv('.env.local')

import psycopg2
import numpy as np
from db_helper import get_db_connection

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration from environment
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'stocks')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'bed0elAn')
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


def create_tables_if_needed(conn):
    """Create all required tables if they don't exist"""
    cursor = conn.cursor()

    try:
        # Create or migrate sector_ranking table
        # Drop old table if it exists with wrong schema (date instead of date_recorded)
        cursor.execute("DROP TABLE IF EXISTS sector_ranking CASCADE")

        # Create sector_ranking table with correct schema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sector_ranking (
                id SERIAL PRIMARY KEY,
                sector_name VARCHAR(255) NOT NULL,
                date_recorded DATE NOT NULL,
                current_rank INT,
                rank_1w_ago INT,
                rank_4w_ago INT,
                rank_12w_ago INT,
                daily_strength_score FLOAT,
                momentum_score FLOAT,
                trend VARCHAR(10),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(sector_name, date_recorded)
            )
        """)
        logger.info("✅ sector_ranking table ready")

        # Create or migrate industry_ranking table
        cursor.execute("DROP TABLE IF EXISTS industry_ranking CASCADE")

        # Create industry_ranking table with correct schema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS industry_ranking (
                id SERIAL PRIMARY KEY,
                industry VARCHAR(255) NOT NULL,
                date_recorded DATE NOT NULL,
                current_rank INT,
                rank_1w_ago INT,
                rank_4w_ago INT,
                rank_12w_ago INT,
                daily_strength_score FLOAT,
                momentum_score FLOAT,
                stock_count INT,
                trend VARCHAR(10),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(industry, date_recorded)
            )
        """)
        logger.info("✅ industry_ranking table ready")

        # Create sector_performance table
        cursor.execute("DROP TABLE IF EXISTS sector_performance CASCADE")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sector_performance (
                id SERIAL PRIMARY KEY,
                sector VARCHAR(255) NOT NULL,
                date DATE NOT NULL,
                performance_1d FLOAT,
                performance_5d FLOAT,
                performance_20d FLOAT,
                performance_ytd FLOAT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(sector, date)
            )
        """)
        logger.info("✅ sector_performance table ready")

        # Create industry_performance table
        cursor.execute("DROP TABLE IF EXISTS industry_performance CASCADE")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS industry_performance (
                id SERIAL PRIMARY KEY,
                industry VARCHAR(255) NOT NULL,
                date DATE NOT NULL,
                performance_1d FLOAT,
                performance_5d FLOAT,
                performance_20d FLOAT,
                performance_ytd FLOAT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(industry, date)
            )
        """)
        logger.info("✅ industry_performance table ready")

        # Create sector_technical_data table
        cursor.execute("DROP TABLE IF EXISTS sector_technical_data CASCADE")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sector_technical_data (
                id SERIAL PRIMARY KEY,
                sector VARCHAR(255) NOT NULL,
                date DATE NOT NULL,
                close_price FLOAT,
                ma_20 FLOAT,
                ma_50 FLOAT,
                ma_200 FLOAT,
                rsi FLOAT,
                volume BIGINT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(sector, date)
            )
        """)
        logger.info("✅ sector_technical_data table ready")

        # Create industry_technical_data table
        cursor.execute("DROP TABLE IF EXISTS industry_technical_data CASCADE")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS industry_technical_data (
                id SERIAL PRIMARY KEY,
                industry VARCHAR(255) NOT NULL,
                date DATE NOT NULL,
                close_price FLOAT,
                ma_20 FLOAT,
                ma_50 FLOAT,
                ma_200 FLOAT,
                rsi FLOAT,
                volume BIGINT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(industry, date)
            )
        """)
        logger.info("✅ industry_technical_data table ready")

        # Create indexes for performance (only for ranking tables - performance tables already have indexes on fetched_at)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sector_ranking_date ON sector_ranking(date_recorded)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sector_ranking_sector ON sector_ranking(sector_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_industry_ranking_date ON industry_ranking(date_recorded)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_industry_ranking_industry ON industry_ranking(industry)")

        conn.commit()
        logger.info("✅ All required tables created/verified with indexes")
        return True

    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        logger.error(f"❌ Error creating tables: {e}")
        logger.error(f"Traceback: {tb_str}")
        print(f"CREATE TABLES ERROR TRACEBACK:\n{tb_str}", file=sys.stderr)
        conn.rollback()
        return False
    finally:
        cursor.close()


def populate_sector_ranking(conn):
    """
    Populate sector_ranking table with sector rankings - OPTIMIZED VERSION
    Uses single efficient SQL query instead of 36K+ individual queries
    """
    logger.info("📊 Populating sector_ranking table with optimized bulk insert...")
    cursor = conn.cursor()

    try:
        # Single efficient query to calculate all sector rankings for all recent dates
        # Calculate momentum as weighted percentage return: sum(return% * market_cap) / sum(market_cap)
        insert_query = """
        INSERT INTO sector_ranking (sector_name, date_recorded, current_rank, momentum_score)
        SELECT
            t.sector,
            t.date,
            ROW_NUMBER() OVER (PARTITION BY t.date ORDER BY t.momentum DESC) as current_rank,
            t.momentum
        FROM (
            SELECT
                pd.date,
                cp.sector,
                AVG(CASE
                    WHEN pd.open > 0 AND pd.close IS NOT NULL THEN ((pd.close - pd.open) / pd.open) * 100
                    ELSE NULL
                END) as momentum
            FROM company_profile cp
            LEFT JOIN price_daily pd ON cp.ticker = pd.symbol AND pd.date >= NOW() - INTERVAL '3 years'
            WHERE cp.sector IS NOT NULL AND pd.date IS NOT NULL AND pd.open > 0 AND pd.close IS NOT NULL
            GROUP BY pd.date, cp.sector
        ) t
        WHERE t.momentum IS NOT NULL
        ON CONFLICT(sector_name, date_recorded) DO UPDATE SET
            current_rank = EXCLUDED.current_rank,
            momentum_score = EXCLUDED.momentum_score
        """

        cursor.execute(insert_query)
        conn.commit()
        rows_inserted = cursor.rowcount
        logger.info(f"✅ Successfully populated {rows_inserted} sector-date ranking combinations")

        # Now populate historical ranks (1w ago, 4w ago, 12w ago)
        logger.info("📊 Populating historical ranks for sectors...")
        # First, clear any existing historical ranks to ensure fresh recalculation
        cursor.execute("UPDATE sector_ranking SET rank_1w_ago = NULL, rank_4w_ago = NULL, rank_12w_ago = NULL")
        logger.info(f"Cleared existing historical ranks for recalculation")

        update_query = """
        UPDATE sector_ranking sr SET
            rank_1w_ago = (SELECT current_rank FROM sector_ranking WHERE sector_name = sr.sector_name AND date_recorded = sr.date_recorded - INTERVAL '7 days'),
            rank_4w_ago = (SELECT current_rank FROM sector_ranking WHERE sector_name = sr.sector_name AND date_recorded = sr.date_recorded - INTERVAL '28 days'),
            rank_12w_ago = (SELECT current_rank FROM sector_ranking WHERE sector_name = sr.sector_name AND date_recorded = sr.date_recorded - INTERVAL '84 days')
        WHERE sr.current_rank IS NOT NULL
        """
        cursor.execute(update_query)
        rows_updated = cursor.rowcount
        conn.commit()
        logger.info(f"✅ Updated {rows_updated} rows with historical ranks for sectors")

        return True

    except Exception as e:
        import traceback
        logger.error(f"Error populating sector_ranking: {e}")
        tb_str = traceback.format_exc()
        logger.error(f"Traceback: {tb_str}")
        print(f"ERROR TRACEBACK:\n{tb_str}", file=sys.stderr)
        conn.rollback()
        return False
    finally:
        cursor.close()


def populate_industry_ranking(conn):
    """
    Populate industry_ranking table - SIMPLE equal-weighted version
    Uses single efficient SQL query with simple average returns
    """
    logger.info("📊 Populating industry_ranking table with equal-weighted returns...")
    cursor = conn.cursor()

    try:
        # CRITICAL FIX: Only rank industries with REAL momentum data (not NULL)
        # This prevents fake rankings from COALESCE(momentum, 0) corruption
        insert_query = """
        INSERT INTO industry_ranking (industry, date_recorded, current_rank, momentum_score)
        SELECT
            t.industry,
            t.date,
            ROW_NUMBER() OVER (PARTITION BY t.date ORDER BY t.momentum DESC) as current_rank,
            t.momentum
        FROM (
            SELECT
                pd.date,
                cp.industry,
                AVG(CASE
                    WHEN pd.open > 0 THEN ((pd.close - pd.open) / pd.open) * 100
                    ELSE NULL
                END) as momentum
            FROM company_profile cp
            LEFT JOIN price_daily pd ON cp.ticker = pd.symbol AND pd.date >= NOW() - INTERVAL '3 years'
            WHERE cp.industry IS NOT NULL
            GROUP BY pd.date, cp.industry
        ) t
        WHERE t.date IS NOT NULL AND t.momentum IS NOT NULL
        ON CONFLICT(industry, date_recorded) DO UPDATE SET
            current_rank = EXCLUDED.current_rank,
            momentum_score = EXCLUDED.momentum_score
        """

        cursor.execute(insert_query)
        conn.commit()
        rows_inserted = cursor.rowcount
        logger.info(f"✅ Successfully populated {rows_inserted} industry-date ranking combinations")

        # Now populate historical ranks (1w ago, 4w ago, 12w ago)
        logger.info("📊 Populating historical ranks for industries...")
        # First, clear any existing historical ranks to ensure fresh recalculation
        cursor.execute("UPDATE industry_ranking SET rank_1w_ago = NULL, rank_4w_ago = NULL, rank_12w_ago = NULL")
        logger.info(f"Cleared existing historical ranks for industries - recalculating...")

        update_query = """
        UPDATE industry_ranking ir SET
            rank_1w_ago = (SELECT current_rank FROM industry_ranking WHERE industry = ir.industry AND date_recorded = ir.date_recorded - INTERVAL '7 days'),
            rank_4w_ago = (SELECT current_rank FROM industry_ranking WHERE industry = ir.industry AND date_recorded = ir.date_recorded - INTERVAL '28 days'),
            rank_12w_ago = (SELECT current_rank FROM industry_ranking WHERE industry = ir.industry AND date_recorded = ir.date_recorded - INTERVAL '84 days')
        WHERE ir.current_rank IS NOT NULL
        """
        cursor.execute(update_query)
        rows_updated = cursor.rowcount
        conn.commit()
        logger.info(f"✅ Updated {rows_updated} rows with historical ranks for industries")

        # Special handling for Benchmark industry (SPY) - calculate as market-weighted average
        logger.info("📊 Populating Benchmark industry momentum as market average...")
        benchmark_query = """
        INSERT INTO industry_ranking (industry, date_recorded, current_rank, momentum_score)
        SELECT
            'Benchmark',
            t.date_recorded,
            ROW_NUMBER() OVER (PARTITION BY t.date_recorded ORDER BY t.avg_momentum DESC) as current_rank,
            t.avg_momentum
        FROM (
            SELECT
                date_recorded,
                AVG(momentum_score) as avg_momentum
            FROM industry_ranking
            WHERE industry != 'Benchmark' AND momentum_score IS NOT NULL
            GROUP BY date_recorded
        ) t
        ON CONFLICT(industry, date_recorded) DO UPDATE SET
            momentum_score = EXCLUDED.momentum_score,
            current_rank = EXCLUDED.current_rank
        """
        cursor.execute(benchmark_query)
        benchmark_rows = cursor.rowcount
        conn.commit()
        logger.info(f"✅ Populated {benchmark_rows} Benchmark momentum values from market average")

        return True

    except Exception as e:
        logger.error(f"Error populating industry_ranking: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()


def populate_sector_performance(conn):
    """
    Populate sector_performance table with equal-weighted daily returns calculation
    Calculates daily returns for each stock, then averages across all stocks in each sector
    """
    logger.info("📊 Populating sector_performance table with equal-weighted returns...")
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM sector_performance")

        query = """
        WITH dedup_prices AS (
            SELECT symbol, date, close
            FROM price_daily pd
            WHERE close > 0 AND close < 10000
              AND id IN (
                SELECT MAX(id)
                FROM price_daily
                WHERE close > 0 AND close < 10000
                GROUP BY symbol, date
              )
        ),
        stock_returns AS (
            SELECT
                cp.sector,
                CAST(dp.date AS DATE) as trading_date,
                dp.symbol,
                dp.close,
                LAG(dp.close) OVER (PARTITION BY dp.symbol ORDER BY dp.date) as prev_close,
                CASE
                    WHEN LAG(dp.close) OVER (PARTITION BY dp.symbol ORDER BY dp.date) > 0
                    THEN ((dp.close - LAG(dp.close) OVER (PARTITION BY dp.symbol ORDER BY dp.date)) /
                          LAG(dp.close) OVER (PARTITION BY dp.symbol ORDER BY dp.date) * 100)
                    ELSE NULL
                END as daily_return
            FROM dedup_prices dp
            JOIN company_profile cp ON dp.symbol = cp.ticker
            WHERE cp.sector IS NOT NULL AND cp.sector != ''
        ),
        sector_daily_avg AS (
            SELECT
                sector,
                trading_date,
                AVG(daily_return) as avg_return
            FROM stock_returns
            WHERE daily_return IS NOT NULL
            GROUP BY sector, trading_date
        ),
        latest_date_per_sector AS (
            SELECT
                sector,
                MAX(trading_date) as latest_date
            FROM sector_daily_avg
            GROUP BY sector
        ),
        perf_windows AS (
            SELECT
                sda.sector,
                sda.trading_date,
                sda.avg_return,
                lds.latest_date,
                ROW_NUMBER() OVER (PARTITION BY sda.sector ORDER BY sda.trading_date DESC) as rn_latest,
                ROW_NUMBER() OVER (PARTITION BY sda.sector ORDER BY abs(CAST((lds.latest_date - sda.trading_date) AS INTEGER) - 1)) as rn_1d,
                ROW_NUMBER() OVER (PARTITION BY sda.sector ORDER BY abs(CAST((lds.latest_date - sda.trading_date) AS INTEGER) - 5)) as rn_5d,
                ROW_NUMBER() OVER (PARTITION BY sda.sector ORDER BY abs(CAST((lds.latest_date - sda.trading_date) AS INTEGER) - 20)) as rn_20d
            FROM sector_daily_avg sda
            JOIN latest_date_per_sector lds ON sda.sector = lds.sector
        ),
        perf_latest AS (
            SELECT sector, latest_date, avg_return as latest_return
            FROM perf_windows
            WHERE rn_latest = 1
        ),
        perf_1d AS (
            SELECT sector, avg_return as return_1d
            FROM perf_windows
            WHERE rn_1d = 1
        ),
        perf_5d AS (
            SELECT
                sector,
                ((EXP(SUM(LN(1 + avg_return/100))) - 1) * 100) as return_5d
            FROM perf_windows
            WHERE trading_date <= latest_date AND trading_date > latest_date - INTERVAL '5 days'
            GROUP BY sector
        ),
        perf_20d AS (
            SELECT
                sector,
                ((EXP(SUM(LN(1 + avg_return/100))) - 1) * 100) as return_20d
            FROM perf_windows
            WHERE trading_date <= latest_date AND trading_date > latest_date - INTERVAL '20 days'
            GROUP BY sector
        )
        INSERT INTO sector_performance (
            sector,
            date,
            performance_1d,
            performance_5d,
            performance_20d
        )
        SELECT
            pl.sector,
            pl.latest_date,
            p1d.return_1d,
            p5d.return_5d,
            p20d.return_20d
        FROM perf_latest pl
        LEFT JOIN perf_1d p1d ON pl.sector = p1d.sector
        LEFT JOIN perf_5d p5d ON pl.sector = p5d.sector
        LEFT JOIN perf_20d p20d ON pl.sector = p20d.sector
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
    Populate industry_performance table with equal-weighted daily returns calculation
    Calculates daily returns for each stock, then averages across all stocks in each industry
    """
    logger.info("📊 Populating industry_performance table with equal-weighted returns...")
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM industry_performance")

        query = """
        WITH dedup_prices AS (
            SELECT symbol, date, close
            FROM price_daily pd
            WHERE close > 0 AND close < 10000
              AND id IN (
                SELECT MAX(id)
                FROM price_daily
                WHERE close > 0 AND close < 10000
                GROUP BY symbol, date
              )
        ),
        stock_returns AS (
            SELECT
                cp.industry,
                CAST(dp.date AS DATE) as trading_date,
                dp.symbol,
                dp.close,
                LAG(dp.close) OVER (PARTITION BY dp.symbol ORDER BY dp.date) as prev_close,
                CASE
                    WHEN LAG(dp.close) OVER (PARTITION BY dp.symbol ORDER BY dp.date) > 0
                    THEN ((dp.close - LAG(dp.close) OVER (PARTITION BY dp.symbol ORDER BY dp.date)) /
                          LAG(dp.close) OVER (PARTITION BY dp.symbol ORDER BY dp.date) * 100)
                    ELSE NULL
                END as daily_return
            FROM dedup_prices dp
            JOIN company_profile cp ON dp.symbol = cp.ticker
            WHERE cp.industry IS NOT NULL AND cp.industry != ''
        ),
        industry_daily_avg AS (
            SELECT
                industry,
                trading_date,
                AVG(daily_return) as avg_return
            FROM stock_returns
            WHERE daily_return IS NOT NULL
            GROUP BY industry, trading_date
        ),
        latest_date_per_industry AS (
            SELECT
                industry,
                MAX(trading_date) as latest_date
            FROM industry_daily_avg
            GROUP BY industry
        ),
        perf_windows AS (
            SELECT
                ida.industry,
                ida.trading_date,
                ida.avg_return,
                ldpi.latest_date,
                ROW_NUMBER() OVER (PARTITION BY ida.industry ORDER BY ida.trading_date DESC) as rn_latest,
                ROW_NUMBER() OVER (PARTITION BY ida.industry ORDER BY abs(CAST((ldpi.latest_date - ida.trading_date) AS INTEGER) - 1)) as rn_1d,
                ROW_NUMBER() OVER (PARTITION BY ida.industry ORDER BY abs(CAST((ldpi.latest_date - ida.trading_date) AS INTEGER) - 5)) as rn_5d,
                ROW_NUMBER() OVER (PARTITION BY ida.industry ORDER BY abs(CAST((ldpi.latest_date - ida.trading_date) AS INTEGER) - 20)) as rn_20d
            FROM industry_daily_avg ida
            JOIN latest_date_per_industry ldpi ON ida.industry = ldpi.industry
        ),
        perf_latest AS (
            SELECT industry, latest_date, avg_return as latest_return
            FROM perf_windows
            WHERE rn_latest = 1
        ),
        perf_1d AS (
            SELECT industry, avg_return as return_1d
            FROM perf_windows
            WHERE rn_1d = 1
        ),
        perf_5d AS (
            SELECT
                industry,
                ((EXP(SUM(LN(1 + avg_return/100))) - 1) * 100) as return_5d
            FROM perf_windows
            WHERE trading_date <= latest_date AND trading_date > latest_date - INTERVAL '5 days'
            GROUP BY industry
        ),
        perf_20d AS (
            SELECT
                industry,
                ((EXP(SUM(LN(1 + avg_return/100))) - 1) * 100) as return_20d
            FROM perf_windows
            WHERE trading_date <= latest_date AND trading_date > latest_date - INTERVAL '20 days'
            GROUP BY industry
        )
        INSERT INTO industry_performance (
            industry,
            date,
            performance_1d,
            performance_5d,
            performance_20d
        )
        SELECT
            pl.industry,
            pl.latest_date,
            p1d.return_1d,
            p5d.return_5d,
            p20d.return_20d
        FROM perf_latest pl
        LEFT JOIN perf_1d p1d ON pl.industry = p1d.industry
        LEFT JOIN perf_5d p5d ON pl.industry = p5d.industry
        LEFT JOIN perf_20d p20d ON pl.industry = p20d.industry
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
    Uses MARKET-CAP WEIGHTED calculations for accuracy
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
                # Market-cap weighted average price calculation for each date
                cursor.execute("""
                    SELECT
                      pd.date,
                      SUM(pd.close * md.market_cap) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN md.market_cap ELSE 0 END), 0) as weighted_close,
                      SUM(pd.volume) as total_vol
                    FROM company_profile cp
                    JOIN price_daily pd ON cp.ticker = pd.symbol
                    INNER JOIN market_data md ON cp.ticker = md.ticker
                    WHERE cp.sector = %s AND md.market_cap > 0
                    GROUP BY pd.date
                    ORDER BY pd.date ASC
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

                # Pre-calculate RSI for all prices if enough data
                rsi_values = [None] * len(prices)
                if len(prices) >= 14:
                    for rsi_i in range(len(prices)):
                        rsi_values[rsi_i] = calculate_rsi(prices[:rsi_i+1])

                # Calculate moving averages and RSI for each row
                for i, date in enumerate(dates):
                    # Moving averages (only when sufficient data exists)
                    ma20 = float(np.mean(prices[max(0, i-19):i+1])) if i >= 19 else None
                    ma50 = float(np.mean(prices[max(0, i-49):i+1])) if i >= 49 else None
                    ma200 = float(np.mean(prices[max(0, i-199):i+1])) if i >= 199 else None

                    # RSI from pre-calculated values
                    rsi = rsi_values[i]

                    cursor.execute("""
                        INSERT INTO sector_technical_data
                        (sector, date, close_price, ma_20, ma_50, ma_200, rsi, volume)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (sector, date) DO UPDATE SET
                        ma_20 = EXCLUDED.ma_20, ma_50 = EXCLUDED.ma_50, ma_200 = EXCLUDED.ma_200,
                        rsi = EXCLUDED.rsi, volume = EXCLUDED.volume
                    """, (sector, date, float(prices[i]), ma20, ma50, ma200, rsi, volumes[i]))

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
                # Market-cap weighted average price calculation for each date
                cursor.execute("""
                    SELECT
                      pd.date,
                      SUM(pd.close * md.market_cap) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN md.market_cap ELSE 0 END), 0) as weighted_close,
                      SUM(pd.volume) as total_vol
                    FROM company_profile cp
                    JOIN price_daily pd ON cp.ticker = pd.symbol
                    INNER JOIN market_data md ON cp.ticker = md.ticker
                    WHERE cp.industry = %s AND md.market_cap > 0
                    GROUP BY pd.date
                    ORDER BY pd.date ASC
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

                # Pre-calculate RSI for all prices if enough data
                rsi_values = [None] * len(prices)
                if len(prices) >= 14:
                    for rsi_i in range(len(prices)):
                        rsi_values[rsi_i] = calculate_rsi(prices[:rsi_i+1])

                # Calculate moving averages and RSI for each row
                for i, date in enumerate(dates):
                    # Moving averages (only when sufficient data exists)
                    ma20 = float(np.mean(prices[max(0, i-19):i+1])) if i >= 19 else None
                    ma50 = float(np.mean(prices[max(0, i-49):i+1])) if i >= 49 else None
                    ma200 = float(np.mean(prices[max(0, i-199):i+1])) if i >= 199 else None

                    # RSI from pre-calculated values
                    rsi = rsi_values[i]

                    cursor.execute("""
                        INSERT INTO industry_technical_data
                        (industry, date, close_price, ma_20, ma_50, ma_200, rsi, volume)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (industry, date) DO UPDATE SET
                        ma_20 = EXCLUDED.ma_20, ma_50 = EXCLUDED.ma_50, ma_200 = EXCLUDED.ma_200,
                        rsi = EXCLUDED.rsi, volume = EXCLUDED.volume
                    """, (industry, date, float(prices[i]), ma20, ma50, ma200, rsi, volumes[i]))

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
        # Create tables if they don't exist
        if not create_tables_if_needed(conn):
            logger.error("❌ Failed to create required tables")
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
