#!/usr/bin/env python3
"""
Load current sector and industry technical data with moving averages and RSI
Uses aggregated price data from price_daily table
"""

import logging
import os
import sys
from datetime import datetime, timedelta
import numpy as np

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


def calculate_rsi(prices, period=14):
    """Calculate RSI for a price series"""
    if len(prices) < period + 1:
        return None

    deltas = np.diff(prices)
    seed = deltas[:period + 1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # Calculate for the last point
    for d in deltas[period + 1:]:
        if d >= 0:
            up = (up * (period - 1) + d) / period
            down = (down * (period - 1)) / period
        else:
            up = (up * (period - 1)) / period
            down = (down * (period - 1) - d) / period
        rs = up / down if down != 0 else 0
        rsi = 100.0 - (100.0 / (1.0 + rs))

    return min(100, max(0, rsi))


def load_sector_technical_data(conn):
    """Load sector technical data with moving averages"""
    logger.info("📊 Loading sector technical data (last 3 years)...")
    cursor = conn.cursor()

    try:
        # Clear old data from last 3 years
        cursor.execute("""
            DELETE FROM sector_technical_data
            WHERE date >= NOW() - INTERVAL '3 years'
        """)
        logger.info(f"  Cleared old data")

        # Get unique sectors and dates
        cursor.execute("""
            SELECT DISTINCT cp.sector, pd.date
            FROM price_daily pd
            JOIN company_profile cp ON pd.symbol = cp.ticker
            WHERE pd.date >= NOW() - INTERVAL '3 years' AND cp.sector IS NOT NULL
            ORDER BY cp.sector, pd.date
        """)

        sector_dates = {}
        for sector, date in cursor.fetchall():
            if sector not in sector_dates:
                sector_dates[sector] = []
            sector_dates[sector].append(date)

        batch_data = []
        processed = 0

        for sector in sorted(sector_dates.keys()):
            dates = sorted(sector_dates[sector])

            # Get price data for this sector
            cursor.execute("""
                SELECT pd.date, SUM(COALESCE(pd.close, 0))::float as sector_price, SUM(COALESCE(pd.volume, 0))::bigint as sector_volume
                FROM price_daily pd
                JOIN company_profile cp ON pd.symbol = cp.ticker
                WHERE cp.sector = %s AND pd.date >= NOW() - INTERVAL '3 years'
                GROUP BY pd.date
                ORDER BY pd.date
            """, (sector,))

            price_data = {}
            for date, price, volume in cursor.fetchall():
                price_data[date] = (price, volume)

            # Calculate technical indicators for each date
            for i, target_date in enumerate(dates):
                if target_date not in price_data:
                    continue

                close_price, volume = price_data[target_date]

                # Get prices for moving averages (20, 50, 200 days)
                ma_20 = None
                ma_50 = None
                ma_200 = None

                # Collect prices for MAs
                recent_prices = []
                for j in range(max(0, i - 200), i + 1):
                    if j < len(dates) and dates[j] in price_data:
                        recent_prices.append(price_data[dates[j]][0])

                if len(recent_prices) >= 20:
                    ma_20 = sum(recent_prices[-20:]) / 20
                if len(recent_prices) >= 50:
                    ma_50 = sum(recent_prices[-50:]) / 50
                if len(recent_prices) >= 200:
                    ma_200 = sum(recent_prices[-200:]) / 200

                # Calculate RSI
                rsi = None
                if len(recent_prices) >= 15:
                    try:
                        rsi = calculate_rsi(np.array(recent_prices))
                    except:
                        pass

                batch_data.append((
                    sector,
                    target_date,
                    float(close_price),
                    float(ma_20) if ma_20 else None,
                    float(ma_50) if ma_50 else None,
                    float(ma_200) if ma_200 else None,
                    float(rsi) if rsi else None,
                    int(volume) if volume else None
                ))

                # Insert batch when full
                if len(batch_data) >= BATCH_SIZE:
                    cursor.executemany("""
                        INSERT INTO sector_technical_data (sector, date, close_price, ma_20, ma_50, ma_200, rsi, volume)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT(sector, date) DO UPDATE SET
                            close_price = EXCLUDED.close_price,
                            ma_20 = EXCLUDED.ma_20,
                            ma_50 = EXCLUDED.ma_50,
                            ma_200 = EXCLUDED.ma_200,
                            rsi = EXCLUDED.rsi,
                            volume = EXCLUDED.volume
                    """, batch_data)
                    batch_data = []
                    processed += 1
                    if processed % 5 == 0:
                        logger.info(f"  ✅ Processed {processed * BATCH_SIZE} records...")

        # Insert remaining batch
        if batch_data:
            cursor.executemany("""
                INSERT INTO sector_technical_data (sector, date, close_price, ma_20, ma_50, ma_200, rsi, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(sector, date) DO UPDATE SET
                    close_price = EXCLUDED.close_price,
                    ma_20 = EXCLUDED.ma_20,
                    ma_50 = EXCLUDED.ma_50,
                    ma_200 = EXCLUDED.ma_200,
                    rsi = EXCLUDED.rsi,
                    volume = EXCLUDED.volume
            """, batch_data)

        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM sector_technical_data WHERE date >= NOW() - INTERVAL '3 years'")
        count = cursor.fetchone()[0]
        logger.info(f"✅ Successfully loaded {count} sector technical records")

    except Exception as e:
        logger.error(f"Error loading sector technical data: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()


def load_industry_technical_data(conn):
    """Load industry technical data with moving averages"""
    logger.info("📊 Loading industry technical data (last 3 years)...")
    cursor = conn.cursor()

    try:
        # Clear old data from last 3 years
        cursor.execute("""
            DELETE FROM industry_technical_data
            WHERE date >= NOW() - INTERVAL '3 years'
        """)
        logger.info(f"  Cleared old data")

        # Get unique industries and dates
        cursor.execute("""
            SELECT DISTINCT cp.industry, pd.date
            FROM price_daily pd
            JOIN company_profile cp ON pd.symbol = cp.ticker
            WHERE pd.date >= NOW() - INTERVAL '3 years' AND cp.industry IS NOT NULL
            ORDER BY cp.industry, pd.date
        """)

        industry_dates = {}
        for industry, date in cursor.fetchall():
            if industry not in industry_dates:
                industry_dates[industry] = []
            industry_dates[industry].append(date)

        batch_data = []
        processed = 0

        for industry in sorted(industry_dates.keys()):
            dates = sorted(industry_dates[industry])

            # Get price data for this industry
            cursor.execute("""
                SELECT pd.date, SUM(COALESCE(pd.close, 0))::float as industry_price, SUM(COALESCE(pd.volume, 0))::bigint as industry_volume
                FROM price_daily pd
                JOIN company_profile cp ON pd.symbol = cp.ticker
                WHERE cp.industry = %s AND pd.date >= NOW() - INTERVAL '3 years'
                GROUP BY pd.date
                ORDER BY pd.date
            """, (industry,))

            price_data = {}
            for date, price, volume in cursor.fetchall():
                price_data[date] = (price, volume)

            # Calculate technical indicators for each date
            for i, target_date in enumerate(dates):
                if target_date not in price_data:
                    continue

                close_price, volume = price_data[target_date]

                # Get prices for moving averages
                ma_20 = None
                ma_50 = None
                ma_200 = None

                recent_prices = []
                for j in range(max(0, i - 200), i + 1):
                    if j < len(dates) and dates[j] in price_data:
                        recent_prices.append(price_data[dates[j]][0])

                if len(recent_prices) >= 20:
                    ma_20 = sum(recent_prices[-20:]) / 20
                if len(recent_prices) >= 50:
                    ma_50 = sum(recent_prices[-50:]) / 50
                if len(recent_prices) >= 200:
                    ma_200 = sum(recent_prices[-200:]) / 200

                # Calculate RSI
                rsi = None
                if len(recent_prices) >= 15:
                    try:
                        rsi = calculate_rsi(np.array(recent_prices))
                    except:
                        pass

                batch_data.append((
                    industry,
                    target_date,
                    float(close_price),
                    float(ma_20) if ma_20 else None,
                    float(ma_50) if ma_50 else None,
                    float(ma_200) if ma_200 else None,
                    float(rsi) if rsi else None,
                    int(volume) if volume else None
                ))

                # Insert batch when full
                if len(batch_data) >= BATCH_SIZE:
                    cursor.executemany("""
                        INSERT INTO industry_technical_data (industry, date, close_price, ma_20, ma_50, ma_200, rsi, volume)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT(industry, date) DO UPDATE SET
                            close_price = EXCLUDED.close_price,
                            ma_20 = EXCLUDED.ma_20,
                            ma_50 = EXCLUDED.ma_50,
                            ma_200 = EXCLUDED.ma_200,
                            rsi = EXCLUDED.rsi,
                            volume = EXCLUDED.volume
                    """, batch_data)
                    batch_data = []
                    processed += 1
                    if processed % 5 == 0:
                        logger.info(f"  ✅ Processed {processed * BATCH_SIZE} records...")

        # Insert remaining batch
        if batch_data:
            cursor.executemany("""
                INSERT INTO industry_technical_data (industry, date, close_price, ma_20, ma_50, ma_200, rsi, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(industry, date) DO UPDATE SET
                    close_price = EXCLUDED.close_price,
                    ma_20 = EXCLUDED.ma_20,
                    ma_50 = EXCLUDED.ma_50,
                    ma_200 = EXCLUDED.ma_200,
                    rsi = EXCLUDED.rsi,
                    volume = EXCLUDED.volume
            """, batch_data)

        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM industry_technical_data WHERE date >= NOW() - INTERVAL '3 years'")
        count = cursor.fetchone()[0]
        logger.info(f"✅ Successfully loaded {count} industry technical records")

    except Exception as e:
        logger.error(f"Error loading industry technical data: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()


def main():
    conn = get_db_connection()
    try:
        logger.info("=" * 60)
        logger.info("🚀 TECHNICAL DATA LOADER")
        logger.info("=" * 60)

        load_sector_technical_data(conn)
        load_industry_technical_data(conn)

        logger.info("=" * 60)
        logger.info("✨ Technical data load completed successfully!")
        logger.info("=" * 60)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
