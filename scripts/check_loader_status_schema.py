#!/usr/bin/env python3
from utils.db.context import DatabaseContext

print("data_loader_status columns:")
with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name='data_loader_status'
        ORDER BY ordinal_position
    """)
    for col_name, col_type in cur.fetchall():
        print(f"  {col_name:30} {col_type}")

print("\nLatest price_daily status:")
with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT * FROM data_loader_status
        WHERE table_name = 'price_daily'
        LIMIT 1
    """)
    row = cur.fetchone()
    if row:
        cols = [desc[0] for desc in cur.description]
        for col, val in zip(cols, row, strict=False):
            print(f"  {col:30} {val}")
