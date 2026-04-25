#!/usr/bin/env python3
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
import os

env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', '5432'),
    database=os.getenv('DB_NAME', 'stockdb'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD', 'postgres')
)

cursor = conn.cursor()

# Get all table names
cursor.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name
""")

tables = [row[0] for row in cursor.fetchall()]
print("Tables in database:")
for table in tables:
    print(f"  - {table}")

print("\n\nquality_metrics columns:")
cursor.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'quality_metrics'
    ORDER BY ordinal_position
""")

for col, dtype in cursor.fetchall():
    print(f"  - {col}: {dtype}")

print("\n\ngrowth_metrics columns:")
cursor.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'growth_metrics'
    ORDER BY ordinal_position
""")

for col, dtype in cursor.fetchall():
    print(f"  - {col}: {dtype}")

print("\n\nannual_balance_sheet columns:")
cursor.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'annual_balance_sheet'
    ORDER BY ordinal_position
""")

for col, dtype in cursor.fetchall():
    print(f"  - {col}: {dtype}")

cursor.close()
conn.close()
