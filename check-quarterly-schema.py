import os
from dotenv import load_dotenv
from pathlib import Path
import psycopg2

load_dotenv(Path('.') / '.env.local')

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cursor = conn.cursor()

cursor.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name='quarterly_balance_sheet'
    ORDER BY ordinal_position
""")

print("quarterly_balance_sheet columns:")
for row in cursor.fetchall():
    print(f"  - {row[0]}")

conn.close()
