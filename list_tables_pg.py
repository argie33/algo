#!/usr/bin/env python3
"""List all tables in PostgreSQL database."""
import sys
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.db import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

# Get all tables from information_schema
cur.execute("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name
""")

tables = cur.fetchall()
print("\n=== POSTGRESQL TABLES ===")
for table in tables:
    print(f"  {table[0]}")

cur.close()
conn.close()
