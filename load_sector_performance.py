#!/usr/bin/env python3
"""
Sector & Industry Performance Loader
Populates sector_performance and industry_performance tables with:
- 1D%, 5D%, 20D% percentage changes
- 20-day, 50-day, 200-day moving averages
- Technical indicators (RSI, MACD)
"""

import logging
import os
import sys
from datetime import datetime, timedelta

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


def calculate_moving_average(prices, period):
    """Calculate simple moving average"""
    if len(prices) < period:
        return None
    return float(np.mean(prices[-period:]))


def calculate_macd(prices, fast=12, slow=26, signal=9):
    """Calculate MACD (Moving Average Convergence Divergence)"""
    if len(prices) < slow:
        return None, None, None

    ema_fast = None
    ema_slow = None

    # Calculate EMAs
    prices_arr = np.array(prices)
    if len(prices_arr) >= fast:
        ema_fast = prices_arr[-fast:].mean()
    if len(prices_arr) >= slow:
        ema_slow = prices_arr[-slow:].mean()

    if ema_fast is None or ema_slow is None:
        return None, None, None

    macd_line = float(ema_fast - ema_slow)
    signal_line = None  # Would need more complex calculation with full history
    histogram = None

    return macd_line, signal_line, histogram


def populate_sector_performance(conn):
    """
    Populate sector_performance table with real percentage calculations
    Calculates 1D%, 5D%, 20D% from company MARKET-CAP WEIGHTED average prices by sector
    """
    logger.info("📊 Populating sector_performance table with MARKET-CAP WEIGHTED percentage data...")
    cursor = conn.cursor()

    try:
        # Delete old data
        cursor.execute("DELETE FROM sector_performance")

        # Calculate sector performance based on MARKET-CAP WEIGHTED company average prices
        query = """
        WITH sector_daily_prices AS (
            SELECT
                cp.sector,
                pd.date,
                SUM(pd.close * md.market_cap) / NULLIF(SUM(md.market_cap), 0) as avg_close
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
            -- 1D performance (today vs yesterday)
            CASE
                WHEN d1.avg_close > 0 THEN
                    ((ld.latest_close - d1.avg_close) / d1.avg_close * 100)
                ELSE NULL
            END as perf_1d,
            -- 5D performance (today vs 5 days ago)
            CASE
                WHEN d5.avg_close > 0 THEN
                    ((ld.latest_close - d5.avg_close) / d5.avg_close * 100)
                ELSE NULL
            END as perf_5d,
            -- 20D performance (today vs 20 days ago)
            CASE
                WHEN d20.avg_close > 0 THEN
                    ((ld.latest_close - d20.avg_close) / d20.avg_close * 100)
                ELSE NULL
            END as perf_20d,
            NOW()
        FROM latest_data ld
        LEFT JOIN (
            SELECT sector, avg_close
            FROM sector_daily_prices
            WHERE date = CURRENT_DATE - INTERVAL '1 day'
        ) d1 ON ld.sector = d1.sector
        LEFT JOIN (
            SELECT sector, avg_close
            FROM sector_daily_prices
            WHERE date = CURRENT_DATE - INTERVAL '5 days'
        ) d5 ON ld.sector = d5.sector
        LEFT JOIN (
            SELECT sector, avg_close
            FROM sector_daily_prices
            WHERE date = CURRENT_DATE - INTERVAL '20 days'
        ) d20 ON ld.sector = d20.sector
        """

        cursor.execute(query)
        conn.commit()
        logger.info(f"✅ Populated sector_performance table")

    except Exception as e:
        logger.error(f"❌ Error populating sector_performance: {e}")
        conn.rollback()
        return False

    return True


def populate_industry_performance(conn):
    """
    Populate industry_performance table with real percentage calculations
    Calculates 1D%, 5D%, 20D% from company MARKET-CAP WEIGHTED average prices by industry
    """
    logger.info("📊 Populating industry_performance table with MARKET-CAP WEIGHTED percentage data...")
    cursor = conn.cursor()

    try:
        # Delete old data
        cursor.execute("DELETE FROM industry_performance")

        # Calculate industry performance based on MARKET-CAP WEIGHTED company average prices
        query = """
        WITH industry_daily_prices AS (
            SELECT
                cp.sector,
                cp.industry,
                pd.date,
                SUM(pd.close * md.market_cap) / NULLIF(SUM(md.market_cap), 0) as avg_close
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
            -- 1D performance (today vs yesterday)
            CASE
                WHEN d1.avg_close > 0 THEN
                    ((ld.latest_close - d1.avg_close) / d1.avg_close * 100)
                ELSE NULL
            END as perf_1d,
            -- 5D performance (today vs 5 days ago)
            CASE
                WHEN d5.avg_close > 0 THEN
                    ((ld.latest_close - d5.avg_close) / d5.avg_close * 100)
                ELSE NULL
            END as perf_5d,
            -- 20D performance (today vs 20 days ago)
            CASE
                WHEN d20.avg_close > 0 THEN
                    ((ld.latest_close - d20.avg_close) / d20.avg_close * 100)
                ELSE NULL
            END as perf_20d
        FROM latest_data ld
        LEFT JOIN (
            SELECT sector, industry, avg_close
            FROM industry_daily_prices
            WHERE date = CURRENT_DATE - INTERVAL '1 day'
        ) d1 ON ld.sector = d1.sector AND ld.industry = d1.industry
        LEFT JOIN (
            SELECT sector, industry, avg_close
            FROM industry_daily_prices
            WHERE date = CURRENT_DATE - INTERVAL '5 days'
        ) d5 ON ld.sector = d5.sector AND ld.industry = d5.industry
        LEFT JOIN (
            SELECT sector, industry, avg_close
            FROM industry_daily_prices
            WHERE date = CURRENT_DATE - INTERVAL '20 days'
        ) d20 ON ld.sector = d20.sector AND ld.industry = d20.industry
        """

        cursor.execute(query)
        conn.commit()
        logger.info(f"✅ Populated industry_performance table")

    except Exception as e:
        logger.error(f"❌ Error populating industry_performance: {e}")
        conn.rollback()
        return False

    return True


def verify_tables_exist(conn):
    """Verify that required tables exist"""
    cursor = conn.cursor()

    try:
        # Check sector_performance table
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'sector_performance'
            )
        """)
        if not cursor.fetchone()[0]:
            logger.error("❌ sector_performance table does not exist")
            return False

        # Check industry_performance table
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'industry_performance'
            )
        """)
        if not cursor.fetchone()[0]:
            logger.error("❌ industry_performance table does not exist")
            return False

        logger.info("✅ Both performance tables exist")
        return True

    except Exception as e:
        logger.error(f"❌ Error checking tables: {e}")
        return False


def populate_technical_data(conn):
    """
    Populate sector_technical_data and industry_technical_data tables
    with 200-day price history, moving averages, and RSI indicators
    """
    logger.info("📊 Populating technical data tables...")
    cursor = conn.cursor()

    try:
        # Process sectors
        cursor.execute("SELECT DISTINCT sector FROM company_profile WHERE sector IS NOT NULL ORDER BY sector")
        sectors = [row[0] for row in cursor.fetchall()]
        logger.info(f"Processing {len(sectors)} sectors...")

        for sector in sectors:
            try:
                cursor.execute("""
                    SELECT pd.date, SUM(pd.close * COALESCE(md.market_cap, 0)) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN COALESCE(md.market_cap, 0) ELSE 0 END), 0) as avg_close, SUM(pd.volume) as total_vol
                    FROM company_profile cp
                    JOIN price_daily pd ON cp.ticker = pd.symbol
                    LEFT JOIN market_data md ON cp.ticker = md.ticker
                    WHERE cp.sector = %s
                    GROUP BY pd.date
                    ORDER BY pd.date ASC LIMIT 200
                """, (sector,))

                data = cursor.fetchall()
                if not data:
                    continue

                dates = [row[0] for row in data]
                prices = np.array([float(row[1]) for row in data])
                volumes = [int(row[2]) for row in data]

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

        logger.info(f"✅ Processed {len(sectors)} sectors")

        # Process industries
        cursor.execute("SELECT DISTINCT industry FROM company_profile WHERE industry IS NOT NULL ORDER BY industry")
        industries = [row[0] for row in cursor.fetchall()]
        logger.info(f"Processing {len(industries)} industries...")

        for industry in industries:
            try:
                cursor.execute("""
                    SELECT pd.date, SUM(pd.close * COALESCE(md.market_cap, 0)) / NULLIF(SUM(CASE WHEN pd.close IS NOT NULL THEN COALESCE(md.market_cap, 0) ELSE 0 END), 0) as avg_close, SUM(pd.volume) as total_vol
                    FROM company_profile cp
                    JOIN price_daily pd ON cp.ticker = pd.symbol
                    LEFT JOIN market_data md ON cp.ticker = md.ticker
                    WHERE cp.industry = %s
                    GROUP BY pd.date
                    ORDER BY pd.date ASC LIMIT 200
                """, (industry,))

                data = cursor.fetchall()
                if not data:
                    continue

                dates = [row[0] for row in data]
                prices = np.array([float(row[1]) for row in data])
                volumes = [int(row[2]) for row in data]

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

        logger.info(f"✅ Processed {len(industries)} industries")
        logger.info("✅ Technical data population completed!")
        return True

    except Exception as e:
        logger.error(f"❌ Error populating technical data: {e}")
        conn.rollback()
        return False


def main():
    """Main execution"""
    logger.info("🚀 Starting Sector & Industry Performance Loader")
    logger.info(f"Database: {DB_HOST}:{DB_PORT}/{DB_NAME}")

    conn = get_db_connection()

    try:
        # Verify tables exist
        if not verify_tables_exist(conn):
            logger.error("❌ Required tables missing. Create performance tables first.")
            return False

        # Populate sector performance
        if not populate_sector_performance(conn):
            return False

        # Populate industry performance
        if not populate_industry_performance(conn):
            return False

        # Populate technical data (moving averages, RSI, etc.)
        if not populate_technical_data(conn):
            logger.warning("⚠️  Technical data population had errors, but continuing...")

        logger.info("✅ Performance data load completed successfully!")
        return True

    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
