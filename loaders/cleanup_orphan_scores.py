#!/usr/bin/env python3
"""
Remove orphan stock scores (symbols with no price data in price_daily).

These are scores for symbols that don't have actual trading data,
so they shouldn't be shown in the UI or considered by the algo.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
env_file = Path(__file__).parent.parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

import psycopg2
from config.credential_helper import get_db_password

def get_db_conn():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=get_db_password(),
        database=os.getenv('DB_NAME', 'stocks'),
    )

def main():
    conn = get_db_conn()
    try:
        cur = conn.cursor()

        # Count orphans
        cur.execute("""
            SELECT COUNT(DISTINCT ss.symbol)
            FROM stock_scores ss
            LEFT JOIN price_daily pd ON ss.symbol = pd.symbol
            WHERE pd.symbol IS NULL
        """)
        orphan_count = cur.fetchone()[0]
        print(f"Found {orphan_count:,} orphan stock scores (symbols with no price data)")

        if orphan_count > 0:
            # Get list of orphans
            cur.execute("""
                SELECT DISTINCT ss.symbol
                FROM stock_scores ss
                LEFT JOIN price_daily pd ON ss.symbol = pd.symbol
                WHERE pd.symbol IS NULL
                ORDER BY ss.symbol
            """)
            orphans = [row[0] for row in cur.fetchall()]

            print(f"Sample orphans: {', '.join(orphans[:10])}")

            # Delete orphans
            cur.execute("""
                DELETE FROM stock_scores
                WHERE symbol IN (
                    SELECT DISTINCT ss.symbol
                    FROM stock_scores ss
                    LEFT JOIN price_daily pd ON ss.symbol = pd.symbol
                    WHERE pd.symbol IS NULL
                )
            """)
            conn.commit()
            print(f"Deleted {cur.rowcount} orphan score records")

        # Verify
        cur.execute("SELECT COUNT(DISTINCT symbol) FROM stock_scores")
        total_scores = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT symbol) FROM price_daily")
        total_prices = cur.fetchone()[0]

        print(f"\nAfter cleanup:")
        print(f"  Stock scores: {total_scores:,}")
        print(f"  Symbols with prices: {total_prices:,}")
        print(f"  Match: {total_scores == total_prices}")

        return 0
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
        return 1
    finally:
        conn.close()

if __name__ == '__main__':
    sys.exit(main())
