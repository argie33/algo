#!/usr/bin/env python3
"""Check actual table schema in database."""

from utils.db import DatabaseContext

def main():
    """List all relevant tables."""
    with DatabaseContext("read") as cur:
        # Get all tables
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = cur.fetchall()

        print("\n" + "="*70)
        print("ALL TABLES IN DATABASE")
        print("="*70 + "\n")

        relevant_keywords = [
            'performance', 'trade', 'circuit', 'histogram',
            'distribution', 'position', 'run', 'order'
        ]

        for row in tables:
            table_name = row[0] if isinstance(row, tuple) else row.get('table_name')
            # Highlight relevant tables
            highlight = any(kw in table_name.lower() for kw in relevant_keywords)
            marker = "[***]" if highlight else "     "
            print(f"{marker} {table_name}")

        print("\n" + "="*70)
        print("CHECKING SPECIFIC TABLES FOR COLUMNS")
        print("="*70 + "\n")

        # Check the columns in algo_performance_daily
        print("\n1. algo_performance_daily columns:")
        try:
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'algo_performance_daily'
                ORDER BY ordinal_position
            """)
            for row in cur.fetchall():
                print(f"   {row[0]:<30} {row[1]}")
        except Exception as e:
            print(f"   ERROR: {e}")

if __name__ == "__main__":
    main()
