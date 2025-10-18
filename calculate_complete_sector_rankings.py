#!/usr/bin/env python3
"""
Calculate and store complete historical rankings for sectors
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
        # Complete sector historical rankings - tracks rank changes over time
        cursor.execute("""
            DROP TABLE IF EXISTS sector_ranking_complete CASCADE;
            CREATE TABLE sector_ranking_complete (
                id SERIAL PRIMARY KEY,
                sector_name VARCHAR(100) NOT NULL,
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
                current_perf_5d FLOAT,
                perf_5d_1w_ago FLOAT,
                perf_5d_4w_ago FLOAT,
                perf_5d_12w_ago FLOAT,
                current_perf_20d FLOAT,
                perf_20d_1w_ago FLOAT,
                perf_20d_4w_ago FLOAT,
                perf_20d_12w_ago FLOAT,
                current_momentum VARCHAR(20),
                current_trend VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sector_name, snapshot_date)
            )
        """)

        conn.commit()
        print("✅ Complete sector historical ranking table created")
    except Exception as e:
        print(f"⚠️  Table creation note: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def get_rankings_for_date(cursor, target_date):
    """Get sector rankings for a specific date"""
    cursor.execute("""
        SELECT DISTINCT ON (sector_name)
            sector_name,
            sector_rank,
            relative_strength,
            performance_1d,
            performance_5d,
            performance_20d,
            momentum,
            rsi as trend,
            DATE(fetched_at) as data_date
        FROM sector_performance
        WHERE DATE(fetched_at) <= %s
        ORDER BY sector_name, fetched_at DESC
    """, (target_date,))

    rows = cursor.fetchall()
    if not rows:
        return {}

    # Create a dict: sector_name -> {rank, rs, perf_1d, perf_5d, perf_20d, momentum, trend}
    rankings = {}
    for row in rows:
        key = row['sector_name']
        rankings[key] = {
            'rank': row['sector_rank'],
            'rs': row['relative_strength'],
            'perf_1d': row['performance_1d'],
            'perf_5d': row['performance_5d'],
            'perf_20d': row['performance_20d'],
            'momentum': row['momentum'],
            'trend': row['trend']
        }

    return rankings

def calculate_complete_sector_rankings():
    """Calculate rankings for every date in database"""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Get all unique dates in sector_performance table
        cursor.execute("""
            SELECT DISTINCT DATE(fetched_at) as data_date
            FROM sector_performance
            ORDER BY data_date DESC
        """)

        all_dates = [row['data_date'] for row in cursor.fetchall()]
        print(f"\n📊 Found {len(all_dates)} unique dates in database")
        if all_dates:
            print(f"   Date range: {all_dates[-1]} to {all_dates[0]}")

        # For each date, calculate current rank and historical ranks
        for idx, current_date in enumerate(all_dates):
            if idx % 10 == 0:
                print(f"  Processing date {idx+1}/{len(all_dates)}: {current_date}")

            # Get rankings for current date and 1W/4W/8W ago (changed from 12W to 8W)
            date_1w_ago = current_date - timedelta(days=7)
            date_4w_ago = current_date - timedelta(days=28)
            date_12w_ago = current_date - timedelta(days=56)  # 8 weeks = 56 days

            ranks_current = get_rankings_for_date(cursor, current_date)
            ranks_1w = get_rankings_for_date(cursor, date_1w_ago)
            ranks_4w = get_rankings_for_date(cursor, date_4w_ago)
            ranks_12w = get_rankings_for_date(cursor, date_12w_ago)

            # Get all unique sectors for current date
            all_sectors = set(ranks_current.keys())
            all_sectors.update(ranks_1w.keys())
            all_sectors.update(ranks_4w.keys())
            all_sectors.update(ranks_12w.keys())

            # Insert ranking snapshot
            for sector_name in sorted(all_sectors):
                curr = ranks_current.get(sector_name, {})
                one_w = ranks_1w.get(sector_name, {})
                four_w = ranks_4w.get(sector_name, {})
                twelve_w = ranks_12w.get(sector_name, {})

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
                        INSERT INTO sector_ranking_complete
                        (sector_name, snapshot_date, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago,
                         rank_change_1w, rank_change_4w, rank_change_12w,
                         current_rs, rs_1w_ago, rs_4w_ago, rs_12w_ago,
                         current_perf_1d, perf_1d_1w_ago, perf_1d_4w_ago, perf_1d_12w_ago,
                         current_perf_5d, perf_5d_1w_ago, perf_5d_4w_ago, perf_5d_12w_ago,
                         current_perf_20d, perf_20d_1w_ago, perf_20d_4w_ago, perf_20d_12w_ago,
                         current_momentum, current_trend)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (sector_name, snapshot_date) DO UPDATE SET
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
                        perf_1d_12w_ago = EXCLUDED.perf_1d_12w_ago,
                        current_perf_5d = EXCLUDED.current_perf_5d,
                        perf_5d_1w_ago = EXCLUDED.perf_5d_1w_ago,
                        perf_5d_4w_ago = EXCLUDED.perf_5d_4w_ago,
                        perf_5d_12w_ago = EXCLUDED.perf_5d_12w_ago,
                        current_perf_20d = EXCLUDED.current_perf_20d,
                        perf_20d_1w_ago = EXCLUDED.perf_20d_1w_ago,
                        perf_20d_4w_ago = EXCLUDED.perf_20d_4w_ago,
                        perf_20d_12w_ago = EXCLUDED.perf_20d_12w_ago,
                        current_momentum = EXCLUDED.current_momentum,
                        current_trend = EXCLUDED.current_trend
                    """, (
                        sector_name, current_date,
                        curr_rank, rank_1w, rank_4w, rank_12w,
                        change_1w, change_4w, change_12w,
                        curr.get('rs'), one_w.get('rs'), four_w.get('rs'), twelve_w.get('rs'),
                        curr.get('perf_1d'), one_w.get('perf_1d'), four_w.get('perf_1d'), twelve_w.get('perf_1d'),
                        curr.get('perf_5d'), one_w.get('perf_5d'), four_w.get('perf_5d'), twelve_w.get('perf_5d'),
                        curr.get('perf_20d'), one_w.get('perf_20d'), four_w.get('perf_20d'), twelve_w.get('perf_20d'),
                        curr.get('momentum'), curr.get('trend')
                    ))
                except Exception as e:
                    pass  # Silently skip conflicts

            conn.commit()

        # Get summary stats
        cursor.execute("SELECT COUNT(*) as total FROM sector_ranking_complete")
        total_records = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(DISTINCT snapshot_date) as dates FROM sector_ranking_complete")
        unique_dates = cursor.fetchone()['dates']

        cursor.execute("SELECT COUNT(DISTINCT sector_name) as sectors FROM sector_ranking_complete")
        unique_sectors = cursor.fetchone()['sectors']

        print(f"\n✅ Complete! Summary:")
        print(f"   Total ranking snapshots: {total_records:,}")
        print(f"   Unique dates tracked: {unique_dates}")
        print(f"   Unique sectors: {unique_sectors}")
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
    print("🚀 Calculating complete sector historical rankings...")
    create_historical_tables()
    calculate_complete_sector_rankings()
    print("✨ Done!")
