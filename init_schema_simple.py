#!/usr/bin/env python3
"""
Simple schema initializer - uses psycopg2 properly to handle complex SQL
"""
import psycopg2
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('.env.local')

db_config = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "stocks"),
}

print("Connecting to database...")
conn = psycopg2.connect(**db_config)
conn.autocommit = True  # Important for DO blocks
cur = conn.cursor()

print("Reading schema file...")
with open('init_db.sql', 'r', encoding='utf-8') as f:
    schema = f.read()

# Split on statement boundaries but preserve DO blocks
statements = []
current = ""
in_do_block = False

for line in schema.split('\n'):
    if 'DO $$' in line:
        in_do_block = True

    current += line + "\n"

    if in_do_block:
        if line.strip() == "END $$;":
            statements.append(current)
            current = ""
            in_do_block = False
    elif line.strip().endswith(";") and line.strip() and not line.strip().startswith("--"):
        statements.append(current)
        current = ""

if current.strip():
    statements.append(current)

# Execute statements
executed = 0
skipped = 0
errors = 0

for stmt in statements:
    stmt = stmt.strip()
    if not stmt or stmt.startswith("--"):
        continue

    try:
        cur.execute(stmt)
        executed += 1
        if executed % 10 == 0:
            print(f"  {executed} statements executed...")
    except psycopg2.errors.DuplicateTable as e:
        skipped += 1  # Table already exists
    except Exception as e:
        errors += 1
        print(f"ERROR: {str(e)[:100]}")

conn.close()

print(f"\nSchema initialization complete:")
print(f"  Executed: {executed}")
print(f"  Skipped (already exist): {skipped}")
print(f"  Errors: {errors}")

if errors == 0:
    print("\nSUCCESS: Schema initialized")
else:
    print("\nWARNING: Some errors occurred, but tables may still be created")

