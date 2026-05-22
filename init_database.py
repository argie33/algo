#!/usr/bin/env python3
"""Initialize database schema from init.sql."""

import os
import psycopg2
from pathlib import Path

def init_database():
    """Load and execute init.sql schema."""
    db_host = os.getenv("DB_HOST", "localhost")
    db_user = os.getenv("DB_USER", "stocks")
    db_password = os.getenv("DB_PASSWORD", "testpass")
    db_name = os.getenv("DB_NAME", "stocks")

    # Read the init.sql file
    init_sql_path = Path(__file__).parent / "terraform" / "modules" / "database" / "init.sql"
    if not init_sql_path.exists():
        print(f"Warning: init.sql not found at {init_sql_path}, skipping")
        return

    with open(init_sql_path) as f:
        sql = f.read()

    # Connect and execute
    try:
        conn = psycopg2.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
            connect_timeout=10
        )
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ Database schema initialized: {db_name}")
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        raise

if __name__ == "__main__":
    init_database()
