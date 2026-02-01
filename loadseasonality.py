#!/usr/bin/env python3
"""
Load seasonality analysis data from historical price data.
Calculates monthly and quarterly returns for S&P 500 (SPY).
"""

import os
import sys
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
import pandas as pd
from collections import defaultdict

import boto3
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_config():
    """Get database configuration - works in AWS and locally.
    
    Priority:
    1. AWS Secrets Manager (if DB_SECRET_ARN is set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
    """
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")
    
    # Try AWS Secrets Manager first
    if db_secret_arn and aws_region:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logger.info(f"Using AWS Secrets Manager for database config")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "database": sec["dbname"]
            }
        except Exception as e:
            logger.warning(f"AWS Secrets Manager failed ({e.__class__.__name__}): {str(e)[:100]}. Falling back to environment variables.")
    
    # Fall back to environment variables
    logger.info("Using environment variables for database config")
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", "stocks")
    }

# Database connection
def get_db_connection():
    """Create database connection from environment variables or AWS Secrets Manager"""
    try:
        cfg = get_db_config()
        conn = psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            database=cfg["database"],
            user=cfg["user"],
            password=cfg["password"]
        )
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        sys.exit(1)

def load_spy_prices(conn):
    """Load SPY (S&P 500) price data"""
    print("📊 Loading SPY price data...")

    try:
        cursor = conn.cursor()

        # Get SPY price data, ordered by date
        cursor.execute("""
            SELECT date, close
            FROM price_daily
            WHERE symbol = 'SPY'
            AND close IS NOT NULL
            ORDER BY date ASC
        """)

        data = cursor.fetchall()
        cursor.close()

        if not data:
            print("⚠️  No SPY data found in database")
            return pd.DataFrame()

        # Create DataFrame
        df = pd.DataFrame(data, columns=['date', 'close'])
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)

        print(f"✅ Loaded {len(df)} SPY price records from {df['date'].min().date()} to {df['date'].max().date()}")
        return df

    except Exception as e:
        print(f"❌ Error loading SPY prices: {e}")
        return pd.DataFrame()

def calculate_monthly_returns(spy_df):
    """Calculate monthly returns for SPY"""
    print("📈 Calculating monthly returns...")

    if spy_df.empty:
        return []

    # Group by year-month and get first and last close
    spy_df['year_month'] = spy_df['date'].dt.to_period('M')

    monthly_data = []
    for period, group in spy_df.groupby('year_month'):
        first_close = float(group.iloc[0]['close'])
        last_close = float(group.iloc[-1]['close'])

        if first_close > 0:
            return_pct = ((last_close - first_close) / first_close) * 100
        else:
            return_pct = 0

        monthly_data.append({
            'year': int(period.year),
            'month': int(period.month),
            'month_name': period.strftime('%B'),
            'close': float(last_close),
            'return_pct': float(round(return_pct, 2))
        })

    print(f"✅ Calculated {len(monthly_data)} monthly returns")
    return monthly_data

def calculate_quarterly_returns(spy_df):
    """Calculate quarterly returns for SPY"""
    print("📊 Calculating quarterly returns...")

    if spy_df.empty:
        return []

    # Group by year-quarter
    spy_df['year'] = spy_df['date'].dt.year
    spy_df['quarter'] = spy_df['date'].dt.quarter

    quarterly_data = []
    for (year, quarter), group in spy_df.groupby(['year', 'quarter']):
        first_close = float(group.iloc[0]['close'])
        last_close = float(group.iloc[-1]['close'])

        if first_close > 0:
            return_pct = ((last_close - first_close) / first_close) * 100
        else:
            return_pct = 0

        quarterly_data.append({
            'year': int(year),
            'quarter': int(quarter),
            'close': float(last_close),
            'return_pct': float(round(return_pct, 2))
        })

    print(f"✅ Calculated {len(quarterly_data)} quarterly returns")
    return quarterly_data

def calculate_monthly_statistics(monthly_returns):
    """Calculate average returns by month across all years"""
    print("📅 Calculating monthly statistics...")

    monthly_stats = defaultdict(list)

    for record in monthly_returns:
        monthly_stats[record['month']].append(record['return_pct'])

    results = []
    month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']

    for month in range(1, 13):
        if month in monthly_stats:
            returns = monthly_stats[month]
            avg_return = float(round(sum(returns) / len(returns), 2))
            best_return = float(round(max(returns), 2))
            worst_return = float(round(min(returns), 2))

            results.append({
                'month': int(month),
                'month_name': month_names[month],
                'avg_return': avg_return,
                'best_return': best_return,
                'worst_return': worst_return,
                'years_counted': int(len(returns)),
                'winning_years': int(len([r for r in returns if r > 0])),
                'losing_years': int(len([r for r in returns if r < 0]))
            })

    print(f"✅ Calculated statistics for {len(results)} months")
    return results

def calculate_day_of_week_effects(spy_df):
    """Calculate average returns by day of week"""
    print("📆 Calculating day-of-week effects...")

    if spy_df.empty:
        return []

    spy_df = spy_df.copy()
    spy_df['prev_close'] = spy_df['close'].shift(1)
    spy_df['day_of_week'] = spy_df['date'].dt.day_name()
    spy_df['day_num'] = spy_df['date'].dt.dayofweek  # 0=Monday, 4=Friday

    # Calculate daily returns
    spy_df['daily_return'] = ((spy_df['close'] - spy_df['prev_close']) / spy_df['prev_close']) * 100
    spy_df = spy_df.dropna()

    day_stats = []
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    for day_num, day_name in enumerate(days):
        day_data = spy_df[spy_df['day_num'] == day_num]

        if len(day_data) > 0:
            avg_return = float(round(day_data['daily_return'].mean(), 2))
            win_rate = float(round((day_data['daily_return'] > 0).sum() / len(day_data) * 100, 1))

            day_stats.append({
                'day': day_name,
                'day_num': int(day_num),
                'avg_return': avg_return,
                'win_rate': win_rate,
                'days_counted': int(len(day_data))
            })

    print(f"✅ Calculated statistics for {len(day_stats)} days of week")
    return day_stats

def store_seasonality_data(conn, monthly_returns, quarterly_returns, monthly_stats, dow_stats):
    """Store seasonality data in database"""
    print("💾 Storing seasonality data...")

    try:
        cursor = conn.cursor()

        # Create tables if they don't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seasonality_monthly (
                id SERIAL PRIMARY KEY,
                year INTEGER,
                month INTEGER,
                month_name VARCHAR(20),
                close NUMERIC,
                return_pct NUMERIC(10,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(year, month)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seasonality_quarterly (
                id SERIAL PRIMARY KEY,
                year INTEGER,
                quarter INTEGER,
                close NUMERIC,
                return_pct NUMERIC(10,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(year, quarter)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seasonality_monthly_stats (
                id SERIAL PRIMARY KEY,
                month INTEGER,
                month_name VARCHAR(20),
                avg_return NUMERIC(10,2),
                best_return NUMERIC(10,2),
                worst_return NUMERIC(10,2),
                years_counted INTEGER,
                winning_years INTEGER,
                losing_years INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(month)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seasonality_day_of_week (
                id SERIAL PRIMARY KEY,
                day VARCHAR(20),
                day_num INTEGER,
                avg_return NUMERIC(10,2),
                win_rate NUMERIC(5,1),
                days_counted INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(day_num)
            )
        """)

        # Clear existing data
        cursor.execute("DELETE FROM seasonality_monthly")
        cursor.execute("DELETE FROM seasonality_quarterly")
        cursor.execute("DELETE FROM seasonality_monthly_stats")
        cursor.execute("DELETE FROM seasonality_day_of_week")

        # Insert monthly returns
        if monthly_returns:
            insert_monthly = """
                INSERT INTO seasonality_monthly (year, month, month_name, close, return_pct)
                VALUES %s
            """
            monthly_values = [
                (r['year'], r['month'], r['month_name'], r['close'], r['return_pct'])
                for r in monthly_returns
            ]
            execute_values(cursor, insert_monthly, monthly_values)
            print(f"✅ Inserted {len(monthly_returns)} monthly return records")

        # Insert quarterly returns
        if quarterly_returns:
            insert_quarterly = """
                INSERT INTO seasonality_quarterly (year, quarter, close, return_pct)
                VALUES %s
            """
            quarterly_values = [
                (r['year'], r['quarter'], r['close'], r['return_pct'])
                for r in quarterly_returns
            ]
            execute_values(cursor, insert_quarterly, quarterly_values)
            print(f"✅ Inserted {len(quarterly_returns)} quarterly return records")

        # Insert monthly statistics
        if monthly_stats:
            insert_stats = """
                INSERT INTO seasonality_monthly_stats
                (month, month_name, avg_return, best_return, worst_return, years_counted, winning_years, losing_years)
                VALUES %s
            """
            stats_values = [
                (s['month'], s['month_name'], s['avg_return'], s['best_return'],
                 s['worst_return'], s['years_counted'], s['winning_years'], s['losing_years'])
                for s in monthly_stats
            ]
            execute_values(cursor, insert_stats, stats_values)
            print(f"✅ Inserted {len(monthly_stats)} monthly statistics records")

        # Insert day-of-week statistics
        if dow_stats:
            insert_dow = """
                INSERT INTO seasonality_day_of_week (day, day_num, avg_return, win_rate, days_counted)
                VALUES %s
            """
            dow_values = [
                (s['day'], s['day_num'], s['avg_return'], s['win_rate'], s['days_counted'])
                for s in dow_stats
            ]
            execute_values(cursor, insert_dow, dow_values)
            print(f"✅ Inserted {len(dow_stats)} day-of-week statistics records")

        conn.commit()
        cursor.close()
        print("✅ Seasonality data stored successfully")
        return True

    except Exception as e:
        print(f"❌ Error storing data: {e}")
        conn.rollback()
        return False

def main():
    """Main execution"""
    print("=" * 60)
    print("🔄 Loading Seasonality Data")
    print("=" * 60)

    # Connect to database
    conn = get_db_connection()

    try:
        # Load SPY price data
        spy_df = load_spy_prices(conn)

        if spy_df.empty:
            print("⚠️  No data to process")
            conn.close()
            return

        # Calculate returns
        monthly_returns = calculate_monthly_returns(spy_df)
        quarterly_returns = calculate_quarterly_returns(spy_df)
        monthly_stats = calculate_monthly_statistics(monthly_returns)
        dow_stats = calculate_day_of_week_effects(spy_df)

        # Store in database
        success = store_seasonality_data(conn, monthly_returns, quarterly_returns, monthly_stats, dow_stats)

        if success:
            print("\n" + "=" * 60)
            print("✅ Seasonality data loaded successfully!")
            print("=" * 60)

    except Exception as e:
        print(f"❌ Error: {e}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
