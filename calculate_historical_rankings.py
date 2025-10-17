#!/usr/bin/env python3
"""
Calculate and store historical rankings for sectors and industries
Shows how rankings changed over time (today, 1w ago, 3w ago, 6w ago, 12w ago)
"""

import os
import sys
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_NAME = os.getenv('DB_NAME', 'stocks')

def get_db_connection():
    """Connect to PostgreSQL database"""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

def create_historical_tables():
    """Create tables for storing historical rankings"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Sector historical rankings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sector_ranking_history (
                id SERIAL PRIMARY KEY,
                sector_name VARCHAR(100) NOT NULL,
                symbol VARCHAR(10),
                ranking_date DATE NOT NULL,
                days_ago INT NOT NULL,
                period_label VARCHAR(20),
                sector_rank INT,
                relative_strength FLOAT,
                momentum VARCHAR(20),
                rsi FLOAT,
                performance_1d FLOAT,
                performance_5d FLOAT,
                performance_20d FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sector_name, ranking_date)
            )
        """)
        
        # Industry historical rankings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS industry_ranking_history (
                id SERIAL PRIMARY KEY,
                sector VARCHAR(100) NOT NULL,
                industry VARCHAR(100) NOT NULL,
                ranking_date DATE NOT NULL,
                days_ago INT NOT NULL,
                period_label VARCHAR(20),
                overall_rank INT,
                sector_rank INT,
                rs_rating FLOAT,
                momentum VARCHAR(20),
                trend VARCHAR(20),
                performance_1d FLOAT,
                performance_5d FLOAT,
                performance_20d FLOAT,
                stock_count INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sector, industry, ranking_date)
            )
        """)
        
        conn.commit()
        print("✅ Historical ranking tables created")
    except Exception as e:
        print(f"⚠️  Tables may already exist: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def calculate_historical_rankings():
    """Calculate rankings for different time periods"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Define time periods to analyze
    periods = [
        (0, "Today", "TODAY"),
        (7, "1 Week Ago", "1W_AGO"),
        (21, "3 Weeks Ago", "3W_AGO"),
        (42, "6 Weeks Ago", "6W_AGO"),
        (84, "12 Weeks Ago", "12W_AGO"),
    ]
    
    try:
        # Calculate sector rankings for each period
        print("\n📊 Calculating sector historical rankings...")
        for days_ago, label, period_key in periods:
            target_date = (datetime.now() - timedelta(days=days_ago)).date()
            print(f"  📅 {label} ({target_date})...")
            
            # Get the closest available data for this date
            cursor.execute("""
                SELECT 
                    sector_name,
                    symbol,
                    sector_rank,
                    relative_strength,
                    momentum,
                    rsi,
                    performance_1d,
                    performance_5d,
                    performance_20d,
                    DATE(fetched_at) as data_date
                FROM sector_performance
                WHERE DATE(fetched_at) <= %s
                ORDER BY fetched_at DESC
                LIMIT 1000
            """, (target_date,))
            
            sectors = cursor.fetchall()
            
            if not sectors:
                print(f"    ⚠️  No data available for {label}")
                continue
            
            # Group by sector_name and get most recent
            sector_dict = {}
            for s in sectors:
                if s['sector_name'] not in sector_dict:
                    sector_dict[s['sector_name']] = s
            
            # Rank sectors by performance_1d or similar for this period
            ranked_sectors = sorted(sector_dict.values(), 
                                  key=lambda x: (x['performance_1d'] or -999), 
                                  reverse=True)
            
            for rank, sector in enumerate(ranked_sectors, 1):
                try:
                    cursor.execute("""
                        INSERT INTO sector_ranking_history 
                        (sector_name, symbol, ranking_date, days_ago, period_label, sector_rank, relative_strength, momentum, rsi, performance_1d, performance_5d, performance_20d)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (sector_name, ranking_date) DO UPDATE SET
                        sector_rank = EXCLUDED.sector_rank,
                        relative_strength = EXCLUDED.relative_strength,
                        momentum = EXCLUDED.momentum,
                        rsi = EXCLUDED.rsi,
                        performance_1d = EXCLUDED.performance_1d,
                        performance_5d = EXCLUDED.performance_5d,
                        performance_20d = EXCLUDED.performance_20d
                    """, (
                        sector['sector_name'],
                        sector['symbol'],
                        target_date,
                        days_ago,
                        label,
                        rank,
                        sector['relative_strength'],
                        sector['momentum'],
                        sector['rsi'],
                        sector['performance_1d'],
                        sector['performance_5d'],
                        sector['performance_20d']
                    ))
                except Exception as e:
                    print(f"    ❌ Error inserting sector: {e}")
            
            conn.commit()
            print(f"    ✅ Processed {len(ranked_sectors)} sectors")
        
        # Calculate industry rankings for each period
        print("\n📊 Calculating industry historical rankings...")
        for days_ago, label, period_key in periods:
            target_date = (datetime.now() - timedelta(days=days_ago)).date()
            print(f"  📅 {label} ({target_date})...")
            
            cursor.execute("""
                SELECT 
                    sector,
                    industry,
                    overall_rank,
                    sector_rank,
                    rs_rating,
                    momentum,
                    trend,
                    performance_1d,
                    performance_5d,
                    performance_20d,
                    stock_count,
                    DATE(fetched_at) as data_date
                FROM industry_performance
                WHERE DATE(fetched_at) <= %s
                ORDER BY fetched_at DESC
                LIMIT 10000
            """, (target_date,))
            
            industries = cursor.fetchall()
            
            if not industries:
                print(f"    ⚠️  No data available for {label}")
                continue
            
            # Group by sector+industry and get most recent
            ind_dict = {}
            for i in industries:
                key = (i['sector'], i['industry'])
                if key not in ind_dict:
                    ind_dict[key] = i
            
            # Rank industries overall
            ranked_industries = sorted(ind_dict.values(), 
                                      key=lambda x: (x['overall_rank'] or 999))
            
            for rank, industry in enumerate(ranked_industries, 1):
                try:
                    cursor.execute("""
                        INSERT INTO industry_ranking_history 
                        (sector, industry, ranking_date, days_ago, period_label, overall_rank, sector_rank, rs_rating, momentum, trend, performance_1d, performance_5d, performance_20d, stock_count)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (sector, industry, ranking_date) DO UPDATE SET
                        overall_rank = EXCLUDED.overall_rank,
                        sector_rank = EXCLUDED.sector_rank,
                        rs_rating = EXCLUDED.rs_rating,
                        momentum = EXCLUDED.momentum,
                        trend = EXCLUDED.trend,
                        performance_1d = EXCLUDED.performance_1d,
                        performance_5d = EXCLUDED.performance_5d,
                        performance_20d = EXCLUDED.performance_20d,
                        stock_count = EXCLUDED.stock_count
                    """, (
                        industry['sector'],
                        industry['industry'],
                        target_date,
                        days_ago,
                        label,
                        rank,
                        industry['sector_rank'],
                        industry['rs_rating'],
                        industry['momentum'],
                        industry['trend'],
                        industry['performance_1d'],
                        industry['performance_5d'],
                        industry['performance_20d'],
                        industry['stock_count']
                    ))
                except Exception as e:
                    print(f"    ❌ Error: {e}")
            
            conn.commit()
            print(f"    ✅ Processed {len(ranked_industries)} industries")
        
        print("\n✅ Historical rankings calculation complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print("🚀 Starting historical rankings calculation...")
    create_historical_tables()
    calculate_historical_rankings()
    print("✨ Done!")
