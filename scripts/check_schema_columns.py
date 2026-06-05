#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.database_context import DatabaseContext

print("\nChecking data_loader_status table schema...\n")

try:
    with DatabaseContext('read') as cur:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name='data_loader_status'
            ORDER BY ordinal_position
        """)

        print("data_loader_status columns:")
        for row in cur.fetchall():
            print(f"  {row[0]:30s} {row[1]}")

        print("\n\nSample data_loader_status rows:")
        cur.execute("SELECT * FROM data_loader_status LIMIT 5")

        # Get column names from description
        col_names = [desc[0] for desc in cur.description]
        print(f"Columns: {col_names}\n")

        for row in cur.fetchall():
            print(f"  {dict(zip(col_names, row))}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
