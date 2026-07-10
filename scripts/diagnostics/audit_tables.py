#!/usr/bin/env python3
"""List all tables to find schema gaps"""
from utils.db.context import DatabaseContext
import json

with DatabaseContext('read') as cur:
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public'
        ORDER BY table_name
    """)
    tables = cur.fetchall()
    table_list = [t[0] for t in tables]
    print("Tables in database:")
    for t in table_list:
        print(f"  - {t}")

    print(f"\nTotal: {len(table_list)} tables")

    # Look for orchestrator-related tables
    orch_tables = [t for t in table_list if 'orchestr' in t.lower() or 'run' in t.lower()]
    print(f"\nOrchestrator/Run-related tables: {orch_tables if orch_tables else 'NONE'}")
