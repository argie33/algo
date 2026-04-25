#!/usr/bin/env python3
"""
Database State Verification Tool
Checks all critical tables to see what data is available
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# Fix encoding for Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load environment
env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

# Database configuration
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_USER = os.environ.get("DB_USER", "stocks")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "stocks")

# Tables to check
TABLES_TO_CHECK = [
    ("stock_symbols", "Stock symbols"),
    ("company_profile", "Company profiles"),
    ("daily_prices", "Daily prices"),
    ("stock_scores", "Stock scores"),
    ("key_metrics", "Key metrics"),
    ("earnings_calendar", "Earnings calendar"),
    ("earnings_history", "Earnings history"),
    ("earnings_estimates", "Earnings estimates"),
    ("technical_indicators", "Technical indicators"),
    ("portfolio_holdings", "Portfolio holdings"),
    ("manual_positions", "Manual positions"),
    ("trades", "Trades"),
    ("buy_sell_daily", "Buy/sell signals"),
    ("institutional_positioning", "Institutional positioning"),
    ("positioning_metrics", "Positioning metrics"),
    ("market_data", "Market data"),
    ("sector_performance", "Sector performance"),
    ("industry_performance", "Industry performance"),
]

def check_table(cursor, table_name):
    """Check if table exists and count rows"""
    try:
        cursor.execute(f"""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s
            )
        """, (table_name,))
        exists = cursor.fetchone()[0]

        if not exists:
            return {"exists": False, "count": 0, "columns": []}

        # Get row count
        cursor.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
        count = cursor.fetchone()[0]

        # Get columns
        cursor.execute(f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        columns = [f"{row[0]} ({row[1]})" for row in cursor.fetchall()]

        # Get sample data (first row if exists)
        sample = None
        if count > 0:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 1")
            result = cursor.fetchone()
            if result:
                sample = dict(result)
                # Remove large fields from display
                for key in list(sample.keys()):
                    if isinstance(sample[key], (str, bytes)) and len(str(sample[key])) > 100:
                        sample[key] = f"<{len(str(sample[key]))} chars>"

        return {
            "exists": True,
            "count": count,
            "columns": len(columns),
            "column_names": columns[:5] if columns else [],
            "sample": sample,
        }
    except Exception as e:
        return {"exists": False, "error": str(e)}

def main():
    print("🔍 Database State Verification")
    print(f"   Host: {DB_HOST}:{DB_PORT}")
    print(f"   Database: {DB_NAME}")
    print(f"   User: {DB_USER}\n")

    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname=DB_NAME,
            connect_timeout=5
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        print("✅ Connected to database\n")
        print("📊 Table Status:\n")

        total_rows = 0
        total_with_data = 0

        for table_name, description in TABLES_TO_CHECK:
            result = check_table(cursor, table_name)

            if result["exists"]:
                status = "✅" if result["count"] > 0 else "⚠️ "
                total_rows += result["count"]
                if result["count"] > 0:
                    total_with_data += 1

                print(f"{status} {description:35} | {table_name:30} | {result['count']:10,} rows")

                if result["count"] > 0 and result.get("column_names"):
                    cols_preview = ", ".join(result["column_names"][:3])
                    print(f"   Columns: {cols_preview}...")

                    if result.get("sample"):
                        print(f"   Sample: {json.dumps(result['sample'], default=str, indent=2)[:200]}...")
            else:
                print(f"❌ {description:35} | {table_name:30} | TABLE NOT FOUND")

        cursor.close()
        conn.close()

        print(f"\n\n📈 Summary:")
        print(f"   Tables with data: {total_with_data}/{len(TABLES_TO_CHECK)}")
        print(f"   Total rows across all tables: {total_rows:,}")

    except psycopg2.OperationalError as e:
        print(f"❌ Failed to connect to database: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
