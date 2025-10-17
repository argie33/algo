#!/usr/bin/env python3
"""
Calculate and store complete historical rankings for sectors and industries
For EVERY date in the database, calculate ranks for that date and 1W/4W/12W ago
Enables comprehensive historical analysis
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
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME
    )

def create_historical_tables():
    """Create tables for storing complete historical rankings"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Complete industry historical rankings - tracks rank changes over time
        cursor.execute("""
            DROP TABLE IF EXISTS industry_ranking_complete CASCADE;
            CREATE TABLE industry_ranking_complete (
                id SERIAL PRIMARY KEY,
                sector VARCHAR(100) NOT NULL,
                industry VARCHAR(100) NOT NULL,
                snapshot_date DATE NOT NULL,
                current_rank INT,
                rank_1w_ago INT,
                rank_4w_ago INT,
                rank_12w_ago INT,
                rank_change_1w INT,
                rank_change_4w INT,
                rank_change_12w INT,
                current_rs FLOAT,
                rs_1w_ago FLOAT,
                rs_4w_ago FLOAT,
                rs_12w_ago FLOAT,
                current_perf_1d FLOAT,
                perf_1d_1w_ago FLOAT,
                perf_1d_4w_ago FLOAT,
                perf_1d_12w_ago FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sector, industry, snapshot_date)
            )
        """)
        
        conn.commit()
        print("✅ Complete historical ranking table created")
    except Exception as e:
        print(f"⚠️  Table creation note: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def get_rankings_for_date(cursor, target_date):
    """Get industry rankings for a specific date"""
    cursor.execute("""
        SELECT DISTINCT ON (sector, industry)
            sector,
            industry,
            overall_rank,
            rs_rating,
            performance_1d,
            DATE(fetched_at) as data_date
        FROM industry_performance
        WHERE DATE(fetched_at) <= %s
        ORDER BY sector, industry, fetched_at DESC
    """, (target_date,))
    
    rows = cursor.fetchall()
    if not rows:
        return {}
    
    # Create a dict: (sector, industry) -> {rank, rs_rating, perf_1d}
    rankings = {}
    for row in rows:
        key = (row['sector'], row['industry'])
        rankings[key] = {
            'rank': row['overall_rank'],
            'rs': row['rs_rating'],
            'perf_1d': row['performance_1d']
        }
    
    return rankings

def calculate_complete_historical_rankings():
    """Calculate rankings for every date in database"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get all unique dates in industry_performance table
        cursor.execute("""
            SELECT DISTINCT DATE(fetched_at) as data_date
            FROM industry_performance
            ORDER BY data_date DESC
        """)
        
        all_dates = [row['data_date'] for row in cursor.fetchall()]
        print(f"\n📊 Found {len(all_dates)} unique dates in database")
        print(f"   Date range: {all_dates[-1]} to {all_dates[0]}")
        
        # For each date, calculate current rank and historical ranks
        for idx, current_date in enumerate(all_dates):
            if idx % 10 == 0:
                print(f"  Processing date {idx+1}/{len(all_dates)}: {current_date}")
            
            # Get rankings for current date and 1W/4W/12W ago
            date_1w_ago = current_date - timedelta(days=7)
            date_4w_ago = current_date - timedelta(days=28)
            date_12w_ago = current_date - timedelta(days=84)
            
            ranks_current = get_rankings_for_date(cursor, current_date)
            ranks_1w = get_rankings_for_date(cursor, date_1w_ago)
            ranks_4w = get_rankings_for_date(cursor, date_4w_ago)
            ranks_12w = get_rankings_for_date(cursor, date_12w_ago)
            
            # Get all unique industries for current date
            all_industries = set(ranks_current.keys())
            all_industries.update(ranks_1w.keys())
            all_industries.update(ranks_4w.keys())
            all_industries.update(ranks_12w.keys())
            
            # Insert ranking snapshot
            for sector, industry in sorted(all_industries):
                curr = ranks_current.get((sector, industry), {})
                one_w = ranks_1w.get((sector, industry), {})
                four_w = ranks_4w.get((sector, industry), {})
                twelve_w = ranks_12w.get((sector, industry), {})
                
                curr_rank = curr.get('rank')
                rank_1w = one_w.get('rank')
                rank_4w = four_w.get('rank')
                rank_12w = twelve_w.get('rank')
                
                # Calculate rank changes (positive = improved/lower number)
                change_1w = rank_1w - curr_rank if rank_1w and curr_rank else None
                change_4w = rank_4w - curr_rank if rank_4w and curr_rank else None
                change_12w = rank_12w - curr_rank if rank_12w and curr_rank else None
                
                try:
                    cursor.execute("""
                        INSERT INTO industry_ranking_complete
                        (sector, industry, snapshot_date, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago,
                         rank_change_1w, rank_change_4w, rank_change_12w,
                         current_rs, rs_1w_ago, rs_4w_ago, rs_12w_ago,
                         current_perf_1d, perf_1d_1w_ago, perf_1d_4w_ago, perf_1d_12w_ago)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (sector, industry, snapshot_date) DO UPDATE SET
                        current_rank = EXCLUDED.current_rank,
                        rank_1w_ago = EXCLUDED.rank_1w_ago,
                        rank_4w_ago = EXCLUDED.rank_4w_ago,
                        rank_12w_ago = EXCLUDED.rank_12w_ago,
                        rank_change_1w = EXCLUDED.rank_change_1w,
                        rank_change_4w = EXCLUDED.rank_change_4w,
                        rank_change_12w = EXCLUDED.rank_change_12w,
                        current_rs = EXCLUDED.current_rs,
                        rs_1w_ago = EXCLUDED.rs_1w_ago,
                        rs_4w_ago = EXCLUDED.rs_4w_ago,
                        rs_12w_ago = EXCLUDED.rs_12w_ago,
                        current_perf_1d = EXCLUDED.current_perf_1d,
                        perf_1d_1w_ago = EXCLUDED.perf_1d_1w_ago,
                        perf_1d_4w_ago = EXCLUDED.perf_1d_4w_ago,
                        perf_1d_12w_ago = EXCLUDED.perf_1d_12w_ago
                    """, (
                        sector, industry, current_date,
                        curr_rank, rank_1w, rank_4w, rank_12w,
                        change_1w, change_4w, change_12w,
                        curr.get('rs'), one_w.get('rs'), four_w.get('rs'), twelve_w.get('rs'),
                        curr.get('perf_1d'), one_w.get('perf_1d'), four_w.get('perf_1d'), twelve_w.get('perf_1d')
                    ))
                except Exception as e:
                    pass  # Silently skip conflicts
            
            conn.commit()
        
        # Get summary stats
        cursor.execute("SELECT COUNT(*) as total FROM industry_ranking_complete")
        total_records = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(DISTINCT snapshot_date) as dates FROM industry_ranking_complete")
        unique_dates = cursor.fetchone()['dates']
        
        cursor.execute("SELECT COUNT(DISTINCT (sector, industry)) as industries FROM industry_ranking_complete")
        unique_industries = cursor.fetchone()['industries']
        
        print(f"\n✅ Complete! Summary:")
        print(f"   Total ranking snapshots: {total_records:,}")
        print(f"   Unique dates tracked: {unique_dates}")
        print(f"   Unique industries: {unique_industries}")
        print(f"   Ready for historical analysis!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    print("🚀 Calculating complete historical rankings...")
    create_historical_tables()
    calculate_complete_historical_rankings()
    print("✨ Done!")
