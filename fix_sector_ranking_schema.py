#!/usr/bin/env python3
"""
Fix sector_ranking and industry_ranking table schemas
Changes momentum_score from NUMERIC(8,2) to NUMERIC(15,4) to prevent overflow
"""

import psycopg2
import sys

DB_HOST = 'localhost'
DB_PORT = '5432'
DB_USER = 'postgres'
DB_PASSWORD = 'password'
DB_NAME = 'stocks'

def fix_schema():
    """Fix the numeric overflow issue in sector and industry ranking tables"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        cursor = conn.cursor()

        print("🔧 Fixing sector_ranking table schema...")
        # Alter sector_ranking momentum_score column
        cursor.execute("""
            ALTER TABLE sector_ranking
            ALTER COLUMN momentum_score
            TYPE NUMERIC(15,4);
        """)
        print("✅ Fixed sector_ranking.momentum_score")

        print("🔧 Fixing industry_ranking table schema...")
        # Alter industry_ranking momentum_score column
        cursor.execute("""
            ALTER TABLE industry_ranking
            ALTER COLUMN momentum_score
            TYPE NUMERIC(15,4);
        """)
        print("✅ Fixed industry_ranking.momentum_score")

        conn.commit()
        cursor.close()
        conn.close()

        print("\n✨ Schema fixes applied successfully!")
        return True

    except psycopg2.errors.UndefinedTable:
        print("❌ ERROR: Table does not exist. Run loaders to create tables first.")
        return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    success = fix_schema()
    sys.exit(0 if success else 1)
